# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""HTTP client with a cookie jar stored in the add-on profile.

The jar is the session. Callers pass a transport so tests can answer
without leaving the machine. Cookie values are never logged.
"""

import json
import os
from urllib.parse import urlencode

import xbmcaddon
import xbmcvfs

from resources.lib.nf.const import ADDON_ID, SITE, USER_AGENT
from resources.lib.nf.log import log


class Response(object):
    def __init__(self, status, body, headers=None, cookies=None):
        self.status = status
        self.body = body if isinstance(body, bytes) else body.encode('utf-8')
        self.headers = headers or {}
        self.cookies = cookies or {}

    @property
    def text(self):
        return self.body.decode('utf-8', 'replace')


class RequestsTransport(object):
    """Talks to Netflix with script.module.requests."""

    def request(self, method, url, headers, body, timeout):
        import requests
        response = requests.request(
            method, url, headers=headers, data=body or None, timeout=timeout)
        cookies = {item.name: item.value for item in response.cookies}
        return Response(response.status_code, response.content, dict(response.headers), cookies)


class Http(object):
    def __init__(self, transport=None):
        self.transport = transport or RequestsTransport()
        self.cookies = {}
        self._load()

    def _file(self):
        profile = xbmcvfs.translatePath(xbmcaddon.Addon(ADDON_ID).getAddonInfo('profile'))
        xbmcvfs.mkdirs(profile)
        return os.path.join(profile, 'cookies.json')

    def _load(self):
        path = self._file()
        if not xbmcvfs.exists(path):
            return
        handle = xbmcvfs.File(path, 'r')
        try:
            raw = handle.read()
        finally:
            handle.close()
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        try:
            saved = json.loads(raw or '{}')
        except ValueError:
            saved = {}
        if isinstance(saved, dict):
            self.cookies = {str(key): str(value) for key, value in saved.items()}

    def _save(self):
        path = self._file()
        handle = xbmcvfs.File(path, 'w')
        try:
            handle.write(json.dumps(self.cookies))
        finally:
            handle.close()

    def clear(self):
        self.cookies = {}
        path = self._file()
        if xbmcvfs.exists(path):
            xbmcvfs.delete(path)
        log('cleared the saved session')

    def has(self, name):
        return bool(self.cookies.get(name))

    def request(self, method, url, form=None, json_body=None, raw=None, headers=None, timeout=30):
        if url.startswith('/'):
            url = SITE + url
        header_set = {
            'User-Agent': USER_AGENT,
            'Accept': 'application/json, text/html;q=0.9, */*;q=0.8',
        }
        if self.cookies:
            header_set['Cookie'] = '; '.join(
                '%s=%s' % (key, value) for key, value in self.cookies.items())
        body = b''
        if raw is not None:
            body = raw if isinstance(raw, bytes) else raw.encode('utf-8')
            header_set['Content-Type'] = 'application/json'
        elif json_body is not None:
            body = json.dumps(json_body).encode('utf-8')
            header_set['Content-Type'] = 'application/json'
        elif form is not None:
            body = urlencode(form).encode('utf-8')
            header_set['Content-Type'] = 'application/x-www-form-urlencoded'
        if headers:
            header_set.update(headers)
        log('%s %s' % (method, url.split('?', 1)[0]))
        response = self.transport.request(method, url, header_set, body, timeout)
        if response.cookies:
            self.cookies.update(response.cookies)
            self._save()
        return response

    def get(self, url, headers=None):
        return self.request('GET', url, headers=headers)

    def post(self, url, form=None, json_body=None, headers=None):
        return self.request('POST', url, form=form, json_body=json_body, headers=headers)


_CLIENT = None


def install(transport=None):
    """Replace the shared client. Tests pass a fake transport."""
    global _CLIENT
    _CLIENT = Http(transport)
    return _CLIENT


def client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = Http()
    return _CLIENT
