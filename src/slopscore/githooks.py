"""Git hook implementations and the hook installer.

The shell files in ``hooks/`` are thin shims that exec ``slopscore hook
commit-msg``/``pre-push``; all behaviour lives here so a pip-installed
package is self-contained (``slopscore install-hooks``). Hooks fail OPEN:
any internal error warns and allows the operation - a broken linter must
never block a commit.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys

from slopscore.config import Config, default_config, load_config
from slopscore.ingest import MAX_INPUT_CHARS, files_from_diff
from slopscore.signals import Document
from slopscore.triage import triage

_ZERO = "0" * 40
_OBJECT_ID = re.compile(r"[0-9a-f]{7,64}")  # git sha-1/sha-256 abbreviations

COMMIT_MSG_SHIM = """\
#!/bin/sh
# slopscore commit-msg shim - the logic lives in `slopscore hook commit-msg`.
# Install: `slopscore install-hooks` (writes this shim into .git/hooks; from a
# checkout). Bypass any time with `git commit --no-verify`.
if command -v slopscore >/dev/null 2>&1; then
  exec slopscore hook commit-msg "$1"
fi
# -P (isolated sys.path, Python 3.11+) is load-bearing: without it this would
# import a slopscore/ package from the repo being scored - code execution on
# commit in a hostile clone. On 3.10 the probe fails and the hook skips.
if command -v python3 >/dev/null 2>&1 && python3 -P -c "import slopscore" 2>/dev/null; then
  exec python3 -P -m slopscore.cli hook commit-msg "$1"
fi
exit 0  # slopscore not available - skip rather than block a commit
"""

PRE_PUSH_SHIM = """\
#!/bin/sh
# slopscore pre-push shim - the logic lives in `slopscore hook pre-push`.
# Install: `slopscore install-hooks` (writes this shim into .git/hooks; from a
# checkout). Bypass any time with `git push --no-verify`.
if command -v slopscore >/dev/null 2>&1; then
  exec slopscore hook pre-push "$@"
fi
# -P (isolated sys.path, Python 3.11+) is load-bearing: without it this would
# import a slopscore/ package from the repo being scored - code execution on
# push in a hostile clone. On 3.10 the probe fails and the hook skips.
if command -v python3 >/dev/null 2>&1 && python3 -P -c "import slopscore" 2>/dev/null; then
  exec python3 -P -m slopscore.cli hook pre-push "$@"
fi
exit 0  # slopscore not available - skip rather than block a push
"""

SHIMS = {"commit-msg": COMMIT_MSG_SHIM, "pre-push": PRE_PUSH_SHIM}


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def _git_config(key: str, type_flag: str | None = None) -> str:
    cmd = ["config"]
    if type_flag:
        cmd.append(f"--type={type_flag}")
    cmd += ["--get", key]
    result = _git(*cmd)
    return result.stdout.strip() if result.returncode == 0 else ""


class _Settings:
    """Per-repo hook settings from git config plus the SLOPSCORE_BLOCK env."""

    def __init__(self) -> None:
        self.block = _git_config("slopscore.block", "bool") == "true"
        env = os.environ.get("SLOPSCORE_BLOCK", "")
        if env == "1":
            self.block = True
        elif env == "0":
            self.block = False
        elif env:
            print(
                f"slopscore: SLOPSCORE_BLOCK must be 1 or 0 (got '{env}'); ignoring it.",
                file=sys.stderr,
            )
        self.threshold_raw = _git_config("slopscore.threshold")
        self.config = default_config()
        self.broken: str | None = None  # error text when settings are unusable
        config_path = _git_config("slopscore.config", "path")
        if config_path:
            if os.path.isfile(config_path):
                try:
                    with open(config_path, encoding="utf-8") as fh:
                        self.config = load_config(fh.read())
                except (OSError, ValueError) as exc:
                    self.broken = f"slopscore: invalid config: {exc}"
            else:
                print(
                    f"slopscore: git config slopscore.config points at "
                    f"'{config_path}' which does not exist; ignoring it.",
                    file=sys.stderr,
                )
        self.threshold = self.config.threshold
        if self.threshold_raw:
            try:
                self.threshold = float(self.threshold_raw)
            except ValueError:
                self.broken = (
                    f"slopscore: threshold must be a number 0-100 "
                    f"(got '{self.threshold_raw}')"
                )
            else:
                if not 0.0 <= self.threshold <= 100.0:
                    self.broken = (
                        f"slopscore: threshold must be between 0 and 100 "
                        f"(got {self.threshold})"
                    )

    @property
    def threshold_display(self) -> str:
        return self.threshold_raw or "30"


def _footer(settings: _Settings) -> None:
    """Config status footer so the knobs are discoverable from the report."""
    if sys.stdout.isatty():
        b, d, c, r = "\x1b[1m", "\x1b[2m", "\x1b[36m", "\x1b[0m"
    else:
        b = d = c = r = ""
    thr = settings.threshold_display
    print()
    if settings.block:
        print(f"{b}Blocking: ON{r}{d} - commits and pushes scoring {thr}+ are refused.{r}")
        print(f"{d}To turn off run:{r} {c}git config slopscore.block false{r}")
    else:
        print(f"{b}Blocking: off{r}{d} - commits and pushes only get this advisory.{r}")
        print(
            f"{d}To turn on run:{r} {c}git config slopscore.block true{r}"
            f"{d} (refuses at score {thr}+){r}"
        )
    print()


def _score(msg: str, diff: str, settings: _Settings, label: str | None, badge: str):
    cfg: Config = settings.config
    doc = Document(
        body=msg[:MAX_INPUT_CHARS], files=files_from_diff(diff[:MAX_INPUT_CHARS])
    )
    report = triage(
        doc, threshold=settings.threshold, enabled=cfg.enabled, weights=cfg.weights
    )
    text = report.to_text(color=sys.stdout.isatty(), label=label, badge=badge)
    return report, text


def commit_msg(args: list[str]) -> int:
    if not args:
        print("slopscore: hook commit-msg needs the message file path", file=sys.stderr)
        return 0
    settings = _Settings()
    if settings.broken:
        print(settings.broken, file=sys.stderr)
        print("slopscore: scoring failed (see above) - commit allowed.", file=sys.stderr)
        return 0
    try:
        with open(args[0], encoding="utf-8", errors="replace") as fh:
            msg = fh.read(MAX_INPUT_CHARS)
    except OSError as exc:
        print(f"slopscore: cannot read commit message: {exc}", file=sys.stderr)
        return 0
    diff = _git("diff", "--cached", "--diff-filter=ACMR").stdout
    report, text = _score(msg, diff, settings, None, "SLOPSCORE COMMIT CHECK")
    print(text)
    _footer(settings)
    if settings.block and report.verdict == "FLAG":
        print(
            "slopscore: score at/above threshold; commit blocked (slopscore.block). "
            "Use --no-verify to bypass.",
            file=sys.stderr,
        )
        return 1
    return 0


def _outgoing_pairs() -> list[tuple[str, str]]:
    """(local_sha, remote_sha) pairs from the pre-push stdin protocol, or from
    PRE_COMMIT_FROM_REF/TO_REF when run under the pre-commit framework
    (which consumes stdin itself)."""
    pairs = []
    if not sys.stdin.isatty():
        for line in sys.stdin.read().splitlines():
            parts = line.split()
            if len(parts) == 4:
                pairs.append((parts[1], parts[3]))
    if not pairs and os.environ.get("PRE_COMMIT_TO_REF"):
        local = _git("rev-parse", os.environ["PRE_COMMIT_TO_REF"]).stdout.strip()
        remote = _git(
            "rev-parse", os.environ.get("PRE_COMMIT_FROM_REF", _ZERO)
        ).stdout.strip()
        if local:
            pairs.append((local, remote or _ZERO))
    return pairs


def pre_push(args: list[str]) -> int:
    settings = _Settings()
    if settings.broken:
        print(settings.broken, file=sys.stderr)
        print("slopscore: scoring failed (see above) - push allowed.", file=sys.stderr)
        return 0
    flagged = 0
    scanned = 0
    for local_sha, remote_sha in _outgoing_pairs():
        if local_sha == _ZERO:
            continue  # ref delete - nothing outgoing
        if remote_sha == _ZERO:
            # New remote ref: score only what no remote has seen yet.
            rev_args = ["rev-list", local_sha, "--not", "--remotes"]
        else:
            rev_args = ["rev-list", f"{remote_sha}..{local_sha}"]
        for sha in _git(*rev_args).stdout.split():
            # Defence-in-depth: only ever interpolate a real object id into the
            # git calls below, so a future change can't let a dash-prefixed
            # token reach git as an option (review, security Low).
            if not _OBJECT_ID.fullmatch(sha):
                continue
            scanned += 1
            msg = _git("log", "-1", "--format=%B", sha).stdout
            # First-parent diff so a merge scores what it introduced.
            diff = _git(
                "show", sha, "--diff-merges=first-parent", "--diff-filter=ACMR",
                "--format=",
            ).stdout
            label = _git("log", "-1", "--format=[%h] %s", sha).stdout.strip()
            report, text = _score(msg, diff, settings, label, "SLOPSCORE PUSH CHECK")
            if report.verdict == "FLAG":
                flagged += 1
                print(text)
    if flagged:
        print(f"slopscore: {flagged} of {scanned} outgoing commits at/above threshold.")
        _footer(settings)
        if settings.block:
            print(
                "slopscore: push blocked (slopscore.block). Use --no-verify to bypass.",
                file=sys.stderr,
            )
            return 1
    return 0


def install_hooks() -> int:
    hook_dir = _git("rev-parse", "--git-path", "hooks").stdout.strip()
    if not hook_dir:
        print("slopscore: not inside a git repository", file=sys.stderr)
        return 1
    os.makedirs(hook_dir, exist_ok=True)
    installed = []
    for name, shim in SHIMS.items():
        dst = os.path.join(hook_dir, name)
        if os.path.exists(dst):
            with open(dst, encoding="utf-8", errors="replace") as fh:
                if "slopscore" not in fh.read():
                    print(
                        f"Skipped {name}: a non-slopscore hook already exists at "
                        f"{dst} (remove it and re-run to replace).",
                        file=sys.stderr,
                    )
                    continue
            os.remove(dst)  # never write through a pre-existing symlink
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write(shim)
        os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        installed.append(name)
    if not installed:
        return 1
    print(f"Installed slopscore hooks ({', '.join(installed)}) -> {hook_dir}")
    print(
        "Advisory by default (never blocks). Opt in: git config slopscore.block true; "
        "set the bar with git config slopscore.threshold 50. "
        "SLOPSCORE_BLOCK=1/0 overrides; --no-verify bypasses."
    )
    print(
        "Config: slopscore.toml in the repo root (threshold, signals, weights) - "
        "see the README."
    )
    return 0


def hook_main(args: list[str]) -> int:
    """Dispatch for `slopscore hook <name> ...`. Fails OPEN on any crash."""
    try:
        if args and args[0] == "commit-msg":
            return commit_msg(args[1:])
        if args and args[0] == "pre-push":
            return pre_push(args[1:])
        print(
            "slopscore: unknown hook (expected commit-msg or pre-push)", file=sys.stderr
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - a broken linter must not block
        print(
            f"slopscore: internal hook error: {exc} - operation allowed.",
            file=sys.stderr,
        )
        return 0
