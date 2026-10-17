"""Release zips stay in the channel trees; pre-releases go under dev/ and leave when promoted."""

import importlib.util
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


update = load("update", "tools/update.py")
generate_repo = load("generate_repo", "generate_repo.py")


def kodi_zip(path, addon_id, version, floor=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    requires = (
        f'  <requires><import addon="xbmc.addon" version="{floor}"/></requires>\n'
        if floor
        else ""
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<addon id="{addon_id}" version="{version}" name="Fixture" provider-name="test">\n'
        f"{requires}"
        '  <extension point="xbmc.python.pluginsource" library="addon.py"/>\n'
        '  <extension point="xbmc.addon.metadata"><summary>t</summary></extension>\n'
        "</addon>\n"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{addon_id}/addon.xml", xml)
    return path


def release(tag, prerelease, day):
    return {
        "tagName": tag,
        "isDraft": False,
        "isPrerelease": prerelease,
        "publishedAt": f"2026-10-{day:02d}T00:00:00Z",
    }


def fake_github(releases, zips):
    """gh_json and download over {tag: zip path}; returns the download log."""
    downloaded = []

    def gh_json(*args):
        if args[1] == "list":
            return releases
        path = zips[args[2]]
        return {"assets": [{"name": path.name, "size": path.stat().st_size}]}

    def download(repo, tag, patterns, dest):
        downloaded.append(tag)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(zips[tag], dest / zips[tag].name)

    update.gh_json = gh_json
    update.download = download
    return downloaded


KOFIN = {
    "id": "plugin.video.kofin",
    "repo": "kontell/plugin.video.kofin",
    "model": "variant",
    "variants": {
        "sql": {"below": "0.90"},
        "api": {"from": "0.90", "below": "0.95"},
        "master": {"from": "0.95"},
    },
    "stable": {"omega": "sql", "piers": "sql", "kodi23": "master"},
    "dev": {"piers": "api", "kodi23": "master"},
}


class PrereleaseTreeTest(unittest.TestCase):
    def test_release_prerelease_and_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pages = root / "pages"
            pages.mkdir()
            zips = {
                "fixture.addon-1.0.0.zip": kodi_zip(
                    root / "zips" / "fixture.addon-1.0.0.zip", "fixture.addon", "1.0.0"
                ),
                "fixture.addon-2.0.0.zip": kodi_zip(
                    root / "zips" / "fixture.addon-2.0.0.zip", "fixture.addon", "2.0.0"
                ),
                "fixture.stable-1.0.0.zip": kodi_zip(
                    root / "zips" / "fixture.stable-1.0.0.zip", "fixture.stable", "1.0.0"
                ),
            }
            # A dev directory left behind for an add-on that has only a release.
            for channel in ("omega", "piers"):
                stale = pages / "dev" / channel / "fixture.stable"
                stale.mkdir(parents=True)
                shutil.copy(zips["fixture.stable-1.0.0.zip"], stale / "fixture.stable-9.0.0.zip")

            releases = {
                "kontell/fixture": [
                    {
                        "tagName": "v9",
                        "isDraft": True,
                        "isPrerelease": False,
                        "publishedAt": "2026-03-01T00:00:00Z",
                    },
                    {
                        "tagName": "v2",
                        "isDraft": False,
                        "isPrerelease": True,
                        "publishedAt": "2026-02-01T00:00:00Z",
                    },
                    {
                        "tagName": "v1",
                        "isDraft": False,
                        "isPrerelease": False,
                        "publishedAt": "2026-01-01T00:00:00Z",
                    },
                ],
                "kontell/stable": [
                    {
                        "tagName": "v1",
                        "isDraft": False,
                        "isPrerelease": False,
                        "publishedAt": "2026-01-01T00:00:00Z",
                    },
                ],
            }
            assets = {
                ("kontell/fixture", "v9"): [
                    {"name": "fixture.addon-9.0.0.zip", "size": 1}
                ],
                ("kontell/fixture", "v2"): [
                    {
                        "name": "fixture.addon-2.0.0.zip",
                        "size": zips["fixture.addon-2.0.0.zip"].stat().st_size,
                    }
                ],
                ("kontell/fixture", "v1"): [
                    {
                        "name": "fixture.addon-1.0.0.zip",
                        "size": zips["fixture.addon-1.0.0.zip"].stat().st_size,
                    }
                ],
                ("kontell/stable", "v1"): [
                    {
                        "name": "fixture.stable-1.0.0.zip",
                        "size": zips["fixture.stable-1.0.0.zip"].stat().st_size,
                    }
                ],
            }
            downloaded = []

            def gh_json(*args):
                if args[1] == "list":
                    repo = args[args.index("--repo") + 1]
                    return releases[repo]
                tag = args[2]
                repo = args[args.index("--repo") + 1]
                return {"assets": assets[(repo, tag)]}

            def download(repo, tag, patterns, dest):
                downloaded.append((repo, tag))
                dest.mkdir(parents=True, exist_ok=True)
                for asset in assets[(repo, tag)]:
                    name = asset["name"]
                    if name in zips:
                        shutil.copy(zips[name], dest / name)

            update.gh_json = gh_json
            update.download = download

            both = {"id": "fixture.addon", "repo": "kontell/fixture", "model": "shared"}
            stable_only = {
                "id": "fixture.stable",
                "repo": "kontell/stable",
                "model": "shared",
            }
            update.reconcile_kodi(both, root / "work-both", pages, False)
            update.reconcile_kodi(stable_only, root / "work-stable", pages, False)

            self.assertEqual(
                downloaded,
                [("kontell/fixture", "v1"), ("kontell/fixture", "v2"), ("kontell/stable", "v1")],
            )
            for channel in ("omega", "piers"):
                self.assertTrue(
                    (pages / channel / "fixture.addon" / "fixture.addon-1.0.0.zip").is_file()
                )
                self.assertTrue(
                    (pages / "dev" / channel / "fixture.addon" / "fixture.addon-2.0.0.zip").is_file()
                )
                self.assertFalse((pages / "dev" / channel / "fixture.stable").exists())
                self.assertTrue(
                    (pages / channel / "fixture.stable" / "fixture.stable-1.0.0.zip").is_file()
                )
            self.assertFalse(any("9.0.0" in path.name for path in pages.rglob("*.zip")))

            downloaded.clear()
            update.reconcile_kodi(both, root / "work-again", pages, False)
            self.assertEqual(downloaded, [])
            self.assertTrue(
                (pages / "dev" / "omega" / "fixture.addon" / "fixture.addon-2.0.0.zip").is_file()
            )

            # Promoting the pre-release makes it the newest release and clears dev/.
            releases["kontell/fixture"][1]["isPrerelease"] = False
            downloaded.clear()
            update.reconcile_kodi(both, root / "work-promoted", pages, False)

            self.assertEqual(downloaded, [("kontell/fixture", "v2")])
            for channel in ("omega", "piers"):
                stable_dir = pages / channel / "fixture.addon"
                self.assertEqual(
                    [path.name for path in stable_dir.glob("*.zip")],
                    ["fixture.addon-2.0.0.zip"],
                )
                self.assertFalse((pages / "dev" / channel / "fixture.addon").exists())

    def test_binary_channels_keep_their_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pages = root / "pages"
            pages.mkdir()
            names = {
                "bin.addon-21.1.0-linux-x86_64.zip": ("21.1.0", "omega"),
                "bin.addon-22.1.0-linux-x86_64.zip": ("22.1.0", "piers"),
                "bin.addon-21.2.0-linux-x86_64.zip": ("21.2.0", "dev/omega"),
                "bin.addon-22.2.0-linux-x86_64.zip": ("22.2.0", "dev/piers"),
            }
            zips = {
                name: kodi_zip(root / "zips" / name, "bin.addon", version)
                for name, (version, _channel) in names.items()
            }
            assets = {
                "v1": [
                    {"name": name, "size": zips[name].stat().st_size}
                    for name in (
                        "bin.addon-21.1.0-linux-x86_64.zip",
                        "bin.addon-22.1.0-linux-x86_64.zip",
                    )
                ],
                "v2": [
                    {"name": name, "size": zips[name].stat().st_size}
                    for name in (
                        "bin.addon-21.2.0-linux-x86_64.zip",
                        "bin.addon-22.2.0-linux-x86_64.zip",
                    )
                ],
            }
            releases = [
                {
                    "tagName": "v2",
                    "isDraft": False,
                    "isPrerelease": True,
                    "publishedAt": "2026-02-01T00:00:00Z",
                },
                {
                    "tagName": "v1",
                    "isDraft": False,
                    "isPrerelease": False,
                    "publishedAt": "2026-01-01T00:00:00Z",
                },
            ]

            def gh_json(*args):
                if args[1] == "list":
                    return releases
                return {"assets": assets[args[2]]}

            def download(repo, tag, patterns, dest):
                dest.mkdir(parents=True, exist_ok=True)
                for asset in assets[tag]:
                    shutil.copy(zips[asset["name"]], dest / asset["name"])

            update.gh_json = gh_json
            update.download = download
            update.reconcile_kodi(
                {
                    "id": "bin.addon",
                    "repo": "kontell/bin.addon",
                    "model": "binary",
                    "platforms": ["linux-x86_64"],
                },
                root / "work",
                pages,
                False,
            )
            self.assertTrue(
                (pages / "omega" / "bin.addon+linux-x86_64" / "bin.addon-21.1.0.zip").is_file()
            )
            self.assertTrue(
                (pages / "piers" / "bin.addon+linux-x86_64" / "bin.addon-22.1.0.zip").is_file()
            )
            self.assertTrue(
                (pages / "dev" / "omega" / "bin.addon+linux-x86_64" / "bin.addon-21.2.0.zip").is_file()
            )
            self.assertTrue(
                (pages / "dev" / "piers" / "bin.addon+linux-x86_64" / "bin.addon-22.2.0.zip").is_file()
            )
            self.assertFalse(
                (pages / "omega" / "bin.addon+linux-x86_64" / "bin.addon-21.2.0.zip").exists()
            )
            self.assertFalse(
                (pages / "dev" / "piers" / "bin.addon+linux-x86_64" / "bin.addon-22.1.0.zip").exists()
            )

    def test_variant_serves_each_channel_its_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pages = root / "pages"
            kofin = "plugin.video.kofin"
            zips = {
                "v0.29.1": kodi_zip(root / "z" / f"{kofin}-0.29.1.zip", kofin, "0.29.1"),
                "v0.29.2": kodi_zip(root / "z" / f"{kofin}-0.29.2.zip", kofin, "0.29.2"),
                "v0.93.5": kodi_zip(
                    root / "z" / f"{kofin}-0.93.5.zip", kofin, "0.93.5", "21.90.802"
                ),
                "v0.93.6": kodi_zip(
                    root / "z" / f"{kofin}-0.93.6.zip", kofin, "0.93.6", "21.90.802"
                ),
                "v0.95.0": kodi_zip(
                    root / "z" / f"{kofin}-0.95.0.zip", kofin, "0.95.0", "22.90.701"
                ),
            }
            # Publish order is not version order: the newest api pre-release by
            # date is the older one, and the master pre-release came out first.
            releases = [
                release("v0.93.5", True, 16),
                release("v0.29.2", False, 15),
                release("v0.93.6", True, 14),
                release("v0.95.0", True, 13),
                release("v0.29.1", False, 1),
            ]
            downloaded = fake_github(releases, zips)
            # What the shared model left in a channel kofin no longer serves.
            stale = pages / "dev" / "omega" / kofin / f"{kofin}-0.93.6.zip"
            stale.parent.mkdir(parents=True)
            shutil.copy(zips["v0.93.6"], stale)

            changed, pending = update.reconcile_kodi(KOFIN, root / "work", pages, False)

            self.assertIsNone(pending)
            served = sorted(
                str(path.relative_to(pages)) for path in pages.rglob("*.zip")
            )
            self.assertEqual(
                served,
                [
                    f"dev/kodi23/{kofin}/{kofin}-0.95.0.zip",
                    f"dev/piers/{kofin}/{kofin}-0.93.6.zip",
                    f"omega/{kofin}/{kofin}-0.29.2.zip",
                    f"piers/{kofin}/{kofin}-0.29.2.zip",
                ],
            )
            # One download per release, however many channels it serves.
            self.assertEqual(sorted(downloaded), ["v0.29.2", "v0.93.6", "v0.95.0"])

            downloaded.clear()
            changed, _ = update.reconcile_kodi(KOFIN, root / "again", pages, False)
            self.assertEqual((changed, downloaded), ([], []))

    def test_variant_refuses_a_zip_the_channel_cannot_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            kofin = "plugin.video.kofin"
            zips = {
                "v0.93.6": kodi_zip(
                    root / "z" / f"{kofin}-0.93.6.zip", kofin, "0.93.6", "21.90.802"
                ),
            }
            fake_github([release("v0.93.6", False, 1)], zips)
            wrong = dict(KOFIN, stable={"omega": "api"})
            with self.assertRaisesRegex(update.Problem, "would refuse it"):
                update.resolve_variant(wrong, root / "work", None, root / "pages")

    def test_variant_ranges_must_not_overlap_or_leave_a_release_out(self):
        overlap = dict(
            KOFIN,
            variants={"sql": {"below": "0.91"}, "api": {"from": "0.90"}},
        )
        with self.assertRaisesRegex(update.Problem, "overlap"):
            update.variant_ranges(overlap)
        gap = dict(
            KOFIN,
            variants={"sql": {"below": "0.90"}, "api": {"from": "0.91"}},
        )
        ranges = update.variant_ranges(gap)
        with self.assertRaisesRegex(update.Problem, "no variant's range"):
            update.variant_of(gap, ranges, "0.90.4")
        self.assertEqual(update.variant_of(KOFIN, update.variant_ranges(KOFIN), "0.94.40"), "api")
        self.assertEqual(update.variant_of(KOFIN, update.variant_ranges(KOFIN), "0.9.0"), "sql")

    def test_channels_limit_a_shared_addon(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pages = root / "pages"
            zips = {"v1": kodi_zip(root / "z" / "fix.addon-1.0.0.zip", "fix.addon", "1.0.0")}
            fake_github([release("v1", True, 1)], zips)
            stale = pages / "dev" / "kodi23" / "fix.addon" / "fix.addon-0.9.0.zip"
            stale.parent.mkdir(parents=True)
            shutil.copy(zips["v1"], stale)
            addon = {
                "id": "fix.addon",
                "repo": "kontell/fix",
                "model": "shared",
                "channels": ["omega", "piers"],
            }
            update.reconcile_kodi(addon, root / "work", pages, False)
            self.assertEqual(
                sorted(str(p.relative_to(pages)) for p in pages.rglob("*.zip")),
                [
                    "dev/omega/fix.addon/fix.addon-1.0.0.zip",
                    "dev/piers/fix.addon/fix.addon-1.0.0.zip",
                ],
            )

    def test_channel_lists_match_the_repository_addons(self):
        self.assertEqual(tuple(update.channel_ceilings("")), update.CHANNELS)
        self.assertEqual(tuple(update.channel_ceilings("dev")), update.CHANNELS)
        self.assertEqual(tuple(generate_repo.VERSION_DIRS), update.CHANNELS)
        self.assertEqual(
            tuple(generate_repo.DEV_VERSION_DIRS),
            tuple(f"dev/{channel}" for channel in update.CHANNELS),
        )
        self.assertEqual(set(update.CHANNEL_BY_KODI.values()), set(update.CHANNELS))

    def test_a_repository_addon_bump_is_a_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            pages = Path(tmp)
            unstaged = update.repository_addons_unstaged(pages)
            self.assertEqual(len(unstaged), 2 * len(update.CHANNELS))
            self.assertIn("in dev/kodi23/", unstaged[-1])
            generate_repo.main(["--pages-dir", str(pages)])
            self.assertEqual(update.repository_addons_unstaged(pages), [])

    def test_generate_repo_keeps_the_trees_apart(self):
        with tempfile.TemporaryDirectory() as tmp:
            pages = Path(tmp)
            for channel, name, version in (
                ("omega", "fixture.addon-1.0.0.zip", "1.0.0"),
                ("piers", "fixture.addon-1.0.0.zip", "1.0.0"),
                ("dev/omega", "fixture.addon-2.0.0.zip", "2.0.0"),
                ("dev/piers", "fixture.addon-2.0.0.zip", "2.0.0"),
            ):
                kodi_zip(
                    pages / channel / "fixture.addon" / name,
                    "fixture.addon",
                    version,
                )
            generate_repo.main(["--pages-dir", str(pages)])

            stable_xml = (pages / "omega" / "addons.xml").read_text(encoding="utf-8")
            dev_xml = (pages / "dev" / "piers" / "addons.xml").read_text(encoding="utf-8")
            self.assertIn("fixture.addon-1.0.0.zip", stable_xml)
            self.assertNotIn("fixture.addon-2.0.0.zip", stable_xml)
            self.assertIn("repository.kontell", stable_xml)
            self.assertNotIn("repository.kontell.dev", stable_xml)
            self.assertIn("fixture.addon-2.0.0.zip", dev_xml)
            self.assertNotIn("fixture.addon-1.0.0.zip", dev_xml)
            self.assertIn("repository.kontell.dev", dev_xml)
            with zipfile.ZipFile(pages / "repository.kontell.dev-1.0.1.zip") as archive:
                xml = archive.read("repository.kontell.dev/addon.xml").decode("utf-8")
            self.assertIn("dev/piers/addons.xml", xml)
            self.assertIn("dev/omega/addons.xml", xml)
            self.assertIn("dev/kodi23/addons.xml", xml)
            self.assertTrue((pages / "dev" / "omega" / "addons.xml.md5").is_file())
            self.assertIn(
                "repository.kontell.dev-1.0.1.zip",
                (pages / "index.html").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
