# slopscore

[![tests](https://github.com/koopatroopa/slopscore/actions/workflows/ci.yml/badge.svg)](https://github.com/koopatroopa/slopscore/actions/workflows/ci.yml)

Lint your own slop before you ship it.

"Slop" is the residue AI tools leave behind: a stray "Co-Authored-By: Claude"
trailer in a commit message, a `# ... rest of the code unchanged` placeholder
that was meant to be replaced, an import for a package that does not exist, a
PR description that opens with "Certainly!" - or prose full of em-dashes and
rocket emoji nobody typed by hand. slopscore reads your commit or PR, scores
the residue from 0 to 100 and lists every finding with its evidence, so it can
be fixed before anyone else reads it.

## Install

The whole setup is two lines - the second one, run inside a repo, is the
point of the tool (a score on every commit and push):

```sh
pip install slopscore
slopscore install-hooks
```

Python 3.11 or newer. No other dependencies. Without the hooks you still have
the CLI and the Action, but the nudge-as-you-work loop is the product.

Plenty of tools lint AI residue in code. **Nothing else scores the prose that
ships with it** - your commit messages and PR text, which is where the residue
lives forever in git history, and which is exactly where AI tools leave their
clearest fingerprints.

The ground rules:

- **It only checks your own work.** You run it on yourself; it never accuses
  anyone else of anything.
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

**2. Git hooks - the report on every commit and push.**

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
silent). **Advisory by default - they never block.** To gate for real:

```sh
git config slopscore.block true     # refuse commits/pushes at/above the threshold
git config slopscore.threshold 50   # optional: move the bar (default 30)
```

`--no-verify` always bypasses; `SLOPSCORE_BLOCK=1`/`=0` overrides the config
for one command.

**3. GitHub Action - the same gate on your own PRs.**

```yaml
- uses: actions/checkout@v4
  with: { fetch-depth: 0 }
# pin to a tag
- uses: koopatroopa/slopscore@v0
  with:
    threshold: "30"
    fail-on-flag: "false"   # report-only by default
```

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
