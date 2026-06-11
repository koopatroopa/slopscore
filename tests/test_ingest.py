"""Behavioural spec for code ingestion: working-tree files and unified diffs."""

from slopscore.ingest import files_from_diff, files_from_paths


def test_files_from_paths_reads_content(tmp_path):
    p = tmp_path / "a.py"
    p.write_text("x = 1\n", encoding="utf-8")
    files = files_from_paths([str(p)])
    assert len(files) == 1
    assert files[0].path == str(p)
    assert "x = 1" in files[0].content


def test_files_from_paths_skips_unreadable(tmp_path):
    # Ingestion is best-effort: a missing path is skipped, not fatal.
    assert files_from_paths([str(tmp_path / "nope.py")]) == ()


def test_files_from_paths_caps_oversized_file(tmp_path):
    # Resource-exhaustion guard: a multi-MB file is truncated, not read whole.
    p = tmp_path / "big.py"
    p.write_text("a = 1\n" * 200_000, encoding="utf-8")  # ~1.2 MB
    files = files_from_paths([str(p)])
    assert len(files[0].content) <= 1_000_000


def test_files_from_diff_extracts_only_added_lines_per_file():
    diff = (
        "diff --git a/foo.py b/foo.py\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+import os\n"
        "+# ... rest of code here\n"
        "diff --git a/bar.py b/bar.py\n"
        "--- a/bar.py\n"
        "+++ b/bar.py\n"
        "@@ -1 +1 @@\n"
        "-old removed line\n"
        "+new added line\n"
    )
    files = {f.path: f.content for f in files_from_diff(diff)}
    assert set(files) == {"foo.py", "bar.py"}
    assert "import os" in files["foo.py"]
    assert "# ... rest of code here" in files["foo.py"]
    assert "new added line" in files["bar.py"]
    assert "old removed line" not in files["bar.py"]  # removed lines excluded
