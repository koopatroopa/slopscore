"""Behavioural spec for code-scanning signals (kind="code").

These run over CodeFiles (path + content), not prose, and report findings with
file:line evidence. The first is the evidence-backed placeholder/stub-leak
signal (unedited AI output left in the diff).
"""

from slopscore.config import default_config
from slopscore.signals import SIGNALS, CodeFile, Document, evaluate
from slopscore.triage import max_possible, triage


def _hits(doc):
    return {h.name: h for h in evaluate(doc)}


def test_placeholder_stub_fires_on_code_placeholder():
    doc = Document(files=(CodeFile("foo.py", "import os\n# ... rest of the code unchanged\n"),))
    h = _hits(doc)
    assert "code_placeholder_stub" in h
    assert h["code_placeholder_stub"].occurrences == 1


def test_placeholder_stub_quiet_on_clean_code():
    doc = Document(files=(CodeFile("foo.py", "import os\n\ndef add(a, b):\n    return a + b\n"),))
    assert "code_placeholder_stub" not in _hits(doc)


def test_placeholder_quiet_on_legit_placeholder_word():
    # "placeholder" is a common UI/forms word; only stub-shaped comments fire.
    doc = Document(files=(CodeFile("ui.py", "field.placeholder = 'Name'  # placeholder text for the input\n"),))
    assert "code_placeholder_stub" not in _hits(doc)


def test_placeholder_quiet_on_human_todo_implement():
    # Real human-tracked TODOs use this phrasing; not an AI stub marker.
    doc = Document(files=(CodeFile("x.py", "# TODO: implement this once the API ships\n"),))
    assert "code_placeholder_stub" not in _hits(doc)


def test_placeholder_evidence_has_file_and_line():
    doc = Document(files=(CodeFile("foo.py", "a = 1\n# Your implementation here\n"),))
    ev = _hits(doc)["code_placeholder_stub"].evidence[0]
    assert ev.startswith("foo.py:2:")


def test_code_signal_excluded_from_ceiling_when_no_files():
    # A prose-only doc's ceiling must exclude code signals (they can't fire), so
    # adding a code signal does not deflate prose scores (D-09 #5). Folklore
    # signals are additive-only and also stay out (D-12).
    assert max_possible(Document(body="some prose here")) == 5.5


def test_placeholder_in_code_only_doc_flags():
    cfg = default_config()
    doc = Document(files=(CodeFile("foo.py", "# ... rest of code\n# TODO: implement this\n"),))
    r = triage(doc, threshold=cfg.threshold, enabled=cfg.enabled, weights=cfg.weights)
    assert r.raw > 0
    assert r.band in {"MEDIUM", "HIGH"}


def test_undeclared_import_signal_registered_default_off_code_kind():
    s = {x.name: x for x in SIGNALS}["code_undeclared_import"]
    assert s.kind == "code"
    assert s.default_enabled is False
