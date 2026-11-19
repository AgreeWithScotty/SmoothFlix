# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Route plugin://plugin.video.smoothflix/ calls."""

import traceback
from urllib.parse import parse_qsl, urlparse

import xbmc
import xbmcgui
import xbmcplugin

from resources.lib import cache, items, netflix


def parse_argv(argv):
    raw = argv[0] if argv else ''
    parsed = urlparse(raw)
    params = dict(parse_qsl(parsed.query))
    if len(argv) > 2 and argv[2]:
        extra = argv[2][1:] if argv[2][:1] == '?' else argv[2]
        params.update(parse_qsl(extra))
    handle = int(argv[1]) if len(argv) > 1 and str(argv[1]).isdigit() else 0
    return handle, parsed.path.strip('/'), params


def show_root(handle, _params):
    items.show_home(handle)


def show_list(handle, params):
    nf_path = params.get('path', '')
    title = params.get('title') or 'SmoothFlix'
    refresh = params.get('refresh') == '1'
    if not netflix.is_directory(nf_path):
        xbmcgui.Dialog().notification(
            'SmoothFlix', 'That list is not available', xbmcgui.NOTIFICATION_ERROR, 4000)
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    if not netflix.ensure():
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    if 'switch_profile_guid=' in nf_path:
        _switch_profile(handle, nf_path)
        return
    files = netflix.load(nf_path, refresh)
    if files is None:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    items.show_files(handle, files, title, refresh)


def _switch_profile(handle, nf_path):
    # Loading this URL is what switches the profile inside the Netflix add-on,
    # including its PIN prompt. The returned home list is discarded: SmoothFlix
    # draws its own home, and the old cache belongs to the previous profile.
    files = netflix.directory(nf_path)
    if files is None:
        xbmcgui.Dialog().notification(
            'SmoothFlix', 'Could not switch profile', xbmcgui.NOTIFICATION_ERROR, 4000)
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    cache.clear()
    xbmcgui.Dialog().notification('SmoothFlix', 'Profile switched', xbmcgui.NOTIFICATION_INFO, 2500)
    xbmc.executebuiltin('Container.Update(%s/)' % netflix.BASE)
    xbmcplugin.endOfDirectory(handle, succeeded=False)


def play(handle, params):
    nf_path = params.get('path', '')
    item = xbmcgui.ListItem()
    if not netflix.is_play(nf_path):
        xbmcplugin.setResolvedUrl(handle, False, item)
        return
    # Kodi follows this plugin URL into plugin.video.netflix, which resolves
    # the stream with inputstream.adaptive. SmoothFlix never sees the manifest.
    item.setPath(nf_path)
    xbmcplugin.setResolvedUrl(handle, True, item)


def search(handle, _params):
    if not netflix.ensure():
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    keyboard = xbmc.Keyboard('', 'Search SmoothFlix')
    keyboard.doModal()
    if not keyboard.isConfirmed():
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    term = keyboard.getText().strip()[:200]
    if not term:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return
    # The Netflix add-on accepts ?query= for a JSON-RPC search and does not
    # store that search in its history.
    url = netflix.list_url(netflix.search_url(term), 'Search: ' + term)
    xbmc.executebuiltin('Container.Update(%s)' % netflix.builtin_url(url))
    xbmcplugin.endOfDirectory(handle, succeeded=False)


def clear_cache(handle, _params):
    cache.clear()
    xbmcgui.Dialog().notification('SmoothFlix', 'Listing cache cleared', xbmcgui.NOTIFICATION_INFO, 3000)
    xbmc.executebuiltin('Container.Refresh')
    xbmcplugin.endOfDirectory(handle, succeeded=True)


_ROUTES = {
    '': show_root,
    'root': show_root,
    'list': show_list,
    'play': play,
    'search': search,
    'clear_cache': clear_cache,
}


def run(argv):
    handle = 0
    try:
        handle, route, params = parse_argv(argv)
        netflix.log(route or 'root')
        handler = _ROUTES.get(route)
        if handler is None:
            netflix.log('unknown route %s' % route, xbmc.LOGERROR)
            xbmcplugin.endOfDirectory(handle, succeeded=False)
            return
        handler(handle, params)
    except Exception:
        xbmc.log('[SmoothFlix]\n' + traceback.format_exc(), xbmc.LOGERROR)
        if handle:
            xbmcplugin.endOfDirectory(handle, succeeded=False)
        xbmcgui.Dialog().notification(
            'SmoothFlix', 'Could not open that page', xbmcgui.NOTIFICATION_ERROR, 4000)
