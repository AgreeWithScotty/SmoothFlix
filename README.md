# SmoothFlix

SmoothFlix is a Kodi 21 front end for the Netflix add-on [plugin.video.netflix](https://github.com/CastagnaIT/plugin.video.netflix) by CastagnaIT. It draws the home screen and the lists. Sign-in, account data, and playback stay in that add-on, which plays through your own account with Kodi's inputstream.adaptive and Widevine.

SmoothFlix does not sign in, request licenses, download manifests, or play from any other source.

## Install

1. Install `plugin.video.netflix` from CastagnaIT's repository and sign in with your own account. SmoothFlix does not ship that add-on. It is not in the official Kodi repository, so Kodi cannot install it from here. The dependency is optional in `addon.xml` for that reason, and SmoothFlix refuses to list or play until the add-on is installed and enabled.
2. In Kodi: Settings, Add-ons, Install from zip file. Use this URL once it is on `main`:

   `https://raw.githubusercontent.com/AgreeWithScotty/SmoothFlix/main/repository.smoothflix-1.0.0.zip`

3. Install **SmoothFlix** from the SmoothFlix repository. Updates come from the same repository.

The repository points Kodi at:

- `https://raw.githubusercontent.com/AgreeWithScotty/SmoothFlix/main/addons.xml`
- `https://raw.githubusercontent.com/AgreeWithScotty/SmoothFlix/main/addons.xml.md5`
- `https://raw.githubusercontent.com/AgreeWithScotty/SmoothFlix/main/<addon-id>/<addon-id>-<version>.zip`

## What you get

The home menu is drawn locally, so it opens without waiting on the Netflix add-on. Continue Watching, My List, Trending, New Releases, Popular, New & Popular, TV Shows, Movies, Search, and Profiles each open one directory of `plugin.video.netflix`. Results are saved on disk (30 minutes by default, or off in settings) so the next visit does not ask again. Posters and fanart are the URLs the Netflix add-on already returned. Kodi's texture cache loads them. Nothing is downloaded before the list is on screen.

A title opens as another SmoothFlix list (a show, a season, a genre, the next page). Play hands Kodi `plugin://plugin.video.netflix/play/...`. Kodi follows that into the Netflix add-on, which resolves the stream. Search uses that add-on's `directory/search/search/?query=` path, the one it exposes for JSON-RPC, and does not keep its own login.

Profiles switch by opening the Netflix add-on's profile URL, so a PIN prompt is still its prompt. The saved lists are dropped after a switch because they belonged to the previous profile.

## Layout

- `plugin.video.smoothflix` — the video add-on, version 0.1.0
- `repository.smoothflix` — the repository add-on, version 1.0.0
- `tools/build_repo.py` — zips both add-ons, writes `addons.xml` and `addons.xml.md5`, and copies `repository.smoothflix-1.0.0.zip` to the repository root
- `tools/smoke_test.py` — runs the root menu, a list, the cache, and play against stubbed Kodi modules
- `tools/make_art.py` — redraws the icon, fanart, and home tiles

```bash
python3 tools/make_art.py
python3 tools/build_repo.py
python3 tools/smoke_test.py
```

## License

GPL-3.0-only. See [LICENSE](LICENSE).
