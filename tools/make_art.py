# -*- coding: utf-8 -*-
# Copyright (C) 2026 Scott
# SPDX-License-Identifier: GPL-3.0-only
"""Draw the SmoothFlix icon, fanart, and home tiles.

Original artwork only: a light ribbon on ink. No third-party logos.
"""

import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, 'plugin.video.smoothflix')
REPO = os.path.join(ROOT, 'repository.smoothflix')
MEDIA = os.path.join(PLUGIN, 'resources', 'media')

FONT_BOLD = '/usr/share/fonts/truetype/macos/Inter-Bold.ttf'
FONT_MEDIUM = '/usr/share/fonts/truetype/macos/Inter-Medium.ttf'

INK_TOP = (12, 16, 24)
INK_BOTTOM = (24, 18, 16)
CREAM = (244, 237, 226)
MUTED = (186, 178, 166)
TEAL = (46, 214, 190)
GOLD = (232, 184, 96)

TILES = [
    ('continue.jpg', 'Continue', (46, 214, 190)),
    ('mylist.jpg', 'My List', (232, 184, 96)),
    ('trending.jpg', 'Trending', (214, 122, 96)),
    ('new.jpg', 'New', (120, 214, 168)),
    ('popular.jpg', 'Popular', (128, 146, 230)),
    ('spotlight.jpg', 'Spotlight', (230, 150, 92)),
    ('shows.jpg', 'Series', (72, 168, 214)),
    ('movies.jpg', 'Movies', (214, 176, 110)),
    ('search.jpg', 'Search', (176, 186, 196)),
    ('profiles.jpg', 'Profiles', (110, 196, 160)),
    ('account.jpg', 'Account', (168, 150, 214)),
]


def gradient(size, top, bottom):
    column = Image.new('RGB', (1, size[1]))
    pixels = column.load()
    last = max(size[1] - 1, 1)
    for y in range(size[1]):
        blend = y / last
        pixels[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * blend) for i in range(3))
    return column.resize(size, Image.Resampling.BILINEAR)


def ribbon(size, color, y_center, amplitude, thickness, phase, cycles):
    layer = Image.new('RGB', size, (0, 0, 0))
    draw = ImageDraw.Draw(layer)
    width, _height = size
    steps = max(width, 240)
    for index in range(steps):
        along = index / (steps - 1)
        x = int(along * (width - 1))
        y = int(y_center + math.sin((along * cycles + phase) * math.tau) * amplitude)
        radius = max(2, int(thickness * (0.45 + 0.55 * math.sin(along * math.pi))))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
    return layer.filter(ImageFilter.GaussianBlur(radius=max(2, thickness // 3)))


def vignette(img):
    small_w, small_h = 96, 54
    mask = Image.new('L', (small_w, small_h), 0)
    pixels = mask.load()
    for y in range(small_h):
        for x in range(small_w):
            dx = (x - (small_w - 1) / 2) / (small_w / 2)
            dy = (y - (small_h - 1) / 2) / (small_h / 2)
            distance = math.sqrt(dx * dx + dy * dy)
            pixels[x, y] = int(max(0, min(255, (distance - 0.35) * 220)))
    mask = mask.resize(img.size, Image.Resampling.BICUBIC)
    return Image.composite(Image.new('RGB', img.size, (0, 0, 0)), img, mask)


def screen_ribbon(base, color, y_center, amplitude, thickness, phase, cycles):
    glow = ribbon(base.size, color, y_center, amplitude, thickness, phase, cycles)
    return ImageChops.screen(base, glow)


def tracked_width(draw, text, font, tracking):
    width = 0
    for index, char in enumerate(text):
        width += draw.textlength(char, font=font)
        if index != len(text) - 1:
            width += tracking
    return width


def tracked(draw, origin, text, font, fill, tracking):
    x, y = origin
    for index, char in enumerate(text):
        draw.text((x, y), char, font=font, fill=fill)
        x += draw.textlength(char, font=font)
        if index != len(text) - 1:
            x += tracking


def save_jpeg(img, path, quality=86):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.convert('RGB').save(path, 'JPEG', quality=quality, optimize=True)
    size = os.path.getsize(path)
    if size > 900 * 1024:
        img.convert('RGB').save(path, 'JPEG', quality=72, optimize=True)
    print('%s %sx%s %s KB' % (
        os.path.relpath(path, ROOT), img.size[0], img.size[1], os.path.getsize(path) // 1024))


def save_png(img, path):
    img = img.convert('RGB')
    if img.size != (256, 256):
        raise SystemExit('icon must be 256x256, got %s' % (img.size,))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, 'PNG', optimize=True)
    print('%s %sx%s %s KB' % (
        os.path.relpath(path, ROOT), 256, 256, os.path.getsize(path) // 1024))


def icon(mark):
    image = gradient((256, 256), INK_TOP, (18, 28, 36))
    image = screen_ribbon(image, TEAL, 118, 36, 18, 0.08, 1.0)
    image = screen_ribbon(image, GOLD, 132, 28, 8, 0.22, 1.0)
    image = vignette(image)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT_BOLD, 28)
    width = draw.textlength(mark, font=font)
    draw.text(((256 - width) / 2, 196), mark, font=font, fill=CREAM)
    return image


def fanart(subtitle):
    image = gradient((1920, 1080), INK_TOP, INK_BOTTOM)
    image = screen_ribbon(image, TEAL, 470, 150, 70, 0.05, 1.15)
    image = screen_ribbon(image, GOLD, 540, 110, 28, 0.18, 1.15)
    image = vignette(image)
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(FONT_BOLD, 108)
    sub_font = ImageFont.truetype(FONT_MEDIUM, 36)
    draw.text((120, 700), 'SmoothFlix', font=title_font, fill=CREAM)
    draw.text((124, 830), subtitle, font=sub_font, fill=MUTED)
    draw.rectangle((124, 892, 280, 898), fill=GOLD)
    return image


def tile(caption, accent):
    image = gradient((400, 600), INK_TOP, tuple(max(0, channel // 5) for channel in accent))
    image = screen_ribbon(image, accent, 230, 70, 26, 0.1, 1.05)
    image = screen_ribbon(image, GOLD, 260, 40, 8, 0.3, 1.05)
    image = vignette(image)
    draw = ImageDraw.Draw(image)
    eyebrow = ImageFont.truetype(FONT_MEDIUM, 16)
    brand = 'SMOOTHFLIX'
    brand_width = tracked_width(draw, brand, eyebrow, 3)
    tracked(draw, ((400 - brand_width) / 2, 48), brand, eyebrow, MUTED, 3)
    title_font = fit(draw, caption, 340, 54)
    title_width = draw.textlength(caption, font=title_font)
    draw.text(((400 - title_width) / 2, 470), caption, font=title_font, fill=CREAM)
    return image


def fit(draw, text, max_width, start):
    size = start
    while size > 22:
        font = ImageFont.truetype(FONT_BOLD, size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 2
    return ImageFont.truetype(FONT_BOLD, 22)


def main():
    os.makedirs(MEDIA, exist_ok=True)
    save_png(icon('SmoothFlix'), os.path.join(PLUGIN, 'icon.png'))
    save_jpeg(fanart('Fast listings for your own library'), os.path.join(PLUGIN, 'fanart.jpg'))
    save_png(icon('Repository'), os.path.join(REPO, 'icon.png'))
    save_jpeg(fanart('Repository'), os.path.join(REPO, 'fanart.jpg'))
    for name, caption, accent in TILES:
        save_jpeg(tile(caption, accent), os.path.join(MEDIA, name), quality=88)


if __name__ == '__main__':
    main()
