"""Real-corpus separation invariants.

These run against locally-harvested corpora of real commits (attribution-
labelled AI commits + matched pre-2022 human commits from the same large
repos). The DATA is deliberately not committed - it is third-party prose
with real author names/emails, and a self-facing linter has no business
publishing other people's commits. So these tests SKIP when the corpus is
absent (CI, fresh clones) and run wherever a maintainer has harvested it
(see eval-private/harvest*.py).

What they lock, that the synthetic anchors cannot: that a future signal or
weight change does not start false-flagging REAL humans, and that real AI
attribution keeps flagging.
"""

import json
from pathlib import Path

import pytest

from slopscore.config import default_config
from slopscore.signals import Document
from slopscore.triage import triage

CORPUS = Path(__file__).resolve().parent.parent / "eval-private"
AI = CORPUS / "ai-commits-big.jsonl"
HUMAN = CORPUS / "human-commits-big.jsonl"


def _load(path):
    return [json.loads(line)["message"] for line in path.read_text().splitlines()]


def _flag(msg):
    cfg = default_config()
    return triage(
        Document(body=msg), threshold=cfg.threshold,
        enabled=cfg.enabled, weights=cfg.weights,
    ).verdict == "FLAG"


@pytest.mark.skipif(not HUMAN.exists(), reason="human corpus not harvested locally")
def test_no_real_human_commit_is_flagged():
    # The never-false-accuse rule, on real pre-2022 commits from large repos -
    # a far larger and harder negative than the 24-PR holdout. Zero tolerance.
    flagged = [m for m in _load(HUMAN) if _flag(m)]
    assert flagged == [], f"{len(flagged)} real human commits flagged: {flagged[:2]}"


@pytest.mark.skipif(not AI.exists(), reason="AI corpus not harvested locally")
def test_real_ai_attribution_commits_flag():
    # The corpus is selected for attribution trailers; every one must flag, or
    # an attribution marker has regressed.
    msgs = _load(AI)
    missed = [m for m in msgs if not _flag(m)]
    assert missed == [], f"{len(missed)}/{len(msgs)} attribution commits missed"


@pytest.mark.skipif(
    not (AI.exists() and HUMAN.exists()), reason="corpora not harvested locally"
)
def test_clean_separation_with_margin():
    # The real-corpus calibration finding (2026-06-11): humans and AI separate
    # cleanly with an empty margin around the threshold - no human scores near
    # the flag bar, no AI commit scores like a human. Locks that a future
    # signal/weight change keeps the bands meaningful, not just non-flagging.
    cfg = default_config()

    def score(m):
        return triage(Document(body=m), threshold=cfg.threshold,
                      enabled=cfg.enabled, weights=cfg.weights).score

    human_max = max(score(m) for m in _load(HUMAN))
    ai_min = min(score(m) for m in _load(AI))
    assert human_max < 20, f"a real human scored {human_max}, near the flag bar"
    assert ai_min >= cfg.threshold, f"a real AI commit scored {ai_min}, below flag"
    assert ai_min - human_max >= 25, "separation margin collapsed"
