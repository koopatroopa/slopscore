"""Command-line entry point for slopscore.

Reads a PR/issue document (JSON ``{title, body, commits[]}`` or, with --text,
raw body text), runs the triage engine, and prints the report. The exit code
doubles as a CI / git-hook gate:

    0  below threshold (PASS)
    1  at or above threshold (FLAG)
    2  usage or input error

Self-facing by design: it reports on your OWN text, it never accuses anyone.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from slopscore.config import default_config, load_config
from slopscore.ingest import MAX_INPUT_CHARS, files_from_diff, files_from_paths
from slopscore.signals import CodeFile, Document
from slopscore.triage import DEFAULT_THRESHOLD, triage


def _document_from_json(raw: str, files: tuple[CodeFile, ...] = ()) -> Document:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object with title/body/commits")
    title = data.get("title", "")
    body = data.get("body", "")
    commits = data.get("commits", [])
    # Validate rather than str()-coerce: a dict/number smuggled into a field
    # would silently poison the scored text and PASS a malformed input.
    if not isinstance(title, str) or not isinstance(body, str):
        raise ValueError("'title' and 'body' must be strings")
    if not isinstance(commits, list) or not all(isinstance(c, str) for c in commits):
        raise ValueError("'commits' must be a list of strings")
    return Document(
        title=title, body=body, commits=tuple(commits), files=files, structured=True
    )


def _read_input(path: str | None) -> str:
    # Capped read: a multi-MB body must not exhaust the scanner. Decode with
    # errors="replace": a stray non-UTF-8 byte (legacy latin-1 file in a diff)
    # must degrade to a replacement character, never raise - an unhandled
    # decode error exits 1, which the hooks read as FLAG (false accusation).
    if path and path != "-":
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(MAX_INPUT_CHARS)
    return sys.stdin.buffer.read(MAX_INPUT_CHARS).decode("utf-8", errors="replace")


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("slopscore")
    except PackageNotFoundError:  # running from a bare checkout
        return "0.0.0-dev"


def _use_color(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    # auto: a real terminal, and the user hasn't asked for no colour
    # (https://no-color.org - any non-empty value disables).
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slopscore",
        description="Score your own commit, PR or text for AI residue and\n"
        "low-craft slop (0-100, itemised findings). Self-facing: it checks\n"
        "your work, never someone else's.",
        epilog=(
            "examples:\n"
            "  slopscore pr.json                     score a PR described as JSON\n"
            "  echo 'Certainly!' | slopscore --text -    score raw text from stdin\n"
            "  slopscore --text msg.txt --diff changes.diff\n"
            "                                        score a message plus a diff's added lines\n"
            "  slopscore --files src/*.py            scan code files for leftovers\n"
            "\n"
            "exit codes: 0 pass, 1 flag (score at/above threshold), 2 usage error.\n"
            "\n"
            "subcommands:\n"
            "  slopscore install-hooks               install the commit-msg + pre-push hooks here\n"
            "  slopscore hook commit-msg|pre-push    what those installed hooks invoke\n"
            "\n"
            "The score, bands and signals are explained in the README."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="input file (JSON, or text with --text); '-' or omitted reads stdin",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="treat the input as raw body text rather than JSON",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="emit a machine-readable JSON report",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help=f"0-100 slop score at/above which the verdict is FLAG "
        f"(default {DEFAULT_THRESHOLD}, or the config's value)",
    )
    parser.add_argument(
        "--config",
        help="path to a TOML config file (per-signal on/off, weight overrides, threshold)",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        metavar="PATH",
        help="code files to scan whole (go wide on your working tree)",
    )
    parser.add_argument(
        "--diff",
        metavar="PATH",
        help="read a unified diff and scan its added lines only; '-' for stdin",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"slopscore {_version()}",
    )
    parser.add_argument(
        "--label",
        help="context shown in the report header (e.g. a commit hash and subject)",
    )
    parser.add_argument(
        "--badge",
        help="wordmark text in the report header (default: SLOPSCORE SLOP REPORT)",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="colour the report (auto: only when stdout is a terminal; "
        "the NO_COLOR convention is respected)",
    )
    parser.add_argument(
        "--root",
        metavar="DIR",
        help="project root for manifest/import resolution (default: current directory)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # Exit-code contract: 0 PASS, 1 FLAG, 2 anything else. A crash must come
    # out as 2, not 1 - the hooks treat 1 as a verdict and would block on it.
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "hook":
        from slopscore.githooks import hook_main

        return hook_main(args[1:])
    if args and args[0] == "install-hooks":
        from slopscore.githooks import install_hooks

        return install_hooks()
    try:
        return _main(argv)
    except Exception as exc:  # noqa: BLE001
        print(f"slopscore: internal error: {exc}", file=sys.stderr)
        return 2


def _main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.config:
        try:
            with open(args.config, encoding="utf-8") as fh:
                config = load_config(fh.read())
        except OSError as exc:
            print(f"slopscore: cannot read config: {exc}", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(f"slopscore: invalid config: {exc}", file=sys.stderr)
            return 2
    else:
        config = default_config()

    threshold = args.threshold if args.threshold is not None else config.threshold
    if not 0.0 <= threshold <= 100.0:
        print(
            f"slopscore: threshold must be between 0 and 100 (got {threshold})",
            file=sys.stderr,
        )
        return 2

    files: tuple[CodeFile, ...] = ()
    if args.files:
        files += files_from_paths(args.files)
    if args.diff:
        try:
            files += files_from_diff(_read_input(args.diff))
        except OSError as exc:
            print(f"slopscore: cannot read diff: {exc}", file=sys.stderr)
            return 2

    # Read prose input unless this is a code-only run (--files/--diff given, no
    # positional path): then there is no prose to wait on stdin for.
    code_only = bool(args.files or args.diff) and not args.path
    if not code_only and not args.path and sys.stdin.isatty():
        # A bare `slopscore` on a terminal would silently block on stdin -
        # exactly a new user's first command. Greet instead.
        print(
            "slopscore - lint your own slop before you ship it.\n"
            "\n"
            "Watch every commit and push (recommended - run inside each repo):\n"
            "  slopscore install-hooks\n"
            "\n"
            "Or score something now:\n"
            '  echo "Certainly! ..." | slopscore --text -\n'
            "  slopscore pr.json\n"
            "\n"
            "Full options: slopscore --help"
        )
        return 0
    if not code_only:
        try:
            raw = _read_input(args.path)
        except OSError as exc:
            print(f"slopscore: cannot read input: {exc}", file=sys.stderr)
            return 2
        try:
            doc = (
                Document(body=raw, files=files)
                if args.text
                else _document_from_json(raw, files)
            )
        except (ValueError, json.JSONDecodeError) as exc:
            hint = ""
            if not args.text and not raw.lstrip().startswith(("{", "[")):
                hint = " - input is not JSON; did you mean --text?"
            print(f"slopscore: invalid input: {exc}{hint}", file=sys.stderr)
            return 2
    else:
        doc = Document(files=files)

    report = triage(
        doc,
        threshold=threshold,
        enabled=config.enabled,
        weights=config.weights,
        root=args.root or ".",
    )
    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(
            report.to_text(
                color=_use_color(args.color), label=args.label, badge=args.badge
            )
        )
    return 1 if report.verdict == "FLAG" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
