#!/bin/bash
set -euo pipefail

# Update the Kontell repository with fresh skin.contuary zips built from a
# local git checkout.
#
# Usage:
#   ./scripts/update-skin-contuary.sh [skin-repo-path]
#
# If no path is given, defaults to
#   /media/minipie/bluecon/docs/IT/devel/skins/skin.contuary
#
# This will:
#   1. For each branch (omega, piers): read addon.xml at the branch tip to
#      get the version, then `git archive` the branch into
#      <repo>/<branch>/skin.contuary/skin.contuary-<version>.zip.
#   2. Regenerate addons.xml + addons.xml.md5 for each branch dir.
#   3. Regenerate the repository installer zip.
#
# Older zips are left in place so users pinned to a specific version can
# still install; generate_repo.py picks the newest for addons.xml.
#
# Each branch's .gitattributes drives export-ignore — that is the only
# mechanism keeping CLAUDE.md / Screenshot.png / build scripts out of
# the released zip. Update both branches' .gitattributes if a new dev
# file needs excluding.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ADDON_ID="skin.contuary"
DEFAULT_SKIN_REPO="/media/minipie/bluecon/docs/IT/devel/skins/skin.contuary"

if [[ $# -ge 1 ]]; then
    SKIN_REPO="$(cd "$1" && pwd)"
else
    SKIN_REPO="$DEFAULT_SKIN_REPO"
fi

if [[ ! -d "$SKIN_REPO/.git" ]]; then
    echo "Error: $SKIN_REPO is not a git repository."
    exit 1
fi

extract_version() {
    # Read version="..." from <addon ...> in the given addon.xml content
    sed -n 's/.*<addon[^>]* version="\([^"]*\)".*/\1/p' | head -1
}

for branch in omega piers; do
    if ! git -C "$SKIN_REPO" rev-parse --verify --quiet "$branch" >/dev/null; then
        echo "Error: branch '$branch' not found in $SKIN_REPO"
        exit 1
    fi

    version="$(git -C "$SKIN_REPO" show "$branch:addon.xml" | extract_version)"
    if [[ -z "$version" ]]; then
        echo "Error: could not read version from $branch:addon.xml"
        exit 1
    fi

    dest_dir="$REPO_DIR/$branch/$ADDON_ID"
    mkdir -p "$dest_dir"
    zip_path="$dest_dir/${ADDON_ID}-${version}.zip"

    echo "Building $branch -> ${ADDON_ID}-${version}.zip"
    git -C "$SKIN_REPO" archive \
        --format=zip \
        --prefix="${ADDON_ID}/" \
        -o "$zip_path" \
        "$branch"
    echo "  -> $branch/$ADDON_ID/${ADDON_ID}-${version}.zip"
done

echo ""
echo "Regenerating repository metadata..."
echo ""

cd "$REPO_DIR"
python3 generate_repo.py

echo ""
echo "Done. Review changes and commit when ready."
