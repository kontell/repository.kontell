#!/bin/bash
# Shared helper for publishing to the gh-pages branch.
#
# The served content (omega/, piers/, the installer zip and index.html) lives on
# the orphan `gh-pages` branch, checked out as a git worktree at <repo>/_site.
# `main` holds only source (scripts, generate_repo.py, addon.xml). See the
# README "Publishing" section for the rationale.
#
# Source this file, then call ensure_pages_worktree to get the worktree path:
#   source "$SCRIPT_DIR/lib-pages.sh"
#   PAGES_DIR="$(ensure_pages_worktree "$REPO_DIR")"

# Print the path to the gh-pages worktree, creating it if necessary.
# All progress/errors go to stderr so stdout carries only the path.
ensure_pages_worktree() {
    local repo_dir="$1"
    local pages_dir="$repo_dir/_site"

    if [[ -e "$pages_dir/.git" ]]; then
        printf '%s' "$pages_dir"
        return 0
    fi

    echo "Setting up gh-pages worktree at _site/ ..." >&2

    # Make the branch available locally if it only exists on the remote.
    if ! git -C "$repo_dir" show-ref --verify --quiet refs/heads/gh-pages; then
        git -C "$repo_dir" fetch --quiet origin gh-pages 2>/dev/null || true
    fi

    if git -C "$repo_dir" show-ref --verify --quiet refs/heads/gh-pages; then
        git -C "$repo_dir" worktree add --quiet "$pages_dir" gh-pages >&2
    elif git -C "$repo_dir" show-ref --verify --quiet refs/remotes/origin/gh-pages; then
        git -C "$repo_dir" worktree add --quiet --track -b gh-pages "$pages_dir" origin/gh-pages >&2
    else
        echo "Error: no gh-pages branch found locally or on origin." >&2
        echo "See the README 'Publishing' section to create it." >&2
        return 1
    fi

    printf '%s' "$pages_dir"
}
