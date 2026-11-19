# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Turn a Netflix manifest into a DASH document and a Widevine license hop.

inputstream.adaptive fetches the manifest and posts the CDM challenge here.
The challenge is forwarded inside MSL. The license bytes go straight back
to the CDM and are not written to disk.
"""

import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape

import xbmc
import xbmcvfs

from resources.lib.nf.auth import _profile_path, _read_json, _write_json
from resources.lib.nf.errors import PlaybackError
from resources.lib.nf.log import log
from resources.lib.nf.msl import license as fetch_license
from resources.lib.nf.msl import manifest as fetch_manifest

_PSSH_URI = 'urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed'


def _port_path():
    return _profile_path('port')


def read_port():
    path = _port_path()
    if not xbmcvfs.exists(path):
        return 0
    handle = xbmcvfs.File(path, 'r')
    try:
        raw = handle.read()
    finally:
        handle.close()
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8')
    text = (raw or '').strip()
    return int(text) if text.isdigit() else 0


def _streams(tracks):
    found = []
    if not isinstance(tracks, list):
        return found
    for track in tracks:
        if not isinstance(track, dict):
            continue
        streams = track.get('streams') or track.get('downloadables') or []
        for stream in streams:
            if isinstance(stream, dict) and isinstance(stream.get('url'), str):
                found.append(stream)
    return found


def mpd(document):
    """Build a short MPEG-DASH document from a manifest dict."""
    if not isinstance(document, dict):
        raise PlaybackError('The manifest was empty.')
    result = document.get('result') if isinstance(document.get('result'), dict) else document
    videos = _streams(result.get('video_tracks') or result.get('videoTracks'))
    audios = _streams(result.get('audio_tracks') or result.get('audioTracks'))
    if not videos:
        raise PlaybackError('The manifest did not include a video stream.')
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" xmlns:cenc="urn:mpeg:cenc:2013"',
        ' type="static" mediaPresentationDuration="PT0S" minBufferTime="PT2S" profiles="urn:mpeg:dash:profile:isoff-on-demand:2011">',
        '<Period>',
        '<AdaptationSet contentType="video" mimeType="video/mp4">',
        '<ContentProtection schemeIdUri="%s" value="Widevine"/>' % _PSSH_URI,
    ]
    for index, stream in enumerate(videos):
        parts.append(
            '<Representation id="v%s" bandwidth="%s" width="%s" height="%s">' % (
                index,
                int(stream.get('bitrate') or stream.get('bandwidth') or 1000000),
                int(stream.get('width') or stream.get('res_w') or 1920),
                int(stream.get('height') or stream.get('res_h') or 1080),
            )
        )
        parts.append('<BaseURL>%s</BaseURL>' % escape(stream['url']))
        parts.append('</Representation>')
    parts.append('</AdaptationSet>')
    if audios:
        parts.append('<AdaptationSet contentType="audio" mimeType="audio/mp4">')
        for index, stream in enumerate(audios):
            parts.append(
                '<Representation id="a%s" bandwidth="%s">' % (
                    index, int(stream.get('bitrate') or 128000))
            )
            parts.append('<BaseURL>%s</BaseURL>' % escape(stream['url']))
            parts.append('</Representation>')
        parts.append('</AdaptationSet>')
    parts.append('</Period></MPD>')
    return ''.join(parts)


def _widevine_ready():
    try:
        import inputstreamhelper
    except ImportError as exc:
        raise PlaybackError('InputStream Helper is not installed.') from exc
    helper = inputstreamhelper.Helper('mpd', drm='com.widevine.alpha')
    if not helper.check_inputstream():
        raise PlaybackError('Widevine or inputstream.adaptive is not available.')


def listitem(video_id, title='', meta=''):
    """ListItem whose path and license URL point at the local playback service."""
    _widevine_ready()
    port = read_port()
    if not port:
        raise PlaybackError(
            'The SmoothFlix playback service is not running. Restart Kodi and try again.')
    record = _read_json('playback.json') or {}
    record['id'] = str(video_id)
    if title:
        record['title'] = title
    if meta:
        record['meta'] = meta
    _write_json('playback.json', record)
    import xbmcgui
    url = 'http://127.0.0.1:%s/manifest' % port
    item = xbmcgui.ListItem(path=url)
    item.setMimeType('application/dash+xml')
    item.setContentLookup(False)
    item.setProperty('inputstream', 'inputstream.adaptive')
    item.setProperty('inputstream.adaptive.manifest_type', 'mpd')
    item.setProperty('inputstream.adaptive.license_type', 'com.widevine.alpha')
    item.setProperty(
        'inputstream.adaptive.license_key',
        'http://127.0.0.1:%s/license||b{SSM}!b{SID}|' % port)
    return item


class _Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        return

    def _send(self, status, body, content_type):
        payload = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path.split('?', 1)[0] != '/manifest':
            self._send(404, 'not found', 'text/plain')
            return
        try:
            video_id = (_read_json('playback.json') or {}).get('id')
            if not video_id:
                raise PlaybackError('Nothing is queued for playback.')
            document = fetch_manifest(video_id)
            self._send(200, mpd(document), 'application/dash+xml')
        except Exception as exc:
            log('manifest failed: %s' % exc.__class__.__name__)
            self._send(500, str(exc), 'text/plain')

    def do_POST(self):
        if self.path.split('?', 1)[0] != '/license':
            self._send(404, 'not found', 'text/plain')
            return
        length = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(length) if length else b''
        try:
            text = raw.decode('utf-8')
            challenge, sid = text.split('!', 1)
            import base64
            session_id = base64.standard_b64decode(sid).decode('utf-8')
            blob = fetch_license(challenge, session_id)
            self._send(200, blob, 'application/octet-stream')
        except Exception as exc:
            log('license hop failed: %s' % exc.__class__.__name__)
            self._send(500, str(exc), 'text/plain')


def _serve_http(server):
    monitor = xbmc.Monitor()
    while not monitor.abortRequested():
        try:
            server.handle_request()
        except socket.timeout:
            continue
    server.server_close()


def _playing_ours(player):
    if not player.isPlaying():
        return False
    try:
        name = player.getPlayingFile() or ''
    except Exception:
        return False
    return name.startswith('http://127.0.0.1:') and '/manifest' in name


def serve():
    """Block as the add-on service. Only 127.0.0.1 can connect."""
    import threading
    server = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
    server.timeout = 0.5
    port = server.server_address[1]
    handle = xbmcvfs.File(_port_path(), 'w')
    try:
        handle.write(str(port))
    finally:
        handle.close()
    log('playback service on 127.0.0.1:%s' % port)
    threading.Thread(target=_serve_http, args=(server,), daemon=True).start()
    from resources.lib.aurora import playback_overlay
    monitor = xbmc.Monitor()
    player = xbmc.Player()
    overlay = None
    while not monitor.abortRequested():
        if _playing_ours(player):
            if overlay is None:
                overlay = playback_overlay()
            overlay.tick(player)
        elif overlay is not None:
            overlay.close()
            overlay = None
        if monitor.waitForAbort(0.5):
            break
