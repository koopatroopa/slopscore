"""Scoring, banding, verdict, and report rendering.

The raw score is the sum of each fired signal's capped contribution - the
deliberate design is that no single weak signal can flag on its own, only
convergence does. The headline number is that raw score normalised to 0-100
against the most the enabled signals could contribute - a GRADIENT of how much
AI residue is present, not a yes/no - then placed in a band:

    LOW     score < 30        little to no residue
    MEDIUM  30 <= score < 70   some residue worth a look
    HIGH    score >= 70        heavy residue

A low non-zero score is light texture, not an accusation. The band classifies;
the VERDICT (the only gate - exit code, CI, git hook) flags at/above the
threshold and is tuned so honest human work passes. Self-facing by design: it
scores text, it never accuses an author.
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


# Additive (out-of-ceiling) signals may together contribute at most this
# fraction of the evidence ceiling to the score. On the default 8.0 prose
# ceiling that is 2.0 raw = 25.0 points: folklore alone can never reach the
# DEFAULT 30.0 threshold, however many additive signals converge (a config
# lowering the threshold to 25.0 or below re-admits folklore-only flags).
# Found the hard way - two real pre-2022 PR bodies scored 100.0 from curly
# quotes + emoji alone (D-15, corpus run 2026-06-11).
ADDITIVE_CAP_FRACTION = 0.25


def _ceiling_totals(
    doc: Document,
    enabled: frozenset[str] | None = None,
    weights: dict[str, float] | None = None,
) -> tuple[float, float]:
    """(in-ceiling total, additive total) of weight*cap over the applicable
    enabled signals - the shared arithmetic behind the normalisation
    denominator and the additive cap."""
    evidence = additive = 0.0
    for s in SIGNALS:
        if enabled is not None and s.name not in enabled:
            continue
        if not _applicable(s, doc):
            continue
        weight = weights.get(s.name, s.weight) if weights else s.weight
        if s.in_ceiling:
            evidence += weight * s.cap
        else:
            additive += weight * s.cap
    return round(evidence, 2), round(additive, 2)


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
    evidence, additive = _ceiling_totals(doc, enabled, weights)
    return evidence or additive


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
    raw: float  # sum of per-signal capped contributions (no aggregate cap)
    counted: float  # score basis: raw after the additive aggregate cap (D-15)
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
            "counted": self.counted,
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
            + (
                f"  (raw {self.raw}, threshold {self.threshold})"
                if self.counted == self.raw
                else f"  (raw {self.raw}, counted {self.counted}"
                f" after the folklore cap, threshold {self.threshold})"
            ),
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
    # Additive contributions are capped in aggregate (D-15): folklore
    # corroborates evidence, it never constitutes it. The cap is skipped in
    # the zero-ceiling fallback - a folklore-only config is an explicit
    # opt-in to scoring on folklore alone (D-12).
    in_ceiling = {s.name for s in SIGNALS if s.in_ceiling}
    raw_evidence = float(sum(h.contribution for h in hits if h.name in in_ceiling))
    raw_additive = float(sum(h.contribution for h in hits if h.name not in in_ceiling))
    evidence_ceiling, additive_ceiling = _ceiling_totals(doc, enabled, weights)
    ceiling = evidence_ceiling or additive_ceiling
    if evidence_ceiling:
        counted = raw_evidence + min(raw_additive, ADDITIVE_CAP_FRACTION * evidence_ceiling)
    else:
        counted = raw_additive
    score = round(100 * counted / ceiling, 1) if ceiling else 0.0
    counted = round(counted, 2)  # display precision; the score used the full value
    # Clamp both ends: full evidence plus capped additive deliberately
    # saturates past 100 before clamping, and odd weight overrides can land
    # anywhere.
    score = max(0.0, min(100.0, score))
    # A certain signal (an explicit AI attribution trailer) is definitive, not a
    # weak convergence signal: it floors the score into HIGH on its own (D-13).
    fired = {h.name for h in hits}
    if any(s.certain and s.name in fired for s in SIGNALS):
        score = max(score, MED_MAX)
    band = band_for(score)
    verdict = "FLAG" if score >= threshold else "PASS"
    return TriageReport(
        score=score, raw=raw, counted=counted, band=band, verdict=verdict,
        threshold=threshold, hits=tuple(hits),
    )
