#!/usr/bin/env python3
"""Place add-on release zips into the served tree.

Reads addons.toml, works out what each add-on's newest *published* release is,
downloads its assets and puts them where generate_repo.py expects them. Replaces
scripts/update-*.sh — seven copies of this logic that had drifted apart.

    tools/update.py --all                      # reconcile everything
    tools/update.py pvr.kofin skin.contuary    # just these
    tools/update.py plugin.video.kofin --from-dir ~/builds   # a local build
    tools/update.py --all --dry-run            # say what would change

Exit status is 0 when the tree is correct afterwards, whether or not anything
moved, and non-zero only on a real failure. That matters: this runs on a
schedule, and "nothing to do" is the common case.

Requires the `gh` CLI, authenticated. In Actions the default GITHUB_TOKEN is
enough — every source repo is public and only releases are read.

Two guards exist because this runs unattended:

* **Drafts and pre-releases are never published.** The shell scripts fell back to
  the newest draft when no published release existed. A human doing that has
  looked at it; a cron job has not.
* **A binary release must be complete.** If the platform set in addons.toml is
  not fully present, nothing is placed for that add-on. A partial placement is
  not corruption — each platform directory carries its own version and Kodi picks
  by platform — but it silently strands some platforms on an older build, and the
  failure is much cheaper to see here than to notice in the wild.

Nothing is written into the served tree until every asset for an add-on has been
downloaded and checked, so an interrupted run leaves the tree as it was.
"""

import argparse
import filecmp
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "addons.toml"

# Kodi major -> served directory. The repository addon.xml routes each Kodi
# version at one of these via <dir minversion/maxversion>.
CHANNEL_BY_KODI = {"21": "omega", "22": "piers"}
CHANNELS = ("omega", "piers")
JELLYFIN_DIR = "jellyfin"

VERSION = r"(?P<version>[0-9][0-9.]*)"
ARCH = r"(?P<os>[a-z]+)-(?P<arch>[a-z0-9_]+)"


class Problem(Exception):
    """A condition that should fail the run, with a message worth reading."""


class NotReleasedYet(Problem):
    """An add-on in the manifest that has nothing published to serve.

    Reported but not fatal. It is the ordinary state of an add-on added to
    addons.toml before its first release, and this runs on a schedule — failing
    every thirty minutes over a known-empty repo trains everyone to ignore the
    mail. A release that exists but is malformed or incomplete stays fatal.
    """


# --------------------------------------------------------------------------
# gh plumbing


def gh_json(*args):
    proc = subprocess.run(
        ["gh", *args], capture_output=True, text=True, encoding="utf-8"
    )
    if proc.returncode != 0:
        raise Problem(f"gh {' '.join(args)} failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout or "[]")


def published_releases(repo, limit=30):
    """Newest-first releases that are neither drafts nor pre-releases."""
    rows = gh_json(
        "release",
        "list",
        "--repo",
        repo,
        "--limit",
        str(limit),
        "--json",
        "tagName,isDraft,isPrerelease,publishedAt",
    )
    kept = [r for r in rows if not r.get("isDraft") and not r.get("isPrerelease")]
    kept.sort(key=lambda r: r.get("publishedAt") or "", reverse=True)
    return kept


def release_assets(repo, tag):
    """[{name, size}] for a release, from the API — nothing is downloaded.

    The size matters as much as the name. Together they are enough to decide
    whether the served tree is already current, which is what lets the common
    case skip the download entirely.
    """
    data = gh_json("release", "view", tag, "--repo", repo, "--json", "assets")
    return [{"name": a["name"], "size": a.get("size", 0)} for a in data.get("assets", [])]


def already_served(expected, pages):
    """True when every (relative path, size) in `expected` is already on disk.

    This is the fast exit. Without it a scheduled run downloads every asset of
    every add-on before discovering nothing changed — measured at ~169 MB per run
    for four add-ons, of which inputstream.tempo's Android zips are 147 MB. At a
    30-minute cadence that is several GB a day to learn nothing.

    Name and size come from the release API, which costs one call already being
    made. Size is what catches a release re-cut at the same version: the filename
    would match but the bytes would not. Bytes that differ at *identical* size
    would slip through, which is accepted — a rebuild that lands on the same
    length is not a case worth paying 169 MB a run to catch, and --force is there
    for when it is suspected.
    """
    for rel, size in expected:
        path = Path(pages) / rel
        if not path.exists():
            return False
        if size and path.stat().st_size != size:
            return False
    return True


def download(repo, tag, patterns, dest):
    dest.mkdir(parents=True, exist_ok=True)
    args = ["release", "download", tag, "--repo", repo, "--dir", str(dest)]
    for pattern in patterns:
        args += ["--pattern", pattern]
    proc = subprocess.run(
        ["gh", *args], capture_output=True, text=True, encoding="utf-8"
    )
    if proc.returncode != 0:
        raise Problem(
            f"downloading {tag} from {repo} failed: {proc.stderr.strip()}"
        )


# --------------------------------------------------------------------------
# zip validation


def verify_kodi_zip(path, addon_id):
    """A zip Kodi will accept: intact, and <id>/addon.xml at the top."""
    try:
        with zipfile.ZipFile(path) as archive:
            broken = archive.testzip()
            if broken is not None:
                raise Problem(f"{path.name} is corrupt at {broken}")
            if f"{addon_id}/addon.xml" not in archive.namelist():
                raise Problem(
                    f"{path.name} has no {addon_id}/addon.xml — Kodi needs the "
                    f"zip's top-level directory to be the addon id"
                )
    except zipfile.BadZipFile as exc:
        raise Problem(f"{path.name} is not a zip: {exc}") from exc


# --------------------------------------------------------------------------
# asset name parsing


def parse_shared(name, addon_id):
    m = re.fullmatch(rf"{re.escape(addon_id)}-{VERSION}\.zip", name)
    return m.group("version") if m else None


def parse_dual(name, addon_id):
    m = re.fullmatch(
        rf"{re.escape(addon_id)}-{VERSION}-(?P<channel>omega|piers)\.zip", name
    )
    return (m.group("version"), m.group("channel")) if m else None


def parse_binary(name, addon_id):
    """(version, platform, channel) for a binary asset, or None.

    Handles both naming schemes on purpose, because the archive holds both.

    Pre-renumbering names carry the channel as an explicit ``-kodi<N>`` suffix and
    a 0.x version that says nothing about Kodi, so there the suffix is the only
    source. Post-renumbering the version's major is authoritative and the suffix
    is gone — it was dropped precisely because two fields that must agree
    eventually will not.

    The transitional shape, a 21/22.x version *and* a suffix, exists for the first
    releases cut under the new numbering. Those are required to agree: the version
    wins, and a disagreement is refused rather than resolved, since guessing which
    field is right is how a Kodi 21 build reaches a Kodi 22 box.
    """
    m = re.fullmatch(
        rf"{re.escape(addon_id)}-{VERSION}-{ARCH}-kodi(?P<kodi>\d+)\.zip", name
    )
    if m:
        version = m.group("version")
        suffix_channel = CHANNEL_BY_KODI.get(m.group("kodi"))
        if suffix_channel is None:
            return None
        version_channel = CHANNEL_BY_KODI.get(version.split(".")[0])
        if version_channel is not None and version_channel != suffix_channel:
            raise Problem(
                f"{name} disagrees with itself: version {version} means "
                f"{version_channel} but the -kodi{m.group('kodi')} suffix means "
                f"{suffix_channel}. Refusing to guess — one of them would put the "
                f"build on the wrong Kodi."
            )
        # The version is authoritative where it carries a channel; the suffix is
        # only consulted for the older 0.x names that have nothing else.
        return version, f"{m.group('os')}-{m.group('arch')}", version_channel or suffix_channel

    m = re.fullmatch(rf"{re.escape(addon_id)}-{VERSION}-{ARCH}\.zip", name)
    if m:
        major = m.group("version").split(".")[0]
        channel = CHANNEL_BY_KODI.get(major)
        if channel is None:
            return None
        return m.group("version"), f"{m.group('os')}-{m.group('arch')}", channel
    return None


# --------------------------------------------------------------------------
# placement


class Placement:
    """One zip to copy, and where. Collected first, applied only if complete."""

    def __init__(self, src, channel, directory, filename):
        self.src = src
        self.channel = channel
        self.directory = directory
        self.filename = filename

    def dest(self, pages):
        return Path(pages) / self.channel / self.directory / self.filename

    def __repr__(self):
        return f"{self.channel}/{self.directory}/{self.filename}"


def apply(placements, pages, dry_run):
    """Copy each placement in, pruning older zips only from directories written.

    Pruning here rather than through generate_repo.py --prune keeps it scoped to
    what this run actually produced: a directory nobody touched keeps whatever it
    had, and cannot be emptied by a run that went wrong somewhere else.
    """
    changed = []
    for placement in placements:
        dest = placement.dest(pages)
        # Byte comparison, not size: a re-cut release keeps its version and so its
        # filename, and "same length" is not the same file. filecmp with
        # shallow=False reads both, which is cheap next to having downloaded them.
        if dest.exists() and filecmp.cmp(dest, placement.src, shallow=False):
            continue  # already published, identical bytes
        changed.append(placement)
        if dry_run:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(placement.src, dest)
        for old in dest.parent.glob("*.zip"):
            if old != dest:
                old.unlink()
    return changed


# --------------------------------------------------------------------------
# per-model resolution


def resolve_shared(addon, work, from_dir, pages):
    addon_id = addon["id"]
    if from_dir:
        zips = sorted(Path(from_dir).glob(f"{addon_id}-*.zip"))
        if not zips:
            raise Problem(f"no {addon_id}-*.zip in {from_dir}")
        src = zips[-1]
    else:
        releases = published_releases(addon["repo"])
        chosen, chosen_assets = None, []
        for release in releases:
            assets = release_assets(addon["repo"], release["tagName"])
            if any(parse_shared(a["name"], addon_id) for a in assets):
                chosen, chosen_assets = release, assets
                break
        if chosen is None:
            raise NotReleasedYet(
                f"no published release of {addon['repo']} carries a "
                f"{addon_id}-<version>.zip asset"
            )
        # Fast exit: the asset name carries the version and the API gave us its
        # size, so whether the tree is current is answerable without downloading.
        asset = next(a for a in chosen_assets if parse_shared(a["name"], addon_id))
        version = parse_shared(asset["name"], addon_id)
        expected = [
            (f"{channel}/{addon_id}/{addon_id}-{version}.zip", asset["size"])
            for channel in CHANNELS
        ]
        if already_served(expected, pages):
            return []
        download(addon["repo"], chosen["tagName"], [f"{addon_id}-*.zip"], work)
        zips = [p for p in work.glob(f"{addon_id}-*.zip") if parse_shared(p.name, addon_id)]
        if len(zips) != 1:
            raise Problem(f"expected one zip for {addon_id}, got {[p.name for p in zips]}")
        src = zips[0]

    version = parse_shared(src.name, addon_id)
    if not version:
        raise Problem(f"{src.name} does not match {addon_id}-<version>.zip")
    verify_kodi_zip(src, addon_id)
    # Pure Python: the same zip serves both Kodi versions.
    return [
        Placement(src, channel, addon_id, f"{addon_id}-{version}.zip")
        for channel in CHANNELS
    ]


def resolve_dual(addon, work, from_dir, pages):
    addon_id = addon["id"]
    placements = []
    if from_dir:
        for path in sorted(Path(from_dir).glob(f"{addon_id}-*.zip")):
            parsed = parse_dual(path.name, addon_id)
            if parsed:
                version, channel = parsed
                verify_kodi_zip(path, addon_id)
                placements.append(
                    Placement(path, channel, addon_id, f"{addon_id}-{version}.zip")
                )
        if not placements:
            raise Problem(
                f"no {addon_id}-<version>-<channel>.zip in {from_dir}"
            )
        return placements

    releases = published_releases(addon["repo"])
    if not any(r["tagName"].startswith(tuple(f"{c}/" for c in CHANNELS)) for r in releases):
        raise NotReleasedYet(
            f"no published {'/'.join(CHANNELS)} release of {addon['repo']}"
        )
    for channel in CHANNELS:
        chosen = next(
            (r for r in releases if r["tagName"].startswith(f"{channel}/")), None
        )
        if chosen is None:
            print(f"    {channel}: no published release, leaving as-is")
            continue
        assets = release_assets(addon["repo"], chosen["tagName"])
        parsed = [(a, parse_dual(a["name"], addon_id)) for a in assets]
        mine = [(a, pd) for a, pd in parsed if pd and pd[1] == channel]
        if mine and already_served(
            [(f"{channel}/{addon_id}/{addon_id}-{pd[0]}.zip", a["size"]) for a, pd in mine],
            pages,
        ):
            print(f"    {channel}: already current")
            continue
        cdir = work / channel
        download(addon["repo"], chosen["tagName"], [f"{addon_id}-*.zip"], cdir)
        found = False
        for path in sorted(cdir.glob(f"{addon_id}-*.zip")):
            parsed = parse_dual(path.name, addon_id)
            if not parsed:
                continue
            version, asset_channel = parsed
            if asset_channel != channel:
                raise Problem(
                    f"{chosen['tagName']} carries {path.name}, whose -{asset_channel} "
                    f"suffix contradicts the tag's {channel} prefix"
                )
            verify_kodi_zip(path, addon_id)
            placements.append(
                Placement(path, channel, addon_id, f"{addon_id}-{version}.zip")
            )
            found = True
        if not found:
            raise Problem(
                f"{chosen['tagName']} has no {addon_id}-<version>-{channel}.zip asset"
            )
    return placements


def resolve_binary(addon, work, from_dir, pages):
    addon_id = addon["id"]
    required = set(addon.get("platforms", []))
    placements = []
    # Channels whose served copy already matches the newest release, established
    # from asset names and sizes alone. They are held apart from by_channel, which
    # only ever holds material actually downloaded — conflating the two makes a
    # satisfied channel look like a release with zero platforms, and the
    # completeness check below then reports every platform missing.
    satisfied = set()

    def collect(paths):
        by_channel = {}
        for path in paths:
            parsed = parse_binary(path.name, addon_id)
            if not parsed:
                continue
            version, platform, channel = parsed
            by_channel.setdefault(channel, {})[platform] = (path, version)
        return by_channel

    if from_dir:
        by_channel = collect(sorted(Path(from_dir).glob(f"{addon_id}-*.zip")))
        if not by_channel:
            raise Problem(f"no recognisable {addon_id} platform zips in {from_dir}")
    else:
        releases = published_releases(addon["repo"])
        by_channel = {}
        for release in releases:
            assets = release_assets(addon["repo"], release["tagName"])
            names = [a["name"] for a in assets]
            channels = {
                parsed[2]
                for name in names
                if (parsed := parse_binary(name, addon_id))
            }
            # Newest-first, so the first release offering a channel wins it. This
            # covers both topologies: one release serving both channels before the
            # migration, and a per-channel tag after it.
            wanted = channels - set(by_channel) - satisfied
            if not wanted:
                continue
            # Would this tag's assets change anything? The names carry version and
            # platform and the API gave sizes, so this is answerable before paying
            # for the download — which for this add-on is ~150 MB a release.
            want_dests = {}
            for name in names:
                parsed = parse_binary(name, addon_id)
                if not parsed or parsed[2] not in wanted:
                    continue
                version, platform, channel = parsed
                size = next((a["size"] for a in assets if a["name"] == name), 0)
                want_dests.setdefault(channel, []).append(
                    (f"{channel}/{addon_id}+{platform}/{addon_id}-{version}.zip", size)
                )
            # Per channel, so one stale channel does not force the other's download.
            current = {c for c, d in want_dests.items() if already_served(d, pages)}
            for channel in sorted(current):
                print(f"    {channel}: already current")
            satisfied |= current
            if not (wanted - current):
                continue
            tagdir = work / release["tagName"].replace("/", "_")
            download(addon["repo"], release["tagName"], [f"{addon_id}-*.zip"], tagdir)
            for channel, platforms in collect(sorted(tagdir.glob("*.zip"))).items():
                if channel in satisfied:
                    continue
                by_channel.setdefault(channel, platforms)
            if set(by_channel) | satisfied >= set(CHANNELS):
                break
        if not by_channel and not satisfied:
            raise NotReleasedYet(
                f"no published release of {addon['repo']} carries recognisable "
                f"{addon_id} platform zips"
            )

    for channel, platforms in sorted(by_channel.items()):
        if required:
            missing = required - set(platforms)
            if missing:
                raise Problem(
                    f"{addon_id} {channel}: release is incomplete, missing "
                    f"{sorted(missing)}. Nothing placed for this add-on — a partial "
                    f"set would strand those platforms on an older build while the "
                    f"rest advertise the new version."
                )
        for platform, (path, version) in sorted(platforms.items()):
            verify_kodi_zip(path, addon_id)
            placements.append(
                Placement(
                    path, channel, f"{addon_id}+{platform}", f"{addon_id}-{version}.zip"
                )
            )
    return placements


def resolve_jellyfin(addon, work, from_dir, pages, dry_run):
    """A Jellyfin server plugin: every zip in the release into jellyfin/.

    *Every* zip, not the newest one. A plugin built for more than one server
    line ships one zip per ABI in a single release — syncplay-v2_10.11.0.3.zip
    and syncplay-v2_12.0.0.3.zip — because Jellyfin serves one manifest in which
    each entry carries its own targetAbi and the server picks the highest it can
    run. Taking only the last of a sorted list would place 12.0.0.3 and drop the
    10.11 build, and the shape of that failure is what makes it worth spelling
    out: nothing raises. already_served correctly sees the set as incomplete and
    re-downloads every run, one zip lands, the run reports success, and the
    manifest quietly stops offering the line most servers are actually on.
    """
    glob = addon.get("asset_glob", f"{addon['id']}_*.zip")
    if from_dir:
        zips = sorted(Path(from_dir).glob(glob))
        if not zips:
            raise Problem(f"no {glob} in {from_dir}")
    else:
        releases = published_releases(addon["repo"])
        if not releases:
            raise NotReleasedYet(f"no published release of {addon['repo']}")
        # Same fast exit as the Kodi models: the served filename is the asset's
        # own name, so name plus size answers "is this current?" for free.
        assets = release_assets(addon["repo"], releases[0]["tagName"])
        matching = [a for a in assets if fnmatch.fnmatch(a["name"], glob)]
        if matching and already_served(
            [(f"{JELLYFIN_DIR}/{a['name']}", a["size"]) for a in matching], pages
        ):
            return []
        download(addon["repo"], releases[0]["tagName"], [glob], work)
        zips = sorted(work.glob(glob))
        if not zips:
            raise Problem(f"{releases[0]['tagName']} has no {glob} asset")

    # Validate the whole set before placing any of it, so a release with one bad
    # zip does not leave half its ABIs served and half not.
    for src in zips:
        # Validated by its own meta.json, not addon.xml — Jellyfin, not Kodi.
        with zipfile.ZipFile(src) as archive:
            if "meta.json" not in archive.namelist():
                raise Problem(f"{src.name} has no meta.json at its root")

    placed = []
    for src in zips:
        dest = Path(pages) / JELLYFIN_DIR / src.name
        if dest.exists() and filecmp.cmp(dest, src, shallow=False):
            continue
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        placed.append(f"{JELLYFIN_DIR}/{src.name}")
    return placed


RESOLVERS = {
    "shared": resolve_shared,
    "dual": resolve_dual,
    "binary": resolve_binary,
}


# --------------------------------------------------------------------------


def resolve_pages_dir(explicit):
    if explicit:
        return Path(explicit).resolve()
    worktree = ROOT / "_site"
    if worktree.is_dir():
        return worktree
    raise Problem(
        "no _site/ worktree and no --pages-dir. See the README 'Publishing' "
        "section, or pass --pages-dir."
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("ids", nargs="*", help="add-on ids from addons.toml")
    parser.add_argument("--all", action="store_true", help="every add-on")
    parser.add_argument("--from-dir", help="use local zips instead of GitHub releases")
    parser.add_argument("--pages-dir", help="served tree (default: ./_site)")
    parser.add_argument(
        "--dry-run", action="store_true", help="report changes, write nothing"
    )
    args = parser.parse_args(argv)

    if not args.all and not args.ids:
        parser.error("give one or more add-on ids, or --all")

    manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    addons = manifest["addon"]
    known = {a["id"]: a for a in addons}
    if args.all:
        selected = addons
    else:
        unknown = [i for i in args.ids if i not in known]
        if unknown:
            parser.error(
                f"not in addons.toml: {', '.join(unknown)}. "
                f"Known: {', '.join(sorted(known))}"
            )
        selected = [known[i] for i in args.ids]
    if args.from_dir and len(selected) > 1:
        parser.error("--from-dir takes one add-on at a time")

    pages = resolve_pages_dir(args.pages_dir)
    print(f"Serving tree: {pages}")
    if args.dry_run:
        print("(dry run — nothing will be written)")

    all_changed, failures, pending = [], [], []
    with tempfile.TemporaryDirectory(prefix="kontell-update-") as tmp:
        work_root = Path(tmp)
        for addon in selected:
            addon_id, model = addon["id"], addon["model"]
            print(f"\n{addon_id} ({model}) from {addon['repo']}")
            work = work_root / addon_id
            work.mkdir(parents=True, exist_ok=True)
            try:
                if model == "jellyfin":
                    changed = resolve_jellyfin(
                        addon, work, args.from_dir, pages, args.dry_run
                    )
                    for item in changed:
                        print(f"    -> {item}")
                    all_changed.extend(changed)
                    continue
                resolver = RESOLVERS.get(model)
                if resolver is None:
                    raise Problem(f"unknown model {model!r}")
                placements = resolver(addon, work, args.from_dir, pages)
                changed = apply(placements, pages, args.dry_run)
                for placement in changed:
                    print(f"    -> {placement}")
                if not changed:
                    print("    already current")
                all_changed.extend(str(p) for p in changed)
            except NotReleasedYet as exc:
                print(f"    not released yet: {exc}")
                pending.append(f"{addon_id}: {exc}")
            except Problem as exc:
                print(f"    FAILED: {exc}", file=sys.stderr)
                failures.append(f"{addon_id}: {exc}")

    print()
    if all_changed:
        print(f"{len(all_changed)} file(s) {'would change' if args.dry_run else 'changed'}")
    else:
        print("nothing to do — the tree is already current")

    # Surfaced for the workflow: it regenerates and commits only when something
    # moved, so an unchanged run costs no Pages deploy.
    if out := os.environ.get("GITHUB_OUTPUT"):
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(f"changed={'true' if all_changed else 'false'}\n")
            handle.write(f"count={len(all_changed)}\n")

    if pending:
        print(f"\n{len(pending)} add-on(s) have nothing published yet:")
        for item in pending:
            print(f"  {item}")

    if failures:
        print(f"\n{len(failures)} add-on(s) failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Problem as exc:
        sys.exit(f"error: {exc}")
