"""Functional tests for the Claude Code plugin (post-commit advisory hook).

The plugin lives in plugin/ and is published via the root marketplace
manifest (`/plugin marketplace add koopatroopa/slopscore`). Its PostToolUse
hook fires after Bash tool calls: when the command was a git commit, it
scores HEAD's message with the slopscore CLI and - only on a FLAG - exits 2
with the report on stderr, which Claude Code feeds back to the agent so it
can amend. Clean commits and non-commit commands stay silent.
"""

import json
import subprocess
from pathlib import Path

import pytest

from tests.test_hooks import SLOPSCORE_BIN, SLOPPY_MSG, CLEAN_MSG, git, hook_env

pytestmark = pytest.mark.skipif(
    SLOPSCORE_BIN is None, reason="no slopscore binary (venv or PATH)"
)

ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
PLUGIN = ROOT / "plugin"
MANIFEST = PLUGIN / ".claude-plugin" / "plugin.json"
HOOKS = PLUGIN / "hooks" / "hooks.json"
HOOK_CMD = "slopscore hook claude-commit"


def test_marketplace_and_manifest_agree():
    market = json.loads(MARKETPLACE.read_text())
    manifest = json.loads(MANIFEST.read_text())
    entry = next(p for p in market["plugins"] if p["name"] == "slopscore")
    assert entry["source"] == "./plugin"
    assert manifest["name"] == "slopscore"
    for field in ("description", "version", "author"):
        assert manifest.get(field), field


def test_hooks_config_invokes_the_cli_directly():
    # No shell wrapper: the pip entry point IS the hook, so the same config
    # works on macOS, Linux and native Windows (no bash, no python3 naming).
    config = json.loads(HOOKS.read_text())
    post = config["hooks"]["PostToolUse"]
    assert post[0]["matcher"] == "^Bash$"
    assert post[0]["hooks"][0]["command"] == HOOK_CMD


def _repo_with_commit(tmp_path, message):
    repo = tmp_path / "repo"
    repo.mkdir()
    env = hook_env(tmp_path)
    git(repo, "init", "-q", env=env)
    git(repo, "config", "user.email", "t@example.com", env=env)
    git(repo, "config", "user.name", "T", env=env)
    (repo / "f.txt").write_text("content\n")
    git(repo, "add", ".", env=env)
    git(repo, "commit", "-q", "-m", message, env=env)
    return repo, env


def _run_hook(repo, env, command, payload=None):
    payload = payload or json.dumps({"tool_input": {"command": command}})
    return subprocess.run(
        [str(SLOPSCORE_BIN), "hook", "claude-commit"], input=payload, cwd=repo,
        env=env, capture_output=True, text=True, timeout=30,
    )


def test_sloppy_commit_feeds_report_back(tmp_path):
    repo, env = _repo_with_commit(tmp_path, SLOPPY_MSG)
    result = _run_hook(repo, env, 'git commit -m "whatever"')
    assert result.returncode == 2, result.stderr
    assert "Slop score" in result.stderr
    assert "FLAG" in result.stderr
    # The report carries its own behavioural contract: evidence goes to the
    # USER, who decides what gets cleaned - the agent must not self-amend.
    assert "let them decide" in result.stderr
    assert "Do not amend without their go-ahead" in result.stderr


def test_clean_commit_stays_silent(tmp_path):
    repo, env = _repo_with_commit(tmp_path, CLEAN_MSG)
    result = _run_hook(repo, env, "git commit -m 'Fix the widget parser'")
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == ""


def test_non_commit_command_ignored(tmp_path):
    repo, env = _repo_with_commit(tmp_path, SLOPPY_MSG)
    result = _run_hook(repo, env, "ls -la")
    assert result.returncode == 0
    assert result.stderr.strip() == ""


def test_outside_git_repo_is_quietly_skipped(tmp_path):
    bare = tmp_path / "notarepo"
    bare.mkdir()
    env = hook_env(tmp_path)
    result = subprocess.run(
        [str(SLOPSCORE_BIN), "hook", "claude-commit"],
        input=json.dumps({"tool_input": {"command": "git commit -m x"}}),
        cwd=bare, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0


def test_missing_binary_is_nonblocking_by_contract():
    # With no wrapper script there is nothing of ours to run when the CLI is
    # absent: Claude Code reports command-not-found, and a non-2 exit on
    # PostToolUse is non-blocking by the hooks contract. The prerequisite is
    # stated in the plugin description and README instead.
    manifest = json.loads(MANIFEST.read_text())
    assert "uv tool install slopscore" in manifest["description"]


def test_clean_command_ships_with_the_loop():
    command = (PLUGIN / "commands" / "clean.md").read_text()
    assert command.startswith("---\ndescription:")
    # The loop's safety rails must survive edits: never rewrite clean work,
    # never amend pushed commits, never force a PASS over repo policy.
    for rail in ("do not rewrite clean work", "NEVER amend", "REQUIRES"):
        assert rail in command, rail


def test_failed_or_mentioned_commit_does_not_score_stale_head(tmp_path):
    # A commit that FAILED (or a command merely mentioning git commit)
    # leaves an old HEAD; flagging it would tell the agent to amend work it
    # does not own. The recency gate keeps the hook silent.
    repo, env = _repo_with_commit(tmp_path, SLOPPY_MSG)
    old = "2020-01-01T00:00:00 +0000"
    git(repo, "commit", "--amend", "-q", "--no-edit", env=env | {
        "GIT_COMMITTER_DATE": old, "GIT_AUTHOR_DATE": old})
    result = _run_hook(repo, env, "git commit -m x")
    assert result.returncode == 0
    assert result.stderr.strip() == ""


def test_malformed_stdin_fails_open(tmp_path):
    repo, env = _repo_with_commit(tmp_path, SLOPPY_MSG)
    result = _run_hook(repo, env, "", payload="not json at all")
    assert result.returncode == 0


def test_repo_threshold_config_is_honoured(tmp_path):
    # The repo relaxed its own gate; the plugin must agree with the git
    # hooks, not re-impose the default threshold (the unwinnable-loop bug).
    repo, env = _repo_with_commit(tmp_path, SLOPPY_MSG)
    git(repo, "config", "slopscore.threshold", "99", env=env)
    result = _run_hook(repo, env, "git commit -m x")
    assert result.returncode == 0, result.stderr


def test_hook_follows_the_tools_cwd(tmp_path):
    # The Bash tool payload carries its own cwd; the hook must score THAT
    # repo, not wherever the hook process happens to start.
    repo, env = _repo_with_commit(tmp_path, SLOPPY_MSG)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    payload = json.dumps(
        {"tool_input": {"command": "git commit -m x"}, "cwd": str(repo)})
    result = subprocess.run(
        [str(SLOPSCORE_BIN), "hook", "claude-commit"], input=payload,
        cwd=elsewhere, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 2, result.stderr
    assert "Slop score" in result.stderr


def _session_start_command():
    config = json.loads(HOOKS.read_text())
    return config["hooks"]["SessionStart"][0]["hooks"][0]["command"]


def test_session_start_hint_fires_only_when_cli_missing(tmp_path):
    # SessionStart stdout lands in Claude's context, so the hint is written
    # as instructions TO Claude: it offers the install (and the git hooks)
    # itself. Silent when the CLI is present - zero noise on the happy path.
    cmd = _session_start_command()
    env = hook_env(tmp_path)
    present = subprocess.run(["bash", "-c", cmd], env=env,
                             capture_output=True, text=True, timeout=30)
    assert present.returncode == 0
    assert present.stdout.strip() == ""
    env["PATH"] = "/usr/bin:/bin"
    missing = subprocess.run(["bash", "-c", cmd], env=env,
                             capture_output=True, text=True, timeout=30)
    assert missing.returncode == 0
    assert "uv tool install slopscore" in missing.stdout
    assert "install-hooks" in missing.stdout


def test_hook_accepts_both_payload_field_namings(tmp_path):
    # The live /hooks panel documents the payload as {"inputs": ...} while
    # the hooks docs say {"tool_input": ...}; the first install attempt
    # silently no-opped on the live shape. Both must score.
    repo, env = _repo_with_commit(tmp_path, SLOPPY_MSG)
    for field in ("tool_input", "inputs"):
        payload = json.dumps({field: {"command": "git commit -m x"}})
        result = _run_hook(repo, env, "", payload=payload)
        assert result.returncode == 2, (field, result.stderr)


def test_matcher_catches_git_dash_c_form(tmp_path):
    # An agent working from outside the repo runs `git -C <path> commit` -
    # the form that silently no-opped on the first live install. The hook
    # must both match it and score the repo -C points at.
    repo, env = _repo_with_commit(tmp_path, SLOPPY_MSG)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    payload = json.dumps({
        "tool_input": {"command": f"git -C {repo} commit --amend --no-edit"},
        "cwd": str(elsewhere),
    })
    result = subprocess.run(
        [str(SLOPSCORE_BIN), "hook", "claude-commit"], input=payload,
        cwd=elsewhere, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 2, result.stderr
    assert "Slop score" in result.stderr


def test_matcher_variants(tmp_path):
    repo, env = _repo_with_commit(tmp_path, SLOPPY_MSG)
    fires = [
        "git commit -m x",
        "git -c user.name=t commit",
        "cd somewhere && git commit --amend",
    ]
    silent = ["git log --grep commit", "git status", "echo hello"]
    for cmd in fires:
        assert _run_hook(repo, env, cmd).returncode == 2, cmd
    for cmd in silent:
        assert _run_hook(repo, env, cmd).returncode == 0, cmd
