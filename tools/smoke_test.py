# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Run SmoothFlix routing with stubbed Kodi modules.

The Netflix add-on is stubbed as Files.GetDirectory, which is the interface
SmoothFlix calls. Nothing here contacts Netflix.
"""

import json
import os
import sys
import tempfile
from urllib.parse import parse_qsl, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON = os.path.join(ROOT, 'plugin.video.smoothflix')
PROFILE = tempfile.mkdtemp(prefix='smoothflix-')

SHOW = 'plugin://plugin.video.netflix/directory/show/80057281/'
MOVIE = 'plugin://plugin.video.netflix/play/movie/80117470/'
POSTER = 'https://example.com/art/midnight-poster.jpg'


class InfoTag(object):
    def __init__(self):
        self.data = {}

    def setTitle(self, value):
        self.data['title'] = value

    def setOriginalTitle(self, value):
        self.data['originaltitle'] = value

    def setPlot(self, value):
        self.data['plot'] = value

    def setTagLine(self, value):
        self.data['tagline'] = value

    def setYear(self, value):
        self.data['year'] = value

    def setMediaType(self, value):
        self.data['mediatype'] = value

    def setGenres(self, value):
        self.data['genre'] = list(value)

    def setDuration(self, value):
        self.data['duration'] = value

    def setRating(self, rating, votes=0, type='', isdefault=False):
        self.data['rating'] = rating
        self.data['votes'] = votes

    def setPremiered(self, value):
        self.data['premiered'] = value

    def setMpaa(self, value):
        self.data['mpaa'] = value

    def setStudios(self, value):
        self.data['studio'] = list(value)

    def setDirectors(self, value):
        self.data['director'] = list(value)

    def setWriters(self, value):
        self.data['writer'] = list(value)

    def setCountries(self, value):
        self.data['country'] = list(value)

    def setTvShowTitle(self, value):
        self.data['showtitle'] = value

    def setSeason(self, value):
        self.data['season'] = value

    def setEpisode(self, value):
        self.data['episode'] = value

    def setPlaycount(self, value):
        self.data['playcount'] = value

    def setResumePoint(self, position, total=0):
        self.data['resume'] = (position, total)

    def setTrailer(self, value):
        self.data['trailer'] = value


class ListItem(object):
    def __init__(self, label='', label2='', path='', offscreen=False):
        self.label = label
        self.path = path
        self.offscreen = offscreen
        self.art = {}
        self.properties = {}
        self.menu = []
        self.info = InfoTag()

    def setArt(self, art):
        self.art.update(art)

    def setProperty(self, key, value):
        self.properties[key] = value

    def setPath(self, path):
        self.path = path

    def getVideoInfoTag(self):
        return self.info

    def addContextMenuItems(self, items):
        self.menu = list(items)


class Keyboard(object):
    def __init__(self, default='', heading=''):
        self.text = ''
        self.confirmed = False

    def doModal(self):
        return None

    def isConfirmed(self):
        return self.confirmed

    def getText(self):
        return self.text


class Dialog(object):
    def ok(self, heading, message):
        print('DIALOG %s: %s' % (heading, message))
        return True

    def notification(self, heading, message, icon='', time=5000, sound=True):
        print('NOTIFY %s: %s' % (heading, message))


class Addon(object):
    def __init__(self, addon_id=None):
        self.id = addon_id or 'plugin.video.smoothflix'

    def getAddonInfo(self, key):
        return {
            'id': 'plugin.video.smoothflix',
            'name': 'SmoothFlix',
            'version': '0.1.0',
            'path': ADDON,
            'profile': PROFILE,
            'icon': os.path.join(ADDON, 'icon.png'),
            'fanart': os.path.join(ADDON, 'fanart.jpg'),
        }[key]

    def getSettingInt(self, key):
        if key == 'cache_minutes':
            return 30
        return 0

    def getLocalizedString(self, string_id):
        return str(string_id)


class File(object):
    def __init__(self, path, mode='r'):
        self._handle = open(path, mode, encoding='utf-8')

    def read(self):
        return self._handle.read()

    def write(self, data):
        self._handle.write(data)
        return len(data)

    def close(self):
        self._handle.close()


def install_stubs():
    xbmc = type(sys)('xbmc')
    xbmc.LOGINFO = 1
    xbmc.LOGERROR = 3
    xbmc.calls = []

    def log(msg, level=1):
        xbmc.calls.append((level, msg))

    def executebuiltin(builtin):
        xbmc.calls.append(('builtin', builtin))

    def executeJSONRPC(payload):
        request = json.loads(payload)
        xbmc.rpc.append(request)
        directory = request['params']['directory']
        files = [
            {
                'file': SHOW,
                'filetype': 'directory',
                'label': 'Harbor Lights',
                'title': 'Harbor Lights',
                'type': 'tvshow',
                'art': {'poster': 'https://example.com/art/harbor-poster.jpg'},
                'plot': 'A coastal town keeps a secret schedule.',
                'year': 2021,
                'genre': ['Mystery'],
            },
            {
                'file': MOVIE,
                'filetype': 'file',
                'label': 'The Midnight Library',
                'title': 'The Midnight Library',
                'type': 'movie',
                'art': {
                    'poster': POSTER,
                    'fanart': 'https://example.com/art/midnight-fanart.jpg',
                    'thumb': 'https://example.com/art/midnight-thumb.jpg',
                },
                'plot': 'A librarian walks through the lives she did not live.',
                'year': 2024,
                'rating': 8.4,
                'votes': 1200,
                'duration': 6420,
                'genre': ['Drama', 'Fantasy'],
                'playcount': 0,
                'resume': {'position': 320.0, 'total': 6420.0},
                'premiered': '2024-03-01',
                'mpaa': 'PG-13',
                'studio': ['Smooth Pictures'],
                'tagline': 'Every book is another life.',
                'director': ['A. Director'],
                'country': ['United Kingdom'],
            },
        ]
        print('JSON-RPC Files.GetDirectory %s' % directory)
        return json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {'files': files}})

    def getCondVisibility(condition):
        return True

    xbmc.log = log
    xbmc.executebuiltin = executebuiltin
    xbmc.executeJSONRPC = executeJSONRPC
    xbmc.getCondVisibility = getCondVisibility
    xbmc.rpc = []
    xbmc.Keyboard = Keyboard

    gui = type(sys)('xbmcgui')
    gui.ListItem = ListItem
    gui.Dialog = Dialog
    gui.NOTIFICATION_INFO = 'info'
    gui.NOTIFICATION_WARNING = 'warning'
    gui.NOTIFICATION_ERROR = 'error'

    plugin = type(sys)('xbmcplugin')
    plugin.ITEMS = []
    plugin.CONTENT = []
    plugin.CATEGORY = []
    plugin.ENDED = []
    plugin.RESOLVED = []
    plugin.SORT_METHOD_NONE = 0
    plugin.SORT_METHOD_LABEL = 1
    plugin.SORT_METHOD_VIDEO_YEAR = 16
    plugin.SORT_METHOD_VIDEO_RATING = 17
    plugin.SORT_METHOD_EPISODE = 24
    plugin.SORT_METHOD_VIDEO_RUNTIME = 29
    plugin.SORT_METHOD_UNSORTED = 40

    def addDirectoryItems(handle, items, totalItems=0):
        plugin.ITEMS.extend(items)
        return True

    def endOfDirectory(handle, succeeded=True, updateListing=False, cacheToDisc=True):
        plugin.ENDED.append((handle, succeeded, updateListing, cacheToDisc))

    def setResolvedUrl(handle, succeeded, listitem):
        plugin.RESOLVED.append((handle, succeeded, listitem))

    def setContent(handle, content):
        plugin.CONTENT.append(content)

    def setPluginCategory(handle, category):
        plugin.CATEGORY.append(category)

    def addSortMethod(handle, method):
        return None

    plugin.addDirectoryItems = addDirectoryItems
    plugin.endOfDirectory = endOfDirectory
    plugin.setResolvedUrl = setResolvedUrl
    plugin.setContent = setContent
    plugin.setPluginCategory = setPluginCategory
    plugin.addSortMethod = addSortMethod

    addon = type(sys)('xbmcaddon')
    addon.Addon = Addon

    vfs = type(sys)('xbmcvfs')
    vfs.File = File
    vfs.translatePath = lambda path: path
    vfs.exists = os.path.exists
    vfs.mkdirs = lambda path: os.makedirs(path, exist_ok=True) or True

    def delete(path):
        if os.path.isfile(path):
            os.remove(path)
        return True

    def listdir(path):
        if not os.path.isdir(path):
            return [], []
        dirs, files = [], []
        for name in os.listdir(path):
            full = os.path.join(path, name)
            if os.path.isdir(full):
                dirs.append(name)
            else:
                files.append(name)
        return dirs, files

    vfs.delete = delete
    vfs.listdir = listdir

    sys.modules['xbmc'] = xbmc
    sys.modules['xbmcgui'] = gui
    sys.modules['xbmcplugin'] = plugin
    sys.modules['xbmcaddon'] = addon
    sys.modules['xbmcvfs'] = vfs
    return xbmc, plugin


def as_argv(url, handle):
    parsed = urlparse(url)
    base = '%s://%s%s' % (parsed.scheme, parsed.netloc, parsed.path)
    query = ('?' + parsed.query) if parsed.query else ''
    return [base, str(handle), query]


def dump(title, plugin):
    print('')
    print('=== %s ===' % title)
    print('content %s' % (plugin.CONTENT[-1] if plugin.CONTENT else None))
    print('category %s' % (plugin.CATEGORY[-1] if plugin.CATEGORY else None))
    print('items %s' % len(plugin.ITEMS))
    for url, item, is_folder in plugin.ITEMS:
        kind = 'folder' if is_folder else 'play' if item.properties.get('IsPlayable') == 'true' else 'item'
        print('[%s] %s' % (kind, item.label))
        print('    url %s' % url)
        if item.art:
            for key in sorted(item.art):
                print('    art.%s %s' % (key, item.art[key]))
        info = item.info.data
        for key in ('mediatype', 'year', 'rating', 'genre', 'duration', 'resume', 'plot'):
            if key in info:
                print('    %s %s' % (key, info[key]))
    if plugin.RESOLVED:
        for handle, succeeded, item in plugin.RESOLVED:
            print('setResolvedUrl handle=%s success=%s path=%s' % (handle, succeeded, item.path))
    if plugin.ENDED:
        handle, succeeded, update, cache_to_disc = plugin.ENDED[-1]
        print('endOfDirectory success=%s updateListing=%s cacheToDisc=%s' % (
            succeeded, update, cache_to_disc))


def main():
    xbmc, plugin = install_stubs()
    sys.path.insert(0, ADDON)
    from resources.lib.router import run

    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)
            print('FAIL %s' % message)

    plugin.ITEMS.clear()
    run(['plugin://plugin.video.smoothflix/', '1', ''])
    dump('root', plugin)
    labels = [item.label for _url, item, _folder in plugin.ITEMS]
    check(xbmc.rpc == [], 'root must not call the Netflix add-on')
    check(plugin.CONTENT[-1] == 'images', 'root content should be images')
    check('Continue Watching' in labels, 'root missing Continue Watching')
    check('Search' in labels, 'root missing Search')
    check('Netflix add-on' in labels, 'root missing Netflix add-on')
    continue_url = next(url for url, item, _folder in plugin.ITEMS if item.label == 'Continue Watching')
    account_url = next(url for url, item, _folder in plugin.ITEMS if item.label == 'Netflix add-on')
    check(account_url == 'plugin://plugin.video.netflix/', 'account item should open the Netflix add-on')
    check(continue_url.startswith('plugin://plugin.video.smoothflix/list?'), 'continue should stay in SmoothFlix')

    plugin.ITEMS.clear()
    plugin.CONTENT.clear()
    plugin.CATEGORY.clear()
    plugin.ENDED.clear()
    run(as_argv(continue_url, 2))
    dump('list Continue Watching', plugin)
    check(len(xbmc.rpc) == 1, 'first list should call JSON-RPC once, got %s' % len(xbmc.rpc))
    check(plugin.CONTENT[-1] == 'videos', 'mixed list content should be videos')
    show = next(row for row in plugin.ITEMS if row[1].label == 'Harbor Lights')
    movie = next(row for row in plugin.ITEMS if row[1].label == 'The Midnight Library')
    check(show[2] is True, 'show should be a folder')
    check('80057281' in show[0], 'show folder should point back at SmoothFlix with the Netflix show path')
    check(movie[2] is False, 'movie should not be a folder')
    check(movie[1].properties.get('IsPlayable') == 'true', 'movie should be playable')
    check(movie[1].art.get('poster') == POSTER, 'poster URL should be passed through, not downloaded')
    check(movie[1].info.data.get('year') == 2024, 'year should be copied onto the info tag')
    check(movie[1].info.data.get('rating') == 8.4, 'rating should be copied onto the info tag')
    check(movie[1].info.data.get('resume') == (320.0, 6420.0), 'resume point should be copied')
    check(movie[0].startswith('plugin://plugin.video.smoothflix/play?'), 'play route should be ours')

    plugin.ITEMS.clear()
    run(as_argv(continue_url, 3))
    print('')
    print('=== list Continue Watching again (cache) ===')
    print('jsonrpc calls %s' % len(xbmc.rpc))
    print('items %s' % len(plugin.ITEMS))
    check(len(xbmc.rpc) == 1, 'cached list must not call JSON-RPC again')
    check(len(plugin.ITEMS) == 2, 'cached list should still return both items')

    parsed = urlparse(continue_url)
    refresh = continue_url + ('&' if parsed.query else '?') + 'refresh=1'
    plugin.ITEMS.clear()
    run(as_argv(refresh, 4))
    print('')
    print('=== list refresh ===')
    print('jsonrpc calls %s' % len(xbmc.rpc))
    check(len(xbmc.rpc) == 2, 'refresh should call JSON-RPC again')

    plugin.RESOLVED.clear()
    plugin.ITEMS.clear()
    plugin.CONTENT.clear()
    plugin.CATEGORY.clear()
    plugin.ENDED.clear()
    run(as_argv(movie[0], 5))
    dump('play', plugin)
    check(len(plugin.RESOLVED) == 1, 'play should resolve once')
    _handle, success, resolved = plugin.RESOLVED[-1]
    check(success is True, 'play should succeed')
    check(resolved.path == MOVIE, 'play should hand Kodi the Netflix play URL, got %s' % resolved.path)
    check(len(xbmc.rpc) == 2, 'play must not call Files.GetDirectory')

    plugin.RESOLVED.clear()
    run(['plugin://plugin.video.smoothflix/play', '6', '?path=https%3A%2F%2Fexample.com%2Fvideo.mpd'])
    print('')
    print('=== play rejected ===')
    print('setResolvedUrl success=%s path=%s' % (plugin.RESOLVED[-1][1], plugin.RESOLVED[-1][2].path))
    check(plugin.RESOLVED[-1][1] is False, 'a non-Netflix URL must not be resolved')

    print('')
    if failures:
        print('%s check(s) failed' % len(failures))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
