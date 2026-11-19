# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Catalogue reads against the website pathEvaluator API.

Row names and the path lists live in this file so a website change is a
local edit. Titles come back as plain dicts for the UI and the disk cache.
"""

from resources.lib.nf.auth import ensure, session
from resources.lib.nf.errors import NetflixError, SessionExpired
from resources.lib.nf.http import client

# Each path is the JSON-graph query the website uses for that row.
ROWS = {
    'continue': ['lolomo', 'continueWatching', {'from': 0, 'to': 40}, 'reference',
                 ['summary', 'title', 'synopsis', 'boxarts', 'bookmark']],
    'mylist': ['lolomo', 'queue', {'from': 0, 'to': 40}, 'reference',
               ['summary', 'title', 'synopsis', 'boxarts']],
    'trending': ['lolomo', 'trendingNow', {'from': 0, 'to': 40}, 'reference',
                 ['summary', 'title', 'synopsis', 'boxarts']],
    'new': ['lolomo', 'newRelease', {'from': 0, 'to': 40}, 'reference',
            ['summary', 'title', 'synopsis', 'boxarts']],
    'popular': ['lolomo', 'popularTitles', {'from': 0, 'to': 40}, 'reference',
                ['summary', 'title', 'synopsis', 'boxarts']],
    'shows': ['genres', 83, 'su', {'from': 0, 'to': 40}, 'reference',
              ['summary', 'title', 'synopsis', 'boxarts']],
    'movies': ['genres', 34399, 'su', {'from': 0, 'to': 40}, 'reference',
               ['summary', 'title', 'synopsis', 'boxarts']],
}


def row(name, genre=None):
    if genre:
        path = ['genres', genre, 'su', {'from': 0, 'to': 40}, 'reference',
                ['summary', 'title', 'synopsis', 'boxarts']]
    else:
        path = ROWS.get(name)
        if path is None:
            raise NetflixError('That row is not available.')
    return _videos([path])


def search(term):
    path = ['search', term, 'titles', {'from': 0, 'to': 24}, 'reference',
            ['summary', 'title', 'synopsis', 'boxarts']]
    return _videos([path])


def seasons(show_id):
    path = ['videos', int(show_id) if str(show_id).isdigit() else show_id,
            'seasonList', {'from': 0, 'to': 20}, 'summary']
    items = _collect(_query([path]))
    seasons_found = [item for item in items if item['type'] == 'season']
    if seasons_found:
        return seasons_found
    # A single-season title often returns episodes directly.
    return [item for item in items if item['type'] == 'episode']


def episodes(show_id, season_id):
    path = ['seasons', int(season_id) if str(season_id).isdigit() else season_id,
            'episodes', {'from': 0, 'to': 60}, 'reference',
            ['summary', 'title', 'synopsis', 'boxarts']]
    items = _collect(_query([path]))
    episodes_found = [item for item in items if item['type'] == 'episode']
    for item in episodes_found:
        item['show_id'] = str(show_id)
    return episodes_found


def _videos(paths):
    items = _collect(_query(paths))
    return [item for item in items if item['type'] in ('movie', 'show', 'episode', 'season', 'genre')]


def _query(paths):
    ensure()
    current = session()
    build = current.get('build_id') or ''
    if not build:
        raise SessionExpired('The catalogue session is missing a build id.')
    url = '/api/shakti/%s/pathEvaluator' % build
    response = client().post(url, json_body={
        'paths': paths,
        'authURL': current.get('auth_url') or '',
    })
    if response.status in (401, 403):
        raise SessionExpired('Netflix ended the session.')
    if response.status >= 400:
        raise NetflixError('The catalogue request failed (%s).' % response.status)
    try:
        return json_loads(response.text)
    except ValueError as exc:
        raise NetflixError('The catalogue response was not JSON.') from exc


def json_loads(text):
    import json
    return json.loads(text)


def _collect(payload):
    found = []
    seen = set()

    def add(item):
        key = (item['type'], item['id'])
        if item['id'] and key not in seen:
            seen.add(key)
            found.append(item)

    def walk(node):
        if isinstance(node, dict):
            video = _video(node)
            if video:
                add(video)
            genre = _genre(node)
            if genre:
                add(genre)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return found


def _video(node):
    summary = node.get('summary')
    if isinstance(summary, dict) and isinstance(summary.get('value'), dict):
        summary = summary['value']
    if not isinstance(summary, dict):
        summary = node if node.get('type') in ('movie', 'show', 'episode', 'season') else None
    if not isinstance(summary, dict):
        return None
    kind = summary.get('type')
    if kind not in ('movie', 'show', 'episode', 'season'):
        return None
    video_id = summary.get('id') or summary.get('videoId')
    if video_id is None:
        return None
    title = _text(node.get('title')) or _text(summary.get('title')) or 'Untitled'
    return {
        'id': str(video_id),
        'type': kind,
        'title': title,
        'plot': _text(node.get('synopsis')) or _text(summary.get('synopsis')),
        'year': _year(summary.get('releaseYear') or node.get('releaseYear')),
        'art': _art(node.get('boxarts') or summary.get('boxarts')),
        'season': _whole(summary.get('season') or node.get('season')),
        'episode': _whole(summary.get('episode') or node.get('episode')),
        'show_id': str(summary.get('showId') or summary.get('parentShowId') or ''),
        'progress': _progress(node.get('bookmark') or summary.get('bookmark')),
    }


def _genre(node):
    if node.get('type') in ('movie', 'show', 'episode', 'season'):
        return None
    if node.get('type') != 'genre' and 'genreId' not in node and 'genreName' not in node:
        return None
    genre_id = node.get('genreId') or node.get('id')
    name = _text(node.get('name')) or _text(node.get('genreName'))
    if genre_id is None or not name:
        return None
    return {
        'id': str(genre_id),
        'type': 'genre',
        'title': name,
        'plot': '',
        'year': 0,
        'art': {},
        'season': 0,
        'episode': 0,
        'show_id': '',
        'progress': 0,
    }


def _text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if isinstance(value.get('value'), str):
            return value['value']
        for key in ('title', 'text', 'name'):
            if isinstance(value.get(key), str):
                return value[key]
    return ''


def _year(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _progress(bookmark):
    if isinstance(bookmark, dict) and isinstance(bookmark.get('value'), dict):
        bookmark = bookmark['value']
    if not isinstance(bookmark, dict):
        return 0
    percent = bookmark.get('percentage')
    if percent is None:
        percent = bookmark.get('percent')
    if percent is not None:
        try:
            return max(0, min(100, int(float(percent))))
        except (TypeError, ValueError):
            return 0
    offset = bookmark.get('offset')
    if offset is None:
        offset = bookmark.get('position')
    runtime = bookmark.get('runtime') or bookmark.get('total')
    try:
        if offset is not None and runtime:
            return max(0, min(100, int(100 * float(offset) / float(runtime))))
    except (TypeError, ValueError, ZeroDivisionError):
        return 0
    return 0


def _whole(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _art(boxarts):
    art = {}
    if isinstance(boxarts, str) and boxarts.startswith('http'):
        art['poster'] = boxarts
        return art
    if not isinstance(boxarts, dict):
        return art
    for key, value in boxarts.items():
        url = value.get('url') if isinstance(value, dict) else value
        if not isinstance(url, str) or not url.startswith('http'):
            continue
        name = str(key)
        if '342' in name or 'poster' in name:
            art['poster'] = url
        elif '1280' in name or 'fanart' in name or '1920' in name:
            art['fanart'] = url
        else:
            art.setdefault('thumb', url)
    if 'poster' not in art and 'thumb' in art:
        art['poster'] = art['thumb']
    return art
