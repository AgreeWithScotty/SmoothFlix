# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Kodi service. Stays up so playback can fetch the manifest and license."""

from resources.lib.nf.play import serve

serve()
