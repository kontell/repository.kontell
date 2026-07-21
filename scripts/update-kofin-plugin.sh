#!/bin/bash
set -euo pipefail

# Update the Kontell repository with the latest plugin.video.kofin zip.
#
# Usage:
#   ./scripts/update-kofin-plugin.sh [zip-path]
#
# If no path is given, downloads from the latest GitHub release.
# Pass a zip file path or a directory containing the zip to use a local build.
# Requires: gh (GitHub CLI) for downloading from GitHub.
#
# plugin.video.kofin is pure Python (<platform>all</platform>), so the same zip
# is used for both Kodi 21 (omega) and Kodi 22 (piers) — no per-platform matrix.
#
# Pre-releases are included: the newest non-draft release is used, whether it is
# marked as a full release or a pre-release. (GitHub's "latest release" excludes
# pre-releases, so we select from the full list rather than /releases/latest.)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ADDON_ID="plugin.video.kofin"
ADDON_REPO="kontell/plugin.video.kofin"

# Published content lives on the gh-pages branch (worktree at _site/).
source "$SCRIPT_DIR/lib-pages.sh"
PAGES_DIR="$(ensure_pages_worktree "$REPO_DIR")"

cleanup_tmp=""
trap '[[ -n "$cleanup_tmp" ]] && rm -rf "$cleanup_tmp"' EXIT

# Resolve a zip to copy
if [[ $# -ge 1 ]]; then
    arg="$1"
    if [[ -f "$arg" ]]; then
        ZIP_PATH="$(realpath "$arg")"
    elif [[ -d "$arg" ]]; then
        # Pick the latest kofin zip in the directory
        ZIP_PATH="$(ls -t "$arg"/${ADDON_ID}-*.zip 2>/dev/null | head -1 || true)"
        [[ -z "$ZIP_PATH" ]] && { echo "Error: no ${ADDON_ID}-*.zip in $arg"; exit 1; }
        ZIP_PATH="$(realpath "$ZIP_PATH")"
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

    echo "Fetching latest release (incl. pre-releases) from $ADDON_REPO..."
    # Newest non-draft release, whether a full release or a pre-release.
    release_tag=$(gh release list --repo "$ADDON_REPO" --limit 20 --json tagName,isDraft --jq '.[] | select(.isDraft == false) | .tagName' | head -1)

    if [[ -z "$release_tag" ]]; then
        echo "No published or pre-release found. Trying latest draft..."
        release_tag=$(gh release list --repo "$ADDON_REPO" --limit 1 --json tagName --jq '.[0].tagName')
    fi

    if [[ -z "$release_tag" ]]; then
        echo "Error: no releases found in $ADDON_REPO"
        exit 1
    fi

    echo "Downloading zip from release $release_tag..."
    gh release download "$release_tag" --repo "$ADDON_REPO" --pattern "${ADDON_ID}-*.zip" --dir "$cleanup_tmp"
    ZIP_PATH="$(ls "$cleanup_tmp"/${ADDON_ID}-*.zip | head -1)"
fi

filename="$(basename "$ZIP_PATH")"

# Parse: plugin.video.kofin-<ver>.zip
if [[ ! "$filename" =~ ^${ADDON_ID}-([0-9][0-9.]*)\.zip$ ]]; then
    echo "Error: $filename doesn't match expected pattern ${ADDON_ID}-<version>.zip"
    exit 1
fi
ver="${BASH_REMATCH[1]}"

echo "Adding Kofin (plugin) $ver to Kontell repository"
echo ""

# Copy to both omega and piers (pure Python — same zip works everywhere).
# generate_repo.py --prune (below) then keeps only the newest build.
for version_dir in omega piers; do
    dest_dir="$PAGES_DIR/$version_dir/$ADDON_ID"
    mkdir -p "$dest_dir"
    cp "$ZIP_PATH" "$dest_dir/$filename"
    echo "  -> $version_dir/$ADDON_ID/$filename"
done

echo ""
echo "Regenerating repository metadata..."
echo ""

python3 "$REPO_DIR/generate_repo.py" --pages-dir "$PAGES_DIR" --prune

echo ""
echo "Done. Review with 'git -C _site status', then publish with:"
echo "  ./scripts/publish.sh \"update plugin.video.kofin\""
