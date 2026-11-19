# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Aurora Cinema windows. Layout is skin XML. Python only fills properties."""

from urllib.parse import urlencode

import xbmc
import xbmcaddon
import xbmcgui

from resources.lib import cache
from resources.lib.nf import auth, browse
from resources.lib.nf.const import ADDON_ID, BASE
from resources.lib.nf.errors import NetflixError
from resources.lib.nf.log import log

_BACK = (10, 92)
_TINTS = ('66181C22', '661C1916', '66141A1C', '661A1814', '66121618')
_ROWS = {
    'continue': 'CONTINUE WATCHING',
    'movies': 'MOVIES',
    'shows': 'TV SHOWS',
    'mylist': 'MY LIST',
    'search': 'SEARCH',
}
_NAV = {301: 'movies', 302: 'shows', 303: 'mylist'}


def _addon_path():
    return xbmcaddon.Addon(ADDON_ID).getAddonInfo('path')


def _cached(key, fn):
    ttl = cache.minutes() * 60
    if ttl > 0:
        hit = cache.get_fresh(key, ttl)
        if hit is not None:
            return hit
    videos = fn()
    if videos and ttl > 0:
        try:
            cache.put(key, videos)
        except Exception as exc:
            log('cache write failed: %s' % exc.__class__.__name__)
    return videos


def _split_title(title):
    words = (title or '').strip().split()
    if len(words) >= 2 and len(words[0]) <= 4:
        return words[0].upper(), ' '.join(words[1:]).upper()
    return '', (title or '').upper()


def _track(text):
    text = ' '.join((text or '').upper().split())
    if text and len(text) <= 28:
        return ' '.join(text)
    return text


def _meta(video):
    if video.get('type') == 'episode' and (video.get('season') or video.get('episode')):
        return 'S%02dE%02d · %s' % (
            int(video.get('season') or 0), int(video.get('episode') or 0), video.get('title') or '')
    if video.get('progress'):
        return '%s%% WATCHED' % int(video['progress'])
    if video.get('year'):
        return str(video['year'])
    return ''


def _item(video):
    item = xbmcgui.ListItem(label=(video.get('title') or 'Untitled').upper())
    art = video.get('art') or {}
    thumb = art.get('thumb') or art.get('poster') or ''
    fanart = art.get('fanart') or thumb
    item.setArt({'thumb': thumb, 'fanart': fanart, 'poster': art.get('poster') or thumb})
    item.setProperty('Meta', _meta(video))
    item.setProperty('Watched', '%s%% WATCHED' % int(video.get('progress') or 0))
    item.setProperty('Plot', video.get('plot') or '')
    item.setProperty('Id', str(video.get('id') or ''))
    item.setProperty('Type', video.get('type') or '')
    tag = item.getVideoInfoTag()
    progress = int(video.get('progress') or 0)
    if progress:
        tag.setResumePoint(progress, 100)
    return item


class AuroraHome(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        self.row = 'continue'
        self._videos = []
        xbmcgui.WindowXML.__init__(self, *args)

    def onInit(self):
        self._load(self.row)
        if self._videos:
            self.setFocusId(200)

    def onAction(self, action):
        if action.getId() in _BACK:
            self.close()

    def onFocus(self, control_id):
        if control_id == 200:
            self._hero_from_list()

    def onClick(self, control_id):
        if control_id in _NAV:
            self.row = _NAV[control_id]
            self._load(self.row)
            self.setFocusId(200)
            return
        if control_id == 304:
            self._search()
            return
        if control_id == 200:
            video = self._selected()
            if video:
                open_title(video)

    def _load(self, row):
        self.setProperty('Nav', row if row in _NAV.values() else '')
        self.setProperty('Section', _ROWS.get(row, 'CONTINUE WATCHING'))
        auth.ensure()
        key = '%s:row:%s' % (auth.profile_guid(), row)
        videos = _cached(key, lambda: browse.row(row))
        self._show(videos)

    def _search(self):
        keyboard = xbmc.Keyboard('', 'Search')
        keyboard.doModal()
        if not keyboard.isConfirmed():
            return
        term = keyboard.getText().strip()[:200]
        if not term:
            return
        self.row = 'search'
        self.setProperty('Nav', '')
        self.setProperty('Section', 'SEARCH')
        auth.ensure()
        videos = _cached('%s:search:%s' % (auth.profile_guid(), term), lambda: browse.search(term))
        self._show(videos)
        self.setFocusId(200)

    def _show(self, videos):
        self._videos = list(videos or [])
        control = self.getControl(200)
        control.reset()
        for video in self._videos:
            control.addItem(_item(video))
        if self._videos:
            self._apply_hero(self._videos[0], 0)

    def _selected(self):
        control = self.getControl(200)
        if not self._videos:
            return None
        position = 0
        if hasattr(control, 'getSelectedPosition'):
            position = control.getSelectedPosition() or 0
        if position < 0 or position >= len(self._videos):
            position = 0
        return self._videos[position]

    def _hero_from_list(self):
        video = self._selected()
        if video:
            position = 0
            control = self.getControl(200)
            if hasattr(control, 'getSelectedPosition'):
                position = control.getSelectedPosition() or 0
            self._apply_hero(video, position)

    def _apply_hero(self, video, index):
        kicker, title = _split_title(video.get('title') or '')
        self.setProperty('HeroKicker', kicker)
        self.setProperty('HeroTitle', title)
        self.setProperty('HeroTag', _track(video.get('plot') or _meta(video)))
        art = video.get('art') or {}
        self.setProperty('HeroFanart', art.get('fanart') or art.get('poster') or art.get('thumb') or '')
        tint = _TINTS[index % len(_TINTS)]
        self.setProperty('HeroTint', tint)
        wash = self.getControl(101)
        if hasattr(wash, 'setColorDiffuse'):
            wash.setColorDiffuse(tint)


class TitleWindow(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        self.video = {}
        xbmcgui.WindowXML.__init__(self, *args)

    def onInit(self):
        video = self.video or {}
        _kicker, title = _split_title(video.get('title') or '')
        kind = video.get('type') or ''
        kicker = 'A FILM' if kind == 'movie' else 'A SERIES' if kind == 'show' else 'NOW PLAYING'
        self.setProperty('Kicker', kicker)
        self.setProperty('HeroTitle', title)
        self.setProperty('Meta', _detail_meta(video))
        self.setProperty('Synopsis', video.get('plot') or '')
        art = video.get('art') or {}
        self.setProperty('HeroFanart', art.get('fanart') or art.get('poster') or art.get('thumb') or '')
        control = self.getControl(210)
        control.reset()
        others = _continue_cards(video.get('id'))
        for entry in others:
            control.addItem(_item(entry))
        self.setFocusId(310)

    def onAction(self, action):
        if action.getId() in _BACK:
            self.close()

    def onClick(self, control_id):
        if control_id == 310 and self.video:
            _play(self.video)
        elif control_id == 210:
            control = self.getControl(210)
            position = control.getSelectedPosition() if hasattr(control, 'getSelectedPosition') else 0
            # The row is display-only context. Enter opens that title.
            item = control.getListItem(position) if hasattr(control, 'getListItem') else None
            if item is not None:
                _play({'id': item.getProperty('Id'), 'title': item.getLabel(), 'type': item.getProperty('Type')})


def _detail_meta(video):
    bits = []
    if video.get('year'):
        bits.append(str(video['year']))
    kind = video.get('type') or ''
    if kind == 'movie':
        bits.append('FILM')
    elif kind == 'show':
        bits.append('SERIES')
    elif kind == 'episode':
        bits.append(_meta(video))
    return '  •  '.join(bit for bit in bits if bit)


def _continue_cards(current_id):
    try:
        auth.ensure()
        key = '%s:row:continue' % auth.profile_guid()
        videos = cache.get_fresh(key, cache.minutes() * 60) or []
    except NetflixError:
        return []
    return [video for video in videos if str(video.get('id')) != str(current_id)][:8]


def _play(video):
    meta = _detail_meta(video)
    query = urlencode({
        'id': video.get('id') or '',
        'title': video.get('title') or '',
        'meta': meta,
    })
    xbmc.executebuiltin('PlayMedia(%s)' % (BASE + '/play?' + query))


def open_home():
    window = AuroraHome('Home.xml', _addon_path(), 'Default', '1080i')
    window.doModal()
    del window


def open_title(video):
    window = TitleWindow('Title.xml', _addon_path(), 'Default', '1080i')
    window.video = video
    window.doModal()
    del window


class PlayerOverlay(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.info = {}
        xbmcgui.WindowXMLDialog.__init__(self, *args)

    def onInit(self):
        info = self.info or {}
        self.setProperty('Title', (info.get('title') or 'SMOOTHFLIX').upper())
        self.setProperty('Meta', info.get('meta') or '')
        self.apply_times(info.get('position') or 0, info.get('duration') or 0)
        volume = self.getControl(520)
        if hasattr(volume, 'setPercent'):
            volume.setPercent(int(info.get('volume') or 40))

    def onAction(self, action):
        if action.getId() in _BACK:
            self.close()

    def onClick(self, control_id):
        if control_id == 500:
            xbmc.executebuiltin('PlayerControl(Previous)')
        elif control_id == 501:
            xbmc.executebuiltin('PlayerControl(Play)')
        elif control_id == 502:
            xbmc.executebuiltin('PlayerControl(Next)')

    def apply_times(self, position, duration):
        self.setProperty('Elapsed', _clock(position))
        self.setProperty('Total', _clock(duration))
        percent = 0
        if duration:
            percent = max(0, min(100, int(100 * float(position) / float(duration))))
        bar = self.getControl(400)
        if hasattr(bar, 'setPercent'):
            bar.setPercent(percent)

    def tick(self, player):
        try:
            position = player.getTime()
            duration = player.getTotalTime()
        except Exception:
            return
        self.apply_times(position, duration)


def _clock(seconds):
    seconds = int(seconds or 0)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return '%d:%02d:%02d' % (hours, minutes, secs)
    return '%d:%02d' % (minutes, secs)


def playback_overlay():
    """Modeless player chrome. The service calls tick() while a title plays."""
    from resources.lib.nf.auth import _read_json
    record = _read_json('playback.json') or {}
    window = PlayerOverlay('Player.xml', _addon_path(), 'Default', '1080i')
    window.info = {
        'title': record.get('title') or '',
        'meta': record.get('meta') or '',
    }
    window.show()
    window.onInit()
    return window
