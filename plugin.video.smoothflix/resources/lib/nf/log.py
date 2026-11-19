# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Logging that refuses to record credentials, cookies, or license bytes."""

import xbmc

_BLOCKED = ('password', 'netflixid', 'cookie', 'authorization', 'challenge', 'license')


def log(message, level=None):
    text = str(message)
    lowered = text.lower()
    if any(word in lowered for word in _BLOCKED):
        text = 'suppressed a log line that mentioned session material'
    xbmc.log('[SmoothFlix] ' + text, xbmc.LOGINFO if level is None else level)
