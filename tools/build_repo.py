# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Zip each add-on, write addons.xml and addons.xml.md5, and the install zip.

Kodi looks up <datadir>/<id>/<id>-<version>.zip. The datadir is the root of
this repository on raw.githubusercontent.com. The install zip sits next to
addons.xml so it can be installed with "Install from zip file".
"""

import hashlib
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDONS = ('plugin.video.smoothflix', 'repository.smoothflix')
SKIP_SUFFIXES = ('.zip', '.pyc', '.pyo')


def addon_id_version(addon_dir):
    root = ET.parse(os.path.join(addon_dir, 'addon.xml')).getroot()
    return root.attrib['id'], root.attrib['version']


def zip_addon(addon_dir, dest):
    addon_id = os.path.basename(addon_dir)
    parent = os.path.dirname(addon_dir)
    # The archive is written outside the add-on folder. Writing it inside the
    # folder being walked makes the zip include itself.
    tmp = os.path.join(tempfile.gettempdir(), os.path.basename(dest) + '.tmp')
    with zipfile.ZipFile(tmp, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for folder, dirs, files in os.walk(addon_dir):
            dirs[:] = [name for name in dirs if name != '__pycache__']
            for name in sorted(files):
                if name.endswith(SKIP_SUFFIXES) or name.endswith('.tmp'):
                    continue
                full = os.path.join(folder, name)
                rel = os.path.relpath(full, parent).replace(os.sep, '/')
                archive.write(full, rel)
    os.replace(tmp, dest)
    with zipfile.ZipFile(dest) as archive:
        names = archive.namelist()
    if '%s/addon.xml' % addon_id not in names:
        raise SystemExit('zip is missing addon.xml: %s' % dest)
    return names


def addon_xml_text(addon_dir):
    with open(os.path.join(addon_dir, 'addon.xml'), encoding='utf-8') as handle:
        text = handle.read().strip()
    if text.startswith('<?xml'):
        text = text.split('?>', 1)[1].strip()
    return text


def main():
    written = []
    for addon_id in ADDONS:
        addon_dir = os.path.join(ROOT, addon_id)
        found_id, version = addon_id_version(addon_dir)
        if found_id != addon_id:
            raise SystemExit('folder %s has id %s' % (addon_id, found_id))
        dest = os.path.join(addon_dir, '%s-%s.zip' % (addon_id, version))
        names = zip_addon(addon_dir, dest)
        written.append((addon_id, version, dest, len(names)))
        print('zip %s (%s files)' % (os.path.relpath(dest, ROOT), len(names)))

    parts = [addon_xml_text(os.path.join(ROOT, addon_id)) for addon_id in ADDONS]
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<addons>\n' + '\n'.join(parts) + '\n</addons>\n'
    )
    xml_path = os.path.join(ROOT, 'addons.xml')
    data = document.encode('utf-8')
    with open(xml_path, 'wb') as handle:
        handle.write(data)
    digest = hashlib.md5(data).hexdigest()
    md5_path = os.path.join(ROOT, 'addons.xml.md5')
    with open(md5_path, 'w', encoding='utf-8') as handle:
        handle.write(digest + '\n')

    repo_id, repo_version, repo_zip, _count = written[1]
    install_zip = os.path.join(ROOT, '%s-%s.zip' % (repo_id, repo_version))
    shutil.copyfile(repo_zip, install_zip)

    print('addons.xml md5 %s' % digest)
    for addon_id, version, _dest, _count in written:
        print('listed %s %s' % (addon_id, version))
    print('install zip %s' % os.path.relpath(install_zip, ROOT))


if __name__ == '__main__':
    main()
