# slopscore

[![tests](https://github.com/koopatroopa/slopscore/actions/workflows/ci.yml/badge.svg)](https://github.com/koopatroopa/slopscore/actions/workflows/ci.yml)

### **_Lint your own slop before you ship it._**

AI tools leave fingerprints: stray "Co-Authored-By: Claude" trailers,
`# ... rest of the code unchanged` stubs, imports that do not exist, commit
messages full of sycophantic prose like "Certainly!" — and em-dashes and
🚀 emoji nobody typed by hand. slopscore reads your commit or PR and
scores the residue 0-100, with evidence for every finding, so you can clean
it up before anyone else reads it.

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
ships with it** - your commit messages and PR text, which is where the residue
lives forever in git history, and which is exactly where AI tools leave their
clearest fingerprints. It starts as a nudge; when you trust the score, **one
git config turns it into a hard gate** that refuses any commit or push over
your threshold - and turns back off just as fast.

The ground rules:

- **Self-facing first.** The hooks and CLI score your own work before anyone
  else sees it. In CI it becomes a published team standard instead - still a
  craft lint with evidence, never an authorship claim (see below).
- **It scores craft, not authorship.** Style-based "is this AI" detection is
  unreliable and biased against people writing in a second language, so
  slopscore only flags concrete, checkable leftovers. A held-out gate of 24
  real pre-2020 human PRs must score LOW forever (`tests/test_holdout.py`).
- **Everything runs on your machine.** Plain Python heuristics; no LLM, no
  network, no telemetry.

## Try it

```sh
echo "Certainly! Let's delve into a robust refactor. Generated with Claude Code." | slopscore --text -
```

```
[ SLOPSCORE SLOP REPORT ]

Slop score 75.0/100  band HIGH  verdict FLAG  (raw 6.0, threshold 30.0)

Signals fired (3):
  [+4.0] ai_self_reference  x1  Explicit AI attribution or assistant self-reference
         Evidence: Generated with Claude
  [+1.0] ai_cliche_phrases  x1  Filler and transition phrases characteristic of LLM prose
         Evidence: delve into
  [+1.0] sycophantic_openers  x1  Chatbot-style enthusiastic or deferential openers
         Evidence: Certainly!

Verdict: FLAG (score 75.0 >= threshold 30.0)
```

Drop the "Generated with Claude Code." sentence and it falls to 25.0, PASS -
single weak signals are normal writing; only convergence flags.

- Bands: **LOW** below 30, **MEDIUM** 30 to under 70, **HIGH** 70 and up. The
  **verdict** FLAGs at/above the threshold (default 30), so MEDIUM and HIGH
  both flag.
- The **exit code** follows the verdict: `0` pass, `1` flag, `2` usage error -
  so it drops straight into CI or a git hook.
- Evidence carries `path:line` for code; JSON input gets prose locations too
  (`body:14`, `commit[2]:1`).

On a terminal the report is coloured by band (green/amber/red); piped output
stays plain. `--color` and `NO_COLOR` override.

## Three ways to use it

**1. The CLI - check your work by hand.**

```sh
# score a PR/issue described as JSON ({title, body, commits})
slopscore pr.json
# or raw text, or stdin
echo "Certainly! Hope this helps!" | slopscore --text -
# scan code files too (go wide on your working tree)
slopscore --files src/*.py --json
```

**2. Git hooks - score every commit and push; block them when you say so.**

```sh
slopscore install-hooks      # from a checkout: tools/install-git-hook.sh
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
```

Escape hatches even with the gate on: `git commit --no-verify` (or push) skips
it once; `SLOPSCORE_BLOCK=0` (or `=1`) overrides the setting for one command.
Every report's footer tells you the current state and the command to flip it.

**3. CI - the same gate on every PR, two lines on either platform.**

Both recipes score the PR/MR's own prose (title + description) plus the
diff's added lines, report-only until you flip the gate. The exit code is
the contract: `0` pass, `1` flag.

One honest note: in CI you are no longer only scoring yourself - the check
runs on every contributor. That is the same social contract as any linter (a
published standard, applied uniformly, with evidence per finding), and the
held-out human gate exists so a person who wrote every word by hand passes.
Still: on repos with outside contributors, prefer report-only.

GitHub:

```yaml
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

- `ai_self_reference` - explicit AI attribution ("Co-Authored-By: Claude",
  "As an AI...")
- `ai_cliche_phrases` - chatbot filler ("delve into", "it's worth noting")
- `sycophantic_openers` - "Certainly!", "Hope this helps!"
- `code_placeholder_stub` - placeholder markers left in code ("// ... rest of
  code", "your implementation here"), reported with file and line.
- `em_dash_density`, `emoji_density` and `curly_quotes` - U+2014, decorative
  emoji and word-processor quotes are not on your keyboard; in coding
  artefacts they arrive via tooling. These only ever add to a score (they are
  excluded from the normalisation ceiling), so enabling or disabling them
  cannot dilute the signals above.

Signals that are **opt-in**, because humans genuinely type them:

- `code_undeclared_import` - an import that is not in the standard library, not
  declared in your manifest and not a local module - possibly a package the
  model made up. It reads your `pyproject`/`requirements` and never imports or
  installs anything.
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

- The weights and band cut-points are calibrated against two anchors: the 24
  real-human holdout (all score 0.0) and a slop corpus. A fuller pass against a
  large set of real sloppy AI output could still refine the high band, so treat
  a high score as "give this a second read", not a verdict.
- The import check resolves against your manifest; import-name vs package-name
  mismatches (`yaml` vs `PyYAML`) are only partly covered by an alias map -
  hence opt-in. `requirements.txt` `-r` includes are not followed.
- It is a *signal*, not a judge. A high score means "give this a second read",
  never "this is AI".

## Design

The detection engine is framework-free; the CLI, git hooks and Action are thin
front-ends over it. Heuristic-only by design - the value is the discipline
(low false-positive, self-facing, craft not accusation), not a cleverer
classifier.

MIT licensed.
