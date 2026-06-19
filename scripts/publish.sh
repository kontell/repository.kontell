#!/bin/bash
set -euo pipefail

# Commit and push the generated site to the gh-pages branch.
#
# Run this after an update-*.sh script has regenerated the site in _site/.
# Review first with:  git -C _site status   (and git -C _site diff)
#
# Usage:
#   ./scripts/publish.sh ["commit message"]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/lib-pages.sh"
PAGES_DIR="$(ensure_pages_worktree "$REPO_DIR")"

cd "$PAGES_DIR"
git add -A

if git diff --cached --quiet; then
    echo "No changes to publish."
    exit 0
fi

echo "Publishing these changes to gh-pages:"
git diff --cached --stat
echo ""

git commit -q -m "${1:-Update repository content}"
git push origin gh-pages

echo ""
echo "Published. Live at https://kontell.github.io/repository.kontell/ shortly."
