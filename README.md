# slopscore

[![tests](https://github.com/koopatroopa/slopscore/actions/workflows/ci.yml/badge.svg)](https://github.com/koopatroopa/slopscore/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/slopscore?cacheSeconds=3600)](https://pypi.org/project/slopscore/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/koopatroopa/slopscore/blob/main/LICENSE)

![slopscore - catch the slop before it ships](https://raw.githubusercontent.com/koopatroopa/slopscore/main/assets/social-preview.png)

AI tools leave fingerprints — em-dashes, a rocket 🚀 emoji no human would
ever type by hand, stray `Co-Authored-By: Claude` trailers,
`# ... rest of the code unchanged` stubs, ghost import declarations,
`Summary by CodeRabbit` stamps. slopscore detects these AI-generated
tells by putting a number on them: every commit, push and PR scored out
of 100, every finding backed by evidence, all before it ships.

## Install

```sh
pip install slopscore
```

Then, inside each repo you want watched:

```sh
slopscore install-hooks
```

That second step is the point of the tool - a score on every commit and push.
Python 3.11 or newer. No other dependencies.

Plenty of tools lint AI residue in code. **Nothing else scores the prose that
ships with it** - the commit messages and PR text where the residue lives in
git history forever. It starts as a nudge; **one git config turns it into a
hard gate** that refuses any commit or push over your threshold, and off again
just as fast.

It flags **craft, not authorship**. slopscore never claims "this is AI" - it
points at fixable leftovers with evidence, like a linter flagging a missing
semicolon. (Style-based AI detection is unreliable and biased against
second-language writers, so it refuses to do it: 24 real pre-2020 human PRs
must score LOW forever - `tests/test_holdout.py`.) Everything runs locally: no
LLM, no network, no telemetry.

## Who runs it

Two kinds of people, both on their **own** work:

- **You used AI and want to ship clean.** Catch the residue - a leftover
  trailer, a placeholder stub, unedited boilerplate - before a reviewer does.
  Run it on yourself via the hooks, or as a shared standard in CI (report-only
  for repos with outside contributors).
- **You didn't use AI but fear a detector will say you did.** Formal and
  second-language writers get wrongly flagged constantly. Turn on the thorough
  tier (`--strict`) and slopscore shows your *own* writing through a crude
  detector's eyes - the em-dashes, the "delve", the scaffolding those tools
  latch onto - with evidence for every hit. slopscore is not intelligent, and
  neither are the detectors: that is the point. It shows you your attack
  surface before someone else's dumb tool does, so you can shrink it on your
  own terms. It does not believe these tells prove AI; it refuses that.

Either way the score is *information*, never an accusation: the verdict is the
only gate, and honest human work is built to pass.

## Tested against reality

Every claim above is measured, not asserted. The signals are validated
against nearly 5,000 real commits and PR bodies from public GitHub history,
under pre-registered rules: the metric and the pass bar are written down
before the data is scored, every rejected idea is logged, and a held-out set
of 24 pre-2020 human PRs is never tuned against - CI enforces that it scores
LOW forever.

- **2,300+ real human commits and PR bodies (pre-2022, definitionally
  pre-LLM): zero false flags.**
- **1,700+ commits and PR bodies carrying real AI attribution: 99.9%
  flagged.**
- **785 disciplined, human-reviewed AI-assisted commits: all PASS.** It
  measures residue, not authorship - AI-assisted work that someone actually
  edited scores like human work.

When the corpus catches the engine being wrong, the engine changes - and
signals that false-fired on real humans were rejected and stay rejected.

## Try it

Scoring a commit on its way out - the message and the staged code, with each
finding pinned to where it is:

![slopscore scoring a commit: 70/100 HIGH](https://raw.githubusercontent.com/koopatroopa/slopscore/v0.1.0/assets/sample-report.svg)

Or score raw text from the command line:

```sh
echo "Certainly! Let's delve into a robust refactor. Generated with Claude Code." | slopscore --text -
```

![slopscore scoring the line above: 86/100 HIGH](https://raw.githubusercontent.com/koopatroopa/slopscore/v0.1.0/assets/text-demo.svg)

Drop the "Generated with Claude Code." sentence and it falls to 13.6, PASS -
single weak signals are normal writing; only convergence flags. (No install
needed to play: swap `slopscore` for `uvx slopscore` in any of these.)

The score is a **gradient** - *how much* AI residue is in the text, not a
yes/no. A low non-zero score is light texture, not an accusation; the
**verdict** is the only gate, and it is tuned so honest human work passes.

- Bands: **LOW** below 30, **MEDIUM** 30 to under 70, **HIGH** 70 and up. The
  **verdict** FLAGs at/above the threshold (default 30), so MEDIUM and HIGH
  both flag.
- The **exit code** follows the verdict: `0` pass, `1` flag, `2` usage error -
  so it drops straight into CI or a git hook.
- Evidence carries `path:line` for code; JSON input gets prose locations too
  (`body:14`, `commit[2]:1`).

On a terminal the report is coloured by band (green/amber/red); piped output
stays plain. `--color` and `NO_COLOR` override.

## Four ways to use it

**1. The CLI - check your work by hand.**

```sh
# score a PR/issue described as JSON ({title, body, commits})
slopscore pr.json
# or raw text, or stdin
echo "Quick fix. Generated with Claude Code." | slopscore --text -
# scan code files too (go wide on your working tree)
slopscore --files src/*.py --json
# thorough tier: also score the opt-in signals (see "Who runs it")
slopscore --strict pr.json
```

**2. Git hooks - score every commit and push; block them when you say so.**

```sh
slopscore install-hooks
```

Or via the [pre-commit](https://pre-commit.com) framework:

```yaml
repos:
  - repo: https://github.com/koopatroopa/slopscore
    rev: v0.1.0
    hooks:
      - id: slopscore-commit-msg
      - id: slopscore-pre-push
```

`commit-msg` scores your message plus the staged code; `pre-push` scores each
outgoing commit (flagged ones reported as `[abc1234] Subject`, clean pushes
silent). **Advisory by default - they never block until you ask.** The gate is
one setting, per repo, instant in both directions:

```sh
git config slopscore.block true       # gate ON: refuse commits/pushes at/above the threshold
git config slopscore.threshold 50     # move the bar (default 30)
git config slopscore.block false      # gate OFF: back to advisory
git config slopscore.strict true      # thorough tier: score the opt-in signals too
```

Escape hatches even with the gate on: `git commit --no-verify` (or push) skips
it once; `SLOPSCORE_BLOCK=0` (or `=1`) overrides the setting for one command.
Every report's footer tells you the current state and the command to flip it.

**3. Claude Code - make the agent clean up after itself.**

```
/plugin marketplace add koopatroopa/slopscore
/plugin install slopscore@slopscore
```

Then restart the session once - hooks attach at session start, so the
scoring begins from your next conversation.

Every `git commit` the agent makes gets scored; a flagged report is fed
straight back to the agent, which lays out each finding's evidence and asks
before touching anything - you decide what gets cleaned, finding by
finding. `/slopscore:clean` runs the full remediation loop - the agent fixes
each piece of evidence, amends, and re-scores until the commit passes, with
the deterministic linter as the gate on the rewrite. Advisory only - it
never blocks, and it works on macOS, Linux and Windows alike (the hook is
the CLI itself, no shell involved).

The plugin needs the CLI (`uv tool install slopscore`) - and if it is
missing, Claude is told at session start and will offer to install it for
you, then offer the git hooks so your own commits are covered too. To
remove: `/plugin uninstall slopscore`, then `uv tool uninstall slopscore`
and (if you installed the git hooks) delete the slopscore shims from
`.git/hooks/`.

**4. CI - the same gate on every PR, two lines on either platform.**

Both recipes score the PR/MR's prose (title + description) plus the diff's
added lines, report-only until you flip the gate (exit `0` pass, `1` flag).
It runs on every contributor, so it is a shared craft standard - keep it
report-only on repos with outside contributors.

GitHub (run it under `pull_request`, not `pull_request_target` - slopscore
only needs to read the diff, never repo write access or secrets):

```yaml
on: pull_request
permissions:
  contents: read
# ...
- uses: actions/checkout@v4
  with: { fetch-depth: 0 }
- uses: koopatroopa/slopscore@v0   # pin to a tag
  with: { fail-on-flag: "false" }  # "true" = gate the merge
```

GitLab:

```yaml
include:
  - remote: https://raw.githubusercontent.com/koopatroopa/slopscore/main/ci/slopscore.gitlab-ci.yml
```

The GitLab job ships advisory (`allow_failure: true`); redeclare the job to
remove that or set `SLOPSCORE_THRESHOLD`. Any other CI works the same way:
`pip install slopscore`, feed it `--text` and `--diff`, gate on the exit
code.

## What it looks for

Signals that are **on by default** - distinctive leftovers with a very low
false-positive rate:

- `ai_self_reference` - explicit AI attribution: trailers ("Co-Authored-By:
  Claude"), assistant self-talk ("As an AI..."), and the stamps AI review
  bots leave in PR bodies ("## Summary by CodeRabbit", aider's
  auto-generated-PR header)
- `ai_cliche_phrases` - chatbot filler ("delve into", "it's worth noting")
- `code_placeholder_stub` - placeholder markers left in code ("// ... rest of
  code", "your implementation here"), reported with file and line.
- `em_dash_density`, `emoji_density` and `curly_quotes` - U+2014, decorative
  emoji and word-processor quotes are not on your keyboard; in coding
  artefacts they arrive via tooling. These only ever add to a score (they are
  excluded from the normalisation ceiling), so enabling or disabling them
  cannot dilute the signals above - and their combined contribution is
  capped, so however many fire at once they can colour a score but never
  flag on their own. Real Greenkeeper-era PR bodies taught us that one.

Signals that are **opt-in**, because humans genuinely type them:

- `code_undeclared_import` - an import that is not in the standard library, not
  declared in your manifest and not a local module - possibly a package the
  model made up. It reads your `pyproject`/`requirements` and never imports or
  installs anything.
- `sycophantic_openers` ("Certainly!", "Hope this helps!") - chat register,
  not commit register: across 2,500+ real AI-attributed commits and PR bodies
  it fired zero times, and its only corpus hits were friendly humans. Kept
  for scanning pasted chat output.
- `promotional_adjectives` ("robust", "comprehensive"), `section_scaffolding`
  (`## Overview` headers - PR templates generate these), `bold_lead_in_lists`,
  `negative_parallelism` ("not just X, but Y" and its TED-talk cousins),
  `rhetorical_qa` ("Why? Because...") and `vague_authority` ("studies show").

## Configure it

A TOML config toggles any signal, overrides weights and sets the threshold:

```toml
threshold = 40

[signals]
emoji_density = false           # opt a default signal out
code_undeclared_import = true   # opt the import check in

[weights]
ai_self_reference = 6.0
```

Point each surface at it:

```sh
slopscore --config slopscore.toml --files src/*.py   # CLI
git config slopscore.config slopscore.toml           # hooks, per repo
# Action: pass `config: "slopscore.toml"` in the workflow's `with:` block
```

## Honest about its limits

- Calibration is validated on the corpus above: humans top out at a score
  of 25, real attributed-AI sits at 70+, and the flag bar (30) lives in the
  empty gap between them. An explicit attribution trailer is a certain tell, so it
  scores HIGH on its own; weak signals must converge to get there.
- The corpus has an era gap by construction: the human side is pre-2022
  (provably pre-LLM), the AI side is 2023+. Stated, not pretended away - a
  pass against modern human PR-template prose is the known next step.
- The import check resolves against your manifest; import-name vs package-name
  mismatches (`yaml` vs `PyYAML`) are only partly covered by an alias map -
  hence opt-in. `requirements.txt` `-r` includes are not followed.
- It is a *signal*, not a judge. A high score means "give this a second read",
  never "this is AI".

## Design

The detection engine is framework-free; the CLI, git hooks and Action are thin
front-ends over it. Heuristic-only by design - the value is the discipline
(low false-positive, evidence-backed, craft not authorship), not a cleverer
classifier.

MIT licensed.
