# Changelog

All notable changes to slopscore are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-06-11

Initial release.

### Added

- Scoring engine: 12 deterministic signals for AI residue in prose and code,
  combined as a convergence score (0-100) with LOW/MEDIUM/HIGH bands and a
  pass/flag verdict. Heuristic-only: no LLM, no network, no telemetry.
- Never-false-accuse gate: 24 real pre-2020 human PRs are a held-out test
  corpus; none may leave the LOW band on the default config.
- CLI: score PR JSON, raw text or stdin; scan files (`--files`) and unified
  diffs (`--diff`); JSON output (`--json`); per-signal TOML config
  (`--config`) with weight overrides and threshold.
- Git hooks: `slopscore install-hooks` adds commit-msg and pre-push hooks
  that score every commit and outgoing push. Advisory by default; opt-in
  blocking per repo via `git config slopscore.block true`, with
  `slopscore.threshold` and `slopscore.config` to tune, `SLOPSCORE_BLOCK=1/0`
  one-shot overrides and `--no-verify` always available.
- pre-commit framework integration (`slopscore-commit-msg` and
  `slopscore-pre-push` hook ids).
- GitHub Action: report-only by default, `fail-on-flag` to gate a PR.
- Report output: band-coloured badge header, evidence with `path:line` for
  code and `field:line` locations for JSON input, and a footer stating the
  current blocking state. Colour respects `NO_COLOR` and `--color`.

[0.1.0]: https://github.com/koopatroopa/slopscore/releases/tag/v0.1.0
