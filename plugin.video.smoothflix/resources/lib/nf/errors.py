# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Errors a person can act on. Messages must not contain passwords or cookies."""


class NetflixError(Exception):
    """Base for failures we show in a dialog."""


class MissingCredentials(NetflixError):
    pass


class BadCredentials(NetflixError):
    pass


class CaptchaRequired(NetflixError):
    pass


class SessionExpired(NetflixError):
    pass


class PinRequired(NetflixError):
    pass


class BadPin(NetflixError):
    pass


class PlaybackError(NetflixError):
    pass
