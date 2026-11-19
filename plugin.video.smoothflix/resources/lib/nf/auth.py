# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Sign in with the account in the add-on settings and keep the session.

Credentials stay in Kodi's add-on settings (the profile directory). They are
sent only to Netflix over HTTPS and are never written to the log.
"""

import json
import os

import xbmcaddon
import xbmcvfs

from resources.lib.nf.const import ADDON_ID
from resources.lib.nf.errors import (
    BadCredentials, BadPin, CaptchaRequired, MissingCredentials, NetflixError, PinRequired,
    SessionExpired)
from resources.lib.nf.http import client
from resources.lib.nf.log import log

_CAPTCHA = ('recaptcha', 'g-recaptcha', 'challenge required', 'verify you are human')
_BAD_PASSWORD = (
    'incorrect password', 'incorrect_password', 'unrecognized email',
    'email or password', 'invalid credentials',
)
_BAD_PIN = ('incorrect pin', 'incorrect_pin', 'pin is incorrect', 'wrong pin')
_NEED_PIN = ('pin_required', 'pin required', 'profile pin')


def _profile_path(name):
    profile = xbmcvfs.translatePath(xbmcaddon.Addon(ADDON_ID).getAddonInfo('profile'))
    xbmcvfs.mkdirs(profile)
    return os.path.join(profile, name)


def _read_json(name):
    path = _profile_path(name)
    if not xbmcvfs.exists(path):
        return {}
    handle = xbmcvfs.File(path, 'r')
    try:
        raw = handle.read()
    finally:
        handle.close()
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8')
    try:
        data = json.loads(raw or '{}')
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(name, data):
    handle = xbmcvfs.File(_profile_path(name), 'w')
    try:
        handle.write(json.dumps(data))
    finally:
        handle.close()


def credentials():
    addon = xbmcaddon.Addon(ADDON_ID)
    email = (addon.getSetting('email') or '').strip()
    password = addon.getSetting('password') or ''
    if not email or not password:
        raise MissingCredentials(
            'Add your Netflix email and password in SmoothFlix settings.')
    return email, password


def session():
    return _read_json('session.json')


def profile_guid():
    return session().get('profile_guid') or ''


def _save_session(data):
    current = session()
    current.update(data)
    _write_json('session.json', current)


def logged_in():
    return client().has('NetflixId') and bool(session().get('auth_url'))


def _page_state(html):
    marker = 'netflix.reactContext'
    start = html.find(marker)
    context = {}
    if start >= 0:
        brace = html.find('{', start)
        if brace >= 0:
            try:
                context, _end = json.JSONDecoder().raw_decode(html[brace:])
            except ValueError:
                context = {}
    auth_url = _find_string(context, 'authURL') or _find_string(html_fallback(html), 'authURL')
    build = _find_string(context, 'BUILD_IDENTIFIER')
    profiles = _find_profiles(context)
    return {
        'auth_url': auth_url or '',
        'build_id': build or '',
        'profiles': profiles,
    }


def html_fallback(html):
    """Pull a few JSON strings out of a page that has no reactContext object."""
    import re
    found = {}
    for key in ('authURL', 'BUILD_IDENTIFIER'):
        match = re.search(r'"%s"\s*:\s*"([^"]+)"' % key, html)
        if match:
            found[key] = match.group(1)
    return found


def _find_string(node, key):
    if isinstance(node, dict):
        if key in node and isinstance(node[key], str) and node[key]:
            return node[key]
        for value in node.values():
            found = _find_string(value, key)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_string(value, key)
            if found:
                return found
    return ''


def _find_profiles(node):
    found = []

    def walk(value):
        if isinstance(value, dict):
            guid = value.get('guid') or value.get('profileGuid')
            name = value.get('name') or value.get('profileName') or value.get('firstName')
            if isinstance(guid, str) and isinstance(name, str) and guid and name:
                pin = bool(value.get('isPinProtected') or value.get('pinProtected'))
                item = {'guid': guid, 'name': name, 'pin': pin}
                if item not in found:
                    found.append(item)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return found


def _captcha(text):
    lowered = text.lower()
    return any(token in lowered for token in _CAPTCHA)


def _contains(text, tokens):
    lowered = text.lower()
    return any(token in lowered for token in tokens)


def login():
    """Sign in with the saved email and password. Raises a clear error."""
    email, password = credentials()
    http = client()
    http.clear()
    page = http.get('/login')
    if page.status >= 500:
        raise NetflixError('Netflix did not answer the sign-in page (%s).' % page.status)
    state = _page_state(page.text)
    if not state['auth_url']:
        if _captcha(page.text):
            raise CaptchaRequired(
                'Netflix is asking for a verification challenge. '
                'Finish it in a browser on this network, then try again.')
        raise NetflixError('The sign-in page did not include a session token.')
    form = {
        'userLoginId': email,
        'email': email,
        'password': password,
        'rememberMe': 'true',
        'flow': 'websiteSignUp',
        'mode': 'login',
        'action': 'loginAction',
        'withFields': 'rememberMe,nextPage,userLoginId,password,email',
        'authURL': state['auth_url'],
        'nextPage': '',
    }
    result = http.post('/login', form=form)
    text = result.text
    if _contains(text, _BAD_PASSWORD):
        http.clear()
        raise BadCredentials('That email or password was not accepted.')
    if _captcha(text) and not http.has('NetflixId'):
        http.clear()
        raise CaptchaRequired(
            'Netflix asked for a verification challenge instead of signing in. '
            'Finish it in a browser, then try again.')
    if not http.has('NetflixId'):
        http.clear()
        if result.status in (400, 401):
            raise BadCredentials('That email or password was not accepted.')
        raise NetflixError('Sign-in stopped before a session was issued.')
    home = http.get('/browse')
    if home.status in (401, 403):
        http.clear()
        raise SessionExpired('Netflix ended the session immediately after sign-in.')
    saved = _page_state(home.text)
    if not saved['auth_url']:
        saved['auth_url'] = state['auth_url']
    if not saved['profiles']:
        saved['profiles'] = state['profiles']
    if saved['profiles'] and not saved.get('profile_guid'):
        saved['profile_guid'] = saved['profiles'][0]['guid']
    _save_session(saved)
    log('signed in, %s profiles' % len(saved['profiles']))
    return saved


def ensure():
    if logged_in():
        return session()
    return login()


def relogin():
    """Drop the session and sign in again. Used once after an expiry."""
    log('session expired, signing in again')
    return login()


def logout():
    client().clear()
    for name in ('session.json', 'msl.json', 'playback.json', 'port'):
        path = _profile_path(name)
        if xbmcvfs.exists(path):
            xbmcvfs.delete(path)
    log('signed out')


def profiles():
    ensure()
    return session().get('profiles') or []


def switch_profile(guid, pin=None):
    """Activate a profile. A protected profile needs its PIN."""
    ensure()
    current = session()
    chosen = None
    for item in current.get('profiles') or []:
        if item.get('guid') == guid:
            chosen = item
            break
    if chosen is None:
        raise NetflixError('That profile is not on this account.')
    if chosen.get('pin') and not pin:
        raise PinRequired('That profile needs a PIN.')
    build = current.get('build_id') or ''
    path = '/api/shakti/%s/profiles/switch' % build if build else '/SwitchProfile'
    payload = {
        'switchProfileGuid': guid,
        'guid': guid,
        'authURL': current.get('auth_url') or '',
    }
    if pin:
        payload['pin'] = pin
    response = client().post(path, json_body=payload)
    text = response.text
    if _contains(text, _BAD_PIN):
        raise BadPin('That profile PIN was not accepted.')
    if response.status in (401, 403) and _contains(text, _NEED_PIN):
        raise PinRequired('That profile needs a PIN.')
    if response.status in (401, 403):
        raise SessionExpired('Netflix rejected the profile switch.')
    state = _page_state(text)
    update = {'profile_guid': guid}
    if state.get('auth_url'):
        update['auth_url'] = state['auth_url']
    if state.get('build_id'):
        update['build_id'] = state['build_id']
    _save_session(update)
    log('switched profile')
    return session()
