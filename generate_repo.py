#!/usr/bin/env python3
"""
Generate addons.xml and addons.xml.md5 for the Kontell repository.
Also creates the repository addon zip.

Directory layout uses the Kodi convention of addon+platform directories:
  pvr.kofin+linux-x86_64/pvr.kofin-0.2.1.zip
  pvr.kofin+android-armv7/pvr.kofin-0.2.1.zip
  pvr.kofin+android-aarch64/pvr.kofin-0.2.1.zip

A single addons.xml at the root contains one <addon> entry per platform,
each with a <platform> tag and <path> element. Kodi filters by platform
automatically.

Usage: python3 generate_repo.py
Run from the repository root directory.
"""

import hashlib
import os
import re
import zipfile

REPO_DIR = os.path.dirname(os.path.abspath(__file__))


def find_addon_dirs():
    """Find all addon+platform directories."""
    dirs = []
    for name in sorted(os.listdir(REPO_DIR)):
        if "+" in name and os.path.isdir(os.path.join(REPO_DIR, name)):
            dirs.append(name)
    return dirs


def get_addon_xml_from_zip(zip_path, platform_dir_name):
    """Extract addon.xml from a zip, inject <path> element."""
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            for name in z.namelist():
                if name.endswith("/addon.xml") and name.count("/") == 1:
                    xml = z.read(name).decode("utf-8")
                    xml = re.sub(r'<\?xml[^>]+\?>\s*', '', xml)
                    xml = xml.strip()

                    # Inject <path> element if not already present
                    zip_filename = os.path.basename(zip_path)
                    path_element = f"<path>{platform_dir_name}/{zip_filename}</path>"
                    if "<path>" not in xml:
                        xml = xml.replace("</extension>\n</addon>", f"    {path_element}\n  </extension>\n</addon>")
                        # Try alternate formatting
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


def generate_addons_xml():
    """Generate a single addons.xml with all platform entries."""
    addon_dirs = find_addon_dirs()
    if not addon_dirs:
        print("  No addon+platform directories found")
        return

    addon_xmls = []
    for dir_name in addon_dirs:
        dir_path = os.path.join(REPO_DIR, dir_name)
        zips = sorted(
            [f for f in os.listdir(dir_path) if f.endswith(".zip")],
            reverse=True,
        )
        if not zips:
            print(f"  Skipping {dir_name} (no zips)")
            continue

        xml = get_addon_xml_from_zip(os.path.join(dir_path, zips[0]), dir_name)
        if xml:
            addon_xmls.append(xml)
            print(f"  {dir_name}: {zips[0]}")

    if not addon_xmls:
        print("  No addon entries found")
        return

    content = '<?xml version="1.0" encoding="UTF-8"?>\n<addons>\n'
    for xml in addon_xmls:
        content += xml + "\n"
    content += "</addons>\n"

    xml_path = os.path.join(REPO_DIR, "addons.xml")
    with open(xml_path, "w") as f:
        f.write(content)

    md5 = hashlib.md5(content.encode("utf-8")).hexdigest()
    with open(xml_path + ".md5", "w") as f:
        f.write(md5)

    print(f"  addons.xml: {len(addon_xmls)} entry/entries, md5={md5}")


def generate_repo_zip():
    """Create the repository addon zip."""
    addon_xml = os.path.join(REPO_DIR, "addon.xml")
    if not os.path.exists(addon_xml):
        print("  Warning: addon.xml not found, skipping repo zip")
        return

    zip_path = os.path.join(REPO_DIR, "repository.kontell-1.0.0.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(addon_xml, "repository.kontell/addon.xml")

    print(f"  Repository zip: {zip_path}")


if __name__ == "__main__":
    print("Generating Kontell repository...")
    generate_addons_xml()
    generate_repo_zip()
    print("Done.")
