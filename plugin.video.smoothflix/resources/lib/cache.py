# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Disk cache for Netflix directory listings.

A plugin process exits after every screen, so the only cache that makes the
next open instant is on disk. Artwork is not stored here; Kodi loads those
URLs itself.
"""

import hashlib
import json
import os
import time

import xbmcaddon
import xbmcvfs

from resources.lib.nf.const import ADDON_ID
from resources.lib.nf.log import log


def _folder():
    profile = xbmcvfs.translatePath(xbmcaddon.Addon(ADDON_ID).getAddonInfo('profile'))
    folder = os.path.join(profile, 'cache')
    xbmcvfs.mkdirs(folder)
    return folder


def _path(key):
    digest = hashlib.sha1(key.encode('utf-8')).hexdigest()
    return os.path.join(_folder(), digest + '.json')


def _read(key):
    path = _path(key)
    if not xbmcvfs.exists(path):
        return None
    handle = xbmcvfs.File(path, 'r')
    try:
        raw = handle.read()
    finally:
        handle.close()
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8')
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        xbmcvfs.delete(path)
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get('files'), list):
        return None
    return payload


def minutes():
    try:
        return max(0, int(xbmcaddon.Addon(ADDON_ID).getSettingInt('cache_minutes')))
    except (TypeError, ValueError):
        return 30


def get_fresh(key, ttl_seconds):
    if ttl_seconds <= 0:
        return None
    payload = _read(key)
    if payload is None:
        return None
    age = time.time() - float(payload.get('time') or 0)
    if age <= ttl_seconds:
        return payload['files']
    return None


def get_any(key):
    payload = _read(key)
    if payload is None:
        return None
    return payload['files']


def put(key, files):
    path = _path(key)
    payload = json.dumps({'time': time.time(), 'files': files})
    handle = xbmcvfs.File(path, 'w')
    try:
        handle.write(payload)
    finally:
        handle.close()


def clear():
    folder = _folder()
    _dirs, names = xbmcvfs.listdir(folder)
    removed = 0
    for name in names:
        name = name.decode('utf-8') if isinstance(name, bytes) else name
        if not str(name).endswith('.json'):
            continue
        if xbmcvfs.delete(os.path.join(folder, name)):
            removed += 1
    log('cleared %s cached lists' % removed)
    return removed
