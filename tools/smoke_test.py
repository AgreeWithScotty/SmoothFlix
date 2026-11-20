# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Headless SmoothFlix run with stubbed Kodi modules and a fake Netflix HTTP layer."""

import base64
import json
import os
import sys
import tempfile
import threading
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON = os.path.join(ROOT, 'plugin.video.smoothflix')
PROFILE = tempfile.mkdtemp(prefix='smoothflix-')

BROWSE_HTML = (
    '<html><script>netflix.reactContext = %s;</script></html>' % json.dumps({
        'authURL': 'c1.example-auth',
        'serverDefs': {'data': {'BUILD_IDENTIFIER': 'build123'}},
        'profiles': [
            {'guid': 'aaa', 'name': 'Ada', 'isPinProtected': False},
            {'guid': 'bbb', 'name': 'Bea', 'isPinProtected': True},
        ],
    })
)
LOGIN_HTML = (
    '<html><script>netflix.reactContext = %s;</script></html>' % json.dumps({
        'authURL': 'c1.login-auth',
    })
)
CAPTCHA_HTML = '<html><div class="g-recaptcha"></div>verify you are human</html>'

CONTINUE = {
    'videos': [
        {
            'summary': {'id': '80057281', 'type': 'show', 'title': 'Harbor Lights', 'releaseYear': 2021},
            'synopsis': 'A coastal town keeps a secret schedule.',
            'bookmark': {'offset': 320, 'runtime': 1000},
            'boxarts': {'_342x684': {'url': 'https://example.com/art/harbor-poster.jpg'}},
        },
        {
            'summary': {'id': '80117470', 'type': 'movie', 'title': 'The Midnight Library', 'releaseYear': 2024},
            'synopsis': 'A librarian walks through the lives she did not live.',
            'boxarts': {'_342x684': {'url': 'https://example.com/art/midnight-poster.jpg'}},
        },
    ]
}
SEASONS = {
    'seasons': [{
        'summary': {'id': 's1', 'type': 'season', 'title': 'Season 1', 'showId': '80057281'},
    }]
}
EPISODES = {
    'episodes': [{
        'summary': {
            'id': 'e1', 'type': 'episode', 'title': 'Pilot',
            'season': 1, 'episode': 1, 'showId': '80057281',
        },
        'synopsis': 'The first night.',
    }]
}
MANIFEST = {
    'video_tracks': [{
        'streams': [{
            'url': 'https://example.com/video/init.mp4',
            'bitrate': 3000000, 'width': 1920, 'height': 1080,
        }],
    }],
    'audio_tracks': [{
        'streams': [{'url': 'https://example.com/audio/init.mp4', 'bitrate': 128000}],
    }],
}
LICENSE_BYTES = b'WIDEVINE-LICENSE'


class Response(object):
    def __init__(self, status, body, cookies=None):
        self.status = status
        self.body = body if isinstance(body, bytes) else body.encode('utf-8')
        self.headers = {}
        self.cookies = cookies or {}

    @property
    def text(self):
        return self.body.decode('utf-8')


class FakeNetflix(object):
    def __init__(self):
        self.calls = []
        self.mode = 'ok'
        self.expired = False
        self.aes = None
        self.sign = None

    def request(self, method, url, headers, body, timeout):
        text = body.decode('utf-8') if isinstance(body, bytes) else ''
        path = url.split('?', 1)[0]
        self.calls.append((method, path))
        if path.endswith('/login') and method == 'GET':
            return Response(200, CAPTCHA_HTML if self.mode == 'captcha' else LOGIN_HTML)
        if path.endswith('/login') and method == 'POST':
            if 'password=wrong' in text:
                return Response(200, 'Incorrect password')
            return Response(200, BROWSE_HTML, cookies={
                'NetflixId': 'nid-value', 'SecureNetflixId': 'sid-value'})
        if path.endswith('/browse'):
            return Response(200, BROWSE_HTML)
        if path.endswith('/pathEvaluator'):
            if self.expired:
                self.expired = False
                return Response(401, '{"error":"login"}')
            if 'seasonList' in text:
                return Response(200, json.dumps(SEASONS))
            if 'episodes' in text:
                return Response(200, json.dumps(EPISODES))
            return Response(200, json.dumps(CONTINUE))
        if path.endswith('/profiles/switch') or path.endswith('/SwitchProfile'):
            if '"guid": "bbb"' in text or '"guid":"bbb"' in text:
                if 'pin' not in text:
                    return Response(401, '{"error":"pin_required"}')
            return Response(200, json.dumps({'authURL': 'c1.switched'}))
        if 'licensedmanifest' in path or 'pbo_licenses' in path:
            return self._msl(text, path)
        return Response(404, 'unhandled ' + path)

    def _msl(self, text, path):
        from resources.lib.nf import rsaoaep
        from resources.lib.nf.msl import seal
        pieces = []
        decoder = json.JSONDecoder()
        index = 0
        while index < len(text):
            while index < len(text) and text[index].isspace():
                index += 1
            if index >= len(text):
                break
            obj, index = decoder.raw_decode(text, index)
            pieces.append(obj)
        header_piece = next(piece for piece in pieces if 'headerdata' in piece)
        header_raw = base64.standard_b64decode(header_piece['headerdata']).decode('utf-8')
        if 'entityauthdata' in text:
            header = json.loads(header_raw)
            public_b64 = header['keyrequestdata'][0]['keydata']['publickey']
            public = rsaoaep.public_from_der(base64.standard_b64decode(public_b64))
            self.aes = os.urandom(16)
            self.sign = os.urandom(32)
            reply = {
                'messageid': 1,
                'keyresponsedata': {
                    'scheme': 'ASYMMETRIC_WRAPPED',
                    'keydata': {
                        'keypairid': 'rsaKeypairId',
                        'encryptionkey': _wrap(public, self.aes),
                        'hmackey': _wrap(public, self.sign),
                        'mastertoken': {
                            'tokendata': base64.standard_b64encode(b'{"s":1}').decode('utf-8'),
                            'signature': 'AA==',
                        },
                    },
                },
            }
            return Response(200, json.dumps({
                'headerdata': base64.standard_b64encode(json.dumps(reply).encode('utf-8')).decode('utf-8'),
                'signature': '',
            }))
        if 'pbo_licenses' in path:
            body = {'licenseResponseBase64': base64.standard_b64encode(LICENSE_BYTES).decode('utf-8')}
        else:
            body = MANIFEST
        plain = json.dumps({
            'messageid': 1,
            'data': base64.standard_b64encode(json.dumps(body).encode('utf-8')).decode('utf-8'),
            'sequencenumber': 1,
            'endofmsg': True,
        })
        envelope, signature = seal(plain, self.aes, self.sign, 'test_1')
        return Response(200, json.dumps({
            'payload': base64.standard_b64encode(envelope.encode('utf-8')).decode('utf-8'),
            'signature': signature,
        }))


def _wrap(public, raw):
    payload = json.dumps({
        'k': base64.urlsafe_b64encode(raw).decode('utf-8').rstrip('='),
    }).encode('utf-8')
    return base64.standard_b64encode(rsa_encrypt(public, payload)).decode('utf-8')


def rsa_encrypt(public, payload):
    from resources.lib.nf import rsaoaep
    return rsaoaep.encrypt(public, payload)


class InfoTag(object):
    def __init__(self):
        self.data = {}

    def setTitle(self, value):
        self.data['title'] = value

    def setPlot(self, value):
        self.data['plot'] = value

    def setYear(self, value):
        self.data['year'] = value

    def setMediaType(self, value):
        self.data['mediatype'] = value

    def setSeason(self, value):
        self.data['season'] = value

    def setEpisode(self, value):
        self.data['episode'] = value

    def setResumePoint(self, position, total=0):
        self.data['resume'] = (position, total)


class ListItem(object):
    def __init__(self, label='', label2='', path='', offscreen=False):
        self.label = label
        self.path = path
        self.art = {}
        self.properties = {}
        self.info = InfoTag()
        self.mime = ''

    def setArt(self, art):
        self.art.update(art)

    def setProperty(self, key, value):
        self.properties[key] = value

    def setPath(self, path):
        self.path = path

    def getVideoInfoTag(self):
        return self.info

    def addContextMenuItems(self, items):
        self.menu = items

    def setMimeType(self, mime):
        self.mime = mime

    def setContentLookup(self, enabled):
        self.lookup = enabled

    def getLabel(self):
        return self.label

    def getProperty(self, key):
        return self.properties.get(key, '')


class Keyboard(object):
    def __init__(self, default='', heading='', hidden=False):
        self.confirmed = False
        self.text = ''

    def doModal(self):
        return None

    def isConfirmed(self):
        return self.confirmed

    def getText(self):
        return self.text


class Dialog(object):
    def ok(self, heading, message):
        print('DIALOG %s: %s' % (heading, message))

    def notification(self, heading, message, icon='', time=5000, sound=True):
        print('NOTIFY %s: %s' % (heading, message))


class Monitor(object):
    def abortRequested(self):
        return False

    def waitForAbort(self, seconds=0):
        import time
        time.sleep(0.02)
        return False


class Player(object):
    def isPlaying(self):
        return False

    def getPlayingFile(self):
        return ''

    def getTime(self):
        return 0

    def getTotalTime(self):
        return 0


class FakeControl(object):
    def __init__(self):
        self.items = []
        self.percent = 0
        self.color = ''
        self.position = 0

    def reset(self):
        self.items = []

    def addItem(self, item):
        self.items.append(item)

    def size(self):
        return len(self.items)

    def getListItem(self, index):
        return self.items[index]

    def getSelectedItem(self):
        return self.items[self.position] if self.items else None

    def getSelectedPosition(self):
        return self.position

    def setPercent(self, value):
        self.percent = value

    def setColorDiffuse(self, color):
        self.color = color


class WindowXML(object):
    opened = []

    def __init__(self, xml, path, skin, res):
        self.xml = xml
        self.properties = {}
        self.controls = {}

    def setProperty(self, key, value):
        self.properties[key] = value

    def getProperty(self, key):
        return self.properties.get(key, '')

    def getControl(self, control_id):
        return self.controls.setdefault(control_id, FakeControl())

    def setFocusId(self, control_id):
        self.focus = control_id

    def doModal(self):
        WindowXML.opened.append(self)
        self.onInit()

    def show(self):
        self.shown = True

    def close(self):
        self.closed = True


class WindowXMLDialog(WindowXML):
    def __init__(self, *args):
        WindowXML.__init__(self, *args)


class Addon(object):
    settings = {'email': 'ada@example.com', 'password': 'secret', 'cache_minutes': '30'}

    def __init__(self, addon_id=None):
        self.id = addon_id or 'plugin.video.smoothflix'

    def getAddonInfo(self, key):
        return {
            'id': 'plugin.video.smoothflix',
            'path': ADDON,
            'profile': PROFILE,
            'icon': os.path.join(ADDON, 'icon.png'),
            'fanart': os.path.join(ADDON, 'fanart.jpg'),
            'version': '0.2.0',
        }[key]

    def getSetting(self, key):
        return self.settings.get(key, '')

    def getSettingInt(self, key):
        try:
            return int(self.settings.get(key, '0'))
        except ValueError:
            return 0

    def getSettingBool(self, key):
        return str(self.settings.get(key, 'false')).lower() == 'true'

    def setSetting(self, key, value):
        self.settings[key] = value


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
    xbmc.log = lambda message, level=1: None
    xbmc.executebuiltin = lambda builtin: xbmc.builtins.append(builtin)
    xbmc.builtins = []
    xbmc.Keyboard = Keyboard
    xbmc.Monitor = Monitor
    xbmc.Player = Player

    gui = type(sys)('xbmcgui')
    gui.ListItem = ListItem
    gui.Dialog = Dialog
    gui.WindowXML = WindowXML
    gui.WindowXMLDialog = WindowXMLDialog
    gui.NOTIFICATION_INFO = 'info'
    gui.NOTIFICATION_ERROR = 'error'

    plugin = type(sys)('xbmcplugin')
    plugin.ITEMS = []
    plugin.CONTENT = []
    plugin.CATEGORY = []
    plugin.RESOLVED = []
    plugin.ENDED = []
    plugin.SORT_METHOD_UNSORTED = 40
    plugin.SORT_METHOD_LABEL = 1
    plugin.SORT_METHOD_VIDEO_YEAR = 16
    plugin.SORT_METHOD_VIDEO_RATING = 17
    plugin.SORT_METHOD_EPISODE = 24

    def addDirectoryItems(handle, items, totalItems=0):
        plugin.ITEMS.extend(items)
        return True

    def endOfDirectory(handle, succeeded=True, updateListing=False, cacheToDisc=True):
        plugin.ENDED.append(succeeded)

    def setResolvedUrl(handle, succeeded, listitem):
        plugin.RESOLVED.append((succeeded, listitem))

    def setContent(handle, content):
        plugin.CONTENT.append(content)

    def setPluginCategory(handle, category):
        plugin.CATEGORY.append(category)

    plugin.addDirectoryItems = addDirectoryItems
    plugin.endOfDirectory = endOfDirectory
    plugin.setResolvedUrl = setResolvedUrl
    plugin.setContent = setContent
    plugin.setPluginCategory = setPluginCategory
    plugin.addSortMethod = lambda handle, method: None

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
            (dirs if os.path.isdir(full) else files).append(name)
        return dirs, files

    vfs.delete = delete
    vfs.listdir = listdir

    helper = type(sys)('inputstreamhelper')

    class Helper(object):
        def __init__(self, protocol, drm=None):
            self.inputstream_addon = 'inputstream.adaptive'

        def check_inputstream(self):
            return True

    helper.Helper = Helper

    sys.modules['xbmc'] = xbmc
    sys.modules['xbmcgui'] = gui
    sys.modules['xbmcplugin'] = plugin
    sys.modules['xbmcaddon'] = addon
    sys.modules['xbmcvfs'] = vfs
    sys.modules['inputstreamhelper'] = helper
    return xbmc, plugin


def as_argv(url, handle):
    base, _, query = url.partition('?')
    return [base, str(handle), ('?' + query) if query else '']


def dump(title, plugin):
    print('')
    print('=== %s ===' % title)
    if plugin.CONTENT:
        print('content %s' % plugin.CONTENT[-1])
    if plugin.CATEGORY:
        print('category %s' % plugin.CATEGORY[-1])
    print('items %s' % len(plugin.ITEMS))
    for url, item, is_folder in plugin.ITEMS:
        kind = 'folder' if is_folder else 'play' if item.properties.get('IsPlayable') == 'true' else 'item'
        print('[%s] %s' % (kind, item.label))
        print('    url %s' % url)
        poster = item.art.get('poster')
        if poster:
            print('    poster %s' % poster)
        if item.info.data:
            print('    info %s' % item.info.data)


def main():
    xbmc, plugin = install_stubs()
    sys.path.insert(0, ADDON)
    from resources.lib.nf import auth
    from resources.lib.nf.errors import BadCredentials, CaptchaRequired, PinRequired
    from resources.lib.nf.http import install
    from resources.lib.nf.play import serve
    from resources.lib.router import run

    fake = FakeNetflix()
    install(fake)
    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)
            print('FAIL %s' % message)

    fake.mode = 'captcha'
    try:
        auth.login()
        check(False, 'captcha page should not sign in')
    except CaptchaRequired as exc:
        print('captcha: %s' % exc)
    fake.mode = 'ok'

    Addon.settings['password'] = 'wrong'
    try:
        auth.login()
        check(False, 'wrong password should not sign in')
    except BadCredentials as exc:
        print('bad password: %s' % exc)
    check(not os.path.exists(os.path.join(PROFILE, 'cookies.json')), 'bad password must not leave a session')

    Addon.settings['password'] = 'secret'
    signed = auth.login()
    print('login profiles: %s' % [(item['name'], item['pin']) for item in signed['profiles']])
    check(signed['profiles'][0]['name'] == 'Ada', 'first profile should be Ada')

    try:
        auth.switch_profile('bbb')
        check(False, 'pin profile should ask for a PIN')
    except PinRequired as exc:
        print('profile pin: %s' % exc)
    plugin.ITEMS.clear()
    run(['plugin://plugin.video.smoothflix/profiles', '1', ''])
    dump('profiles', plugin)
    check(any(item.label == 'Ada' for _url, item, _folder in plugin.ITEMS), 'profile list should include Ada')

    fake.expired = True
    before = len([call for call in fake.calls if call[0] == 'POST' and call[1].endswith('/login')])
    plugin.ITEMS.clear()
    plugin.CONTENT.clear()
    plugin.CATEGORY.clear()
    continue_url = 'plugin://plugin.video.smoothflix/list?row=continue&title=Continue+Watching'
    run(as_argv(continue_url, 3))
    dump('list Continue Watching (after expired session)', plugin)
    logins = len([call for call in fake.calls if call[0] == 'POST' and call[1].endswith('/login')])
    print('login posts after expiry %s (was %s)' % (logins, before))
    check(logins == before + 1, 'expired session should sign in again once')
    check(any(item.label == 'Harbor Lights' for _url, item, _folder in plugin.ITEMS), 'list should include the show')
    check(any(item.label == 'The Midnight Library' for _url, item, _folder in plugin.ITEMS), 'list should include the movie')
    movie = next(row for row in plugin.ITEMS if row[1].label == 'The Midnight Library')
    check(movie[1].properties.get('IsPlayable') == 'true', 'movie should be playable')
    check(movie[1].art.get('poster') == 'https://example.com/art/midnight-poster.jpg', 'poster URL is passed through')
    calls_after_list = len(fake.calls)

    plugin.ITEMS.clear()
    run(as_argv(continue_url, 4))
    print('')
    print('=== cache hit ===')
    print('http calls %s (unchanged %s)' % (len(fake.calls), len(fake.calls) == calls_after_list))
    print('items %s' % len(plugin.ITEMS))
    check(len(fake.calls) == calls_after_list, 'cached list must not call Netflix')
    check(len(plugin.ITEMS) == 2, 'cached list should still have both titles')

    plugin.ITEMS.clear()
    plugin.CONTENT.clear()
    run(as_argv('plugin://plugin.video.smoothflix/list?show=80057281&title=Harbor+Lights', 5))
    dump('seasons', plugin)
    check(any(item.label == 'Season 1' for _url, item, _folder in plugin.ITEMS), 'season list')

    plugin.ITEMS.clear()
    plugin.CONTENT.clear()
    run(as_argv('plugin://plugin.video.smoothflix/list?show=80057281&season=s1&title=Season+1', 6))
    dump('episodes', plugin)
    episode = next(row for row in plugin.ITEMS if row[1].label == 'Pilot')
    check(episode[1].info.data.get('episode') == 1, 'episode number')
    check(episode[1].properties.get('IsPlayable') == 'true', 'episode should be playable')

    import xml.etree.ElementTree as ET
    skin = os.path.join(ADDON, 'resources', 'skins', 'Default', '1080i')
    for name in ('Font.xml', 'SmoothFlixHome.xml', 'SmoothFlixTitle.xml', 'SmoothFlixPlayer.xml'):
        ET.parse(os.path.join(skin, name))
        print('parsed %s' % name)

    from resources.lib.aurora import AuroraHome, PlayerOverlay
    WindowXML.opened = []
    run(['plugin://plugin.video.smoothflix/', '8', ''])
    home = WindowXML.opened[-1]
    row = home.getControl(200)
    print('')
    print('=== aurora home ===')
    print('xml %s' % home.xml)
    print('section %s' % home.getProperty('Section'))
    print('kicker %s' % home.getProperty('HeroKicker'))
    print('title %s' % home.getProperty('HeroTitle'))
    print('tag %s' % home.getProperty('HeroTag'))
    print('fanart %s' % home.getProperty('HeroFanart'))
    print('tint %s' % home.getControl(101).color)
    print('cards %s' % row.size())
    for card in row.items:
        print('[card] %s' % card.label)
        print('    meta %s' % card.getProperty('Meta'))
        print('    thumb %s' % card.art.get('thumb'))
        if card.info.data.get('resume'):
            print('    progress %r' % (card.info.data['resume'],))
    check(home.xml == 'SmoothFlixHome.xml', 'home should load SmoothFlixHome.xml')
    check(row.size() == 2, 'home row should list both cached titles')
    check(home.getProperty('HeroTitle') == 'HARBOR LIGHTS', 'hero title')
    check(home.getProperty('HeroFanart').startswith('https://'), 'hero fanart is a url')
    check(home.getControl(101).color.startswith('66'), 'focus tint is a charcoal wash')
    check(row.items[0].getProperty('Meta') == '32% WATCHED', 'progress caption')

    home.onClick(200)
    title = WindowXML.opened[-1]
    print('')
    print('=== aurora title ===')
    print('kicker %s' % title.getProperty('Kicker'))
    print('title %s' % title.getProperty('HeroTitle'))
    print('meta %s' % title.getProperty('Meta'))
    print('synopsis %s' % title.getProperty('Synopsis'))
    print('related %s' % title.getControl(210).size())
    check(title.xml == 'SmoothFlixTitle.xml', 'title window')
    check(title.getProperty('Kicker') == 'A SERIES', 'series kicker')
    check(title.getProperty('HeroTitle') == 'HARBOR LIGHTS', 'title page name')
    check('secret schedule' in title.getProperty('Synopsis'), 'synopsis copied onto the title page')

    overlay = PlayerOverlay('SmoothFlixPlayer.xml', ADDON, 'Default', '1080i')
    overlay.info = {
        'title': 'The Revenant',
        'meta': '2015 • Director',
        'position': 754,
        'duration': 9360,
        'volume': 35,
    }
    overlay.doModal()
    print('')
    print('=== aurora player ===')
    print('xml %s' % overlay.xml)
    print('title %s' % overlay.getProperty('Title'))
    print('meta %s' % overlay.getProperty('Meta'))
    print('elapsed %s' % overlay.getProperty('Elapsed'))
    print('total %s' % overlay.getProperty('Total'))
    print('progress %s' % overlay.getControl(400).percent)
    print('volume %s' % overlay.getControl(520).percent)
    check(overlay.xml == 'SmoothFlixPlayer.xml', 'player layout')
    check(overlay.getProperty('Title') == 'THE REVENANT', 'player title')
    check(overlay.getProperty('Meta') == '2015 • Director', 'player meta')
    check(overlay.getProperty('Elapsed') == '12:34', 'elapsed time')
    check(overlay.getControl(400).percent == 8, 'progress percent')

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    port_path = os.path.join(PROFILE, 'port')
    for _ in range(50):
        if os.path.exists(port_path):
            break
        thread.join(0.05)
    plugin.RESOLVED.clear()
    run(as_argv(episode[0], 7))
    print('')
    print('=== play ===')
    success, item = plugin.RESOLVED[-1]
    print('setResolvedUrl success=%s' % success)
    print('path %s' % item.path)
    print('mime %s' % item.mime)
    for key in (
        'inputstream',
        'inputstream.adaptive.manifest_type',
        'inputstream.adaptive.license_type',
        'inputstream.adaptive.license_key',
    ):
        print('%s = %s' % (key, item.properties.get(key)))
    check(success is True, 'play should resolve')
    check(item.properties.get('inputstream') == 'inputstream.adaptive', 'inputstream property')
    check(item.properties.get('inputstream.adaptive.manifest_type') == 'mpd', 'manifest type')
    check(item.properties.get('inputstream.adaptive.license_type') == 'com.widevine.alpha', 'widevine type')
    check('b{SSM}' in (item.properties.get('inputstream.adaptive.license_key') or ''), 'license challenge placeholder')

    manifest = urllib.request.urlopen(item.path, timeout=5).read().decode('utf-8')
    print('manifest bytes %s' % len(manifest))
    print(manifest)
    check('edef8ba9-79d6-4ace-a3c8-27dcd51d21ed' in manifest, 'MPD should name Widevine')
    check('https://example.com/video/init.mp4' in manifest, 'MPD should carry the stream URL')
    license_url = item.properties['inputstream.adaptive.license_key'].split('|', 1)[0]
    challenge = base64.standard_b64encode(b'cdm-challenge').decode('utf-8')
    sid = base64.standard_b64encode(b'session-1').decode('utf-8')
    request = urllib.request.Request(license_url, data=('%s!%s' % (challenge, sid)).encode('utf-8'))
    license_body = urllib.request.urlopen(request, timeout=5).read()
    print('license bytes %s' % license_body)
    check(license_body == LICENSE_BYTES, 'license hop should return the license bytes for the CDM')

    print('')
    if failures:
        print('%s check(s) failed' % len(failures))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
