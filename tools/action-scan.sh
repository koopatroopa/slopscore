#!/usr/bin/env bash
# Scan a pull request's changed files for slop. Driven entirely by env vars set
# by action.yml, so it is testable outside GitHub Actions:
#   SLOP_BASE       base commit to diff against (PR base sha); falls back to HEAD~1
#   SLOP_TITLE      PR/MR title (scored as prose alongside the diff)
#   SLOP_BODY       PR/MR description (scored as prose alongside the diff)
#   SLOP_THRESHOLD  0-100 flag threshold (default 30)
#   SLOP_CONFIG     optional path to a slopscore TOML config
#   SLOP_FAIL       "true" to fail the check on FLAG; default report-only
set -uo pipefail

base="${SLOP_BASE:-}"
if [ -n "$base" ] && git rev-parse --verify --quiet "$base" >/dev/null; then
  range="$base...HEAD"
else
  range="HEAD~1...HEAD"  # fallback for push events / shallow checkouts
fi

diff=$(git diff --diff-filter=ACM "$range" 2>/dev/null)
if [ -z "$diff" ]; then
  echo "slopscore: no changes to scan."
  exit 0
fi

# Scan the diff's ADDED lines, not whole files, so pre-existing slop is not
# attributed to this PR - plus the PR's own prose (title + body) when provided.
args=(--threshold "${SLOP_THRESHOLD:-30}")
[ -n "${SLOP_CONFIG:-}" ] && args+=(--config "${SLOP_CONFIG}")
if [ -n "${SLOP_TITLE:-}${SLOP_BODY:-}" ]; then
  prose=$(mktemp)
  trap 'rm -f "$prose"' EXIT
  printf '%s\n\n%s\n' "${SLOP_TITLE:-}" "${SLOP_BODY:-}" > "$prose"
  args+=(--text "$prose")
fi
args+=(--diff -)

printf '%s\n' "$diff" | slopscore "${args[@]}"
rc=$?

if [ "${SLOP_FAIL:-false}" = "true" ] && [ "$rc" -eq 1 ]; then
  echo "slopscore: score at/above threshold; failing the check (fail-on-flag)." >&2
  exit 1
fi
exit 0
