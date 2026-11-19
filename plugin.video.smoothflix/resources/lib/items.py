# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Kodi directory items. Data comes from the catalogue layer as plain dicts."""

import os
from urllib.parse import urlencode

import xbmcaddon
import xbmcgui
import xbmcplugin

from resources.lib.nf.const import ADDON_ID, BASE

PLUGIN = BASE

_CONTENT = {
    'movie': 'movies',
    'show': 'tvshows',
    'season': 'seasons',
    'episode': 'episodes',
}

HOME = [
    {'label': 'Continue Watching', 'art': 'continue.jpg', 'row': 'continue',
     'plot': 'Pick up what you already started.'},
    {'label': 'My List', 'art': 'mylist.jpg', 'row': 'mylist',
     'plot': 'Titles you saved on your account.'},
    {'label': 'Trending', 'art': 'trending.jpg', 'row': 'trending',
     'plot': 'What people are watching now.'},
    {'label': 'New Releases', 'art': 'new.jpg', 'row': 'new',
     'plot': 'Titles that just arrived.'},
    {'label': 'Popular', 'art': 'popular.jpg', 'row': 'popular',
     'plot': 'The most watched titles.'},
    {'label': 'TV Shows', 'art': 'shows.jpg', 'row': 'shows',
     'plot': 'Series from your account.'},
    {'label': 'Movies', 'art': 'movies.jpg', 'row': 'movies',
     'plot': 'Films from your account.'},
    {'label': 'Search', 'art': 'search.jpg', 'route': 'search',
     'plot': 'Find a title on your account.'},
    {'label': 'Profiles', 'art': 'profiles.jpg', 'route': 'profiles',
     'plot': 'Switch profile. A PIN stays on this device only for that request.'},
    {'label': 'Sign out', 'art': 'account.jpg', 'route': 'logout',
     'plot': 'Forget the saved session on this device.'},
]


def _addon():
    return xbmcaddon.Addon(ADDON_ID)


def _fanart():
    return _addon().getAddonInfo('fanart')


def _media(name):
    return os.path.join(_addon().getAddonInfo('path'), 'resources', 'media', name)


def _url(path, params):
    query = urlencode(params)
    return '%s/%s?%s' % (PLUGIN, path, query) if query else '%s/%s' % (PLUGIN, path)


def show_home(handle):
    fanart = _fanart()
    built = []
    for entry in HOME:
        if entry.get('route') == 'search':
            url = PLUGIN + '/search'
        elif entry.get('route'):
            url = PLUGIN + '/' + entry['route']
        else:
            url = _url('list', {'row': entry['row'], 'title': entry['label']})
        item = xbmcgui.ListItem(label=entry['label'], path=url, offscreen=True)
        tile = _media(entry['art'])
        item.setArt({
            'icon': tile, 'thumb': tile, 'poster': tile,
            'fanart': fanart, 'landscape': fanart,
        })
        tag = item.getVideoInfoTag()
        tag.setTitle(entry['label'])
        tag.setPlot(entry['plot'])
        folder = entry.get('route') != 'logout'
        built.append((url, item, folder))
    _finish(handle, built, 'images', 'SmoothFlix', False)


def show_profiles(handle, profiles):
    built = []
    fanart = _fanart()
    for entry in profiles:
        url = _url('profile', {'guid': entry['guid']})
        label = entry['name'] + (' (PIN)' if entry.get('pin') else '')
        item = xbmcgui.ListItem(label=label, path=url, offscreen=True)
        item.setArt({'icon': 'DefaultUser.png', 'fanart': fanart})
        tag = item.getVideoInfoTag()
        tag.setTitle(entry['name'])
        tag.setPlot('Switch to this profile.')
        built.append((url, item, False))
    _finish(handle, built, 'images', 'Profiles', False)


def show_videos(handle, videos, title, refresh):
    fanart = _fanart()
    built = []
    for video in videos:
        kind = video.get('type')
        label = video.get('title') or 'Untitled'
        if kind == 'genre':
            url = _url('list', {'genre': video['id'], 'title': label})
            folder = True
            playable = False
        elif kind == 'show':
            url = _url('list', {'show': video['id'], 'title': label})
            folder = True
            playable = False
        elif kind == 'season':
            url = _url('list', {
                'show': video.get('show_id') or '',
                'season': video['id'],
                'title': label,
            })
            folder = True
            playable = False
        elif kind in ('movie', 'episode'):
            url = _url('play', {'id': video['id']})
            folder = False
            playable = True
        else:
            continue
        item = xbmcgui.ListItem(label=label, path=url, offscreen=True)
        art = dict(video.get('art') or {})
        art.setdefault('fanart', fanart)
        if 'poster' not in art and 'thumb' not in art:
            art['icon'] = 'DefaultFolder.png' if folder else 'DefaultVideo.png'
        item.setArt(art)
        tag = item.getVideoInfoTag()
        tag.setTitle(label)
        if video.get('plot'):
            tag.setPlot(video['plot'])
        if video.get('year'):
            tag.setYear(int(video['year']))
        if kind in _CONTENT:
            tag.setMediaType({'show': 'tvshow'}.get(kind, kind))
        if kind == 'episode':
            if video.get('season'):
                tag.setSeason(int(video['season']))
            if video.get('episode'):
                tag.setEpisode(int(video['episode']))
        if playable:
            item.setProperty('IsPlayable', 'true')
        elif folder:
            refresh_url = url + '&refresh=1'
            item.addContextMenuItems([
                ('Refresh', 'Container.Update(%s)' % refresh_url.replace('&', '&amp;')),
            ])
        built.append((url, item, folder))
    _finish(handle, built, _content(videos), title, refresh)


def _content(videos):
    counts = {}
    for video in videos:
        kind = {'show': 'tvshow'}.get(video.get('type'), video.get('type'))
        if kind in ('movies', 'tvshow', 'season', 'episode', 'movie'):
            counts[kind] = counts.get(kind, 0) + 1
    if not counts:
        return 'files'
    if len(counts) > 1:
        return 'videos'
    only = next(iter(counts))
    return {'movie': 'movies', 'tvshow': 'tvshows', 'season': 'seasons', 'episode': 'episodes'}[only]


def _finish(handle, built, content, category, update):
    if built:
        xbmcplugin.addDirectoryItems(handle, built, len(built))
    xbmcplugin.setPluginCategory(handle, category)
    xbmcplugin.setContent(handle, content)
    xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_UNSORTED)
    if content != 'images':
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_LABEL)
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_VIDEO_YEAR)
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_VIDEO_RATING)
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_EPISODE)
    xbmcplugin.endOfDirectory(handle, succeeded=True, updateListing=update, cacheToDisc=True)
