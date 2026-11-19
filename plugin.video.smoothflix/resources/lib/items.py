# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Build Kodi directory items for the home menu and for Netflix results."""

import os

import xbmcaddon
import xbmcgui
import xbmcplugin

from resources.lib import netflix

_CONTENT = {
    'movie': 'movies',
    'tvshow': 'tvshows',
    'season': 'seasons',
    'episode': 'episodes',
}

# kind is list (a Netflix directory), route (a SmoothFlix page), or plugin
# (open the Netflix add-on itself, which is where sign-in lives).
HOME = [
    {'label': 'Continue Watching', 'art': 'continue.jpg',
     'plot': 'Pick up what you already started.', 'kind': 'list', 'path': 'continue'},
    {'label': 'My List', 'art': 'mylist.jpg',
     'plot': 'Titles you saved on your account.', 'kind': 'list', 'path': 'mylist'},
    {'label': 'Trending', 'art': 'trending.jpg',
     'plot': 'What people are watching now.', 'kind': 'list', 'path': 'trending'},
    {'label': 'New Releases', 'art': 'new.jpg',
     'plot': 'Titles that just arrived.', 'kind': 'list', 'path': 'new'},
    {'label': 'Popular', 'art': 'popular.jpg',
     'plot': 'The most watched titles.', 'kind': 'list', 'path': 'popular'},
    {'label': 'New & Popular', 'art': 'spotlight.jpg',
     'plot': 'Rows of what is new and notable.', 'kind': 'list', 'path': 'spotlight'},
    {'label': 'TV Shows', 'art': 'shows.jpg',
     'plot': 'Series, grouped by genre.', 'kind': 'list', 'path': 'shows'},
    {'label': 'Movies', 'art': 'movies.jpg',
     'plot': 'Films, grouped by genre.', 'kind': 'list', 'path': 'movies'},
    {'label': 'Search', 'art': 'search.jpg',
     'plot': 'Find a title on your account.', 'kind': 'route', 'route': 'search'},
    {'label': 'Profiles', 'art': 'profiles.jpg',
     'plot': 'Switch the active profile. A PIN prompt comes from the Netflix add-on.',
     'kind': 'list', 'path': 'profiles'},
    {'label': 'Netflix add-on', 'art': 'account.jpg',
     'plot': 'Sign in or change account settings. Playback stays with that add-on.',
     'kind': 'plugin'},
]


def _addon():
    return xbmcaddon.Addon(netflix.ADDON_ID)


def _fanart():
    return _addon().getAddonInfo('fanart')


def _media(name):
    return os.path.join(_addon().getAddonInfo('path'), 'resources', 'media', name)


def _home_url(entry):
    if entry['kind'] == 'route':
        return netflix.BASE + '/' + entry['route']
    if entry['kind'] == 'plugin':
        return netflix.NETFLIX + '/'
    return netflix.list_url(netflix.nf(netflix.PATHS[entry['path']]), entry['label'])


def show_home(handle):
    fanart = _fanart()
    built = []
    for entry in HOME:
        url = _home_url(entry)
        item = xbmcgui.ListItem(label=entry['label'], path=url, offscreen=True)
        tile = _media(entry['art'])
        item.setArt({
            'icon': tile,
            'thumb': tile,
            'poster': tile,
            'fanart': fanart,
            'landscape': fanart,
        })
        tag = item.getVideoInfoTag()
        tag.setTitle(entry['label'])
        tag.setPlot(entry['plot'])
        built.append((url, item, True))
    _finish(handle, built, 'images', 'SmoothFlix', False)


def content_for(entries):
    counts = {}
    for entry in entries:
        kind = entry.get('type')
        if kind in _CONTENT:
            counts[kind] = counts.get(kind, 0) + 1
    if not counts:
        return 'files'
    if len(counts) > 1:
        return 'videos'
    return _CONTENT[next(iter(counts))]


def _classify(entry):
    url = entry.get('file') or ''
    if netflix.is_play(url):
        return 'play'
    if netflix.is_directory(url):
        return 'wrap'
    if url.startswith(netflix.NETFLIX + '/') and '..' not in url:
        if entry.get('filetype') == 'directory':
            return 'direct-folder'
        return 'direct'
    return 'skip'


def _apply_tag(tag, entry):
    title = entry.get('title') or entry.get('label') or ''
    if title:
        tag.setTitle(title)
    if entry.get('originaltitle'):
        tag.setOriginalTitle(entry['originaltitle'])
    if entry.get('plot'):
        tag.setPlot(entry['plot'])
    if entry.get('tagline'):
        tag.setTagLine(entry['tagline'])
    if entry.get('year'):
        tag.setYear(entry['year'])
    media = entry.get('type')
    if media in _CONTENT:
        tag.setMediaType(media)
    if entry.get('genre'):
        tag.setGenres(entry['genre'])
    if entry.get('duration'):
        tag.setDuration(entry['duration'])
    if entry.get('rating'):
        tag.setRating(entry['rating'], entry.get('votes') or 0)
    if entry.get('premiered'):
        tag.setPremiered(entry['premiered'])
    if entry.get('mpaa'):
        tag.setMpaa(entry['mpaa'])
    if entry.get('studio'):
        tag.setStudios(entry['studio'])
    if entry.get('director'):
        tag.setDirectors(entry['director'])
    if entry.get('writer'):
        tag.setWriters(entry['writer'])
    if entry.get('country'):
        tag.setCountries(entry['country'])
    if entry.get('showtitle'):
        tag.setTvShowTitle(entry['showtitle'])
    if entry.get('season'):
        tag.setSeason(entry['season'])
    if entry.get('episode'):
        tag.setEpisode(entry['episode'])
    if media in ('movie', 'episode'):
        tag.setPlaycount(entry.get('playcount') or 0)
    if entry.get('resume_position'):
        tag.setResumePoint(entry['resume_position'], entry.get('resume_total') or 0)
    trailer = entry.get('trailer') or ''
    if trailer.startswith('plugin://') or trailer.startswith('http://') or trailer.startswith('https://'):
        tag.setTrailer(trailer)


def _art_for(entry):
    art = dict(entry.get('art') or {})
    if 'fanart' not in art:
        art['fanart'] = _fanart()
    if 'poster' not in art and 'thumb' not in art and 'icon' not in art:
        art['icon'] = 'DefaultFolder.png' if entry.get('filetype') == 'directory' else 'DefaultVideo.png'
    return art


def show_files(handle, entries, title, refresh):
    built = []
    for entry in entries:
        kind = _classify(entry)
        if kind == 'skip':
            netflix.log('skipped %s' % (entry.get('file') or entry.get('label')))
            continue
        label = entry.get('label') or entry.get('title') or title
        source = entry.get('file') or ''
        if kind == 'play':
            url = netflix.play_url(source)
            folder = False
        elif kind == 'wrap':
            url = netflix.list_url(source, label)
            folder = True
        else:
            url = source
            folder = kind == 'direct-folder'
        item = xbmcgui.ListItem(label=label, path=url, offscreen=True)
        item.setArt(_art_for(entry))
        _apply_tag(item.getVideoInfoTag(), entry)
        if kind == 'play':
            item.setProperty('IsPlayable', 'true')
        elif kind == 'wrap':
            refresh_url = netflix.list_url(source, label, refresh=True)
            item.addContextMenuItems([
                ('Refresh', 'Container.Update(%s)' % netflix.builtin_url(refresh_url)),
            ])
        built.append((url, item, folder))
    _finish(handle, built, content_for(entries), title, refresh)


def _finish(handle, built, content, category, update):
    if built:
        xbmcplugin.addDirectoryItems(handle, built, len(built))
    xbmcplugin.setPluginCategory(handle, category)
    xbmcplugin.setContent(handle, content)
    # UNSORTED first so the Netflix order is what opens. Other methods stay
    # available when the skin offers a sort menu.
    xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_UNSORTED)
    if content != 'images':
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_LABEL)
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_VIDEO_YEAR)
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_VIDEO_RATING)
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
        xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_EPISODE)
    xbmcplugin.endOfDirectory(handle, succeeded=True, updateListing=update, cacheToDisc=True)
