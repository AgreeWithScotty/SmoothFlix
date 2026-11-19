# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Call plugin.video.netflix. Do not sign in or touch a stream.

Catalogue rows come from Files.GetDirectory on that add-on's directory URLs.
Playback URLs are its /play/ routes. Kodi resolves those through the Netflix
add-on, which sets inputstream.adaptive and Widevine for the signed-in account.
"""

import json
import time
from urllib.parse import urlencode

import xbmc
import xbmcgui

ADDON_ID = 'plugin.video.smoothflix'
BASE = 'plugin://' + ADDON_ID
NETFLIX_ID = 'plugin.video.netflix'
NETFLIX = 'plugin://' + NETFLIX_ID

# Paths match MAIN_MENU_ITEMS in plugin.video.netflix resources/lib/globals.py.
# The home menu can be drawn from these without asking the Netflix add-on.
# For a loco list the third segment is the context name; the add-on replaces
# it with the live list id when the context is one it already knows.
PATHS = {
    'continue': 'directory/video_list/continueWatching/continueWatching/',
    'mylist': 'directory/video_list_sorted/myList/queue/',
    'trending': 'directory/video_list/currentTitles/trendingNow/',
    'new': 'directory/video_list_sorted/newRelease/newRelease/',
    'popular': 'directory/video_list/mostViewed/popularTitles/',
    'spotlight': 'directory/category_list/newAndPopular/',
    'shows': 'directory/genres/tvshows/83/',
    'movies': 'directory/genres/movies/34399/',
    'profiles': 'directory/profiles/',
}

# Keep this list small. Each property is copied into the JSON-RPC reply, and
# cast or stream details would slow the listing without changing the posters.
PROPERTIES = [
    'title', 'art', 'plot', 'year', 'rating', 'duration', 'genre',
    'season', 'episode', 'playcount', 'resume', 'showtitle', 'premiered',
    'mpaa', 'studio', 'tagline', 'director', 'writer', 'country', 'trailer',
    'votes', 'originaltitle',
]


def log(message, level=None):
    xbmc.log('[SmoothFlix] ' + message, xbmc.LOGINFO if level is None else level)


def nf(path):
    return NETFLIX + '/' + path.lstrip('/')


def list_url(nf_path, title, refresh=False):
    params = {'path': nf_path, 'title': title}
    if refresh:
        params['refresh'] = '1'
    return BASE + '/list?' + urlencode(params)


def play_url(nf_path):
    return BASE + '/play?' + urlencode({'path': nf_path})


def search_url(term):
    return NETFLIX + '/directory/search/search/?' + urlencode({'query': term})


def builtin_url(url):
    # Kodi splits builtin arguments on a raw ampersand.
    return url.replace('&', '&amp;')


def _safe(url):
    return isinstance(url, str) and '..' not in url and '\n' not in url and '\r' not in url


def is_directory(url):
    return _safe(url) and url.startswith(NETFLIX + '/directory/')


def is_play(url):
    return _safe(url) and url.startswith(NETFLIX + '/play/')


def ensure():
    """True when the Netflix add-on is installed and enabled."""
    installed = xbmc.getCondVisibility('System.HasAddon(%s)' % NETFLIX_ID)
    enabled = xbmc.getCondVisibility('System.AddonIsEnabled(%s)' % NETFLIX_ID)
    if installed and enabled:
        return True
    xbmcgui.Dialog().ok(
        'SmoothFlix',
        'Install and enable the Netflix add-on (plugin.video.netflix), '
        'sign in with your own account, then open this list again. '
        'SmoothFlix does not sign in or play video itself.')
    return False


def _text(value):
    return value if isinstance(value, str) else ''


def _whole(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _texts(value):
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []


def slim(entry):
    """Keep the fields the skin can show. Drop anything else."""
    art = {}
    raw_art = entry.get('art')
    if isinstance(raw_art, dict):
        for key, value in raw_art.items():
            if isinstance(value, str) and value:
                art[str(key)] = value
    resume = entry.get('resume') if isinstance(entry.get('resume'), dict) else {}
    label = _text(entry.get('label')) or _text(entry.get('title'))
    return {
        'file': _text(entry.get('file')),
        'filetype': _text(entry.get('filetype')),
        'label': label,
        'title': _text(entry.get('title')) or label,
        'type': _text(entry.get('type')),
        'art': art,
        'plot': _text(entry.get('plot')),
        'year': _whole(entry.get('year')),
        'rating': _number(entry.get('rating')),
        'votes': _whole(entry.get('votes')),
        'duration': _whole(entry.get('duration')),
        'genre': _texts(entry.get('genre')),
        'season': _whole(entry.get('season')),
        'episode': _whole(entry.get('episode')),
        'playcount': _whole(entry.get('playcount')),
        'resume_position': _number(resume.get('position')),
        'resume_total': _number(resume.get('total')),
        'showtitle': _text(entry.get('showtitle')),
        'premiered': _text(entry.get('premiered')),
        'mpaa': _text(entry.get('mpaa')),
        'studio': _texts(entry.get('studio')),
        'tagline': _text(entry.get('tagline')),
        'director': _texts(entry.get('director')),
        'writer': _texts(entry.get('writer')),
        'country': _texts(entry.get('country')),
        'trailer': _text(entry.get('trailer')),
        'originaltitle': _text(entry.get('originaltitle')),
    }


def directory(url):
    """Return slimmed files, or None when the Netflix add-on did not answer."""
    payload = {
        'jsonrpc': '2.0',
        'method': 'Files.GetDirectory',
        'id': 1,
        'params': {
            'directory': url,
            'media': 'video',
            'properties': PROPERTIES,
        },
    }
    try:
        data = json.loads(xbmc.executeJSONRPC(json.dumps(payload)))
    except ValueError:
        log('The Netflix add-on returned a response that was not JSON', xbmc.LOGERROR)
        return None
    if not isinstance(data, dict) or 'error' in data:
        message = data.get('error') if isinstance(data, dict) else data
        log('Directory failed: %s' % message, xbmc.LOGERROR)
        return None
    files = data.get('result', {}).get('files')
    if not isinstance(files, list):
        return None
    return [slim(item) for item in files if isinstance(item, dict)]


def load(url, refresh):
    """Cached directory. A failed refresh falls back to the saved list."""
    from resources.lib import cache

    ttl = cache.minutes() * 60
    if not refresh and ttl > 0:
        hit = cache.get_fresh(url, ttl)
        if hit is not None:
            log('cache hit')
            return hit
    started = time.perf_counter()
    files = directory(url)
    spent = int((time.perf_counter() - started) * 1000)
    if files is None:
        saved = cache.get_any(url) if ttl > 0 else None
        if saved is not None:
            log('using saved list after a failed refresh')
            xbmcgui.Dialog().notification(
                'SmoothFlix', 'Showing the saved list', xbmcgui.NOTIFICATION_INFO, 4000)
            return saved
        xbmcgui.Dialog().notification(
            'SmoothFlix',
            'The Netflix add-on did not return this list. Open it and sign in, then try again.',
            xbmcgui.NOTIFICATION_WARNING,
            6000)
        return None
    log('fetched %s items in %s ms' % (len(files), spent))
    if files and ttl > 0:
        try:
            cache.put(url, files)
        except Exception as exc:  # cache must not block the list
            log('cache write failed: %s' % exc, xbmc.LOGERROR)
    return files
