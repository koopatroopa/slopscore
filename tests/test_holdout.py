"""The never-false-accuse gate (spec AC2, predecessor D-04).

Every record in eval/holdout/ is a real merged PR from before 2020 -
definitionally human. On the DEFAULT config, not one may score above LOW. The
corpus is held out (never tuned against), so 0/24 is genuine evidence the tool
discriminates. The assertion reads the corpus directly, independent of any
fixture the weights were calibrated on.
"""

import json
from pathlib import Path

import pytest

from slopscore.config import default_config
from slopscore.signals import Document
from slopscore.triage import triage

_HOLDOUT = Path(__file__).resolve().parent.parent / "eval" / "holdout"


def _records():
    return sorted(_HOLDOUT.glob("*.json"))


def _document(path: Path) -> Document:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Document(
        title=data.get("title", ""),
        body=data.get("body", ""),
        commits=tuple(data.get("commits", [])),
    )


def test_holdout_corpus_is_present():
    assert len(_records()) >= 24


@pytest.mark.parametrize("path", _records(), ids=lambda p: p.stem)
def test_real_human_pr_stays_in_low_band(path: Path):
    cfg = default_config()
    report = triage(
        _document(path),
        threshold=cfg.threshold,
        enabled=cfg.enabled,
        weights=cfg.weights,
    )
    assert report.band == "LOW", (
        f"{path.stem}: scored {report.score}/100 ({report.band}, raw {report.raw}) - "
        f"a real human PR must never leave the LOW band on the default config"
    )
