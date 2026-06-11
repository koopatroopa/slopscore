#!/bin/sh
# Install the slopscore commit-msg and pre-push hooks into the current git repo.
set -eu

hook_dir=$(git rev-parse --git-path hooks)
src_dir=$(cd "$(dirname "$0")/.." && pwd)/hooks

mkdir -p "$hook_dir"  # git init does not always create it (custom init.templateDir)

installed=""
for hook in commit-msg pre-push; do
  dst="$hook_dir/$hook"
  if [ -e "$dst" ] && ! grep -q slopscore "$dst" 2>/dev/null; then
    echo "Skipped $hook: a non-slopscore hook already exists at $dst (remove it and re-run to replace)." >&2
    continue
  fi
  # Remove first: cp through a pre-existing symlink would write to its
  # target; rm replaces the link itself with a real file.
  rm -f "$dst"
  cp "$src_dir/$hook" "$dst"
  chmod +x "$dst"
  installed="$installed $hook"
done

[ -n "$installed" ] || exit 1
echo "Installed slopscore hooks ($(echo "$installed" | sed 's/^ //; s/ /, /g')) -> $hook_dir"
echo "Advisory by default (never blocks). Opt in: git config slopscore.block true; set the bar with git config slopscore.threshold 50. SLOPSCORE_BLOCK=1/0 overrides; --no-verify bypasses."
echo "Config: slopscore.toml in the repo root (threshold, signals, weights) - see the README."
