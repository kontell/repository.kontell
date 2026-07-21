#!/bin/bash
set -euo pipefail

# Update the Kontell Jellyfin plugin repository with the latest Kofin Sync Queue
# (jellyfin-plugin-kofinsyncqueue) build.
#
# NOTE: this is a JELLYFIN SERVER plugin, not a Kodi addon. It is served from
# the same published site as the Kodi repo but under jellyfin/, as its own
# Jellyfin plugin-repository manifest.json (built by generate_jellyfin_repo.py).
# See the README "Jellyfin plugins" section.
#
# Usage:
#   ./scripts/update-kofin-sync-queue.sh [zip-or-directory]
#
# If no argument is given, downloads from the latest GitHub release.
# Pass a zip file or a directory containing the zip to use a local build.
# Requires: gh (GitHub CLI) for downloading from GitHub.
#
# Pre-releases are included: the newest non-draft release is used, whether it is
# marked as a full release or a pre-release.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ADDON_REPO="kontell/jellyfin-plugin-kofinsyncqueue"
# Zips are named kofin-sync-queue_<4-part-version>.zip (underscore, unlike the
# hyphenated Kodi naming).
ZIP_GLOB="kofin-sync-queue_*.zip"

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
        # Pick the newest matching zip in the directory
        ZIP_PATH="$(ls -t "$arg"/$ZIP_GLOB 2>/dev/null | head -1 || true)"
        [[ -z "$ZIP_PATH" ]] && { echo "Error: no $ZIP_GLOB in $arg"; exit 1; }
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
    gh release download "$release_tag" --repo "$ADDON_REPO" --pattern "$ZIP_GLOB" --dir "$cleanup_tmp"
    ZIP_PATH="$(ls "$cleanup_tmp"/$ZIP_GLOB | head -1)"
fi

filename="$(basename "$ZIP_PATH")"

# Parse: kofin-sync-queue_<version>.zip
if [[ ! "$filename" =~ ^kofin-sync-queue_([0-9][0-9.]*)\.zip$ ]]; then
    echo "Error: $filename doesn't match expected pattern kofin-sync-queue_<version>.zip"
    exit 1
fi
ver="${BASH_REMATCH[1]}"

echo "Adding Kofin Sync Queue $ver to the Kontell Jellyfin plugin repository"
echo ""

# Jellyfin manifests carry version history, so we keep every build present and
# do not prune. Copy in the new zip (idempotent for a re-run of the same ver).
dest_dir="$PAGES_DIR/jellyfin"
mkdir -p "$dest_dir"
cp "$ZIP_PATH" "$dest_dir/$filename"
echo "  -> jellyfin/$filename"

echo ""
echo "Regenerating Jellyfin manifest..."
echo ""

python3 "$REPO_DIR/generate_jellyfin_repo.py" --pages-dir "$PAGES_DIR"

echo ""
echo "Done. Review with 'git -C _site status', then publish with:"
echo "  ./scripts/publish.sh \"update Kofin Sync Queue\""
