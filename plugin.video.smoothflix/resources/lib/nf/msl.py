# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""A small MSL client for manifest and Widevine license messages.

MSL is the channel Netflix's own website uses. The video stays encrypted.
The license bytes returned here are for inputstream.adaptive's CDM only
and are not stored.
"""

import base64
import hashlib
import hmac
import json
import os
import time

import xbmcvfs

from resources.lib.nf import rsaoaep
from resources.lib.nf.auth import _profile_path, _read_json, _write_json, session
from resources.lib.nf.errors import NetflixError, SessionExpired
from resources.lib.nf.http import client
from resources.lib.nf.log import log

_MANIFEST = 'https://www.netflix.com/msl/playapi/cadmium/licensedmanifest/1'
_LICENSE = 'https://www.netflix.com/nq/msl_v1/cadmium/pbo_licenses/%5E1.0.0/router'


def _b64(raw):
    return base64.standard_b64encode(raw).decode('utf-8')


def _b64d(text):
    return base64.standard_b64decode(text)


def _pad(text):
    missing = len(text) % 4
    if missing:
        text += '=' * (4 - missing)
    return text


def _aes(key, iv, plaintext):
    import pyaes
    cipher = pyaes.Encrypter(pyaes.AESModeOfOperationCBC(key, iv=iv))
    return cipher.feed(plaintext) + cipher.feed()


def _unaes(key, iv, ciphertext):
    import pyaes
    cipher = pyaes.Decrypter(pyaes.AESModeOfOperationCBC(key, iv=iv))
    return cipher.feed(ciphertext) + cipher.feed()


def _pkcs7(data):
    fill = 16 - (len(data) % 16)
    return data + bytes([fill]) * fill


def _unpad(data):
    fill = data[-1]
    if fill < 1 or fill > 16 or data[-fill:] != bytes([fill]) * fill:
        raise NetflixError('The session reply could not be opened.')
    return data[:-fill]


def seal(plaintext, key, sign_key, key_id):
    """AES-CBC envelope plus HMAC, the MSL JSON encryption frame."""
    iv = os.urandom(16)
    ciphertext = _aes(key, iv, _pkcs7(plaintext.encode('utf-8')))
    envelope = json.dumps({
        'ciphertext': _b64(ciphertext),
        'keyid': key_id,
        'sha256': 'AA==',
        'iv': _b64(iv),
    }, separators=(',', ':'))
    signature = _b64(hmac.new(sign_key, envelope.encode('utf-8'), hashlib.sha256).digest())
    return envelope, signature


def open_sealed(envelope_text, key, sign_key, signature):
    if signature:
        expected = _b64(hmac.new(sign_key, envelope_text.encode('utf-8'), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature):
            raise NetflixError('The session reply failed its integrity check.')
    envelope = json.loads(envelope_text)
    iv = _b64d(envelope['iv'])
    ciphertext = _b64d(envelope['ciphertext'])
    return _unpad(_unaes(key, iv, ciphertext)).decode('utf-8')


def _split_json(blob):
    decoder = json.JSONDecoder()
    index = 0
    found = []
    while index < len(blob):
        while index < len(blob) and blob[index].isspace():
            index += 1
        if index >= len(blob):
            break
        obj, end = decoder.raw_decode(blob, index)
        found.append(obj)
        index = end
    return found


def _load_keys():
    data = _read_json('msl.json')
    if not data.get('n') or not data.get('d'):
        key = rsaoaep.generate()
        data = {
            'n': str(key['n']),
            'e': key['e'],
            'd': str(key['d']),
            'encryption_key': '',
            'sign_key': '',
            'mastertoken': None,
            'esn': data.get('esn') or ('NFCDCH-02-' + os.urandom(16).hex()),
            'sequence': 1,
        }
        _write_json('msl.json', data)
    return data


def _save_keys(data):
    stored = dict(data)
    stored['n'] = str(stored['n'])
    stored['d'] = str(stored['d'])
    _write_json('msl.json', stored)


def _private(data):
    return {'n': int(data['n']), 'e': int(data['e']), 'd': int(data['d'])}


def _public(data):
    return {'n': int(data['n']), 'e': int(data['e'])}


def handshake():
    """Create MSL session keys bound to the current NetflixId cookies."""
    data = _load_keys()
    if data.get('encryption_key') and data.get('mastertoken') and client().has('NetflixId'):
        return data
    esn = data['esn']
    header = {
        'messageid': 1,
        'renewable': True,
        'capabilities': {'languages': ['en-US'], 'compressionalgos': []},
        'keyrequestdata': [{
            'scheme': 'ASYMMETRIC_WRAPPED',
            'keydata': {
                'publickey': _b64(rsaoaep.public_der(_public(data))),
                'mechanism': 'JWK_RSA',
                'keypairid': 'rsaKeypairId',
            },
        }],
    }
    message = json.dumps({
        'entityauthdata': {'scheme': 'NONE', 'authdata': {'identity': esn}},
        'headerdata': _b64(json.dumps(header).encode('utf-8')),
        'signature': '',
    })
    message += json.dumps({
        'payload': _b64(json.dumps({
            'messageid': 1, 'data': '', 'sequencenumber': 1, 'endofmsg': True,
        }).encode('utf-8')),
        'signature': '',
    })
    response = _raw_post(_MANIFEST, message)
    parsed = _header_from(response.text, private=_private(data), keys=None)
    keydata = parsed.get('keyresponsedata', {}).get('keydata') or {}
    if 'encryptionkey' not in keydata or 'hmackey' not in keydata:
        raise NetflixError('Netflix did not return session keys.')
    data['encryption_key'] = _b64(_unwrap(_private(data), keydata['encryptionkey']))
    data['sign_key'] = _b64(_unwrap(_private(data), keydata['hmackey']))
    data['mastertoken'] = keydata.get('mastertoken') or parsed.get('mastertoken')
    data['sequence'] = 1
    _save_keys(data)
    log('session channel is ready')
    return data


def _raw_post(url, message):
    return client().request('POST', url, raw=message)


def _unwrap(private, field):
    decrypted = rsaoaep.decrypt(private, _b64d(field))
    wrapped = json.loads(decrypted.decode('utf-8'))
    return base64.urlsafe_b64decode(_pad(wrapped['k']))


def _header_from(text, private, keys):
    pieces = _split_json(text)
    for piece in pieces:
        if 'headerdata' not in piece:
            continue
        raw = _b64d(piece['headerdata']).decode('utf-8')
        if raw[:1] == '{':
            try:
                header = json.loads(raw)
            except ValueError:
                header = None
            if isinstance(header, dict) and 'ciphertext' in header and keys:
                opened = open_sealed(raw, _b64d(keys['encryption_key']),
                                     _b64d(keys['sign_key']), piece.get('signature') or '')
                return json.loads(opened)
            if isinstance(header, dict):
                return header
        if keys:
            opened = open_sealed(raw, _b64d(keys['encryption_key']),
                                 _b64d(keys['sign_key']), piece.get('signature') or '')
            return json.loads(opened)
    if 'login' in text.lower() or 'user must login' in text.lower():
        raise SessionExpired('Netflix ended the playback session.')
    raise NetflixError('The playback service returned an unexpected reply.')


def _user_header(data):
    cookies = client().cookies
    if not cookies.get('NetflixId') or not cookies.get('SecureNetflixId'):
        raise SessionExpired('The playback session has no account cookies.')
    data['sequence'] = int(data.get('sequence') or 1)
    header = {
        'messageid': data['sequence'],
        'renewable': True,
        'capabilities': {'languages': ['en-US'], 'compressionalgos': []},
        'sender': data['esn'],
        'userauthdata': {
            'scheme': 'NETFLIXID',
            'authdata': {
                'netflixid': cookies['NetflixId'],
                'securenetflixid': cookies['SecureNetflixId'],
            },
        },
    }
    return header


def command(url, params):
    """Send one authenticated MSL command and return the decrypted JSON body."""
    data = handshake()
    header = _user_header(data)
    key = _b64d(data['encryption_key'])
    sign = _b64d(data['sign_key'])
    key_id = '%s_%s' % (data['esn'], data['sequence'])
    envelope, signature = seal(json.dumps(header), key, sign, key_id)
    body = {
        'version': 2,
        'url': url,
        'id': int(time.time() * 1000),
        'languages': ['en-US'],
        'params': params,
    }
    payload_plain = json.dumps({
        'messageid': header['messageid'],
        'data': _b64(json.dumps(body).encode('utf-8')),
        'sequencenumber': 1,
        'endofmsg': True,
    })
    payload_envelope, payload_sig = seal(payload_plain, key, sign, key_id)
    message = json.dumps({
        'headerdata': _b64(envelope.encode('utf-8')),
        'signature': signature,
        'mastertoken': data.get('mastertoken') or {},
    })
    message += json.dumps({
        'payload': _b64(payload_envelope.encode('utf-8')),
        'signature': payload_sig,
    })
    data['sequence'] = int(data['sequence']) + 1
    _save_keys(data)
    response = _raw_post(url, message)
    if response.status in (401, 403):
        data['encryption_key'] = ''
        data['mastertoken'] = None
        _save_keys(data)
        raise SessionExpired('Netflix ended the playback session.')
    return _payload_from(response.text, data)


def _payload_from(text, data):
    key = _b64d(data['encryption_key'])
    sign = _b64d(data['sign_key'])
    for piece in _split_json(text):
        if 'payload' not in piece or not piece['payload']:
            continue
        raw = _b64d(piece['payload']).decode('utf-8')
        if raw[:1] == '{' and 'ciphertext' in raw:
            opened = open_sealed(raw, key, sign, piece.get('signature') or '')
        else:
            opened = raw
        chunk = json.loads(opened)
        encoded = chunk.get('data') or ''
        if not encoded:
            continue
        return json.loads(_b64d(encoded).decode('utf-8'))
    raise NetflixError('The playback service returned no payload.')


def manifest(video_id):
    params = {
        'type': 'standard',
        'manifestVersion': 'v2',
        'viewableId': str(video_id),
        'drmType': 'widevine',
        'licenseType': 'standard',
        'usePsshBox': True,
        'useHttpsStreams': True,
        'flavor': 'STANDARD',
        'profiles': [
            'playready-h264mpl30-dash',
            'playready-h264mpl31-dash',
            'playready-h264hpl30-dash',
            'playready-h264hpl31-dash',
            'heaac-2-dash',
            'webvtt-lssdh-ios8',
        ],
        'platform': '113.0.0',
        'clientVersion': '6.0026.0',
        'osName': 'windows',
        'osVersion': '10.0',
        'uiPlatform': 'SHAKTI',
    }
    return command(_MANIFEST, params)


def license(challenge_b64, session_id):
    """Exchange a CDM challenge for a license blob. The blob is not saved."""
    params = [{
        'drmSessionId': session_id,
        'clientTime': int(time.time()),
        'challengeBase64': challenge_b64,
    }]
    payload = command(_LICENSE + '?reqName=license', params)
    encoded = ''
    if isinstance(payload, dict):
        encoded = payload.get('licenseResponseBase64') or _find_license(payload)
    if isinstance(payload, list) and payload:
        encoded = payload[0].get('licenseResponseBase64', '') if isinstance(payload[0], dict) else ''
    if not encoded:
        raise NetflixError('Netflix did not return a Widevine license.')
    return _b64d(encoded)


def _find_license(node):
    if isinstance(node, dict):
        if isinstance(node.get('licenseResponseBase64'), str):
            return node['licenseResponseBase64']
        for value in node.values():
            found = _find_license(value)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_license(value)
            if found:
                return found
    return ''


def clear_channel():
    path = _profile_path('msl.json')
    if xbmcvfs.exists(path):
        xbmcvfs.delete(path)
