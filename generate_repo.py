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

Usage: python3 generate_repo.py
Run from the repository root directory.
"""

import hashlib
import os
import re
import zipfile

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_DIRS = ["omega", "piers"]


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


def get_addon_xml_from_zip(zip_path, platform_dir_name):
    """Extract addon.xml from a zip, inject <path> and fix <platform>."""
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            for name in z.namelist():
                if name.endswith("/addon.xml") and name.count("/") == 1:
                    xml = z.read(name).decode("utf-8")
                    xml = re.sub(r'<\?xml[^>]+\?>\s*', '', xml)
                    xml = xml.strip()

                    # Fix <platform> tag to be arch-specific
                    target_platform = platform_from_dir_name(platform_dir_name)
                    if target_platform:
                        xml = re.sub(
                            r'<platform>[^<]+</platform>',
                            f'<platform>{target_platform}</platform>',
                            xml,
                        )

                    # Inject <path> element if not already present
                    zip_filename = os.path.basename(zip_path)
                    path_element = f"<path>{platform_dir_name}/{zip_filename}</path>"
                    if "<path>" not in xml:
                        xml = xml.replace(
                            "</extension>\n</addon>",
                            f"    {path_element}\n  </extension>\n</addon>",
                        )
                        if path_element not in xml:
                            xml = re.sub(
                                r'(</assets>\s*)',
                                rf'\1    {path_element}\n    ',
                                xml,
                            )

                    return xml
    except Exception as e:
        print(f"  Warning: Failed to read {zip_path}: {e}")
    return None


def generate_addons_xml(version_dir):
    """Generate addons.xml for a version directory (omega or piers)."""
    base_dir = os.path.join(REPO_DIR, version_dir)
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
            reverse=True,
        )
        if not zips:
            continue

        xml = get_addon_xml_from_zip(os.path.join(dir_path, zips[0]), dir_name)
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
    with open(xml_path, "w") as f:
        f.write(content)

    md5 = hashlib.md5(content.encode("utf-8")).hexdigest()
    with open(xml_path + ".md5", "w") as f:
        f.write(md5)

    print(f"  {version_dir}: {len(addon_xmls)} entry/entries, md5={md5}")


def generate_repo_zip():
    """Create the repository addon zip."""
    addon_xml = os.path.join(REPO_DIR, "addon.xml")
    if not os.path.exists(addon_xml):
        print("  Warning: addon.xml not found, skipping repo zip")
        return

    # Read version from addon.xml
    with open(addon_xml, "r") as f:
        content = f.read()
    match = re.search(r'<addon[^>]+version="([^"]+)"', content)
    version = match.group(1) if match else "1.0.0"

    zip_name = f"repository.kontell-{version}.zip"
    zip_path = os.path.join(REPO_DIR, zip_name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(addon_xml, "repository.kontell/addon.xml")

    print(f"  Repository zip: {zip_name}")


if __name__ == "__main__":
    print("Generating Kontell repository...")
    for version_dir in VERSION_DIRS:
        generate_addons_xml(version_dir)
    generate_repo_zip()
    print("Done.")
