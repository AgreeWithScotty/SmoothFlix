# SmoothFlix

SmoothFlix is a Kodi 21 add-on that signs in to your own Netflix account, lists the usual rows, and plays through inputstream.adaptive and Widevine. The picture stays encrypted until the CDM unlocks it.

Aurora Cinema is the screen that opens with the add-on: a near-black home, a title page, and a player overlay, drawn by SmoothFlix itself. Settings has a classic directory list if you want the ordinary Kodi view.

It does not depend on any other Netflix add-on.

## Install

After this is on `main`, install the repository from:

`https://raw.githubusercontent.com/AgreeWithScotty/SmoothFlix/main/repository.smoothflix-1.0.0.zip`

Kodi: Settings, Add-ons, Install from zip file. Then install SmoothFlix from the SmoothFlix repository. Put your email and password in the add-on settings. They stay in this Kodi profile.

The repository points Kodi at:

- `https://raw.githubusercontent.com/AgreeWithScotty/SmoothFlix/main/addons.xml`
- `https://raw.githubusercontent.com/AgreeWithScotty/SmoothFlix/main/addons.xml.md5`
- `https://raw.githubusercontent.com/AgreeWithScotty/SmoothFlix/main/<addon-id>/<addon-id>-<version>.zip`

## How it is put together

Sign-in, cookies, and profile switching are in `resources/lib/nf/auth.py`. Catalogue paths are in `resources/lib/nf/browse.py`. Manifest and license messages are in `resources/lib/nf/msl.py`. `service.py` keeps a localhost listener up so inputstream.adaptive can fetch the DASH manifest and post the CDM challenge; the challenge is forwarded on the session channel and the license bytes go back to the CDM.

The home menu is local. A list is saved on disk (30 minutes by default) so the next open does not ask Netflix again. Posters are URLs. Kodi loads them.

A bad password, a verification challenge, an expired session, and a profile PIN each raise their own error. An expired session signs in once and retries.

## Develop

```bash
python3 tools/make_art.py
python3 tools/build_repo.py
python3 tools/smoke_test.py
```

The smoke test stubs Kodi and answers Netflix itself. It does not sign in to a real account.

## License

GPL-3.0-only. See [LICENSE](LICENSE).
