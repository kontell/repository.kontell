#!/usr/bin/env python3
"""
Generate manifest.json for the Kontell Jellyfin plugin repository.

This is the Jellyfin-server counterpart to generate_repo.py (which builds the
Kodi addons.xml). A Jellyfin server adds a *repository* by URL (Dashboard ->
Plugins -> Repositories); the server then fetches a single manifest.json listing
each plugin and its versions, downloads the chosen version's zip from its
`sourceUrl`, and verifies it against the MD5 `checksum` in the manifest.

Kodi and Jellyfin are different consumers with incompatible manifest formats, so
they live as separate trees under the same published site:

  _site/
    omega/ piers/ ...        (Kodi: addons.xml, built by generate_repo.py)
    jellyfin/                (Jellyfin: manifest.json, built by THIS script)
      manifest.json
      kofin-sync-queue_1.0.0.0.zip

Each plugin zip carries a meta.json at its root (written by the plugin's own
tools/package.sh) with guid/name/overview/description/owner/category/targetAbi/
timestamp/version -- exactly the fields the manifest needs. So this script reads
them straight from the zip (just as generate_repo.py reads addon.xml out of the
Kodi zip). The only fields it computes are the download `sourceUrl` (base URL +
filename) and the MD5 `checksum`.

Usage: python3 generate_jellyfin_repo.py [--pages-dir DIR] [--base-url URL]

The served tree (jellyfin/manifest.json) is written under --pages-dir, which
defaults to ./_site (the gh-pages worktree) when present, or the script's own
directory otherwise.
"""

import argparse
import hashlib
import json
import os
import zipfile

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
JELLYFIN_DIR = "jellyfin"

# Public base URL a Jellyfin server resolves each sourceUrl against. This is the
# same Cloudflare Worker that fronts the Kodi repo -- a transparent pass-through
# to GitHub Pages -- so plugin downloads are logged alongside addon traffic.
# Keep this in step with the <datadir> host in addon.xml.
DEFAULT_BASE_URL = "https://repository.kontell.workers.dev"


def _version_key(version):
    """Sort key for a dotted version ('1.0.0.0') -> tuple of ints, so
    newest-first sorting is numeric ('1.0.10.0' > '1.0.9.0'). Non-numeric
    parts degrade to 0 rather than raising."""
    return tuple(int(p) if p.isdigit() else 0 for p in version.split("."))


def read_meta(zip_path):
    """Return the meta.json dict from a plugin zip, or None if absent/broken."""
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            meta_name = next(
                (n for n in z.namelist() if n.rsplit("/", 1)[-1] == "meta.json"),
                None,
            )
            if not meta_name:
                print(f"  Warning: no meta.json in {os.path.basename(zip_path)}")
                return None
            return json.loads(z.read(meta_name).decode("utf-8"))
    except Exception as e:
        print(f"  Warning: failed to read {os.path.basename(zip_path)}: {e}")
        return None


def md5_file(path):
    """MD5 hex digest of a file -- the checksum Jellyfin verifies a plugin zip
    against before installing it."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(jellyfin_dir, base_url):
    """Scan jellyfin_dir for plugin zips and return the manifest list.

    Zips are grouped by plugin guid; every zip present becomes a version entry
    (sorted newest-first). Unlike the Kodi side we do NOT prune to the latest
    build -- a Jellyfin manifest is meant to carry the version history so a
    server can pick a build compatible with its ABI.
    """
    zips = sorted(f for f in os.listdir(jellyfin_dir) if f.endswith(".zip"))
    plugins = {}   # guid -> plugin dict
    order = []     # first-seen guid order, for stable manifest output

    for filename in zips:
        path = os.path.join(jellyfin_dir, filename)
        meta = read_meta(path)
        if not meta:
            continue
        guid = meta.get("guid")
        if not guid:
            print(f"  Warning: {filename} meta.json has no guid, skipping")
            continue

        version_entry = {
            "version": meta.get("version", ""),
            # meta.json carries no changelog today; surface it if a future
            # package.sh adds one rather than hard-coding "".
            "changelog": meta.get("changelog", ""),
            "targetAbi": meta.get("targetAbi", ""),
            "sourceUrl": f"{base_url.rstrip('/')}/{JELLYFIN_DIR}/{filename}",
            "checksum": md5_file(path),
            "timestamp": meta.get("timestamp", ""),
        }

        if guid not in plugins:
            order.append(guid)
            plugins[guid] = {
                "guid": guid,
                "category": meta.get("category", "General"),
                "name": meta.get("name", ""),
                "overview": meta.get("overview", ""),
                "description": meta.get("description", ""),
                "owner": meta.get("owner", ""),
                "imageUrl": meta.get("imageUrl", ""),
                "versions": [],
            }
        plugins[guid]["versions"].append(version_entry)
        print(f"  {filename}: {meta.get('name')} {version_entry['version']} "
              f"(abi {version_entry['targetAbi']}, md5={version_entry['checksum']})")

    for guid in plugins:
        plugins[guid]["versions"].sort(
            key=lambda v: _version_key(v["version"]), reverse=True)

    return [plugins[g] for g in order]


def resolve_pages_dir(explicit):
    """Where the served tree is written: --pages-dir if given, else the _site
    gh-pages worktree when present, else the source dir (legacy checkout)."""
    if explicit:
        return os.path.abspath(explicit)
    worktree = os.path.join(SOURCE_DIR, "_site")
    return worktree if os.path.isdir(worktree) else SOURCE_DIR


def main():
    parser = argparse.ArgumentParser(
        description="Generate the Kontell Jellyfin plugin repository manifest.")
    parser.add_argument(
        "--pages-dir",
        help="Directory holding the served site (its jellyfin/ subdir is read "
             "and manifest.json written there). Defaults to ./_site when "
             "present, else the script's own directory.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Public base URL each sourceUrl is built from (default: %(default)s).",
    )
    args = parser.parse_args()

    pages_dir = resolve_pages_dir(args.pages_dir)
    jellyfin_dir = os.path.join(pages_dir, JELLYFIN_DIR)
    if not os.path.isdir(jellyfin_dir):
        print(f"  {JELLYFIN_DIR}/ not found under {pages_dir}; nothing to do.")
        return

    print(f"Generating Jellyfin manifest into {jellyfin_dir} ...")
    manifest = build_manifest(jellyfin_dir, args.base_url)

    out_path = os.path.join(jellyfin_dir, "manifest.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4, ensure_ascii=False)
        f.write("\n")

    n_versions = sum(len(p["versions"]) for p in manifest)
    print(f"  manifest.json: {len(manifest)} plugin(s), {n_versions} version(s)")
    print("Done.")


if __name__ == "__main__":
    main()
