#!/usr/bin/env python3
"""
Generate addons.xml and addons.xml.md5 for each platform directory.
Also creates the repository addon zip.

Usage: python3 generate_repo.py
Run from the repository root directory.
"""

import hashlib
import os
import re
import zipfile

PLATFORMS = ["linux-x86_64", "android-armv7", "android-aarch64"]
REPO_DIR = os.path.dirname(os.path.abspath(__file__))


def get_addon_xml(platform_dir):
    """Extract addon.xml from the latest zip in a platform/addon directory."""
    xmls = []
    for addon_dir in sorted(os.listdir(platform_dir)):
        addon_path = os.path.join(platform_dir, addon_dir)
        if not os.path.isdir(addon_path):
            continue

        # Find the latest zip
        zips = sorted(
            [f for f in os.listdir(addon_path) if f.endswith(".zip")],
            reverse=True,
        )
        if not zips:
            continue

        zip_path = os.path.join(addon_path, zips[0])
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                for name in z.namelist():
                    if name.endswith("/addon.xml") and name.count("/") == 1:
                        xml = z.read(name).decode("utf-8")
                        # Strip XML declaration
                        xml = re.sub(r'<\?xml[^>]+\?>\s*', '', xml)
                        xmls.append(xml.strip())
                        break
        except Exception as e:
            print(f"  Warning: Failed to read {zip_path}: {e}")

    return xmls


def generate_addons_xml(platform):
    """Generate addons.xml for a platform directory."""
    platform_dir = os.path.join(REPO_DIR, platform)
    if not os.path.isdir(platform_dir):
        print(f"  Skipping {platform} (directory not found)")
        return

    addon_xmls = get_addon_xml(platform_dir)
    if not addon_xmls:
        print(f"  Skipping {platform} (no addons found)")
        return

    content = '<?xml version="1.0" encoding="UTF-8"?>\n<addons>\n'
    for xml in addon_xmls:
        content += xml + "\n"
    content += "</addons>\n"

    xml_path = os.path.join(platform_dir, "addons.xml")
    with open(xml_path, "w") as f:
        f.write(content)

    # Generate MD5
    md5 = hashlib.md5(content.encode("utf-8")).hexdigest()
    with open(xml_path + ".md5", "w") as f:
        f.write(md5)

    print(f"  {platform}: addons.xml ({len(addon_xmls)} addon(s), md5={md5})")


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
    for platform in PLATFORMS:
        generate_addons_xml(platform)
    generate_repo_zip()
    print("Done.")
