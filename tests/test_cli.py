"""Behavioural spec for the slopscore CLI entry point.

The exit code is the contract: 0 = PASS (below threshold), 1 = FLAG (at/above),
2 = usage/input error. Each test plants a known input file and asserts on the
observable output + exit code, independent of the engine internals.
"""

import json

from slopscore.cli import main


CLEAN_JSON = json.dumps(
    {
        "title": "Fix off-by-one in pagination",
        "body": "The loop ran one past the end. Adjusted the bound and added a test.",
        "commits": ["Fix pagination bound"],
    }
)

SLOP_JSON = json.dumps(
    {
        "title": "Improve the codebase",
        "body": (
            "## Overview\nThis PR will delve into a seamless, robust refactor.\n\n"
            "## Changes\n- **Refactor:** streamline the core module\n"
            "- **Tests:** add comprehensive coverage\n\n"
            "## Summary\nIn conclusion, it's worth noting the gains \U0001f680."
        ),
        "commits": ["Refactor everything"],
    }
)


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_clean_input_exits_zero_and_reports_pass(tmp_path, capsys):
    path = _write(tmp_path, "clean.json", CLEAN_JSON)
    code = main([path])
    out = capsys.readouterr().out
    assert code == 0
    assert "PASS" in out


def test_slop_input_exits_one_and_reports_flag(tmp_path, capsys):
    path = _write(tmp_path, "slop.json", SLOP_JSON)
    code = main([path])
    out = capsys.readouterr().out
    assert code == 1
    assert "FLAG" in out


def test_json_flag_emits_parseable_report(tmp_path, capsys):
    path = _write(tmp_path, "slop.json", SLOP_JSON)
    code = main([path, "--json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert code == 1
    assert data["verdict"] == "FLAG"
    assert set(data) == {"score", "raw", "counted", "band", "verdict", "threshold", "signals"}


def test_invalid_json_exits_two_with_stderr(tmp_path, capsys):
    path = _write(tmp_path, "bad.json", "{not valid json")
    code = main([path])
    err = capsys.readouterr().err
    assert code == 2
    assert "invalid input" in err


def test_non_json_input_suggests_text_flag(tmp_path, capsys):
    # The most natural first try is raw prose without --text; the error must
    # point the user at --text rather than spit a bare JSON parser message.
    path = _write(tmp_path, "prose.txt", "Just some prose, not JSON at all.")
    code = main([path])
    err = capsys.readouterr().err
    assert code == 2
    assert "--text" in err


def test_text_mode_treats_input_as_raw_body(tmp_path, capsys):
    path = _write(tmp_path, "raw.txt", "As an AI language model, I cannot run the tests.")
    main([path, "--text"])
    out = capsys.readouterr().out
    assert "ai_self_reference" in out


def test_threshold_override_changes_verdict(tmp_path, capsys):
    path = _write(tmp_path, "raw.txt", "As an AI language model, I cannot run the tests.")
    code = main([path, "--text", "--threshold", "1"])
    assert code == 1  # ai_self_reference contributes 4.0 >= 1 -> FLAG


def test_commits_non_string_elements_exit_two(tmp_path, capsys):
    # A dict/number in commits must be rejected, not silently str()-coerced into
    # the scored text (which would poison the corpus and PASS a malformed input).
    bad = json.dumps({"title": "x", "body": "y", "commits": [1, {"a": 2}]})
    path = _write(tmp_path, "bad_commits.json", bad)
    code = main([path])
    err = capsys.readouterr().err
    assert code == 2
    assert "commits" in err


def test_threshold_out_of_range_exits_two(tmp_path, capsys):
    path = _write(tmp_path, "clean.json", CLEAN_JSON)
    assert main([path, "--threshold", "-1"]) == 2
    assert main([path, "--threshold", "150"]) == 2


def test_diff_flag_scans_added_lines(tmp_path, capsys):
    diff = (
        "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -0,0 +1,2 @@\n"
        "+def f():\n+    # ... rest of the code unchanged\n"
    )
    path = _write(tmp_path, "x.diff", diff)
    rc = main(["--diff", path])
    out = capsys.readouterr().out
    assert "code_placeholder_stub" in out
    assert "x.py:" in out  # evidence uses the diff's path
    assert rc == 1


def test_files_flag_scans_code_for_placeholders(tmp_path, capsys):
    code = tmp_path / "stub.py"
    code.write_text("def f():\n    # ... rest of the code unchanged\n    pass\n", encoding="utf-8")
    # files-only mode: no positional path, must not block on stdin.
    rc = main(["--files", str(code)])
    out = capsys.readouterr().out
    assert "code_placeholder_stub" in out
    assert rc == 1  # one placeholder -> MEDIUM -> FLAG


def test_non_utf8_input_degrades_not_crashes(tmp_path):
    # A decode crash would exit 1 - the FLAG code - and falsely block in hooks.
    p = tmp_path / "latin1.txt"
    p.write_bytes(b"caf\xe9 fix\n")
    assert main(["--text", str(p)]) == 0


def test_non_utf8_diff_degrades_not_crashes(tmp_path):
    d = tmp_path / "bad.diff"
    d.write_bytes(b"--- a/f.py\n+++ b/f.py\n@@ -0,0 +1 @@\n+x = 'caf\xe9'\n")
    msg = _write(tmp_path, "msg.txt", "Fix the parser")
    assert main(["--text", msg, "--diff", str(d)]) == 0


def test_internal_error_exits_two_not_one(tmp_path, capsys, monkeypatch):
    # Any unexpected crash must come out as 2 (error), never 1 (verdict).
    import slopscore.cli as cli_mod

    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cli_mod, "triage", boom)
    p = _write(tmp_path, "msg.txt", "Fix the parser")
    assert main(["--text", p]) == 2
    assert "internal error" in capsys.readouterr().err


def test_color_always_emits_ansi(tmp_path, capsys):
    p = _write(tmp_path, "msg.txt", "Fix the parser")
    main(["--text", p, "--color", "always"])
    assert "\x1b[" in capsys.readouterr().out


def test_no_ansi_when_stdout_is_not_a_terminal(tmp_path, capsys):
    p = _write(tmp_path, "msg.txt", "Fix the parser")
    main(["--text", p])
    assert "\x1b[" not in capsys.readouterr().out


def test_use_color_modes(monkeypatch):
    import sys

    from slopscore.cli import _use_color

    assert _use_color("always") is True
    assert _use_color("never") is False
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert _use_color("auto") is True
    monkeypatch.setenv("NO_COLOR", "1")
    assert _use_color("auto") is False


def test_json_input_evidence_carries_field_and_line(tmp_path, capsys):
    pr = json.dumps(
        {
            "title": "Improve things",
            "body": "First line.\nIt's worth noting the gains.",
            "commits": ["In summary, a fine commit."],
        }
    )
    p = _write(tmp_path, "pr.json", pr)
    main([str(p), "--json"])
    data = json.loads(capsys.readouterr().out)
    evidence = [e for s in data["signals"] for e in s["evidence"]]
    assert any(e.startswith("body:2: ") for e in evidence), evidence
    assert any(e.startswith("commit[1]:1: ") for e in evidence), evidence


def test_text_input_evidence_stays_unqualified(tmp_path, capsys):
    p = _write(tmp_path, "msg.txt", "It's worth noting, a fine reply.")
    main(["--text", str(p), "--json"])
    data = json.loads(capsys.readouterr().out)
    evidence = [e for s in data["signals"] for e in s["evidence"]]
    assert evidence and all(":" not in e.split(" ")[0] for e in evidence), evidence


def test_version_flag(capsys):
    import pytest as _pytest

    with _pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("slopscore ")


def test_bare_invocation_on_a_terminal_greets_not_hangs(monkeypatch, capsys):
    # A new user's first command is `slopscore` with no args: that must print
    # the getting-started pointer (install-hooks), not block reading stdin.
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "slopscore install-hooks" in out
    assert "--help" in out


def test_bare_text_flag_on_a_terminal_also_greets(monkeypatch, capsys):
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert main(["--text"]) == 0
    assert "install-hooks" in capsys.readouterr().out


def test_strict_enables_opt_in_signals(tmp_path, capsys):
    # --strict turns on the thorough tier: a prose-folklore signal that is
    # off by default (rhetorical_qa) fires under --strict.
    p = _write(tmp_path, "t.txt", "Why? Because the math changed.")
    main(["--text", str(p), "--json"])
    default = json.loads(capsys.readouterr().out)
    main(["--text", str(p), "--strict", "--json"])
    strict = json.loads(capsys.readouterr().out)
    assert "rhetorical_qa" not in {s["name"] for s in default["signals"]}
    assert "rhetorical_qa" in {s["name"] for s in strict["signals"]}


def test_default_run_prints_tier_hint(tmp_path, capsys):
    # Text mode advertises the tier so --strict is discoverable.
    p = _write(tmp_path, "t.txt", "Fix the parser")
    main(["--text", str(p)])
    out = capsys.readouterr().out
    assert "Running default tier" in out
    assert "--strict" in out


def test_strict_run_prints_thorough_tier(tmp_path, capsys):
    p = _write(tmp_path, "t.txt", "Fix the parser")
    main(["--text", str(p), "--strict"])
    assert "Running thorough tier" in capsys.readouterr().out


def test_json_output_carries_no_tier_note(tmp_path, capsys):
    # The tier note is human chrome - it must never land in --json output, or
    # it would corrupt a machine consumer. True in both tiers.
    p = _write(tmp_path, "t.txt", "Fix the parser")
    for argv in (["--text", str(p), "--json"], ["--text", str(p), "--strict", "--json"]):
        main(argv)
        out = capsys.readouterr().out
        assert "Running" not in out and "tier" not in out
        json.loads(out)  # parses clean


def test_strict_overrides_a_config_that_disables_signals(tmp_path, capsys):
    # --strict forces every signal on, even one a --config turned off.
    cfg = _write(tmp_path, "c.toml", "[signals]\nrhetorical_qa = false\n")
    p = _write(tmp_path, "t.txt", "Why? Because the math changed.")
    main(["--text", str(p), "--config", cfg, "--strict", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert "rhetorical_qa" in {s["name"] for s in data["signals"]}
