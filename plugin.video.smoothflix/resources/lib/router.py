# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Route plugin://plugin.video.smoothflix/ calls."""

import traceback
from urllib.parse import parse_qsl, urlparse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

from resources.lib.nf.const import ADDON_ID

from resources.lib import cache, items
from resources.lib.nf import auth, browse
from resources.lib.nf.errors import NetflixError, SessionExpired
from resources.lib.nf.log import log
from resources.lib.nf.play import listitem


def parse_argv(argv):
    raw = argv[0] if argv else ''
    parsed = urlparse(raw)
    params = dict(parse_qsl(parsed.query))
    if len(argv) > 2 and argv[2]:
        extra = argv[2][1:] if argv[2][:1] == '?' else argv[2]
        params.update(parse_qsl(extra))
    handle = int(argv[1]) if len(argv) > 1 and str(argv[1]).isdigit() else 0
    return handle, parsed.path.strip('/'), params


def _fail(handle, exc):
    xbmcgui.Dialog().ok('SmoothFlix', str(exc))
    if handle:
        xbmcplugin.endOfDirectory(handle, succeeded=False)


def _once(fn):
    """Run fn, and sign in again a single time if the session has expired."""
    try:
        return fn()
    except SessionExpired:
        auth.relogin()
        return fn()


def _cached(key, refresh, fn):
    ttl = cache.minutes() * 60
    if not refresh and ttl > 0:
        hit = cache.get_fresh(key, ttl)
        if hit is not None:
            log('cache hit')
            return hit
    videos = _once(fn)
    if videos and ttl > 0:
        try:
            cache.put(key, videos)
        except Exception as exc:
            log('cache write failed: %s' % exc.__class__.__name__)
    return videos


def show_root(handle, _params):
    if xbmcaddon.Addon(ADDON_ID).getSettingBool('classic'):
        items.show_home(handle)
        return
    from resources.lib.aurora import open_home
    open_home()
    xbmcplugin.endOfDirectory(handle, succeeded=False)


def show_list(handle, params):
    title = params.get('title') or 'SmoothFlix'
    refresh = params.get('refresh') == '1'
    auth.ensure()
    profile = auth.profile_guid()
    if params.get('season'):
        key = '%s:season:%s' % (profile, params['season'])
        videos = _cached(key, refresh, lambda: browse.episodes(params.get('show') or '', params['season']))
    elif params.get('show'):
        key = '%s:show:%s' % (profile, params['show'])
        videos = _cached(key, refresh, lambda: browse.seasons(params['show']))
        title = title or 'Seasons'
    elif params.get('genre'):
        key = '%s:genre:%s' % (profile, params['genre'])
        videos = _cached(key, refresh, lambda: browse.row('genre', genre=params['genre']))
    elif params.get('query'):
        key = '%s:search:%s' % (profile, params['query'])
        videos = _cached(key, refresh, lambda: browse.search(params['query']))
    else:
        row = params.get('row') or ''
        key = '%s:row:%s' % (profile, row)
        videos = _cached(key, refresh, lambda: browse.row(row))
    items.show_videos(handle, videos, title, refresh)


def show_profiles(handle, _params):
    found = _once(auth.profiles)
    items.show_profiles(handle, found)


def switch(handle, params):
    guid = params.get('guid') or ''
    pin = None
    chosen = None
    for item in auth.profiles():
        if item.get('guid') == guid:
            chosen = item
            break
    if chosen and chosen.get('pin'):
        keyboard = xbmc.Keyboard('', 'Profile PIN', True)
        keyboard.doModal()
        if not keyboard.isConfirmed() or not keyboard.getText().strip():
            xbmcplugin.endOfDirectory(handle, succeeded=False)
            return
        pin = keyboard.getText().strip()
    _once(lambda: auth.switch_profile(guid, pin))
    cache.clear()
    xbmcgui.Dialog().notification('SmoothFlix', 'Profile switched', xbmcgui.NOTIFICATION_INFO, 2500)
    xbmc.executebuiltin('Container.Update(%s/)' % items.PLUGIN)
    xbmcplugin.endOfDirectory(handle, succeeded=False)


def search(handle, _params):
    keyboard = xbmc.Keyboard('', 'Search SmoothFlix')
    keyboard.doModal()
    if not keyboard.isConfirmed():
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    term = keyboard.getText().strip()[:200]
    if not term:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    from urllib.parse import urlencode
    url = '%s/list?%s' % (items.PLUGIN, urlencode({'query': term, 'title': 'Search: ' + term}))
    xbmc.executebuiltin('Container.Update(%s)' % url.replace('&', '&amp;'))
    xbmcplugin.endOfDirectory(handle, succeeded=False)


def play(handle, params):
    video_id = params.get('id') or ''
    if not video_id:
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return
    item = listitem(video_id, params.get('title') or '', params.get('meta') or '')
    xbmcplugin.setResolvedUrl(handle, True, item)


def clear_cache(handle, _params):
    cache.clear()
    xbmcgui.Dialog().notification('SmoothFlix', 'Listing cache cleared', xbmcgui.NOTIFICATION_INFO, 3000)
    xbmc.executebuiltin('Container.Refresh')
    xbmcplugin.endOfDirectory(handle, succeeded=True)


def sign_out(handle, _params):
    auth.logout()
    cache.clear()
    xbmcgui.Dialog().notification('SmoothFlix', 'Signed out', xbmcgui.NOTIFICATION_INFO, 3000)
    xbmc.executebuiltin('Container.Refresh')
    xbmcplugin.endOfDirectory(handle, succeeded=True)


_ROUTES = {
    '': show_root,
    'root': show_root,
    'list': show_list,
    'profiles': show_profiles,
    'profile': switch,
    'search': search,
    'play': play,
    'clear_cache': clear_cache,
    'logout': sign_out,
}


def run(argv):
    handle = 0
    try:
        handle, route, params = parse_argv(argv)
        log(route or 'root')
        handler = _ROUTES.get(route)
        if handler is None:
            log('unknown route')
            xbmcplugin.endOfDirectory(handle, succeeded=False)
            return
        handler(handle, params)
    except NetflixError as exc:
        _fail(handle, exc)
    except Exception:
        xbmc.log('[SmoothFlix]\n' + traceback.format_exc(), xbmc.LOGERROR)
        _fail(handle, NetflixError('Could not open that page.'))
