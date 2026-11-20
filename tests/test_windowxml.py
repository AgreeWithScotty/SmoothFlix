# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""WindowXML filenames must not be ones Kodi's active skin already ships.

Kodi 21 resolves WindowXML(xmlFilename, scriptPath, defaultSkin, defaultRes)
as <active skin>/<res>/<xmlFilename> first, and only then as
<scriptPath>/resources/skins/<defaultSkin>/<defaultRes>/<xmlFilename>.
Estuary ships Home.xml, so that name loads the skin file and getControl()
raises RuntimeError: Non-Existent Control.
"""

import ast
import importlib.util
import os
import sys
import unittest
import xml.etree.ElementTree as ET
import zipfile
from fnmatch import fnmatch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON = os.path.join(ROOT, 'plugin.video.smoothflix')
ADDON_ID = 'plugin.video.smoothflix'

# skin.estuary/xml at Kodi Omega 21.2. Font.xml is included because Estuary
# ships it; add-on font sets still have to use that name, and it is not a
# WindowXML file.
ESTUARY_XML = """
AddonBrowser.xml
Custom_1100_AddonLauncher.xml
Custom_1101_SettingsList.xml
Custom_1102_TextViewer.xml
Custom_1103_VolumeSlider.xml
Custom_1104_Fanart.xml
Custom_1105_MusicOSDSettings.xml
Custom_1107_SearchDialog.xml
Custom_1109_TopBarOverlay.xml
Custom_1110_TempoControl.xml
Defaults.xml
DialogAddonInfo.xml
DialogAddonSettings.xml
DialogBusy.xml
DialogButtonMenu.xml
DialogColorPicker.xml
DialogConfirm.xml
DialogContextMenu.xml
DialogExtendedProgressBar.xml
DialogFullScreenInfo.xml
DialogGameControllers.xml
DialogKeyboard.xml
DialogMediaSource.xml
DialogMusicInfo.xml
DialogNotification.xml
DialogNumeric.xml
DialogPVRChannelGuide.xml
DialogPVRChannelManager.xml
DialogPVRChannelsOSD.xml
DialogPVRGuideControls.xml
DialogPVRGuideSearch.xml
DialogPVRInfo.xml
DialogPVRRadioRDSInfo.xml
DialogPictureInfo.xml
DialogPlayerProcessInfo.xml
DialogSeekBar.xml
DialogSelect.xml
DialogSettings.xml
DialogSlider.xml
DialogSubtitles.xml
DialogTextViewer.xml
DialogVideoInfo.xml
DialogVideoManager.xml
DialogVolumeBar.xml
EventLog.xml
FileBrowser.xml
FileManager.xml
Font.xml
GameOSD.xml
Home.xml
Includes.xml
Includes_Animations.xml
Includes_Buttons.xml
Includes_DialogSelect.xml
Includes_Games.xml
Includes_Home.xml
Includes_MediaMenu.xml
Includes_MusicInfo.xml
Includes_PVR.xml
LoginScreen.xml
MusicOSD.xml
MusicVisualisation.xml
MyFavourites.xml
MyGames.xml
MyMusicNav.xml
MyMusicPlaylistEditor.xml
MyPVRChannels.xml
MyPVRGuide.xml
MyPVRRecordings.xml
MyPVRSearch.xml
MyPVRTimers.xml
MyPics.xml
MyPlaylist.xml
MyPrograms.xml
MyVideoNav.xml
MyWeather.xml
PlayerControls.xml
Pointer.xml
Settings.xml
SettingsCategory.xml
SettingsProfile.xml
SettingsScreenCalibration.xml
SettingsSystemInfo.xml
SkinSettings.xml
SlideShow.xml
SmartPlaylistEditor.xml
SmartPlaylistRule.xml
Startup.xml
Timers.xml
Variables.xml
VideoFullScreen.xml
VideoOSD.xml
VideoOSDBookmarks.xml
View_500_Wall.xml
View_501_Banner.xml
View_502_FanArt.xml
View_503_NowPlaying.xml
View_50_List.xml
View_51_Poster.xml
View_52_IconWall.xml
View_53_Shift.xml
View_54_InfoWall.xml
View_55_WideList.xml
""".split()

# Names Kodi or older default skins open from the active skin, plus the generic
# Title.xml / Player.xml names this add-on used to pass to WindowXML.
EXTRA_EXACT = (
    'DialogFavourites.xml',
    'DialogGameOSD.xml',
    'DialogGameVideoSelect.xml',
    'DialogGameVolume.xml',
    'DialogOK.xml',
    'DialogProgress.xml',
    'DialogYesNo.xml',
    'Favourites.xml',
    'MusicPlaylist.xml',
    'MusicPlaylistEditor.xml',
    'MusicSearch.xml',
    'MyMusicPlaylist.xml',
    'MyMusicSongs.xml',
    'MyVideoPlaylist.xml',
    'Player.xml',
    'PlayerProcessInfo.xml',
    'Title.xml',
    'VideoPlaylist.xml',
    'Visualisation.xml',
    'VisualisationPresetList.xml',
)

# Patterns the user called out, plus the other families Kodi skins use.
RESERVED_GLOBS = (
    'Dialog*.xml',
    'Video*.xml',
    'Music*.xml',
    'My*.xml',
    'Settings*.xml',
    'Custom_*.xml',
    'View_*.xml',
    'Includes*.xml',
    'Addon*.xml',
    'File*.xml',
    'Game*.xml',
    'SmartPlaylist*.xml',
    'Player*.xml',
    'Home.xml',
)

# Methods the controllers call, and the control type those methods belong to.
METHOD_TYPES = {
    'reset': 'fixedlist',
    'addItem': 'fixedlist',
    'getSelectedPosition': 'fixedlist',
    'getListItem': 'fixedlist',
    'size': 'fixedlist',
    'setColorDiffuse': 'image',
    'setPercent': 'progress',
}

WINDOW_BASES = ('WindowXML', 'WindowXMLDialog')
RETIRED = ('Home.xml', 'Title.xml', 'Player.xml')


def collides(name):
    folded = name.casefold()
    reserved = {item.casefold() for item in ESTUARY_XML}
    reserved.update(item.casefold() for item in EXTRA_EXACT)
    if folded in reserved:
        return True
    return any(fnmatch(folded, pattern.casefold()) for pattern in RESERVED_GLOBS)


def _py_files():
    found = []
    for base in (ADDON, os.path.join(ROOT, 'tools')):
        for folder, dirs, files in os.walk(base):
            dirs[:] = [name for name in dirs if name != '__pycache__']
            for name in files:
                if name.endswith('.py'):
                    found.append(os.path.join(folder, name))
    return found


def _const_str(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _const_int(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    return None


def _attr_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ''


def _callee(node):
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ''


def _getcontrol_id(node):
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr != 'getControl' or not node.args:
        return None
    return _const_int(node.args[0])


def _window_classes(tree):
    bases = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases[node.name] = [_attr_name(base) for base in node.bases]
    names = set()
    changed = True
    while changed:
        changed = False
        for name, class_bases in bases.items():
            if name in names:
                continue
            if any(base in WINDOW_BASES or base in names for base in class_bases):
                names.add(name)
                changed = True
    return names, bases


def _analyze_function(func):
    assigned = {}
    found = {}
    ids = set()
    dynamic = []

    def visit(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            return
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            visit(node.value)
            cid = _getcontrol_id(node.value)
            if cid is not None:
                assigned[node.targets[0].id] = cid
                ids.add(cid)
            elif (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == 'getControl'
            ):
                dynamic.append(node.lineno)
            return
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == 'getControl':
                cid = _const_int(node.args[0]) if node.args else None
                if cid is None:
                    dynamic.append(node.lineno)
                else:
                    ids.add(cid)
            else:
                target = None
                if isinstance(node.func.value, ast.Name):
                    target = assigned.get(node.func.value.id)
                else:
                    target = _getcontrol_id(node.func.value)
                mapped = METHOD_TYPES.get(node.func.attr)
                if target is not None and mapped:
                    ids.add(target)
                    found.setdefault(target, set()).add(mapped)
            visit(node.func.value)
            for arg in node.args:
                visit(arg)
            for keyword in node.keywords:
                visit(keyword.value)
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    for stmt in func.body:
        visit(stmt)
    return ids, found, dynamic


def _class_controls(tree):
    controls = {}
    dynamic = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        ids = set()
        found = {}
        bad_lines = []
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                f_ids, f_found, f_dynamic = _analyze_function(child)
                ids.update(f_ids)
                bad_lines.extend(f_dynamic)
                for cid, types in f_found.items():
                    found.setdefault(cid, set()).update(types)
        controls[node.name] = (ids, found)
        dynamic[node.name] = bad_lines
    return controls, dynamic


def _inherited(name, bases, controls, seen=None):
    seen = seen or set()
    if name in seen:
        return set(), {}
    seen.add(name)
    ids, found = controls.get(name, (set(), {}))
    ids = set(ids)
    merged = {cid: set(types) for cid, types in found.items()}
    for base in bases.get(name, []):
        if base not in controls:
            continue
        base_ids, base_found = _inherited(base, bases, controls, seen)
        ids.update(base_ids)
        for cid, types in base_found.items():
            merged.setdefault(cid, set()).update(types)
    return ids, merged


def load_windows():
    """Return window class info and every WindowXML(xml, path, skin, res) call."""
    classes = {}
    bases = {}
    dynamic = {}
    trees = []
    for path in _py_files():
        with open(path, encoding='utf-8') as handle:
            source = handle.read()
        tree = ast.parse(source, filename=path)
        file_classes, file_bases = _window_classes(tree)
        file_controls, file_dynamic = _class_controls(tree)
        for name in file_classes:
            classes[name] = file_controls.get(name, (set(), {}))
            bases[name] = file_bases.get(name, [])
            dynamic[name] = file_dynamic.get(name, [])
        trees.append((path, tree))
    refs = []
    for path, tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _callee(node)
            if name not in classes and name not in WINDOW_BASES:
                continue
            filename = _const_str(node.args[0]) if node.args else None
            if not filename or not filename.endswith('.xml'):
                refs.append({
                    'file': path,
                    'line': node.lineno,
                    'class': name,
                    'xml': None,
                    'skin': None,
                    'res': None,
                })
                continue
            skin = _const_str(node.args[2]) if len(node.args) > 2 else None
            res = _const_str(node.args[3]) if len(node.args) > 3 else None
            refs.append({
                'file': path,
                'line': node.lineno,
                'class': name,
                'xml': filename,
                'skin': skin,
                'res': res,
            })
    return classes, bases, dynamic, refs


def xml_control_types(path):
    found = {}
    for control in ET.parse(path).getroot().iter('control'):
        raw = control.attrib.get('id')
        if raw is None or not str(raw).isdigit():
            continue
        cid = int(raw)
        kind = control.attrib.get('type')
        if cid in found and found[cid] != kind:
            raise AssertionError('%s control %s is both %s and %s' % (path, cid, found[cid], kind))
        found[cid] = kind
    return found


def skin_xml_files():
    found = []
    root = os.path.join(ADDON, 'resources', 'skins')
    for folder, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name != '__pycache__']
        for name in files:
            if name.endswith('.xml'):
                found.append(os.path.join(folder, name))
    return found


def addon_version():
    root = ET.parse(os.path.join(ADDON, 'addon.xml')).getroot()
    return root.attrib['id'], root.attrib['version']


def _record_kodi():
    """Stub Kodi once, then import Aurora so tests can trip window init."""
    if getattr(_record_kodi, 'done', False):
        return sys.modules['xbmc'], sys.modules['xbmcgui'], sys.modules['resources.lib.aurora']
    sys.path.insert(0, ADDON)
    path = os.path.join(ROOT, 'tools', 'smoke_test.py')
    spec = importlib.util.spec_from_file_location('smoothflix_smoke', path)
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    smoke.install_stubs()
    import resources.lib.aurora as aurora
    _record_kodi.done = True
    return sys.modules['xbmc'], sys.modules['xbmcgui'], aurora


class WindowXMLRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes, cls.bases, cls.dynamic, cls.refs = load_windows()

    def test_window_filenames_do_not_collide_with_kodi(self):
        self.assertTrue(self.refs, 'no WindowXML constructors found')
        referenced = []
        for ref in self.refs:
            self.assertTrue(ref['xml'], 'dynamic WindowXML filename at %s:%s' % (ref['file'], ref['line']))
            self.assertFalse(
                collides(ref['xml']),
                '%s is a Kodi skin window filename (%s:%s)' % (ref['xml'], ref['file'], ref['line']))
            self.assertNotIn(ref['xml'], RETIRED)
            referenced.append(ref['xml'])
        on_disk = skin_xml_files()
        names = [os.path.basename(path) for path in on_disk]
        self.assertIn('Font.xml', names)
        self.assertNotIn('Font.xml', referenced)
        for path in on_disk:
            name = os.path.basename(path)
            if name == 'Font.xml':
                continue
            self.assertIn(name, referenced, '%s is not opened by WindowXML' % path)
            self.assertFalse(collides(name), '%s collides with a standard Kodi skin filename' % name)
        for banned in ('Home.xml', 'DialogSelect.xml', 'DialogBusy.xml', 'VideoOSD.xml', 'VideoFullScreen.xml'):
            self.assertTrue(collides(banned), banned)
        for safe in ('SmoothFlixHome.xml', 'SmoothFlixTitle.xml', 'SmoothFlixPlayer.xml'):
            self.assertFalse(collides(safe), safe)

    def test_packaged_zip_contains_referenced_windows(self):
        addon_id, version = addon_version()
        self.assertEqual(addon_id, ADDON_ID)
        zip_path = os.path.join(ADDON, '%s-%s.zip' % (addon_id, version))
        self.assertTrue(os.path.isfile(zip_path), 'missing packaged zip %s' % zip_path)
        with zipfile.ZipFile(zip_path) as archive:
            self.assertIsNone(archive.testzip())
            names = set(archive.namelist())
            packaged = []
            for ref in self.refs:
                self.assertTrue(ref['skin'] and ref['res'], 'skin/res are not literals at %s:%s' % (ref['file'], ref['line']))
                relative = os.path.join('resources', 'skins', ref['skin'], ref['res'], ref['xml'])
                disk = os.path.join(ADDON, relative)
                entry = '%s/%s' % (addon_id, relative.replace(os.sep, '/'))
                self.assertTrue(os.path.isfile(disk), 'missing %s' % disk)
                self.assertIn(entry, names, 'zip is missing %s' % entry)
                with open(disk, 'rb') as handle:
                    disk_bytes = handle.read()
                self.assertEqual(archive.read(entry), disk_bytes, entry)
                packaged.append(entry)
            for name in names:
                if '/resources/skins/' not in name or not name.endswith('.xml'):
                    continue
                base = name.rsplit('/', 1)[-1]
                if base == 'Font.xml':
                    continue
                self.assertIn(name, packaged, 'zip ships an unreferenced skin window %s' % name)
                self.assertFalse(collides(base), name)

    def test_getcontrol_ids_exist_with_expected_type(self):
        seen = set()
        checked = set()
        for ref in self.refs:
            if ref['class'] not in self.classes:
                continue
            key = (ref['class'], ref['xml'], ref['skin'], ref['res'])
            if key in seen:
                continue
            seen.add(key)
            self.assertFalse(self.dynamic.get(ref['class']), 'non-literal getControl in %s' % ref['class'])
            ids, found = _inherited(ref['class'], self.bases, self.classes)
            self.assertTrue(ids, '%s never calls getControl' % ref['class'])
            path = os.path.join(ADDON, 'resources', 'skins', ref['skin'], ref['res'], ref['xml'])
            types = xml_control_types(path)
            for cid in sorted(ids):
                expected = found.get(cid)
                self.assertTrue(expected, '%s getControl(%s) has no expected type' % (ref['class'], cid))
                self.assertEqual(len(expected), 1, '%s control %s maps to %s' % (ref['class'], cid, sorted(expected)))
                kind = next(iter(expected))
                self.assertIn(cid, types, '%s id %s is missing from %s' % (ref['class'], cid, ref['xml']))
                self.assertEqual(
                    types[cid], kind,
                    '%s control %s is <%s> in %s; the controller uses it as <%s>' % (
                        ref['class'], cid, types[cid], ref['xml'], kind))
                checked.add(cid)
        self.assertTrue({101, 200, 210, 400, 520}.issubset(checked))


class WindowInitErrorTest(unittest.TestCase):
    def setUp(self):
        self.xbmc, self.gui, self.aurora = _record_kodi()
        self.logs = []
        self.dialogs = []
        self._log = self.xbmc.log
        self._dialog = self.gui.Dialog
        self.xbmc.log = lambda message, level=1: self.logs.append((message, level))

        dialogs = self.dialogs

        class RecordingDialog(object):
            def ok(self, heading, message):
                dialogs.append((heading, message))

            def notification(self, heading, message, icon='', time=5000, sound=True):
                dialogs.append((heading, message))

        self.gui.Dialog = RecordingDialog

    def tearDown(self):
        self.xbmc.log = self._log
        self.gui.Dialog = self._dialog

    def _assert_reported(self, exc_text):
        self.assertTrue(self.logs, 'xbmc.log was not called')
        message, level = self.logs[-1]
        self.assertEqual(level, self.xbmc.LOGERROR)
        self.assertTrue(message.startswith('[SmoothFlix]\n'), message)
        self.assertIn('Traceback (most recent call last):', message)
        self.assertIn(exc_text, message)
        self.assertEqual(len(self.dialogs), 1)
        heading, shown = self.dialogs[0]
        self.assertEqual(heading, 'SmoothFlix')
        self.assertEqual(shown, 'RuntimeError: %s' % exc_text)
        self.assertNotIn('Traceback', shown)
        self.assertNotIn('\n', shown)
        self.assertLessEqual(len(shown), 180)

    def test_constructor_failure_logs_traceback_and_shows_text(self):
        text = 'Non-Existent Control 200'

        class Broken(object):
            def __init__(self, *args, **kwargs):
                raise RuntimeError(text)

        originals = (
            self.aurora.AuroraHome,
            self.aurora.TitleWindow,
            self.aurora.PlayerOverlay,
        )
        self.aurora.AuroraHome = Broken
        self.aurora.TitleWindow = Broken
        self.aurora.PlayerOverlay = Broken
        try:
            self.aurora.open_home()
            self._assert_reported(text)
            self.logs[:] = []
            self.dialogs[:] = []
            self.aurora.open_title({'id': '1', 'title': 'Harbor'})
            self._assert_reported(text)
            self.logs[:] = []
            self.dialogs[:] = []
            self.assertIsNone(self.aurora.playback_overlay())
            self._assert_reported(text)
        finally:
            self.aurora.AuroraHome, self.aurora.TitleWindow, self.aurora.PlayerOverlay = originals

    def test_oninit_failure_logs_traceback_and_shows_text(self):
        text = 'Non-Existent Control 200'
        original = self.aurora.AuroraHome._load

        def boom(self, row):
            raise RuntimeError(text)

        self.aurora.AuroraHome._load = boom
        try:
            self.aurora.open_home()
            self._assert_reported(text)
        finally:
            self.aurora.AuroraHome._load = original


if __name__ == '__main__':
    unittest.main()
