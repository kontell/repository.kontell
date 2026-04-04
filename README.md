# Kontell Kodi Repository

Kodi addon repository for [Kofin PVR](https://github.com/kontell/pvr.kofin) — a native Kodi PVR client for Jellyfin Live TV.

## Installation

1. Download the repository installer: [repository.kontell-1.0.1.zip](https://github.com/kontell/repository.kontell/raw/main/repository.kontell-1.0.1.zip)
2. In Kodi, go to **Settings → Add-ons → Install from zip file**
3. Browse to the downloaded zip and install it
4. Go to **Settings → Add-ons → Install from repository → Kontell Repository**
5. Select **PVR clients → Kofin PVR for Jellyfin** and install

The repository provides the correct build for your platform and Kodi version automatically.

## Supported platforms

| Platform | Kodi 21 (Omega) | Kodi 22 (Piers) |
|----------|----------------|-----------------|
| Linux x86_64 | yes | yes |
| Linux armv7 (Pi 2+) | yes | yes |
| Linux aarch64 (Pi 3+) | yes | yes |
| Android ARM32 | yes | yes |
| Android ARM64 | yes | yes |

## How it works

Separate `addons.xml` files are served for each Kodi version (Omega/Piers) using `<dir>` elements with `minversion`/`maxversion`. Within each version, platform filtering is automatic based on the `<platform>` tag.

```
omega/pvr.kofin+linux-x86_64/pvr.kofin-0.2.3.zip
omega/pvr.kofin+android-armv7/pvr.kofin-0.2.3.zip
piers/pvr.kofin+linux-x86_64/pvr.kofin-0.2.3.zip
piers/pvr.kofin+android-armv7/pvr.kofin-0.2.3.zip
...
```

## Updating the repository

After publishing a pvr.kofin release on GitHub:
```bash
./scripts/update-repo.sh
```
This downloads the latest release zips automatically (requires `gh` CLI). Then commit and push.

## Updating

Once the repository is installed, Kodi will check for updates automatically.
