# Kontell Kodi Repository

Kodi addon repository for:

- [Kofin](https://github.com/kontell/plugin.video.kofin) - a Jellyfin client with native Kodi integration (browse, play and library sync);
- [Kofin PVR](https://github.com/kontell/pvr.kofin) - a Kodi PVR client for Jellyfin Live TV;
- [Koshelf](https://github.com/kontell/KoShelf) - A client for AudioBookShelf;
- [InputStream.Tempo](https://github.com/kontell/inputstream.tempo) - A fork of inputstream.ffmpegdirect which provides tempo (playback speed) adjustment for audio only playback;
- [Contuary](https://github.com/kontell/skin.contuary) - Light mod of default Estuary skin with icons-only main menu;
- [script.skin.contuary](https://github.com/kontell/script.skin.contuary/) - Helper script for skin.contuary to adjust the res (scales the UI for bigger screens).
- [Restore Music Queue](https://github.com/kontell/script.music.restore) - A program add-on to restore music to previous play states.
## Installation

### Option 1: Add as a file source

1.  In Kodi, go to: Settings → File Manager → Add source
2.  Enter the URL: `https://kontell.github.io/repository.kontell/`
3.  Name it (e.g. `Kontell`) and click OK
4.  Go to: Add-ons → Install from zip file → Kontell
5.  Select `repository.kontell-1.0.2.zip` and install it
6.  Go to: Add-ons → Install from repository → Kontell Repository

### Option 2: Manual download

1.  Download the repository installer: [repository.kontell-1.0.2.zip](https://kontell.github.io/repository.kontell/repository.kontell-1.0.2.zip)
2.  In Kodi, go to: Add-ons → Install from zip file
3.  Browse to the downloaded zip and install it
4.  Go to: Add-ons → Install from repository → Kontell Repository

The repository provides the correct build for your platform and Kodi version automatically.

## Jellyfin server plugins

This site also hosts a **Jellyfin plugin repository** — a separate manifest for
Jellyfin *servers*, unrelated to the Kodi add-ons above:

- [Kofin Sync Queue](https://github.com/kontell/jellyfin-plugin-kofinsyncqueue) - a typed change queue that lets offline Kofin/Kodi boxes catch up with minimal traffic. Requires Jellyfin 10.11+.
- [Jellyfin SyncPlay v2](https://github.com/kontell/jellyfin-plugin-syncplayv2) - backwards compatible SyncPlay enhancement plugin.

To install:

1.  In Jellyfin, go to: Dashboard → Plugins → Repositories → **+**
2.  Add a repository with the URL: `https://repository.kontell.workers.dev/jellyfin/manifest.json`
3.  Go to: Dashboard → Plugins → Catalog, install **Kofin Sync Queue**, and restart the server.
