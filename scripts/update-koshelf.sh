#!/bin/bash
set -euo pipefail

# Update the Kontell repository with the latest KoShelf zip.
#
# Usage:
#   ./scripts/update-koshelf.sh [zip-path]
#
# If no path is given, downloads from the latest GitHub release.
# Pass a zip file path or a directory containing the zip to use a local build.
# Requires: gh (GitHub CLI) for downloading from GitHub.
#
# KoShelf is pure Python, so the same zip is used for both Kodi 21 (omega)
# and Kodi 22 (piers) — no per-platform matrix.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ADDON_ID="plugin.audio.koshelf"
ADDON_REPO="kontell/KoShelf"

cleanup_tmp=""
trap '[[ -n "$cleanup_tmp" ]] && rm -rf "$cleanup_tmp"' EXIT

# Resolve a zip to copy
if [[ $# -ge 1 ]]; then
    arg="$1"
    if [[ -f "$arg" ]]; then
        ZIP_PATH="$(realpath "$arg")"
    elif [[ -d "$arg" ]]; then
        # Pick the latest koshelf zip in the directory
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

    echo "Fetching latest release from $ADDON_REPO..."
    release_tag=$(gh release list --repo "$ADDON_REPO" --limit 5 --json tagName,isDraft --jq '.[] | select(.isDraft == false) | .tagName' | head -1)

    if [[ -z "$release_tag" ]]; then
        echo "No published release found. Trying latest draft..."
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

# Parse: plugin.audio.koshelf-<ver>.zip
if [[ ! "$filename" =~ ^${ADDON_ID}-([0-9][0-9.]*)\.zip$ ]]; then
    echo "Error: $filename doesn't match expected pattern ${ADDON_ID}-<version>.zip"
    exit 1
fi
ver="${BASH_REMATCH[1]}"

echo "Adding KoShelf $ver to Kontell repository"
echo ""

# Copy to both omega and piers (pure Python — same zip works everywhere)
for version_dir in omega piers; do
    dest_dir="$REPO_DIR/$version_dir/$ADDON_ID"
    mkdir -p "$dest_dir"
    rm -f "$dest_dir"/${ADDON_ID}-*.zip
    cp "$ZIP_PATH" "$dest_dir/$filename"
    echo "  -> $version_dir/$ADDON_ID/$filename"
done

echo ""
echo "Regenerating repository metadata..."
echo ""

cd "$REPO_DIR"
python3 generate_repo.py

echo ""
echo "Done. Review changes and commit when ready."
