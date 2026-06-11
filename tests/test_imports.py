"""Behavioural spec for undeclared/unresolvable import detection.

Deterministic + static: resolves an import's top-level module against stdlib +
the project manifest's declared deps + local modules. Never reads the installed
environment, never imports/installs. Hallucinated AI packages are the
high-value subset of "undeclared". Guarded: no manifest -> no hits.
"""

from slopscore.imports import declared_deps, detect_undeclared_imports
from slopscore.signals import CodeFile, Document
from slopscore.triage import triage


def _pyproject(tmp_path, deps):
    body = ", ".join(f'"{d}"' for d in deps)
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nversion = "0"\ndependencies = [{body}]\n',
        encoding="utf-8",
    )


def test_declared_deps_parses_pyproject(tmp_path):
    _pyproject(tmp_path, ["requests>=2.0", "rich"])
    deps = declared_deps(str(tmp_path))
    assert "requests" in deps
    assert "rich" in deps


def test_undeclared_import_is_flagged(tmp_path):
    _pyproject(tmp_path, ["requests"])
    files = (CodeFile("app.py", "import os\nimport requests\nimport superjson\n"),)
    count, ev = detect_undeclared_imports(files, root=str(tmp_path))
    assert count == 1  # os=stdlib, requests=declared, superjson=hallucinated
    assert "superjson" in ev[0]
    assert ev[0].startswith("app.py:3:")


def test_stdlib_declared_and_local_imports_not_flagged(tmp_path):
    _pyproject(tmp_path, ["requests"])
    files = (
        CodeFile("pkg/app.py", "import os\nimport requests\nfrom pkg import util\nfrom . import helpers\n"),
        CodeFile("pkg/util.py", "x = 1\n"),
    )
    count, _ = detect_undeclared_imports(files, root=str(tmp_path))
    assert count == 0  # os stdlib, requests declared, pkg local, '.' relative


def test_no_manifest_means_no_hits(tmp_path):
    # Guard: without a manifest we cannot know what is declared, so never flag.
    files = (CodeFile("app.py", "import superjson\n"),)
    count, _ = detect_undeclared_imports(files, root=str(tmp_path))
    assert count == 0


def test_import_name_alias_not_flagged(tmp_path):
    _pyproject(tmp_path, ["PyYAML"])
    files = (CodeFile("app.py", "import yaml\n"),)
    count, _ = detect_undeclared_imports(files, root=str(tmp_path))
    assert count == 0  # yaml resolves to PyYAML via the alias map


def test_non_python_files_ignored(tmp_path):
    _pyproject(tmp_path, [])
    files = (CodeFile("notes.md", "import superjson\n"),)
    # no deps declared anyway -> guard; but also .md must never be parsed for imports
    assert detect_undeclared_imports(files, root=str(tmp_path))[0] == 0


def test_semicolon_compound_import_not_flagged(tmp_path):
    # `import os; import sys` must not be read as one token "os; import sys".
    _pyproject(tmp_path, ["requests"])
    files = (CodeFile("app.py", "import os; import sys\n"),)
    assert detect_undeclared_imports(files, root=str(tmp_path))[0] == 0


def test_backslash_continuation_not_emitted_as_module(tmp_path):
    _pyproject(tmp_path, ["requests"])
    files = (CodeFile("app.py", "import os, \\\n"),)
    count, ev = detect_undeclared_imports(files, root=str(tmp_path))
    assert all("\\" not in e for e in ev)
    assert count == 0


def test_egg_fragment_in_requirements_is_declared(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "git+https://example.com/x.git#egg=ypkg\n", encoding="utf-8"
    )
    files = (CodeFile("app.py", "import ypkg\n"),)
    assert detect_undeclared_imports(files, root=str(tmp_path))[0] == 0


def test_undeclared_import_via_triage_honours_root(tmp_path):
    # Drives the signal through the WIRED path (triage), with the manifest root
    # NOT the process CWD - the gap the review caught.
    _pyproject(tmp_path, ["requests"])
    doc = Document(files=(CodeFile("app.py", "import superjson\n"),))
    r = triage(doc, enabled=frozenset({"code_undeclared_import"}), root=str(tmp_path))
    assert "code_undeclared_import" in {h.name for h in r.hits}
