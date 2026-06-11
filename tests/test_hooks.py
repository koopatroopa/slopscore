"""Functional tests for the git hooks (commit-msg + pre-push) and their installer.

Each test builds a throwaway git repo (and a bare remote for push tests),
installs the hooks with the real installer script, and drives real git
commands. PATH is pinned to the project venv so the hooks exercise the
working-tree code, not any globally installed slopscore.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
VENV_BIN = ROOT / ".venv" / "bin"
INSTALLER = ROOT / "tools" / "install-git-hook.sh"
# Prefer the project venv (dev: guarantees working-tree code); fall back to a
# PATH install (CI: pip install . IS the working-tree code there).
SLOPSCORE_BIN = (
    VENV_BIN / "slopscore"
    if (VENV_BIN / "slopscore").exists()
    else shutil.which("slopscore")
)

# A sloppy commit is sloppy in BOTH message and staged code: the input-aware
# ceiling (D-09) includes code signals whenever a code diff is present, so a
# sloppy message over a clean one-line change scores LOW by construction.
# Together these score 47.1 on the default config (ai_self_reference +
# sycophantic_openers + code_placeholder_stub): at/above the default threshold
# (30) but below the 90 used in the threshold tests.
SLOPPY_MSG = (
    "Certainly! Here is the commit you requested.\n\n"
    "This delves into the robust refactor.\n\n"
    "Generated with Claude Code\n"
    "Co-Authored-By: Claude <noreply@anthropic.com>\n"
)
SLOPPY_CODE = "def handler():\n    pass  # ... rest of the code unchanged\n"
CLEAN_MSG = "Fix the widget parser"

pytestmark = pytest.mark.skipif(
    SLOPSCORE_BIN is None, reason="no slopscore binary (venv or PATH)"
)


def hook_env(tmp_path, **extra):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        "PATH": f"{Path(SLOPSCORE_BIN).parent}:{os.environ['PATH']}",
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    env.update(extra)
    return env


def git(repo, *args, env, check=True, **kwargs):
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
        **kwargs,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    env = hook_env(tmp_path)
    git(repo, "init", "-q", env=env)
    git(repo, "config", "user.name", "Test", env=env)
    git(repo, "config", "user.email", "test@example.com", env=env)
    (repo / "README").write_text("seed\n")
    git(repo, "add", "README", env=env)
    git(repo, "commit", "-q", "-m", "Seed", env=env)
    install = subprocess.run(
        [str(INSTALLER)], cwd=repo, capture_output=True, text=True, env=env
    )
    assert install.returncode == 0, install.stderr
    return repo, env


def commit(repo, env, msg, block_env=None):
    """Stage a file change (sloppy code for a sloppy message) and commit."""
    filename = "f.py" if msg == SLOPPY_MSG else "f.txt"
    path = repo / filename
    content = SLOPPY_CODE if msg == SLOPPY_MSG else "x\n"
    path.write_text(path.read_text() + content if path.exists() else content)
    git(repo, "add", filename, env=env)
    commit_env = dict(env)
    if block_env is not None:
        commit_env["SLOPSCORE_BLOCK"] = block_env
    return git(repo, "commit", "-m", msg, env=commit_env, check=False)


def make_repo_with_remote(tmp_path):
    repo, env = make_repo(tmp_path)
    bare = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "-q", "--bare", str(bare)],
        capture_output=True,
        env=env,
        check=True,
    )
    git(repo, "remote", "add", "origin", str(bare), env=env)
    git(repo, "push", "-q", "origin", "HEAD", env=env)
    return repo, env


def push(repo, env, *extra):
    return git(repo, "push", *extra, "origin", "HEAD", env=env, check=False)


class TestCommitMsgHook:
    def test_advisory_by_default(self, tmp_path):
        repo, env = make_repo(tmp_path)
        result = commit(repo, env, SLOPPY_MSG)
        assert result.returncode == 0
        out = result.stdout + result.stderr
        assert "verdict FLAG" in out
        # The config footer makes the blocking knob discoverable.
        assert "git config slopscore.block true" in out

    def test_git_config_block_blocks_sloppy(self, tmp_path):
        repo, env = make_repo(tmp_path)
        git(repo, "config", "slopscore.block", "true", env=env)
        result = commit(repo, env, SLOPPY_MSG)
        assert result.returncode != 0
        assert "commit blocked" in result.stderr
        assert "Blocking: ON" in result.stdout + result.stderr

    def test_git_config_block_allows_clean(self, tmp_path):
        repo, env = make_repo(tmp_path)
        git(repo, "config", "slopscore.block", "true", env=env)
        result = commit(repo, env, CLEAN_MSG)
        assert result.returncode == 0

    def test_git_config_threshold_raises_the_bar(self, tmp_path):
        repo, env = make_repo(tmp_path)
        git(repo, "config", "slopscore.block", "true", env=env)
        git(repo, "config", "slopscore.threshold", "90", env=env)
        result = commit(repo, env, SLOPPY_MSG)  # scores 47.1, below the 90 bar
        assert result.returncode == 0

    def test_env_zero_overrides_git_config_block(self, tmp_path):
        repo, env = make_repo(tmp_path)
        git(repo, "config", "slopscore.block", "true", env=env)
        result = commit(repo, env, SLOPPY_MSG, block_env="0")
        assert result.returncode == 0

    def test_env_one_blocks_without_git_config(self, tmp_path):
        repo, env = make_repo(tmp_path)
        result = commit(repo, env, SLOPPY_MSG, block_env="1")
        assert result.returncode != 0

    def test_invalid_threshold_warns_and_allows(self, tmp_path):
        repo, env = make_repo(tmp_path)
        git(repo, "config", "slopscore.block", "true", env=env)
        git(repo, "config", "slopscore.threshold", "banana", env=env)
        result = commit(repo, env, SLOPPY_MSG)
        assert result.returncode == 0
        assert "scoring failed" in result.stderr


class TestPrePushHook:
    def test_advisory_by_default(self, tmp_path):
        repo, env = make_repo_with_remote(tmp_path)
        commit(repo, env, SLOPPY_MSG)
        result = push(repo, env)
        out = result.stdout + result.stderr
        assert result.returncode == 0
        assert "1 of 1 outgoing commits at/above threshold" in out

    def test_clean_push_is_silent(self, tmp_path):
        repo, env = make_repo_with_remote(tmp_path)
        commit(repo, env, CLEAN_MSG)
        result = push(repo, env)
        assert result.returncode == 0
        assert "slopscore" not in result.stdout + result.stderr

    def test_git_config_block_blocks_sloppy_push(self, tmp_path):
        repo, env = make_repo_with_remote(tmp_path)
        commit(repo, env, CLEAN_MSG)
        commit(repo, env, SLOPPY_MSG)
        # Enable blocking only now: set earlier it would block the commit
        # above and the push would have nothing sloppy to refuse.
        git(repo, "config", "slopscore.block", "true", env=env)
        result = push(repo, env)
        out = result.stdout + result.stderr
        assert result.returncode != 0
        assert "1 of 2 outgoing commits at/above threshold" in out
        assert "push blocked" in result.stderr

    def test_no_verify_bypasses_block(self, tmp_path):
        repo, env = make_repo_with_remote(tmp_path)
        commit(repo, env, SLOPPY_MSG)
        git(repo, "config", "slopscore.block", "true", env=env)
        assert push(repo, env).returncode != 0
        assert push(repo, env, "--no-verify").returncode == 0

    def test_git_config_threshold_raises_the_bar(self, tmp_path):
        repo, env = make_repo_with_remote(tmp_path)
        git(repo, "config", "slopscore.block", "true", env=env)
        git(repo, "config", "slopscore.threshold", "90", env=env)
        commit(repo, env, SLOPPY_MSG)  # scores 47.1, below the 90 bar
        assert push(repo, env).returncode == 0


class TestInstaller:
    def test_installs_both_hooks(self, tmp_path):
        repo, env = make_repo(tmp_path)
        for hook in ("commit-msg", "pre-push"):
            installed = repo / ".git" / "hooks" / hook
            assert installed.exists()
            assert os.access(installed, os.X_OK)
            assert "slopscore" in installed.read_text()

    def test_skips_foreign_hook(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        env = hook_env(tmp_path)
        git(repo, "init", "-q", env=env)
        foreign = repo / ".git" / "hooks" / "pre-push"
        foreign.parent.mkdir(parents=True, exist_ok=True)
        foreign.write_text("#!/bin/sh\n# someone else's hook\n")
        result = subprocess.run(
            [str(INSTALLER)], cwd=repo, capture_output=True, text=True, env=env
        )
        assert result.returncode == 0
        assert "Skipped pre-push" in result.stderr
        assert foreign.read_text() == "#!/bin/sh\n# someone else's hook\n"
        assert "slopscore" in (repo / ".git" / "hooks" / "commit-msg").read_text()


def test_sloppy_fixture_score_within_assumed_window(tmp_path):
    """Recalibration canary: the threshold tests above assume the sloppy
    fixture lands in [30, 90). If a weights change moves it, this fails
    self-describingly instead of a threshold test three hops away."""
    import re

    msg = tmp_path / "msg.txt"
    msg.write_text(SLOPPY_MSG)
    diff = "--- /dev/null\n+++ b/f.py\n@@ -0,0 +1,2 @@\n" + "".join(
        "+" + line + "\n" for line in SLOPPY_CODE.splitlines()
    )
    result = subprocess.run(
        [str(SLOPSCORE_BIN), "--text", str(msg), "--diff", "-"],
        input=diff,
        capture_output=True,
        text=True,
    )
    match = re.search(r"Slop score (\d+(?:\.\d+)?)", result.stdout)
    assert match, result.stdout
    assert 30 <= float(match.group(1)) < 90


class TestHookEdges:
    def test_new_branch_scores_only_unseen_commits(self, tmp_path):
        repo, env = make_repo_with_remote(tmp_path)
        commit(repo, env, CLEAN_MSG)
        push(repo, env)
        git(repo, "checkout", "-q", "-b", "feature", env=env)
        commit(repo, env, SLOPPY_MSG)
        result = push(repo, env)
        out = result.stdout + result.stderr
        assert result.returncode == 0
        # Only the one commit unseen by the remote is scanned, not history.
        assert "1 of 1 outgoing commits at/above threshold" in out

    def test_renamed_file_edits_are_scored(self, tmp_path):
        repo, env = make_repo(tmp_path)
        body = "".join(f"def fn{i}():\n    return {i}\n\n" for i in range(8))
        (repo / "f.py").write_text(body)
        git(repo, "add", "f.py", env=env)
        git(repo, "commit", "-q", "-m", CLEAN_MSG, env=env)
        # Rename plus a small sloppy edit: stages as status R, which
        # --diff-filter=ACM used to drop entirely.
        git(repo, "mv", "f.py", "g.py", env=env)
        (repo / "g.py").write_text(body + SLOPPY_CODE)
        git(repo, "add", "g.py", env=env)
        result = git(repo, "commit", "-m", CLEAN_MSG, env=env, check=False)
        assert result.returncode == 0
        assert "code_placeholder_stub" in result.stdout + result.stderr

    def test_env_unexpected_value_warns_and_ignores(self, tmp_path):
        repo, env = make_repo(tmp_path)
        result = commit(repo, env, SLOPPY_MSG, block_env="true")
        assert result.returncode == 0
        assert "must be 1 or 0" in result.stderr


class TestHookConfig:
    def test_git_config_config_file_toggles_signals(self, tmp_path):
        repo, env = make_repo(tmp_path)
        (repo / "lenient.toml").write_text(
            "[signals]\nai_self_reference = false\nsycophantic_openers = false\n"
            "ai_cliche_phrases = false\ncode_placeholder_stub = false\n"
            "em_dash_density = false\nemoji_density = false\n"
        )
        git(repo, "config", "slopscore.block", "true", env=env)
        git(repo, "config", "slopscore.config", "lenient.toml", env=env)
        # Everything the sloppy fixture trips is disabled, so blocking-on
        # must still allow it: the config file reached the CLI.
        result = commit(repo, env, SLOPPY_MSG)
        assert result.returncode == 0, result.stderr

    def test_missing_config_file_warns_and_continues(self, tmp_path):
        repo, env = make_repo(tmp_path)
        git(repo, "config", "slopscore.config", "nope.toml", env=env)
        result = commit(repo, env, CLEAN_MSG)
        assert result.returncode == 0
        assert "does not exist" in result.stderr
