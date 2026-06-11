"""Detect undeclared / unresolvable imports - hallucinated AI packages are the
high-value subset.

Deterministic and static: an import's top-level module is resolved against the
standard library, the project manifest's declared dependencies, and the local
modules being scanned. It reads the manifest, NEVER the installed environment
(so the same input scores the same anywhere - at a fixed Python version, since
the stdlib name set is version-pinned) and NEVER imports or installs the
package under test (it only parses import lines with a regex, which is also why
it works on diff fragments). Guard: with no manifest it cannot know what is
declared, so it returns nothing rather than false-flag every third-party import.

Default-off (D-10): the import-name vs distribution-name mismatch (import yaml
from the PyYAML distribution) is a real false-positive source the alias map only
partly covers, so this is opt-in.
"""

from __future__ import annotations

import os
import re
import sys
import tomllib

_STDLIB = frozenset(sys.stdlib_module_names)

_IMPORT_LINE = re.compile(r"^\s*(?:from\s+([.\w]+)\s+import\b|import\s+(.+))")

# import-name -> distribution-name, for the common mismatches.
_ALIASES = {
    "yaml": "pyyaml",
    "cv2": "opencv_python",
    "pil": "pillow",
    "sklearn": "scikit_learn",
    "bs4": "beautifulsoup4",
    "dateutil": "python_dateutil",
    "dotenv": "python_dotenv",
    "jwt": "pyjwt",
    "serial": "pyserial",
    "openssl": "pyopenssl",
    "git": "gitpython",
    "attr": "attrs",
}

_EVIDENCE_LIMIT = 5


def _norm(name: str) -> str:
    return name.lower().replace("-", "_").replace(".", "_")


def _dep_name(spec: str) -> str:
    """'requests>=2.0 ; extra == "x"' -> 'requests' (normalised)."""
    spec = spec.split(";")[0].strip()
    name = re.split(r"[<>=!~\[\s]", spec, maxsplit=1)[0]
    return _norm(name)


def declared_deps(root: str = ".") -> set[str]:
    """Normalised distribution names from pyproject.toml + requirements.txt."""
    deps: set[str] = set()
    try:
        with open(os.path.join(root, "pyproject.toml"), "rb") as fh:
            data = tomllib.load(fh)
        project = data.get("project", {})
        for spec in project.get("dependencies", []):
            deps.add(_dep_name(spec))
        for group in project.get("optional-dependencies", {}).values():
            for spec in group:
                deps.add(_dep_name(spec))
    except (OSError, tomllib.TOMLDecodeError, AttributeError):
        pass
    try:
        with open(os.path.join(root, "requirements.txt"), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith(("#", "-")):
                    continue  # -r/-c includes are not followed (documented in D-10)
                if "#egg=" in line:  # VCS deps: git+...#egg=NAME
                    deps.add(_norm(line.split("#egg=", 1)[1].split("&")[0].split("#")[0]))
                else:
                    deps.add(_dep_name(line))
    except OSError:
        pass
    return deps


def _top_levels(content: str):
    """Yield (lineno, top_level_module, line) for each import; skip relative."""
    for lineno, line in enumerate(content.splitlines(), 1):
        m = _IMPORT_LINE.match(line)
        if not m:
            continue
        if m.group(1) is not None:  # from X import ...
            mod = m.group(1)
            if not mod.startswith("."):
                yield lineno, mod.split(".")[0], line.strip()
        else:  # import a, b.c as d
            # Take the import clause only: drop a trailing comment, a ';'-joined
            # second statement, and a line-continuation backslash before splitting.
            rest = m.group(2).split("#")[0].split(";")[0].rstrip().rstrip("\\")
            for part in rest.split(","):
                name = part.strip().split(" as ")[0].strip()
                if name and not name.startswith("."):
                    yield lineno, name.split(".")[0], line.strip()


def _local_names(files) -> set[str]:
    names: set[str] = set()
    for f in files:
        parts = f.path.replace("\\", "/").split("/")
        stem = parts[-1]
        if stem.endswith(".py"):
            names.add(_norm(stem[:-3]))
        for part in parts[:-1]:
            if part and part not in (".", ".."):
                names.add(_norm(part))
    return names


def detect_undeclared_imports(files, root: str = ".") -> tuple[int, list[str]]:
    """Flag imports whose top-level module is not stdlib, declared, or local."""
    deps = declared_deps(root)
    if not deps:
        return 0, []  # no manifest -> cannot establish declared set -> never flag
    resolvable = _STDLIB | deps | _local_names(files)
    count = 0
    evidence: list[str] = []
    for f in files:
        if not f.path.endswith(".py"):
            continue
        for lineno, top, line in _top_levels(f.content):
            name = _norm(top)
            if name in resolvable or _ALIASES.get(name) in deps:
                continue
            count += 1
            if len(evidence) < _EVIDENCE_LIMIT:
                evidence.append(f"{f.path}:{lineno}: {line[:60]}")
    return count, evidence
