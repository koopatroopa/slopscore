# Held-out validation corpus

`holdout/` holds 24 real merged pull requests created **before 2020** - so they
predate ChatGPT and are definitionally human - from eight mature, English-heavy,
diverse public repos: flask, requests, django, pandas, scikit-learn, express,
home-assistant, numpy. Each record stores only the prose surfaces (title, body,
commit messages); that is where the false-accusation harm lives.

## Why it exists - the never-false-accuse gate

A self-facing slop linter must never tell a human their genuine work looks
AI-generated. On the **default config**, not one of these 24 real human PRs may
score above the LOW band. `tests/test_holdout.py` asserts exactly that - 0/24.

This corpus is **held out**: the signal weights and band cut-points are calibrated
against separate fixtures, never against these records. So 0/24 is genuine
evidence the tool discriminates, not evidence that two cut-offs were slid until
three fixtures behaved (the circular trap). Keep it disjoint - never tune here.

Carried forward from the predecessor (decision D-04); the gate is unchanged, only
the verdict shape (now a 0-100 band) moved.
