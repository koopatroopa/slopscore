"""Ingest code to scan: working-tree files (go wide) or a unified diff.

Two ways in. ``files_from_paths`` reads whole files - the CLI self-check path,
where you point slopscore at your working tree. ``files_from_diff`` extracts the
added lines per file from a unified diff - the Action / git-hook path, where the
new code is what the author is responsible for.
"""

from __future__ import annotations

from slopscore.signals import CodeFile

# Cap any single read so a multi-MB file or body cannot exhaust the scanner
# (resource-exhaustion guard, especially the Action path on a hostile PR).
MAX_INPUT_CHARS = 1_000_000


def files_from_paths(paths: list[str]) -> tuple[CodeFile, ...]:
    """Read each path as a CodeFile. Best-effort: an unreadable path is skipped,
    not fatal (a self-check should not abort because one file moved)."""
    out: list[CodeFile] = []
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                out.append(CodeFile(path=path, content=fh.read(MAX_INPUT_CHARS)))
        except OSError:
            continue
    return tuple(out)


def files_from_diff(text: str) -> tuple[CodeFile, ...]:
    """Extract the added (+) lines per file from a unified diff. Removed and
    context lines are ignored - only new code is scored."""
    added: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            current = None if path == "/dev/null" else path
            if current is not None:
                added.setdefault(current, [])
        elif current is not None and line.startswith("+") and not line.startswith("+++"):
            added[current].append(line[1:])
    return tuple(CodeFile(path=p, content="\n".join(lines)) for p, lines in added.items() if lines)
