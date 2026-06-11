# FAQ

Field-tested questions, mostly from watching real first runs.

## It scored text inside a quotation / code fence. Why?

The detectors are context-blind by design (they are fast, dumb regexes; the
calibration is where the intelligence lives). A quoted em-dash or a fenced
`## Summary by CodeRabbit` example counts like any other occurrence. In
practice the folklore cap keeps quoted texture from ever flagging on its
own, and the certain signals are anchored to forms humans do not quote by
accident - but if you hit a real false positive this way on the default
config, that is bounty territory: open an issue.

## It called "revolutionary socialist" a marketing adjective.

Same reason: `promotional_adjectives` counts words, not meanings, and it is
an opt-in signal partly because of exactly this. Describing Marx is not
marketing. Opt-in signals trade precision for recall, which is why they are
off by default and why `--strict` says "read the score, don't gate on it".

## My score is 12 but I wrote it myself. Am I being accused?

No. The score is a gradient of residue-shaped texture, not a verdict on
authorship. LOW scores are normal writing; the verdict (FLAG/PASS) is the
only gate, and it is calibrated so real human writing passes - zero false
flags across 2,389 pre-2022 human commits and PR bodies, with a held-out
human set enforced by CI forever.

## I ran --strict on my essay and it flagged. Should I care?

`--text` on arbitrary prose is an audit surface, not a verdict surface: the
calibration promise is scoped to what people commit (messages, PR bodies,
code). The strict tier exists to show you what crude AI detectors latch
onto in your own writing - word-processor curly quotes are the usual
culprit - so you can decide what to change. Read the evidence, not the
verdict.

## The Claude Code plugin did not flag my last commit.

Two likely reasons. Hooks attach at session start, so the first install
needs one session restart. And the hook only scores a commit made in
roughly the last minute: a failed `git commit`, or a command that merely
mentions one, leaves an old HEAD that is none of the plugin's business -
it will not tell an agent to amend work it does not own.

## I get the report twice.

You have both the git hooks and the Claude Code plugin installed, which is
the recommended setup: the git hook prints in the commit output, the
plugin feeds the agent. Same engine, same config, same numbers. If the
duplication annoys you, say so on the issue tracker - deduplication is a
known candidate.

## Why does an attribution trailer alone score 70+?

An explicit `Co-Authored-By: Claude` is not a weak signal to converge with
others - it is a certain marker, so it floors the score into the HIGH band
on its own (and it is also the single most common piece of residue in the
wild). Everything else needs convergence to flag.
