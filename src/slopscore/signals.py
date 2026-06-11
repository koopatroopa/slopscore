"""Heuristic signal detectors for AI-authored PR/issue text.

Each detector inspects the assembled document text and returns
``(occurrences, evidence)``. No single signal is reliable on its own - the
prior art is explicit that humans use em-dashes, say "delve", and write section
headers. The tool scores the *convergence* of weak signals against a threshold
(see ``triage.py``); detectors here only count, they do not judge.

Shared matching rules (per the spec / qa-clarifier resolution):
- phrase signals are case-insensitive, matched on word boundaries, literal
  (no stemming), counting non-overlapping occurrences;
- occurrences drive the score (capped per signal); evidence is a deduplicated
  sample of the matches, for the report only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from slopscore.imports import detect_undeclared_imports

_EVIDENCE_LIMIT = 5


@dataclass(frozen=True)
class CodeFile:
    """A unit of code to scan: a path and its (added) content."""

    path: str
    content: str


@dataclass(frozen=True)
class Document:
    """A PR or issue reduced to the prose we score, plus any code files."""

    title: str = ""
    body: str = ""
    commits: tuple[str, ...] = ()
    files: tuple[CodeFile, ...] = ()
    # True for documents with addressable fields (JSON input): prose evidence
    # then carries a field:line location. Raw --text input stays unqualified.
    structured: bool = False

    @property
    def assembled(self) -> str:
        """Title, body and each commit joined by blank lines.

        Non-empty parts only, so a missing field never injects a stray blank
        run that would split a multi-line pattern across a boundary.
        """
        parts = [self.title, self.body, *self.commits]
        return "\n\n".join(part for part in parts if part)

    def locate(self, snippet: str) -> str | None:
        """First field:line containing snippet (case-insensitive), e.g.
        "body:14" or "commit[2]:1"; None when the snippet is not findable
        (synthetic evidence such as counts). Presentation only - never
        affects occurrence counting or the score."""
        needle = snippet.lower()
        fields = [("title", self.title), ("body", self.body)]
        fields += [(f"commit[{i}]", c) for i, c in enumerate(self.commits, 1)]
        for name, text in fields:
            for lineno, line in enumerate(text.splitlines(), 1):
                if needle in line.lower():
                    return f"{name}:{lineno}"
        return None


@dataclass(frozen=True)
class SignalHit:
    """The result of one signal firing on a document."""

    name: str
    description: str
    weight: float
    cap: int
    occurrences: int
    evidence: tuple[str, ...]

    @property
    def counted(self) -> int:
        return min(self.occurrences, self.cap)

    @property
    def contribution(self) -> float:
        return round(self.weight * self.counted, 2)


# Detector signature: text -> (occurrences, evidence_sample).
Detector = Callable[[str], "tuple[int, list[str]]"]


@dataclass(frozen=True)
class Signal:
    name: str
    description: str
    weight: float
    cap: int
    detector: Detector
    # Prose-style folklore (high human overlap) ships off; the keyboard-character
    # folklore (em-dash, emoji) ships on, additive-only. The config can turn any
    # signal on or off. See decisions D-09 and D-12.
    default_enabled: bool = True
    # "prose" detectors take the assembled text; "code" detectors take doc.files.
    kind: str = "prose"
    # Additive-only signals raise the raw sum when they fire but stay out of
    # the normalisation ceiling, so enabling them can never deflate the score
    # of the evidence-backed signals (D-12; the D-09 inversion, generalised).
    in_ceiling: bool = True
    # A "certain" signal is a near-definitive tell (an explicit AI attribution
    # trailer), not a weak convergence signal - so it floors the score into the
    # HIGH band on its own (D-13). Weak signals must still converge to get there.
    certain: bool = False


def _dedup(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _phrase_pattern(phrases: list[str]) -> re.Pattern[str]:
    """Compile a case-insensitive alternation of literal phrases.

    Word boundaries are added only next to alphanumeric edges, so phrases that
    end in punctuation (``certainly!``, ``co-authored-by:``) still match.
    Longer phrases are tried first so the most specific match wins.
    """
    ordered = sorted(set(phrases), key=len, reverse=True)
    parts = []
    for phrase in ordered:
        left = r"\b" if phrase[0].isalnum() else ""
        right = r"\b" if phrase[-1].isalnum() else ""
        parts.append(f"{left}{re.escape(phrase)}{right}")
    return re.compile("|".join(parts), re.IGNORECASE)


def _phrase_detector(phrases: list[str]) -> Detector:
    pattern = _phrase_pattern(phrases)

    def detect(text: str) -> tuple[int, list[str]]:
        matches = [m.group(0) for m in pattern.finditer(text)]
        return len(matches), _dedup(matches)[:_EVIDENCE_LIMIT]

    return detect


def _detect_self_reference(text: str) -> tuple[int, list[str]]:
    """Prose-safe AI phrases anywhere, plus bot-identity tokens restricted to
    trailer-context lines (a Co-authored-by trailer or an <email> author), so
    naming a tool in prose never counts (review H2)."""
    matches = [m.group(0) for m in _SELF_REFERENCE_PATTERN.finditer(text)]
    matches += [m.group(0).strip() for m in _REVIEW_BOT_STAMP.finditer(text)]
    for line in text.splitlines():
        if _TRAILER_LINE.search(line):
            matches += [m.group(0) for m in _IDENTITY_PATTERN.finditer(line)]
    return len(matches), _dedup(matches)[:_EVIDENCE_LIMIT]


# --- Phrase lists ----------------------------------------------------------

_SELF_REFERENCE = [
    "as an ai",
    "as a language model",
    "as an ai language model",
    "i am an ai",
    "i'm an ai",
    "i'm just an ai",
    "i cannot browse",
    "i do not have access to real-time",
    "i don't have access to real-time",
    "my training data",
    "knowledge cutoff",
    "generated with claude",
    "generated with chatgpt",
    "generated by claude",
    "generated by chatgpt",
    "co-authored-by: claude",
    "co-authored-by: chatgpt",
    "co-authored-by: copilot",
    "co-authored-by: cursor",
    "co-authored-by: codex",
    "co-authored-by: devin",
    "co-authored-by: aider",
    "co-authored-by: gemini",
    "co-authored-by: windsurf",
    "co-authored-by: jules",
    "generated with aider",
    "generated with gemini",
    "generated by gemini",
    "generated with [claude code]",
    "generated with [claude]",
    "written by an ai",
    # Trailer-key forms beyond Co-Authored-By / Generated-with - the key itself
    # is the context, so these stay prose-safe.
    "assisted-by: claude",
    "generated-by: copilot",
    "generated-by: claude",
    # Tool names that are not also common human names.
    "co-authored-by: openai",
    "co-authored-by: qodo",
    # CodeRabbit's auto-comment wrapper around its stamped summary. The full
    # wrapper text is the anchor - the bare domain is how a human refers to
    # the bot ("the release notes by coderabbit.ai keep appearing"), and the
    # pre-2022 human corpus cannot witness post-2023 bot mentions (review
    # finding on D-16).
    "auto-generated comment: release notes by coderabbit.ai",
]

# Bot identities / noreply emails - the highest-volume real-world markers, but
# they DOUBLE as ordinary words a human writes in prose ("fix the cursoragent
# webhook"). Matched ONLY on a trailer-context line (a Co-authored-by trailer
# or an <email> author), never in free prose - otherwise, with attribution
# flooring to HIGH (D-13), naming a tool would confidently false-accuse a
# human (review H2, D-14 corrected).
_AI_IDENTITIES = [
    "noreply@anthropic.com",
    "cursoragent",
    "devin-ai-integration",
    "copilot-swe-agent",
]
_TRAILER_LINE = re.compile(r"co-authored-by|co-committed-by|<[^>\s]+@[^>\s]+>", re.I)
# AI review-bot stamps left in PR bodies (corpus-mined 2026-06-11: 25+ AI
# records across 4 tools, 0/1993 humans). Anchored to the stamped HEADER form -
# the bot name alone is prose a human writes ("I rewrote the summary by
# CodeRabbit"), and a bare "Auto-Generated PR" header is template/Renovate
# territory, so aider's needs its robot glyph. Same anchoring rule as D-14.
_REVIEW_BOT_STAMP = re.compile(
    r"^[ \t]{0,3}#{1,6}[ \t]+(?:summary by (?:coderabbit|sourcery)\b"
    r"|\U0001f916[ \t]*auto-generated pr\b)",
    re.IGNORECASE | re.MULTILINE,
)
_SELF_REFERENCE_PATTERN = _phrase_pattern(_SELF_REFERENCE)
_IDENTITY_PATTERN = _phrase_pattern(_AI_IDENTITIES)

_CLICHE = [
    "delve into",
    "delve deeper into",
    "dive into",
    "deep dive",
    "at its core",
    "it's worth noting",
    "it is worth noting",
    "worth noting that",
    "in conclusion",
    "in summary",
    "to summarize",
    "to summarise",
    "to put it simply",
    "needless to say",
    "that being said",
    "rest assured",
    "a testament to",
    "plays a crucial role",
    "plays a vital role",
    "it's important to note",
    "it is important to note",
    "important to note that",
    "when it comes to",
    "first and foremost",
    "last but not least",
    "navigating the",
    "look no further",
    "ever-evolving",
    "ever-changing",
    "by leveraging",
    "rich tapestry",
    "underscores the importance",
    "highlights the importance",
    "meticulous attention",
]

_VAGUE_AUTHORITY = [
    "studies show",
    "studies have shown",
    "research shows",
    "research suggests",
    "experts agree",
    "experts argue",
    "experts say",
    "observers note",
    "industry reports",
    "it is well known that",
    "it's well known that",
    "data shows",
    "some critics",
]

_OPENERS = [
    "certainly!",
    "absolutely!",
    "of course!",
    "great question",
    "excellent question",
    "great point",
    "i'd be happy to",
    "i would be happy to",
    "happy to help",
    "sure thing",
    "i hope this helps",
    "hope this helps!",
    "let me know if you",
    "feel free to reach out",
    "thanks for your question",
    "glad to help",
]

_PROMOTIONAL = [
    "seamless",
    "seamlessly",
    "robust",
    "comprehensive",
    "powerful",
    "elegant",
    "elegantly",
    "cutting-edge",
    "state-of-the-art",
    "game-changer",
    "game-changing",
    "revolutionary",
    "innovative",
    "effortless",
    "effortlessly",
    "unparalleled",
    "leverage",
    "leverages",
    "leveraging",
    "harness",
    "harnessing",
    "streamline",
    "streamlined",
    "intuitive",
    "versatile",
    "boasts",
    "pivotal",
    "realm",
    "supercharge",
    "vibrant",
    "groundbreaking",
    "diverse array",
    "nestled",
    "best-in-class",
    "world-class",
    "blazing",
    "blazingly",
]


# --- Structural detectors --------------------------------------------------

_BOLD_LEAD_IN = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+\*\*(.+?)\*\*", re.MULTILINE)

_SECTION = re.compile(
    r"^[ \t]{0,3}#{1,6}[ \t]*[^\w\n]*\b("
    r"overview|summary|changes|key changes|testing|test plan|conclusion|benefits|"
    r"features|implementation|background|solution|problem|motivation|description|"
    r"usage|installation|notes?|next steps|rationale|context|proposed changes|"
    r"what changed|why)\b",
    re.IGNORECASE | re.MULTILINE,
)

_EMOJI = re.compile(
    "["
    "\U0001f300-\U0001f5ff"
    "\U0001f600-\U0001f64f"
    "\U0001f680-\U0001f6ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa70-\U0001faff"
    "☀-⛿"  # misc symbols (sun, umbrella, zap, warning ...)
    "✀-➿"  # dingbats (scissors, check, sparkles, arrows ...)
    "]"
)


def _detect_bold_lead_in(text: str) -> tuple[int, list[str]]:
    labels = [m.strip() for m in _BOLD_LEAD_IN.findall(text)]
    return len(labels), _dedup(labels)[:_EVIDENCE_LIMIT]


def _detect_sections(text: str) -> tuple[int, list[str]]:
    headers = [m.strip() for m in _SECTION.findall(text)]
    return len(headers), _dedup(headers)[:_EVIDENCE_LIMIT]


def _detect_em_dash(text: str) -> tuple[int, list[str]]:
    # Density signal: U+2014 only. En-dash and ASCII "--" are common in legit
    # text and would add false positives.
    return text.count("—"), []


# A grapheme glyph may be several codepoints: a base emoji plus skin-tone
# modifiers (U+1F3FB-U+1F3FF) joined by zero-width joiners (U+200D). Collapse
# those into the base so a single "person coding" glyph counts once, not thrice
# (a real human commit, gardener d0368438, false-flagged on exactly this).
_EMOJI_SEQUENCE = re.compile(
    _EMOJI.pattern + "(?:[\U0001f3fb-\U0001f3ff]|\u200d" + _EMOJI.pattern + ")*"
)


def _detect_emoji(text: str) -> tuple[int, list[str]]:
    # Status glyphs (checkmarks, warnings) are NOT excluded: the real corpus
    # shows humans don't use them (0/372 human commits, 0/24 holdout) while
    # they're a decorative-AI tell. Excluding them would dilute the signal for
    # no false-positive benefit (a review claimed humans use them; the data
    # said otherwise).
    matches = [m.group(0) for m in _EMOJI_SEQUENCE.finditer(text)]
    return len(matches), _dedup(matches)[:_EVIDENCE_LIMIT]


_CURLY = re.compile("[\u2018\u2019\u201c\u201d]")


def _detect_curly_quotes(text: str) -> tuple[int, list[str]]:
    # Word-processor punctuation. Sized so it can never flag alone: phone
    # keyboards auto-insert smart quotes, so unlike the em-dash a human CAN
    # produce these without reaching for them (WP:Signs of AI writing).
    return len(_CURLY.findall(text)), []


_NEGATIVE_PARALLELISM = re.compile(
    # Same-sentence: "not just X, but Y".
    r"\bnot (?:just|only|merely)\b[^.!?\n]{1,60}?[,;]?\s+but\b"
    # Same-sentence: "it's not X, it's Y".
    r"|\b(?:it|this|that)[\u2019']s not\b[^.!?\n]{1,60}?[,;]\s*(?:it|this|that)[\u2019']s\b"
    # Cross-sentence contrastive / inspirational pivot: "isn't just buying
    # content. They're buying credibility." / "This isn't just about AI.
    # It's about humanity."
    r"|\b(?:(?:is|are)n[\u2019']t|not) just\b[^.!?\n]{1,60}[.!?]\s+(?:it|this|that|they)\b"
    # Staccato anaphora triplets: "Not for advertising. Not for distribution."
    r"|(?:\bnot (?:for |a |the |about )?\w[^.!?\n]{0,40}[.!?]\s+){2,}",
    re.IGNORECASE,
)


def _detect_negative_parallelism(text: str) -> tuple[int, list[str]]:
    matches = [m.group(0)[:60] for m in _NEGATIVE_PARALLELISM.finditer(text)]
    return len(matches), _dedup(matches)[:_EVIDENCE_LIMIT]


_RHETORICAL_QA = re.compile(
    # A question immediately answered by its own author: "Why? Because the
    # math did." / "What changed? The math did." / "The result? Simple."
    r"\b(?:why|what|how|when|who|where|the (?:result|catch|problem|answer|takeaway))"
    r"[^.!?\n]{0,30}\?\s+"
    r"(?:because\b|simple\b|it[\u2019']s\b|the \w+ (?:did|is|was)\b|undisclosed\b)",
    re.IGNORECASE,
)


def _detect_rhetorical_qa(text: str) -> tuple[int, list[str]]:
    matches = [m.group(0)[:60] for m in _RHETORICAL_QA.finditer(text)]
    return len(matches), _dedup(matches)[:_EVIDENCE_LIMIT]


# --- Code detectors --------------------------------------------------------

# Deliberately narrow: these are AI-stub markers a human does not commit. The
# "implement this" / "TODO: implement" family was dropped - it collides with
# legitimate human TODOs (review finding, default-on signal, low-FP is the point).
_PLACEHOLDER_PATTERNS = [
    re.compile(r"(?:#|//)\s*\.\.\.\s*(?:rest|remaining|existing|the rest|more|other|unchanged)", re.IGNORECASE),
    re.compile(r"(?:#|//)\s*(?:rest|remainder)\s+of\s+(?:the\s+)?(?:code|file|function|implementation)", re.IGNORECASE),
    re.compile(r"(?:#|//)\s*(?:your|the)\s+(?:implementation|code|logic)\s+(?:goes\s+)?here", re.IGNORECASE),
    re.compile(r"\.\.\.\s*existing\s+code\s*\.\.\.", re.IGNORECASE),
    # "# placeholder" as a stub, not "# placeholder text for the field".
    re.compile(r"(?:#|//)\s*placeholder(?:\s+(?:implementation|code|function|here))?\s*$", re.IGNORECASE),
]


def _detect_placeholder_stub(files: "tuple[CodeFile, ...]", _root: str | None = None) -> tuple[int, list[str]]:
    """Count placeholder/stub markers left in code - "rest of code", "your
    implementation here", "... existing code ...". No human commits these on
    purpose; they are unedited AI output. Evidence is ``path:line: snippet``.

    (Code detectors are called uniformly as ``detector(files, root)``; this one
    has no manifest to resolve against, so it ignores ``_root``.)
    """
    count = 0
    evidence: list[str] = []
    for f in files:
        for lineno, line in enumerate(f.content.splitlines(), 1):
            if any(p.search(line) for p in _PLACEHOLDER_PATTERNS):
                count += 1
                if len(evidence) < _EVIDENCE_LIMIT:
                    evidence.append(f"{f.path}:{lineno}: {line.strip()[:60]}")
    return count, evidence


SIGNALS: list[Signal] = [
    Signal(
        "ai_self_reference",
        "Explicit AI attribution or assistant self-reference",
        4.0,
        1,
        _detect_self_reference,
        certain=True,
    ),
    # Weak-signal caps/weights are sized so no single weak signal can reach
    # the default threshold alone (max 1.5 over the 5.5 prose ceiling = 27.3);
    # only attribution (4.0 -> 72.7, floored to HIGH) flags alone, by design
    # (D-12, resized in D-17).
    Signal(
        "ai_cliche_phrases",
        "Filler and transition phrases characteristic of LLM prose",
        0.75,
        2,
        _phrase_detector(_CLICHE),
    ),
    # Chat-register lore, not commit residue: 0/2,567 attributed-AI records
    # fire it and its only corpus fires were friendly humans ("happy to help
    # out"). Kept reachable for pasted-chat scanning and the strict tier,
    # which the attribution-selected corpus cannot witness (D-17).
    Signal(
        "sycophantic_openers",
        "Chatbot-style enthusiastic or deferential openers",
        1.0,
        2,
        _phrase_detector(_OPENERS),
        default_enabled=False,
        in_ceiling=False,
    ),
    Signal(
        "promotional_adjectives",
        "Clusters of marketing adjectives",
        0.5,
        4,
        _phrase_detector(_PROMOTIONAL),
        default_enabled=False,
        in_ceiling=False,
    ),
    Signal(
        "bold_lead_in_lists",
        "Bulleted items with bold lead-in labels",
        1.5,
        4,
        _detect_bold_lead_in,
        default_enabled=False,
        in_ceiling=False,
    ),
    Signal(
        "section_scaffolding",
        "Templated markdown section headers",
        1.0,
        3,
        _detect_sections,
        default_enabled=False,
        in_ceiling=False,
    ),
    Signal(
        "curly_quotes",
        "Curly quotes (word-processor punctuation, not keyboard input)",
        0.5,
        4,
        _detect_curly_quotes,
        in_ceiling=False,
    ),
    Signal(
        "negative_parallelism",
        "Contrastive not-just-X-but-Y framing and staccato anaphora",
        1.0,
        3,
        _detect_negative_parallelism,
        default_enabled=False,
        in_ceiling=False,
    ),
    Signal(
        "rhetorical_qa",
        "Self-answered rhetorical questions (Why? Because...)",
        1.0,
        3,
        _detect_rhetorical_qa,
        default_enabled=False,
        in_ceiling=False,
    ),
    Signal(
        "vague_authority",
        "Sourceless appeals to authority (studies show, experts agree)",
        1.0,
        3,
        _phrase_detector(_VAGUE_AUTHORITY),
        default_enabled=False,
        in_ceiling=False,
    ),
    Signal(
        "em_dash_density",
        "Em-dash (U+2014) usage",
        0.75,
        6,
        _detect_em_dash,
        in_ceiling=False,
    ),
    Signal(
        "emoji_density",
        "Decorative emoji",
        1.0,
        6,
        _detect_emoji,
        in_ceiling=False,
    ),
    Signal(
        "code_placeholder_stub",
        "Placeholder/stub markers left in code (unedited AI output)",
        3.0,
        3,
        _detect_placeholder_stub,
        kind="code",
    ),
    Signal(
        "code_undeclared_import",
        "Import of a module that is not stdlib, declared, or local (possibly hallucinated)",
        4.0,
        3,
        detect_undeclared_imports,
        default_enabled=False,
        kind="code",
    ),
]


def evaluate(
    doc: Document,
    enabled: frozenset[str] | None = None,
    weights: dict[str, float] | None = None,
    root: str = ".",
) -> list[SignalHit]:
    """Run the enabled signals over the document; return only those that fired.

    ``enabled`` is the set of signal names to run (None = every signal - the raw
    engine default; the product default is set by the config layer). ``weights``
    overrides a signal's default weight by name. ``root`` is the project root that
    code signals resolve against (e.g. the manifest for import resolution).
    """
    text = doc.assembled
    hits = []
    for signal in SIGNALS:
        if enabled is not None and signal.name not in enabled:
            continue
        if signal.kind == "code":
            occurrences, evidence = signal.detector(doc.files, root)
        else:
            occurrences, evidence = signal.detector(text)
            if doc.structured:
                evidence = [
                    f"{loc}: {e}" if (loc := doc.locate(e)) else e for e in evidence
                ]
        if occurrences > 0:
            weight = weights.get(signal.name, signal.weight) if weights else signal.weight
            hits.append(
                SignalHit(
                    name=signal.name,
                    description=signal.description,
                    weight=weight,
                    cap=signal.cap,
                    occurrences=occurrences,
                    evidence=tuple(evidence),
                )
            )
    return hits
