---
description: Score the latest commit for AI residue and remediate it until it passes
---

Run the slopscore remediation loop on the most recent commit:

1. Score it: `git log -1 --format=%B | slopscore --text - --json`,
   honouring the repo's settings: if `git config slopscore.config` or
   `git config slopscore.threshold` are set, pass them through as
   `--config` / `--threshold`. If the verdict is PASS, report the score and
   stop - do not rewrite clean work.
2. For each finding, read the evidence and FIX THE CAUSE in the commit
   message: delete leftover attribution trailers and generated-with footers,
   remove placeholder/stub references, rewrite filler phrases in plain
   language, strip decorative emoji and em-dash texture you would not have
   typed. Preserve the meaning and every factual detail; this is residue
   removal, not a rewrite of substance.
3. If the report shows code findings (placeholder stubs in the diff), fix
   the flagged lines in the working tree and stage them.
4. Amend: `git commit --amend` with the cleaned message (plus staged fixes).
   NEVER amend a commit that has already been pushed - check first with
   `git branch -r --contains HEAD` (empty output means no remote has it:
   safe to amend); if any remote branch contains it, say so and stop.
5. Re-score the amended commit the same way. Repeat until PASS (it normally
   takes one pass). If something must stay - e.g. repo policy REQUIRES
   AI-attribution trailers - keep it, say so explicitly, and report the
   residual score instead of forcing a PASS.

Report the before and after scores in one line each.
