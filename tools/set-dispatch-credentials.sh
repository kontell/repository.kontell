#!/bin/bash
# Place the dispatch App's credentials on every add-on repo that has a forwarder.
#
# Usage: tools/set-dispatch-credentials.sh <app-id> <path-to-key.pem>
#
# `kontell` is a user account, not an organisation, so there are no org-level
# secrets to share one credential across repositories — each repo needs its own
# copy. This does that in one pass, and re-running it is how you rotate the key.
#
# The key is read from the file and piped to `gh secret set`, never passed as an
# argument: an argument would land in shell history and in the process list.
#
# Per repo it sets:
#   variable  REPO_DISPATCH_APP_ID            (not secret — an App id is public)
#   secret    REPO_DISPATCH_APP_PRIVATE_KEY
set -euo pipefail

APP_ID="${1:-}"
KEY_PATH="${2:-}"

if [[ -z "$APP_ID" || -z "$KEY_PATH" ]]; then
    # The header comment, up to but not including the first line of code.
    sed -n '2,/^[^#]/p' "$0" | sed '$d' | sed 's/^# \?//'
    exit 2
fi
if ! [[ "$APP_ID" =~ ^[0-9]+$ ]]; then
    echo "error: app-id should be numeric, got '$APP_ID'" >&2
    exit 1
fi
if [[ ! -f "$KEY_PATH" ]]; then
    echo "error: no such file: $KEY_PATH" >&2
    exit 1
fi
if ! grep -q 'BEGIN .*PRIVATE KEY' "$KEY_PATH"; then
    echo "error: $KEY_PATH does not look like a PEM private key" >&2
    exit 1
fi
if ! command -v gh >/dev/null; then
    echo "error: gh (GitHub CLI) is required" >&2
    exit 1
fi

# Every repo whose notify-repo.yml dispatches at this one. Keep in step with the
# forwarders; a repo missing here simply falls back to the scheduled reconcile.
REPOS=(
    kontell/plugin.video.kofin
    kontell/script.kofin.lyrics
    kontell/script.music.restore
    kontell/script.skin.contuary
    kontell/plugin.timeshiftsaver
    kontell/KoShelf
    kontell/skin.contuary
    kontell/pvr.kofin
    kontell/inputstream.tempo
)

echo "App id $APP_ID, key $KEY_PATH -> ${#REPOS[@]} repositories"
echo

failed=()
for repo in "${REPOS[@]}"; do
    printf '  %-34s ' "$repo"
    # A forwarder that is not on the default branch will never fire, so setting
    # credentials there achieves nothing — say so rather than pretending.
    branch="$(gh api "repos/$repo" --jq .default_branch 2>/dev/null || true)"
    if [[ -z "$branch" ]]; then
        echo "SKIP (cannot read repo)"
        failed+=("$repo")
        continue
    fi
    if ! gh api "repos/$repo/contents/.github/workflows/notify-repo.yml?ref=$branch" \
            --jq .name >/dev/null 2>&1; then
        echo "SKIP (no notify-repo.yml on $branch)"
        continue
    fi
    if gh variable set REPO_DISPATCH_APP_ID --repo "$repo" --body "$APP_ID" >/dev/null 2>&1 \
       && gh secret set REPO_DISPATCH_APP_PRIVATE_KEY --repo "$repo" < "$KEY_PATH" >/dev/null 2>&1; then
        echo "ok"
    else
        echo "FAILED"
        failed+=("$repo")
    fi
done

echo
if [[ ${#failed[@]} -gt 0 ]]; then
    echo "${#failed[@]} repo(s) failed: ${failed[*]}" >&2
    exit 1
fi
echo "Done. Verify by running the 'Notify repository' workflow by hand from any"
echo "add-on repo: it should mint a token and dispatch, and this repo's Publish run"
echo "should appear within seconds. Before this script it reported 'not configured'."
