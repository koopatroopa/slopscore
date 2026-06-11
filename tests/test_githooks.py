"""Unit spec for the in-package hook logic (slopscore.githooks).

The end-to-end behaviour (real git commits/pushes through the shims) is
covered by tests/test_hooks.py; this file pins what that suite cannot:
shim/checkout sync, the installer internals, and fail-open dispatch.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_shims_match_the_checkout_hook_files():
    # hooks/ in the checkout and the shims the installer writes must be the
    # same bytes, or pip installs and checkout installs drift apart.
    from slopscore.githooks import SHIMS

    for name, shim in SHIMS.items():
        assert (ROOT / "hooks" / name).read_text(encoding="utf-8") == shim, name


def _repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    monkeypatch.chdir(repo)
    return repo


def test_install_hooks_writes_executable_shims(tmp_path, monkeypatch, capsys):
    from slopscore.githooks import install_hooks

    repo = _repo(tmp_path, monkeypatch)
    assert install_hooks() == 0
    for name in ("commit-msg", "pre-push"):
        hook = repo / ".git" / "hooks" / name
        assert hook.exists() and os.access(hook, os.X_OK)
        assert "slopscore" in hook.read_text(encoding="utf-8")
    assert "Installed slopscore hooks" in capsys.readouterr().out


def test_install_hooks_skips_foreign_hook(tmp_path, monkeypatch, capsys):
    from slopscore.githooks import install_hooks

    repo = _repo(tmp_path, monkeypatch)
    foreign = repo / ".git" / "hooks" / "pre-push"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_text("#!/bin/sh\n# someone else's hook\n")
    assert install_hooks() == 0  # commit-msg still installs
    assert foreign.read_text() == "#!/bin/sh\n# someone else's hook\n"
    assert "Skipped pre-push" in capsys.readouterr().err


def test_hook_main_fails_open_on_unknown_hook(capsys):
    from slopscore.githooks import hook_main

    assert hook_main(["post-merge"]) == 0
    assert "unknown hook" in capsys.readouterr().err


def test_hook_main_fails_open_on_crash(monkeypatch, capsys):
    import slopscore.githooks as gh

    monkeypatch.setattr(gh, "commit_msg", lambda args: 1 / 0)
    assert gh.hook_main(["commit-msg"]) == 0
    assert "internal hook error" in capsys.readouterr().err
