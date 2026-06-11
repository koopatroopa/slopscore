"""Behavioural spec for configuration: per-signal on/off, weights, threshold.

The default config disables the folklore/formatting signals (high human overlap)
and keeps the distinctive LLM tells, so benign markdown does not flag while
attribution-bearing text does. Every signal is individually toggleable.
"""

import pytest

from slopscore.config import default_config, load_config
from slopscore.signals import SIGNALS, Document
from slopscore.triage import triage


DEFAULT_OFF = {
    "promotional_adjectives",  # everyday engineering vocabulary
    "bold_lead_in_lists",
    "section_scaffolding",  # PR templates generate these
    "negative_parallelism",  # humans use the rhetoric too
    "rhetorical_qa",  # ditto
    "vague_authority",  # ditto
    "sycophantic_openers",  # chat-register lore: 0 AI fires in 2,567 corpus records (D-17)
    "code_undeclared_import",  # default-off: dist-name-mismatch FP risk (D-10)
}
DEFAULT_ON = {
    "ai_self_reference",
    "ai_cliche_phrases",
    "code_placeholder_stub",
    # Keyboard-character folklore: nobody types U+2014 or emoji by accident,
    # so on by default - but additive-only, out of the ceiling (D-12).
    "em_dash_density",
    "emoji_density",
    "curly_quotes",
}


def _triage(doc, cfg):
    return triage(doc, threshold=cfg.threshold, enabled=cfg.enabled, weights=cfg.weights)


def test_default_config_disables_folklore_signals():
    cfg = default_config()
    assert cfg.enabled == DEFAULT_ON
    assert cfg.enabled.isdisjoint(DEFAULT_OFF)


def test_every_signal_is_classified_on_or_off():
    names = {s.name for s in SIGNALS}
    assert DEFAULT_ON | DEFAULT_OFF == names  # partition - nothing unclassified


def test_load_config_can_enable_a_folklore_signal():
    cfg = load_config("[signals]\nem_dash_density = true\n")
    assert "em_dash_density" in cfg.enabled


def test_load_config_can_disable_a_default_signal():
    cfg = load_config("[signals]\nai_cliche_phrases = false\n")
    assert "ai_cliche_phrases" not in cfg.enabled


def test_load_config_overrides_threshold_and_weight():
    cfg = load_config("threshold = 50\n[weights]\nai_self_reference = 6.0\n")
    assert cfg.threshold == 50.0
    assert cfg.weights["ai_self_reference"] == 6.0


def test_load_config_rejects_unknown_signal_name():
    with pytest.raises(ValueError):
        load_config("[signals]\nnot_a_real_signal = true\n")


def test_load_config_rejects_negative_weight():
    with pytest.raises(ValueError):
        load_config("[weights]\nai_self_reference = -5.0\n")


def test_load_config_rejects_non_finite_weight():
    with pytest.raises(ValueError):
        load_config("[weights]\nai_self_reference = inf\n")


def test_folklore_only_text_passes_on_default_config():
    # section headers + bold bullets + em-dash + emoji + marketing word - all
    # folklore, all default-off. This is the D-09 inversion, now resolved.
    doc = Document(body="## Overview\n- **A:** x\n- **B:** y\n\n## Summary\ndone — robust \U0001f680")
    r = _triage(doc, default_config())
    assert r.band == "LOW"
    assert r.verdict == "PASS"


def test_attribution_plus_opener_flags_on_default_config():
    doc = Document(
        body="Co-Authored-By: Claude\n\nHope this helps! Let me know if you need changes."
    )
    r = _triage(doc, default_config())
    assert r.verdict == "FLAG"
