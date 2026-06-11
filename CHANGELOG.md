# Changelog

All notable changes to slopscore are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.1] - 2026-06-11

### Added

- Claude Code plugin (`/plugin marketplace add koopatroopa/slopscore`): a
  post-commit hook scores every commit the agent makes and lays the
  evidence before the user - you decide what gets cleaned - and
  `/slopscore:clean` runs the consented remediation loop: fix the
  evidence, amend, re-score until it passes. Advisory only;
  cross-platform (the hook is the CLI entry point, no shell involved).
- `slopscore hook claude-commit`: the plugin's hook as a CLI subcommand,
  honouring the repo's `slopscore.*` git config like the git hooks do.

## [0.1.0] - 2026-06-11

Initial release.

### Added

- Scoring engine: 14 deterministic signals for AI residue in prose and code,
  combined as a convergence score (0-100) with LOW/MEDIUM/HIGH bands and a
  pass/flag verdict. Heuristic-only: no LLM, no network, no telemetry.
  Folklore signals (em-dash, emoji, curly quotes, opt-in prose patterns) are
  additive-only and capped in aggregate: they colour the score but never
  flag on their own under the default threshold. Defaults validated against
  ~4,500 real commits and PR bodies (pre-2022 human + attributed-AI): zero
  human false flags.
- Attribution detection covers AI review-bot stamps (CodeRabbit and Sourcery
  summary headers, aider auto-generated PR header) alongside the
  co-author/generated-with trailer family.
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

[0.1.1]: https://github.com/koopatroopa/slopscore/releases/tag/v0.1.1
[0.1.0]: https://github.com/koopatroopa/slopscore/releases/tag/v0.1.0
