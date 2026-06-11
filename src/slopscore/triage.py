"""Scoring, banding, verdict, and report rendering.

The raw score is the sum of each fired signal's capped contribution - the
deliberate design is that no single weak signal can flag on its own, only
convergence does. The headline number is that raw score normalised to 0-100
against the most the enabled signals could contribute, then placed in a band:

    LOW     score < 30        likely clean
    MEDIUM  30 <= score < 70   some slop residue worth a look
    HIGH    score >= 70        heavy slop residue

The band classifies; the verdict flags at/above a 0-100 threshold (the exit
code and CI/git-hook gate key off the verdict). Self-facing by design: it
scores text, it does not accuse an author.
"""

from __future__ import annotations

from dataclasses import dataclass

from slopscore.signals import SIGNALS, Document, SignalHit, evaluate

# CALIBRATION (D-09, T-11; amended by D-12): the threshold and band cut-points
# are validated against the real 24-human holdout (all score 0.0) plus a
# slop-by-construction high anchor. Evidence-backed signals (attribution,
# cliche, openers, placeholder) form the ceiling and drive the score; the
# keyboard-character folklore (em-dash, emoji) is default-on but additive-only,
# and the prose-style folklore stays off. Weak-signal caps are sized so no
# single weak signal can flag alone; attribution can, deliberately (D-12).

# Flag at/above this 0-100 score. A distinct concept from the band cut-points
# (the flag bar, vs "how much residue"); they share a value today but are tuned
# independently.
DEFAULT_THRESHOLD = 30.0

# Band cut-points on the 0-100 scale.
LOW_MAX = 30.0
MED_MAX = 70.0


def _applicable(signal, doc: Document) -> bool:
    """A signal can only contribute if the input has the surface it scans - a
    code signal needs files, a prose signal needs prose. This keeps a code
    signal out of a prose-only document's ceiling (and vice versa), so adding
    code signals does not deflate prose scores (D-09 #5)."""
    if signal.kind == "code":
        return bool(doc.files)
    return bool(doc.assembled)


def max_possible(
    doc: Document,
    enabled: frozenset[str] | None = None,
    weights: dict[str, float] | None = None,
) -> float:
    """The largest raw score the applicable enabled in-ceiling signals could
    produce (all at cap) - the normalisation denominator. Additive-only
    (folklore) signals never join it, so the 0-100 scale is stable across
    folklore toggling (D-12); re-run calibration (T-11) only when the
    IN-CEILING enabled set changes (D-09, #5).

    Degenerate case: a config enabling only additive signals would give a
    zero ceiling with a live raw score; fall back to the additive signals'
    own maximum so such a config still scores meaningfully (D-12).
    """

    def total_for(ceiling_only: bool) -> float:
        total = 0.0
        for s in SIGNALS:
            if enabled is not None and s.name not in enabled:
                continue
            if not _applicable(s, doc):
                continue
            if s.in_ceiling != ceiling_only:
                continue
            weight = weights.get(s.name, s.weight) if weights else s.weight
            total += weight * s.cap
        return round(total, 2)

    return total_for(True) or total_for(False)


# ANSI codes for the human report; LOW/MEDIUM/HIGH read as green/amber/red.
_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_RED = "\x1b[31m"
_GREEN = "\x1b[32m"
_YELLOW = "\x1b[33m"
_CYAN = "\x1b[36m"
_BAND_COLOURS = {"LOW": _GREEN, "MEDIUM": _YELLOW, "HIGH": _RED}
# Badge backgrounds for the header: black-on-green/amber, white-on-red.
_BAND_BADGES = {"LOW": "\x1b[1;30;42m", "MEDIUM": "\x1b[1;30;43m", "HIGH": "\x1b[1;97;41m"}
# Drop-shadow in a dark shade of the band colour (256-colour); bright-black
# all but disappears on dark terminal themes.
_BAND_SHADOWS = {"LOW": "\x1b[38;5;22m", "MEDIUM": "\x1b[38;5;58m", "HIGH": "\x1b[38;5;52m"}


def band_for(score: float) -> str:
    """Place a 0-100 score in its band. Upper boundaries are inclusive upward."""
    if score < LOW_MAX:
        return "LOW"
    if score < MED_MAX:
        return "MEDIUM"
    return "HIGH"


@dataclass(frozen=True)
class TriageReport:
    score: float  # 0-100, normalised
    raw: float  # sum of capped contributions
    band: str  # LOW / MEDIUM / HIGH
    verdict: str  # FLAG / PASS
    threshold: float  # 0-100 score at/above which the verdict is FLAG
    hits: tuple[SignalHit, ...]

    def to_dict(self) -> dict:
        """Machine-readable form. Only fired signals, highest contribution first."""
        ordered = sorted(self.hits, key=lambda h: h.contribution, reverse=True)
        return {
            "score": self.score,
            "raw": self.raw,
            "band": self.band,
            "verdict": self.verdict,
            "threshold": self.threshold,
            "signals": [
                {
                    "name": h.name,
                    "description": h.description,
                    "weight": h.weight,
                    "occurrences": h.occurrences,
                    "counted": h.counted,
                    "contribution": h.contribution,
                    "evidence": list(h.evidence),
                }
                for h in ordered
            ],
        }

    def to_text(
        self, color: bool = False, label: str | None = None, badge: str | None = None
    ) -> str:
        """Human-readable slop report. ANSI colour is opt-in: the caller
        decides (terminal detection lives at the CLI layer, not here).
        A label (e.g. "abc1234 Fix the parser") joins the header so multi-
        report output, like a pre-push scan, stays self-identifying."""

        def paint(text: object, *codes: str) -> str:
            if not color:
                return str(text)
            return f"{''.join(codes)}{text}{_RESET}"

        band_code = _BAND_COLOURS.get(self.band, "")
        verdict_code = _RED if self.verdict == "FLAG" else _GREEN
        # Badge-style header: the background takes the band colour, so the
        # verdict is readable before a single line of detail. In colour mode
        # the badge gets a half-block drop shadow (right edge + offset bottom
        # row in grey); the plain fallback stays pure ASCII for logs and CI.
        wordmark = badge or "SLOPSCORE SLOP REPORT"
        if color:
            badge_code = _BAND_BADGES.get(self.band, _BOLD)
            shadow = _BAND_SHADOWS.get(self.band, "\x1b[90m")
            padded = f" {wordmark} "
            suffix = f"  {_BOLD}{label}{_RESET}" if label else ""
            title_lines = [
                "",  # breathing room above the badge
                f"{badge_code}{padded}{_RESET}{shadow}▄{_RESET}{suffix}",
                f" {shadow}{'▀' * len(padded)}{_RESET}",
            ]
        else:
            title = f"[ {wordmark} ]"
            if label:
                title += f" - {label}"
            title_lines = [title, ""]
        lines = [
            *title_lines,
            f"Slop score {paint(f'{self.score}/100', _BOLD, band_code)}"
            f"  band {paint(self.band, band_code)}"
            f"  verdict {paint(self.verdict, _BOLD, verdict_code)}"
            f"  (raw {self.raw}, threshold {self.threshold})",
            "",
        ]
        ordered = sorted(self.hits, key=lambda h: h.contribution, reverse=True)
        if not ordered:
            lines.append("Signals fired: none")
        else:
            lines.append(f"Signals fired ({len(ordered)}):")
            for h in ordered:
                count = f"x{h.occurrences}"
                if h.occurrences > h.cap:
                    count += f" (capped {h.cap})"
                lines.append(
                    f"  {paint(f'[+{h.contribution}]', _CYAN)}"
                    f" {paint(h.name, _BOLD)}  {count}  {h.description}"
                )
                if h.evidence:
                    lines.append(paint(f"         Evidence: {', '.join(h.evidence)}", _DIM))
        lines.append("")
        comparator = ">=" if self.verdict == "FLAG" else "<"
        lines.append(
            f"Verdict: {paint(self.verdict, _BOLD, verdict_code)}"
            f" (score {self.score} {comparator} threshold {self.threshold})"
        )
        return "\n".join(lines)


def triage(
    doc: Document,
    threshold: float = DEFAULT_THRESHOLD,
    enabled: frozenset[str] | None = None,
    weights: dict[str, float] | None = None,
    root: str = ".",
) -> TriageReport:
    hits = evaluate(doc, enabled=enabled, weights=weights, root=root)
    raw = round(float(sum(h.contribution for h in hits)), 2)
    ceiling = max_possible(doc, enabled=enabled, weights=weights)
    score = round(100 * raw / ceiling, 1) if ceiling else 0.0
    score = max(0.0, min(100.0, score))  # clamp both ends (defends against odd weights)
    # A certain signal (an explicit AI attribution trailer) is definitive, not a
    # weak convergence signal: it floors the score into HIGH on its own (D-13).
    fired = {h.name for h in hits}
    if any(s.certain and s.name in fired for s in SIGNALS):
        score = max(score, MED_MAX)
    band = band_for(score)
    verdict = "FLAG" if score >= threshold else "PASS"
    return TriageReport(
        score=score, raw=raw, band=band, verdict=verdict, threshold=threshold, hits=tuple(hits)
    )
