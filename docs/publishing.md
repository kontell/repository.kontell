# How the repository is published

Operational reference for `repository.kontell` itself. The README is for people
installing the add-ons; this is for whoever maintains the plumbing.

## The pipeline

Publishing is automatic. When an add-on's GitHub release is **published** (not
drafted), that repo's `notify-repo.yml` fires a `repository_dispatch` at this
one, and `.github/workflows/publish.yml` downloads the release assets,
regenerates the metadata and pushes `gh-pages`. A scheduled run every 30 minutes
reconciles anything a dispatch missed, so a dropped dispatch costs latency rather
than correctness.

Two things are worth knowing:

- **Publishing must be done by a human** (the GitHub UI, or `gh` with your own
  credentials). A release published by a workflow using the default
  `GITHUB_TOKEN` does not raise a `release` event, so the forwarder never fires.
  The scheduled reconcile is the backstop if that happens.
- **A draft release publishes nothing.** `tools/update.py` ignores drafts and
  pre-releases outright.

### Running it by hand

`addons.toml` is the list of what is served and where each thing comes from;
`tools/update.py` is the single code path that places release assets (it replaced
seven drifting `update-*.sh` scripts).

```bash
tools/update.py --all --dry-run          # what would change, writes nothing
tools/update.py --all                    # reconcile everything
tools/update.py pvr.kofin                # just one add-on
tools/update.py skin.contuary --from-dir ~/builds   # use a local build

python3 generate_repo.py --pages-dir _site          # Kodi addons.xml
python3 generate_jellyfin_repo.py --pages-dir _site # Jellyfin manifest.json
./scripts/publish.sh "why"                          # commit + push gh-pages
```

`update.py` prunes only the directories it wrote into, so a run that fails
partway cannot empty an unrelated one. `generate_repo.py --prune` still exists
for manual use, but the automated path does not pass it.

Adding an add-on is an entry in `addons.toml` plus a `notify-repo.yml` in its
repo. `model` says how its releases map onto the served tree — `shared` (one zip
for both Kodi versions), `dual` (per-channel tags), `binary` (per-platform zips),
or `jellyfin`. Binary add-ons also list the platform set a release must produce
in full before anything is placed.

### Configuring the dispatch App (one-off)

Until this is done the forwarders are **inert**: each logs a notice saying so and
succeeds, and the 30-minute reconcile keeps the repository correct. Instant
publishing is the only thing missing.

A GitHub App is used rather than a personal access token: it is scoped to this one
repository, and there is no expiry to re-issue.

1. **Create the App** — <https://github.com/organizations/kontell/settings/apps/new>
   - Name: `Kontell repository dispatch`; Homepage: this repo's URL.
   - Uncheck **Webhook → Active**.
   - Repository permissions: **Contents: Read and write**. Nothing else.
   - "Only on this account".
2. **Note the App ID**, then **Generate a private key** and download the `.pem`.
3. **Install it** — the App's *Install App* tab → `kontell` → **Only select
   repositories** → `repository.kontell`.
4. **Add the credentials as organisation-level values** so all add-on repos share
   one pair, at <https://github.com/organizations/kontell/settings/secrets/actions>:
   - Variable `REPO_DISPATCH_APP_ID` = the App ID.
   - Secret `REPO_DISPATCH_APP_PRIVATE_KEY` = the whole `.pem`, including the
     `-----BEGIN…` and `-----END…` lines.

   Or with the CLI:

   ```bash
   gh variable set REPO_DISPATCH_APP_ID --org kontell --body '<app-id>'
   gh secret   set REPO_DISPATCH_APP_PRIVATE_KEY --org kontell < key.pem
   ```

   Scope them to the add-on repositories that need them (the org UI's
   "Repository access", or `--visibility`).
5. **Check it** — run *Notify repository* by hand (`workflow_dispatch`) from any
   add-on repo. It should mint a token and dispatch; this repo's *Publish* run
   then appears within seconds.

Nothing here grants access to the add-on repos themselves: the App writes only to
`repository.kontell`, and the reconcile reads releases with the default token
because every source repo is public.
