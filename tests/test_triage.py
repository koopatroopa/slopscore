"""Behavioural spec for scoring (0-100), banding, verdict, and rendering.

The headline number is a 0-100 slop score: the raw convergence sum normalised
against the maximum the enabled signals could contribute. Bands (LOW/MED/HIGH)
classify it; the verdict flags at/above a 0-100 threshold. Expected values are
computed from the signal spec independently of the code under test.
"""

import json

from slopscore.signals import SIGNALS, Document
from slopscore.triage import (
    DEFAULT_THRESHOLD,
    LOW_MAX,
    MED_MAX,
    band_for,
    max_possible,
    triage,
)


CLEAN = Document(
    title="Fix off-by-one in pagination",
    body="The loop ran one past the end. Adjusted the bound and added a test.",
    commits=("Fix pagination bound",),
)

# Heavily AI-shaped: bold lead-in list + scaffolding + cliche + em-dash + emoji.
SLOP = Document(
    title="Improve the codebase",
    body=(
        "## Overview\n"
        "This PR will delve into a seamless, robust refactor \U0001f680.\n\n"
        "## Changes\n"
        "- **Refactor:** streamline the core module\n"
        "- **Tests:** add comprehensive coverage\n"
        "- **Docs:** update the README\n\n"
        "## Summary\n"
        "In conclusion, this is a game-changer — it's worth noting the gains."
    ),
    commits=("Refactor everything",),
)


def test_clean_text_scores_zero_in_low_band():
    r = triage(CLEAN)
    assert r.raw == 0.0
    assert r.score == 0.0
    assert r.band == "LOW"
    assert r.verdict == "PASS"
    assert r.hits == ()


def test_max_possible_is_sum_of_weight_times_cap():
    # Prose-only doc: ceiling sums the in-ceiling prose signals' weight*cap
    # (attribution 4.0 + cliche 2.0 + openers 2.0 = 8.0). Code signals are
    # excluded when there are no files to scan (D-09 #5); folklore signals
    # are additive-only and never join the ceiling (D-12).
    assert max_possible(Document(body="some prose")) == 8.0


def test_score_is_raw_normalised_to_0_100():
    # two em-dashes only: raw = 0.75 * 2 = 1.5, additive over the ceiling of
    # the evidence-backed signals (8.0), so score = 18.8.
    r = triage(Document(body="alpha — beta — gamma"))
    assert r.raw == 1.5
    assert r.score == 18.8
    assert r.band == "LOW"


def test_band_cutpoints_low_medium_high():
    assert band_for(0.0) == "LOW"
    assert band_for(LOW_MAX - 0.1) == "LOW"
    assert band_for(LOW_MAX) == "MEDIUM"          # boundary is inclusive upward
    assert band_for(MED_MAX - 0.1) == "MEDIUM"
    assert band_for(MED_MAX) == "HIGH"
    assert band_for(100.0) == "HIGH"


def test_slop_scores_into_a_flagging_band():
    r = triage(SLOP)
    assert r.score >= DEFAULT_THRESHOLD
    assert r.band in {"MEDIUM", "HIGH"}
    assert r.verdict == "FLAG"


def test_verdict_threshold_is_inclusive():
    doc = Document(body="alpha — beta — gamma")  # score 3.7
    score = triage(doc).score
    assert triage(doc, threshold=score).verdict == "FLAG"        # >= inclusive
    assert triage(doc, threshold=score + 0.1).verdict == "PASS"


def test_to_dict_schema_and_only_fired_signals():
    data = triage(SLOP).to_dict()
    assert set(data) == {"score", "raw", "band", "verdict", "threshold", "signals"}
    assert data["verdict"] == "FLAG"
    assert data["band"] in {"MEDIUM", "HIGH"}
    fired = {s["name"] for s in data["signals"]}
    assert "sycophantic_openers" not in fired  # only-fired
    for sig in data["signals"]:
        assert set(sig) == {
            "name", "description", "weight",
            "occurrences", "counted", "contribution", "evidence",
        }
    json.dumps(data)  # serialisable


def test_to_dict_signals_sorted_by_contribution_desc():
    sigs = triage(SLOP).to_dict()["signals"]
    contribs = [s["contribution"] for s in sigs]
    assert contribs == sorted(contribs, reverse=True)


def test_to_text_shows_band_score_and_fired_names():
    r = triage(SLOP)
    text = r.to_text()
    assert "FLAG" in text
    assert r.band in text
    assert f"{r.score}" in text
    assert "/100" in text
    assert "bold_lead_in_lists" in text


def test_to_text_handles_no_fired_signals():
    assert "PASS" in triage(CLEAN).to_text()


def test_score_is_clamped_to_0_100_against_hostile_weights():
    # Defence-in-depth: a direct triage() call with a negative weight override
    # (bypassing the config validation) must not produce a negative score.
    doc = Document(body="As an AI language model, I cannot help.")
    r = triage(doc, weights={"ai_self_reference": -5.0})
    assert 0.0 <= r.score <= 100.0


def test_single_attribution_signal_flags_under_any_enabled_set():
    # Policy pin (changed DELIBERATELY for D-12, 2026-06-11): attribution is
    # the keystone signal - raw 4.0 over the in-ceiling prose ceiling (8.0)
    # is 50.0, MEDIUM/FLAG. Folklore signals are additive-only, so enabling
    # them can no longer deflate this below threshold (the D-09 inversion,
    # closed for good): the score is identical with every signal enabled.
    doc = Document(body="As an AI language model, I cannot run the tests.")
    r = triage(doc)
    assert {h.name for h in r.hits} == {"ai_self_reference"}
    assert r.raw == 4.0
    assert (r.score, r.band, r.verdict) == (50.0, "MEDIUM", "FLAG")
    assert triage(doc, enabled=frozenset(s.name for s in SIGNALS)).score == 50.0


def test_no_single_weak_signal_flags_alone():
    # D-12 sizing rule: every weak prose signal at cap stays LOW (max 2.0
    # over the 8.0 ceiling = 25.0). Pinned so a weight/cap/ceiling change
    # that lets one weak signal flag a human is deliberate, never silent.
    cliche = "It's worth noting this. In conclusion, when it comes to tests."
    openers = "Certainly! Done now. Hope this helps!"
    for body in (cliche, openers):
        r = triage(Document(body=body))
        assert len(r.hits) == 1, body
        assert r.band == "LOW" and r.verdict == "PASS", (body, r.score)


def test_zero_ceiling_falls_back_to_additive_signals():
    # A config enabling ONLY additive (folklore) signals must still score
    # meaningfully, not 0.0-PASS-with-hits (D-12 degenerate case): the
    # ceiling falls back to the additive signals' own maximum.
    r = triage(Document(body="Done 🎉🎉🎉"), enabled=frozenset({"emoji_density"}))
    assert [h.name for h in r.hits] == ["emoji_density"]
    assert r.raw == 3.0
    assert r.score == 50.0  # 3.0 over the emoji-only ceiling 6.0
