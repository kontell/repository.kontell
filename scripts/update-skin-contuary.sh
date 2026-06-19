#!/bin/bash
set -euo pipefail

# Update the Kontell repository with the latest skin.contuary zips.
#
# Usage:
#   ./scripts/update-skin-contuary.sh [zip-or-directory]
#
# If no argument is given, downloads from the latest GitHub releases
# (one per branch: omega/v* and piers/v*).
# Pass a zip file or directory to use a local build instead.
# Requires: gh (GitHub CLI) for downloading from GitHub.
#
# skin.contuary releases are per-branch (omega vs piers), using tags
# like omega/v2.0.3 and piers/v2.0.3.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ADDON_ID="skin.contuary"
ADDON_REPO="kontell/skin.contuary"

# Published content lives on the gh-pages branch (worktree at _site/).
source "$SCRIPT_DIR/lib-pages.sh"
PAGES_DIR="$(ensure_pages_worktree "$REPO_DIR")"

cleanup_tmp=""
trap '[[ -n "$cleanup_tmp" ]] && rm -rf "$cleanup_tmp"' EXIT

place_zip() {
    local zip_path="$1" branch="$2"
    local filename
    filename="$(basename "$zip_path")"

    if [[ ! "$filename" =~ ^${ADDON_ID}-([0-9][0-9.]*)-[a-z]+\.zip$ ]]; then
        echo "Error: $filename doesn't match expected pattern ${ADDON_ID}-<version>-<branch>.zip"
        exit 1
    fi
    local ver="${BASH_REMATCH[1]}"

    local dest_dir="$PAGES_DIR/$branch/$ADDON_ID"
    local dest_file="${ADDON_ID}-${ver}.zip"
    mkdir -p "$dest_dir"
    cp "$zip_path" "$dest_dir/$dest_file"
    echo "  -> $branch/$ADDON_ID/$dest_file"
}

if [[ $# -ge 1 ]]; then
    arg="$1"
    if [[ -f "$arg" ]]; then
        ZIP_PATH="$(realpath "$arg")"
        echo "Using local zip: $ZIP_PATH"
        echo ""
        for branch in omega piers; do
            place_zip "$ZIP_PATH" "$branch"
        done
    elif [[ -d "$arg" ]]; then
        ZIP_PATH="$(ls -t "$arg"/${ADDON_ID}-*.zip 2>/dev/null | head -1 || true)"
        [[ -z "$ZIP_PATH" ]] && { echo "Error: no ${ADDON_ID}-*.zip in $arg"; exit 1; }
        ZIP_PATH="$(realpath "$ZIP_PATH")"
        echo "Using local zip: $ZIP_PATH"
        echo ""
        for branch in omega piers; do
            place_zip "$ZIP_PATH" "$branch"
        done
    else
        echo "Error: $arg is neither a file nor a directory"
        exit 1
    fi
else
    if ! command -v gh &>/dev/null; then
        echo "Error: gh (GitHub CLI) is required, or pass a zip path/directory."
        exit 1
    fi

    cleanup_tmp="$(mktemp -d)"

    for branch in omega piers; do
        echo "Fetching latest $branch release from $ADDON_REPO..."

        release_tag=$(gh release list --repo "$ADDON_REPO" --limit 20 \
            --json tagName,isDraft \
            --jq ".[] | select(.isDraft == false) | select(.tagName | startswith(\"${branch}/\")) | .tagName" \
            | head -1)

        if [[ -z "$release_tag" ]]; then
            echo "  No published release found for $branch. Trying latest draft..."
            release_tag=$(gh release list --repo "$ADDON_REPO" --limit 20 \
                --json tagName,isDraft \
                --jq ".[] | select(.tagName | startswith(\"${branch}/\")) | .tagName" \
                | head -1)
        fi

        if [[ -z "$release_tag" ]]; then
            echo "  Warning: no releases found for $branch, skipping"
            continue
        fi

        echo "  Downloading from release $release_tag..."
        dl_dir="$cleanup_tmp/$branch"
        mkdir -p "$dl_dir"
        gh release download "$release_tag" --repo "$ADDON_REPO" \
            --pattern "${ADDON_ID}-*.zip" --dir "$dl_dir"

        zip_path="$(ls "$dl_dir"/${ADDON_ID}-*.zip | head -1)"
        place_zip "$zip_path" "$branch"
    done
fi

echo ""
echo "Regenerating repository metadata..."
echo ""

python3 "$REPO_DIR/generate_repo.py" --pages-dir "$PAGES_DIR"

echo ""
echo "Done. Review with 'git -C _site status', then publish with:"
echo "  ./scripts/publish.sh \"update skin.contuary\""
