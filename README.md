# Kontell Kodi Repository

Kodi addon repository for [Kofin PVR](https://github.com/kontell/pvr.kofin) — a native Kodi PVR client for Jellyfin Live TV.

## Installation

1. Download the repository installer: [repository.kontell-1.0.0.zip](https://github.com/kontell/repository.kontell/raw/main/repository.kontell-1.0.0.zip)
2. In Kodi, go to **Settings → Add-ons → Install from zip file**
3. Browse to the downloaded zip and install it
4. Go to **Settings → Add-ons → Install from repository → Kontell Repository**
5. Select **PVR clients → Kofin PVR for Jellyfin** and install

The repository provides the correct build for your platform automatically.

## Supported platforms

| Platform | Kodi version |
|----------|-------------|
| Linux x86_64 | Kodi 21 (Omega) |
| Android ARM32 | Kodi 22 (Piers) |
| Android ARM64 | Kodi 22 (Piers) |

## How it works

A single `addons.xml` contains one entry per platform, each with a `<platform>` tag. Kodi filters entries automatically based on the current platform and only shows compatible builds.

Addon zips are stored in `addon+platform` directories following the Kodi convention:
```
pvr.kofin+linux-x86_64/pvr.kofin-0.2.1.zip
pvr.kofin+android-armv7/pvr.kofin-0.2.1.zip
pvr.kofin+android-aarch64/pvr.kofin-0.2.1.zip
```

## Updating

Once the repository is installed, Kodi will check for updates automatically. New versions of Kofin PVR will appear as available updates in the addon browser.

## Regenerating

After adding or updating addon zips, run:
```bash
python3 generate_repo.py
```
This regenerates `addons.xml`, `addons.xml.md5`, and `repository.kontell-1.0.0.zip`.
