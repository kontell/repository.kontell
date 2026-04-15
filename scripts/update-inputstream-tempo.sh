#!/bin/bash
set -euo pipefail

# Update the Kontell repository with the latest inputstream.tempo release from
# GitHub.
#
# Usage:
#   ./scripts/update-inputstream-tempo.sh [zips-directory]
#
# If no directory is given, downloads zips from the latest GitHub release.
# Requires: gh (GitHub CLI), authenticated.
#
# This will:
#   1. Download release zips (or use provided directory)
#   2. Parse each zip filename to determine platform and Kodi version
#   3. Place zips into omega/ or piers/ subdirectories
#   4. Regenerate addons.xml and addons.xml.md5 for each version
#   5. Regenerate the repository installer zip

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ADDON_ID="inputstream.tempo"
ADDON_REPO="kontell/inputstream.tempo"

if [[ $# -ge 1 ]]; then
    ZIPS_DIR="$(cd "$1" && pwd)"
else
    # Download from latest GitHub release
    if ! command -v gh &>/dev/null; then
        echo "Error: gh (GitHub CLI) is required. Install it or pass a zips directory."
        exit 1
    fi

    ZIPS_DIR="$(mktemp -d)"
    trap "rm -rf $ZIPS_DIR" EXIT

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

    echo "Downloading zips from release $release_tag..."
    gh release download "$release_tag" --repo "$ADDON_REPO" --pattern "${ADDON_ID}-*.zip" --dir "$ZIPS_DIR"
    echo ""
fi

# Map kodi version to directory and branch name
kodi_dir() {
    case "$1" in
        21) echo "omega" ;;
        22) echo "piers" ;;
        *)  echo "Error: unknown Kodi version $1" >&2; exit 1 ;;
    esac
}

# Map os-arch to platform directory name
platform_dir() {
    local os="$1" arch="$2"
    echo "${ADDON_ID}+${os}-${arch}"
}

echo "Updating Kontell repository from $ZIPS_DIR"
echo ""

# Find all inputstream.tempo zips and process them
found=0
for zip in "$ZIPS_DIR"/${ADDON_ID}-*-kodi*.zip; do
    [[ -f "$zip" ]] || continue
    filename="$(basename "$zip")"

    # Parse: inputstream.tempo-<ver>-<os>-<arch>-kodi<N>.zip
    # Version may contain dots (e.g. 0.2.24). Use a tighter pattern.
    if [[ "$filename" =~ ^inputstream\.tempo-([0-9][0-9.]*)-([^-]+)-([^-]+)-kodi([0-9]+)\.zip$ ]]; then
        ver="${BASH_REMATCH[1]}"
        os="${BASH_REMATCH[2]}"
        arch="${BASH_REMATCH[3]}"
        kodi="${BASH_REMATCH[4]}"
    else
        echo "  Skipping $filename (unrecognized naming)"
        continue
    fi

    version_dir="$(kodi_dir "$kodi")"
    plat_dir="$(platform_dir "$os" "$arch")"
    dest_dir="$REPO_DIR/$version_dir/$plat_dir"
    dest_file="$dest_dir/${ADDON_ID}-${ver}.zip"

    mkdir -p "$dest_dir"

    # Remove old zips in this directory
    rm -f "$dest_dir"/${ADDON_ID}-*.zip

    cp "$zip" "$dest_file"
    echo "  $filename -> $version_dir/$plat_dir/${ADDON_ID}-${ver}.zip"
    found=$((found + 1))
done

if [[ $found -eq 0 ]]; then
    echo "Error: no ${ADDON_ID} zips found in $ZIPS_DIR"
    exit 1
fi

echo ""
echo "Placed $found zips. Regenerating repository metadata..."
echo ""

cd "$REPO_DIR"
python3 generate_repo.py

echo ""
echo "Done. Review changes and commit when ready."
