"""Calibration locks (T-11).

The LOW end is validated against the real 24-human holdout (test_holdout.py: all
score 0.0). These lock the HIGH end and the folklore policy (D-12: prose-style
folklore off; keyboard-character folklore on but additive-only and sub-flag at
realistic density), using slop-by-construction documents - valid because the
signals are DETERMINISTIC markers (attribution, cliche, placeholder), not
stylometry, so synthetic content carrying the markers is a sound target.
Calibration evidence is recorded in decisions D-09 and D-12.
"""

from slopscore.config import default_config
from slopscore.signals import CodeFile, Document
from slopscore.triage import triage


def _report(doc):
    cfg = default_config()
    return triage(doc, threshold=cfg.threshold, enabled=cfg.enabled, weights=cfg.weights)


def test_explicit_attribution_flags():
    # Both the bracketed Claude Code footer (the default, the bug calibration
    # caught) and a Co-Authored-By trailer must cross the flag threshold.
    for body in (
        "Improved perf.\n\nGenerated with [Claude Code](https://claude.ai/code)",
        "Co-Authored-By: Claude <noreply@anthropic.com>",
    ):
        r = _report(Document(body=body))
        assert r.verdict == "FLAG", f"attribution must flag: {body!r} -> {r.score}"


def test_converged_slop_reaches_high_band():
    # Attribution + two chatbot openers = strong convergence -> HIGH (raw 6/8).
    doc = Document(
        body=(
            "Certainly! I'd be happy to help.\n\n"
            "Generated with [Claude Code](https://claude.ai/code)"
        )
    )
    r = _report(doc)
    assert r.band == "HIGH", f"converged slop should be HIGH, got {r.score}/{r.band}"


def test_folklore_only_stays_low_on_default():
    # Section headers + bold bullets + marketing words are prose-style folklore
    # (default-off, D-12) and contribute nothing; the two em-dashes DO score
    # (keyboard-character folklore, default-on, additive-only: raw 1.5 -> 18.8)
    # but folklore at realistic density must stay LOW. Score pinned so margin
    # erosion towards the 30.0 flag bar is deliberate, never silent.
    doc = Document(
        body=(
            "## Summary\n"
            "- **Refactor:** a robust, seamless change — elegant.\n"
            "- **Tests:** comprehensive coverage — added."
        )
    )
    r = _report(doc)
    assert r.band == "LOW" and r.verdict == "PASS", f"folklore-only must stay LOW, got {r.score}"
    assert r.score == 25.0


def test_code_placeholder_flags():
    doc = Document(files=(CodeFile("a.py", "def f():\n    # ... rest of the code unchanged\n"),))
    assert _report(doc).verdict == "FLAG"


def test_other_tool_attributions_flag():
    # The keystone signal must cover the major agents' default trailers,
    # not just Claude/ChatGPT (the aider one ships by default).
    for body in (
        "Refactor the parser.\n\nCo-authored-by: aider (gpt-5) <noreply@aider.chat>",
        "Co-authored-by: Gemini <gemini@google.com>",
        "Co-authored-by: Windsurf <windsurf@codeium.com>",
    ):
        assert _report(Document(body=body)).verdict == "FLAG", body


def test_bot_identity_and_form_markers_flag():
    # D-14: the highest-volume real-world tells are bot identities/emails and
    # trailer-key forms, not display-names. All must flag.
    for body in (
        "Fix the parser\n\nCo-authored-by: Claude <noreply@anthropic.com>",
        "rework auth\n\nCo-authored-by: cursoragent <agent@cursor.com>",
        "tidy up\n\nCo-authored-by: devin-ai-integration[bot] <devin@example.com>",
        "Assisted-by: Claude",
        "Generated-by: Copilot",
    ):
        assert _report(Document(body=body)).verdict == "FLAG", body


def test_human_name_coauthors_do_not_flag():
    # The inverse guard (D-14): a human pair-programmer whose name happens to
    # match an agent's display-name must NOT be flagged.
    for body in (
        "Fix pagination\n\nCo-authored-by: Cody Banks <cody@example.com>",
        "Refactor\n\nCo-authored-by: Roo Smith <roo@example.com>",
        "Patch\n\nCo-authored-by: Pat Cline <pat@example.com>",
    ):
        assert _report(Document(body=body)).verdict == "PASS", body


def test_tool_names_in_prose_do_not_flag():
    # REGRESSION (review H2): bot-identity tokens must only count in a trailer,
    # not when a human merely names the tool in prose or a diff. With the D-13
    # HIGH floor these were confident false-accusations.
    for body in (
        "Add cursoragent integration tests",
        "Fix copilot-swe-agent webhook parsing",
        "Migrate CI off devin-ai-integration",
        "Document the noreply@anthropic.com bounce handling",
        "Bump the (aider) chat model",
    ):
        assert _report(Document(body=body)).verdict == "PASS", body


def test_status_glyphs_count_as_emoji_tells():
    # The real corpus shows humans do NOT use check/warning glyphs (0/372
    # human, 0/24 holdout), so they stay as decorative-AI tells rather than
    # being excluded. A review claimed humans use them; the data overruled it.
    from slopscore.signals import _detect_emoji

    assert _detect_emoji("shipped ✅ careful ⚠ ok ✔")[0] == 3
