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
publishing is the only thing missing, so none of this is urgent.

**`kontell` is a user account, not an organisation.** That matters here: there are
no organisation-level secrets to share one credential across repositories, so the
pair has to be set on **each add-on repo** that carries a `notify-repo.yml`. Nine
of them, at the time of writing. `tools/set-dispatch-credentials.sh` does that in
one pass.

A GitHub App is still preferred over a personal access token: the token it mints is
short-lived, scoped to `repository.kontell` alone, and there is no expiry to
re-issue. The cost is two values per repo instead of one.

1. **Create the App** — <https://github.com/settings/apps/new>
   (a user account's App settings; there is no `/organizations/kontell/` path).
   - Name: `Kontell repository dispatch`; Homepage: this repo's URL.
   - Uncheck **Webhook → Active**.
   - Repository permissions: **Contents: Read and write**. Nothing else.
   - "Only on this account".
2. **Note the App ID**, then **Generate a private key** and download the `.pem`.
   Keep it out of any repository and out of your shell history.
3. **Install it** — the App's *Install App* tab → `kontell` → **Only select
   repositories** → `repository.kontell`. Nothing else needs it: the App only ever
   writes to this repo, and the reconcile reads the add-on releases with the
   default token because every source repo is public.
4. **Place the credentials** in every repo with a forwarder:

   ```bash
   tools/set-dispatch-credentials.sh <app-id> /path/to/key.pem
   ```

   It pipes the key from the file rather than taking it as an argument, so the key
   never reaches your shell history or a process listing. Per repo it sets:
   - variable `REPO_DISPATCH_APP_ID`
   - secret `REPO_DISPATCH_APP_PRIVATE_KEY`
5. **Check it** — run *Notify repository* by hand (`workflow_dispatch`) from any
   add-on repo. It should mint a token and dispatch; this repo's *Publish* run
   appears within seconds. Before step 4 the same run reports "not configured" and
   succeeds, which is the difference to look for.

#### If you would rather not

Two smaller options, both legitimate:

- **Do nothing.** The scheduled reconcile already keeps the repository correct
  within 30 minutes of a release being published, needs no credentials anywhere,
  and is the fallback even when the App *is* configured.
- **A fine-grained PAT** scoped to `repository.kontell` with Contents: write — one
  secret per repo instead of two values, but it expires and has to be rotated. The
  forwarder would need its `create-github-app-token` step swapped for a plain
  `GH_TOKEN: ${{ secrets.REPO_DISPATCH_TOKEN }}`.

Whichever you choose, remember that a release published by a workflow using the
default `GITHUB_TOKEN` raises no `release` event, so the draft has to be published
by a human or with your own credentials for the forwarder to fire at all.
