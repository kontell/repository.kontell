#!/usr/bin/env python3
"""
Generate addons.xml and addons.xml.md5 for the Kontell repository.
Also creates the repository addon zip.

Directory layout:
  omega/                           (Kodi 21)
    pvr.kofin+linux-x86_64/pvr.kofin-0.2.3.zip
    pvr.kofin+android-armv7/pvr.kofin-0.2.3.zip
    ...
    addons.xml
    addons.xml.md5
  piers/                           (Kodi 22)
    pvr.kofin+linux-x86_64/pvr.kofin-0.2.3.zip
    ...
    addons.xml
    addons.xml.md5

Each version directory gets its own addons.xml with per-platform entries.
The repository addon.xml uses <dir> elements with minversion/maxversion
to route each Kodi version to the correct addons.xml.

When browsing a repository (as opposed to installing a zip directly), Kodi
fetches an addon's icon/fanart/screenshots over HTTP from the server next to
the zip -- it does NOT open the zip. So this script also extracts each addon's
declared <assets> out of the zip and writes them alongside the zip, and it
fills in <news> (the only changelog source for repo browsing) from the addon's
changelog.txt when the addon.xml doesn't provide one.

Usage: python3 generate_repo.py [--pages-dir DIR]

The served site (omega/, piers/, the installer zip and index.html) is written
to --pages-dir, which defaults to ./_site (the gh-pages worktree) when present,
or the script's own directory otherwise. addon.xml is always read from the
script's directory (the source).
"""

import argparse
import hashlib
import os
import re
import zipfile
from xml.sax.saxutils import escape

# Directory holding the source (this script and addon.xml). The *served* content
# (omega/, piers/, the installer zip, index.html) is published to a separate
# location given by --pages-dir -- the gh-pages worktree. They coincide only in
# a legacy all-in-one checkout.
SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_DIRS = ["omega", "piers"]

# Art that Kodi recognises by convention at the addon root, used when an
# addon.xml declares no <assets> block of its own.
CONVENTIONAL_ART = [("icon", "icon.png"), ("fanart", "fanart.jpg")]


def _version_key(filename):
    """Sort key for addon zip filenames: tuple of int parts of the version.

    Ensures `0.3.10 > 0.3.8`, where lexicographic sort would put `0.3.8`
    higher because `"0.3.10"` starts with `"0.3.1"` and `"1" < "8"`.
    Files that don't match the expected name fall to the bottom.
    """
    m = re.search(r'-([0-9][0-9.]*)\.zip$', filename)
    if not m:
        return ()
    return tuple(int(x) for x in m.group(1).split('.'))


def platform_from_dir_name(dir_name):
    """Derive the Kodi platform tag from an addon+platform directory name.

    E.g. 'pvr.kofin+linux-x86_64' -> 'linux-x86_64'
         'pvr.kofin+android-armv7' -> 'android-armv7'

    Kodi needs arch-specific tags (linux-x86_64, linux-aarch64) to
    distinguish binaries. The cmake build system only sets 'linux' or
    'android', so we override based on the directory name.
    """
    if "+" in dir_name:
        return dir_name.split("+", 1)[1]
    return None


def parse_declared_assets(xml):
    """Return [(art_type, relative_path)] declared in the <assets> block.

    E.g. <assets><icon>icon.png</icon><screenshot>resources/s1.jpg</screenshot>
    -> [('icon', 'icon.png'), ('screenshot', 'resources/s1.jpg')]
    Returns [] if there is no <assets> block.
    """
    m = re.search(r'<assets>(.*?)</assets>', xml, re.DOTALL)
    if not m:
        return []
    return [
        (tag, path.strip())
        for tag, path in re.findall(r'<(\w+)>\s*([^<]+?)\s*</\1>', m.group(1))
    ]


def latest_changelog_entry(text):
    """Return the newest entry of a changelog: the text up to the first blank
    line. The project changelogs list the newest version first, one entry per
    version, separated by blank lines."""
    text = text.replace("\r\n", "\n").strip()
    return re.split(r'\n[ \t]*\n', text, maxsplit=1)[0].strip()


def inject_into_metadata(xml, snippet):
    """Insert `snippet` immediately after the <xbmc.addon.metadata> open tag."""
    m = re.search(r'(<extension\s+point="xbmc\.addon\.metadata"[^>]*>)', xml)
    if not m:
        return xml
    return xml[:m.end()] + "\n" + snippet + xml[m.end():]


def inject_path(xml, path_element):
    """Insert the <path> element into the metadata extension if not present."""
    if "<path>" in xml:
        return xml
    xml = xml.replace(
        "</extension>\n</addon>",
        f"    {path_element}\n  </extension>\n</addon>",
    )
    if path_element not in xml:
        xml = re.sub(r'(</assets>\s*)', rf'\1    {path_element}\n    ', xml)
    return xml


def process_addon_zip(zip_path, dest_dir, platform_dir_name):
    """Read addon.xml from a zip and return its repository entry XML.

    Side effects (so repository *browsing* shows the same metadata as a direct
    zip install):
      * extracts the addon's declared art assets (icon/fanart/screenshots),
        or conventional root-level icon.png/fanart.jpg, into `dest_dir`;
      * injects an <assets> block when art exists but wasn't declared;
      * injects <news> from changelog.txt when the addon.xml has none.

    Also fixes the <platform> tag to be arch-specific and injects <path>.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            names = set(z.namelist())
            xml_name = next(
                (n for n in names if n.endswith("/addon.xml") and n.count("/") == 1),
                None,
            )
            if not xml_name:
                print(f"  Warning: no addon.xml in {zip_path}")
                return None
            prefix = xml_name[: xml_name.index("/")]  # zip's top-level dir == addon id

            xml = z.read(xml_name).decode("utf-8")
            xml = re.sub(r'<\?xml[^>]+\?>\s*', '', xml).strip()

            # Fix <platform> tag to be arch-specific.
            target_platform = platform_from_dir_name(platform_dir_name)
            if target_platform:
                xml = re.sub(
                    r'<platform>[^<]+</platform>',
                    f'<platform>{target_platform}</platform>',
                    xml,
                )

            # --- Art assets: publish them next to the zip on the server ---
            assets = parse_declared_assets(xml)
            declared = bool(assets)
            if not assets:
                # No <assets> block: fall back to conventional root art.
                assets = [
                    (art_type, rel)
                    for art_type, rel in CONVENTIONAL_ART
                    if f"{prefix}/{rel}" in names
                ]

            extracted = 0
            for art_type, rel in assets:
                member = f"{prefix}/{rel}"
                if member not in names:
                    print(f"    Warning: {os.path.basename(zip_path)} references "
                          f"{art_type} '{rel}' but {member} is missing from the zip")
                    continue
                out_path = os.path.join(dest_dir, *rel.split("/"))
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, "wb") as f:
                    f.write(z.read(member))
                extracted += 1

            # If art exists but the author didn't declare it, declare it so Kodi
            # actually fetches it when browsing the repo.
            if assets and not declared:
                block = ("    <assets>\n"
                         + "".join(f"      <{t}>{p}</{t}>\n" for t, p in assets)
                         + "    </assets>")
                xml = inject_into_metadata(xml, block)

            # --- Changelog: <news> is the only source when browsing a repo ---
            injected_news = False
            if "<news>" not in xml and f"{prefix}/changelog.txt" in names:
                changelog = z.read(f"{prefix}/changelog.txt").decode("utf-8", "replace")
                latest = latest_changelog_entry(changelog)
                if latest:
                    xml = inject_into_metadata(xml, f"    <news>{escape(latest)}</news>")
                    injected_news = True

            # --- Path to the zip, relative to the version dir (datadir) ---
            zip_filename = os.path.basename(zip_path)
            xml = inject_path(xml, f"<path>{platform_dir_name}/{zip_filename}</path>")

            notes = []
            if extracted:
                notes.append(f"{extracted} asset(s)")
            if assets and not declared:
                notes.append("auto-declared <assets>")
            if injected_news:
                notes.append("<news> from changelog")
            if notes:
                print(f"    {platform_dir_name}: {', '.join(notes)}")

            return xml
    except Exception as e:
        print(f"  Warning: Failed to process {zip_path}: {e}")
    return None


def generate_addons_xml(version_dir, pages_dir):
    """Generate addons.xml for a version directory (omega or piers)."""
    base_dir = os.path.join(pages_dir, version_dir)
    if not os.path.isdir(base_dir):
        return

    addon_dirs = sorted(
        name for name in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, name))
    )

    if not addon_dirs:
        print(f"  {version_dir}: no addon directories found")
        return

    addon_xmls = []
    for dir_name in addon_dirs:
        dir_path = os.path.join(base_dir, dir_name)
        zips = sorted(
            [f for f in os.listdir(dir_path) if f.endswith(".zip")],
            key=_version_key,
            reverse=True,
        )
        if not zips:
            continue

        xml = process_addon_zip(os.path.join(dir_path, zips[0]), dir_path, dir_name)
        if xml:
            addon_xmls.append(xml)

    if not addon_xmls:
        print(f"  {version_dir}: no addon entries found")
        return

    content = '<?xml version="1.0" encoding="UTF-8"?>\n<addons>\n'
    for xml in addon_xmls:
        content += xml + "\n"
    content += "</addons>\n"

    xml_path = os.path.join(base_dir, "addons.xml")
    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(content)

    md5 = hashlib.md5(content.encode("utf-8")).hexdigest()
    with open(xml_path + ".md5", "w", encoding="utf-8") as f:
        f.write(md5)

    print(f"  {version_dir}: {len(addon_xmls)} entry/entries, md5={md5}")


def read_repo_version():
    """Read the repository addon version from the source addon.xml."""
    with open(os.path.join(SOURCE_DIR, "addon.xml"), "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r'<addon[^>]+version="([^"]+)"', content)
    return match.group(1) if match else "1.0.0"


def generate_repo_zip(pages_dir, version):
    """Create the repository addon installer zip in the published site."""
    addon_xml = os.path.join(SOURCE_DIR, "addon.xml")
    zip_name = f"repository.kontell-{version}.zip"
    zip_path = os.path.join(pages_dir, zip_name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(addon_xml, "repository.kontell/addon.xml")

    print(f"  Repository zip: {zip_name}")


def generate_index_html(pages_dir, version):
    """Write the landing page linking to the installer zip (served at root)."""
    zip_name = f"repository.kontell-{version}.zip"
    html = (
        "<html>\n"
        "<head><title>Kontell Repository</title></head>\n"
        "<body>\n"
        "<h1>Kontell Repository</h1>\n"
        f'<a href="{zip_name}">{zip_name}</a>\n'
        "</body>\n"
        "</html>\n"
    )
    with open(os.path.join(pages_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  index.html -> {zip_name}")


def resolve_pages_dir(explicit):
    """Where the served site is written: --pages-dir if given, else the _site
    gh-pages worktree when present, else the source dir (legacy checkout)."""
    if explicit:
        return os.path.abspath(explicit)
    worktree = os.path.join(SOURCE_DIR, "_site")
    return worktree if os.path.isdir(worktree) else SOURCE_DIR


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate the Kontell Kodi repository metadata and installer.")
    parser.add_argument(
        "--pages-dir",
        help="Directory to write the served site into (omega/, piers/, the "
             "installer zip, index.html). Defaults to ./_site when present, "
             "else the script's own directory.",
    )
    args = parser.parse_args()
    pages_dir = resolve_pages_dir(args.pages_dir)

    print(f"Generating Kontell repository into {pages_dir} ...")
    for version_dir in VERSION_DIRS:
        generate_addons_xml(version_dir, pages_dir)

    if os.path.exists(os.path.join(SOURCE_DIR, "addon.xml")):
        version = read_repo_version()
        generate_repo_zip(pages_dir, version)
        generate_index_html(pages_dir, version)
    else:
        print("  Warning: addon.xml not found, skipping installer zip and index.html")
    print("Done.")
