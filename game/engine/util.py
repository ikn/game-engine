"""A number of utility functions."""

from random import random, randrange
from collections import defaultdict
from bisect import bisect

import pygame as pg

__all__ = ('dd', 'ir', 'sum_pos', 'normalise_colour', 'randsgn', 'rand0',
           'weighted_rand', 'align_rect', 'position_sfc', 'convert_sfc',
           'combine_drawn', 'blank_sfc') # be sure to change util.rst


# abstract


def dd (default, items = {}, **kwargs):
    """Create a ``collections.defaultdict`` with a static default.

dd(default[, items], **kwargs) -> default_dict

:arg default: the default value.
:arg items: dict or dict-like to initialise with.
:arg kwargs: extra items to initialise with.

:return: the created ``defaultdict``.

"""
    items.update(kwargs)
    return defaultdict(lambda: default, items)


def ir (x):
    """Returns the argument rounded to the nearest integer.

This is about twice as fast as int(round(x)).

"""
    y = int(x)
    return (y + (x - y >= .5)) if x > 0 else (y - (y - x >= .5))


def sum_pos (*pos):
    """Sum all given ``(x, y)`` positions component-wise."""
    sx = sy = 0
    for x, y in pos:
        sx +=x
        sy +=y
    return (sx, sy)


def normalise_colour (c):
    """Turn a colour into (R, G, B, A) format with each number from 0 to 255.

Accepts 3- or 4-item sequences (if 3, alpha is assumed to be 255), or an
integer whose hexadecimal representation is 0xrrggbbaa, or a CSS-style colour
in a string ('#rgb', '#rrggbb', '#rgba', '#rrggbbaa' - or without the leading
'#').

"""
    if isinstance(c, int):
        a = c % 256
        c >>= 8
        b = c % 256
        c >>= 8
        g = c % 256
        c >>= 8
        r = c % 256
    elif isinstance(c, basestring):
        if c[0] == '#':
            c = c[1:]
        if len(c) < 6:
            c = list(c)
            if len(c) == 3:
                c.append('f')
            c = [x + x for x in c]
        else:
            if len(c) == 6:
                c = [c[:2], c[2:4], c[4:], 'ff']
            else: # len(c) == 8
                c = [c[:2], c[2:4], c[4:6], c[6:]]
        for i in xrange(4):
            x = 0
            for k, n in zip((16, 1), c[i]):
                n = ord(n)
                x += k * (n - (48 if n < 97 else 87))
            c[i] = x
        r, g, b, a = c
    else:
        r, g, b = c[:3]
        a = 255 if len(c) < 4 else c[3]
    return (r, g, b, a)


# random


def randsgn ():
    """Randomly return ``1`` or `-1``."""
    return 2 * randrange(2) - 1


def rand0 ():
    """Zero-centred random (``-1 <= x < 1``)."""
    return 2 * random() - 1


def weighted_rand (ws):
    """Return a weighted random choice.

weighted_rand(ws) -> index

:arg ws: weightings, either a list of numbers to weight by or a
         ``{key: weighting}`` dict for any keys.

:return: the chosen index in the list or key in the dict.

"""
    if isinstance(ws, dict):
        indices, ws = zip(*ws.iteritems())
    else:
        indices = range(len(ws))
    cumulative = []
    last = 0
    for w in ws:
        last += w
        cumulative.append(last)
    index = min(bisect(cumulative, cumulative[-1] * random()), len(ws) - 1)
    return indices[index]


# graphics


def align_rect (rect, within, alignment = 0, pad = 0, offset = 0):
    """Align a rect within another rect.

align_rect(rect, within, alignment = 0, pad = 0, offset = 0) -> pos

:arg rect: the Pygame-style rect to align.
:arg within: the rect to align ``rect`` within.
:arg alignment: ``(x, y)`` alignment; each is ``< 0`` for left-aligned, ``0``
                for centred, ``> 0`` for right-aligned.  Can be just one number
                to use on both axes.
:arg pad: ``(x, y)`` padding to leave around the inner edge of ``within``.  Can
          be negative to allow positioning outside of ``within``, and can be
          just one number to use on both axes.
:arg offset: ``(x, y)`` amounts to offset by after all other positioning; can
             be just one number to use on both axes.

:return: the position the top-left corner of the rect should be moved to for
         the wanted alignment.

"""
    pos = alignment
    pos = [pos, pos] if isinstance(pos, (int, float)) else list(pos)
    if isinstance(pad, (int, float)):
        pad = (pad, pad)
    if isinstance(offset, (int, float)):
        offset = (offset, offset)
    rect = pg.Rect(rect)
    sz = rect.size
    within = pg.Rect(within)
    within = list(within.inflate(-2 * pad[0], -2 * pad[1]))
    for axis in (0, 1):
        align = pos[axis]
        if align < 0:
            x = 0
        elif align == 0:
            x = (within[2 + axis] - sz[axis]) / 2.
        else: # align > 0
            x = within[2 + axis] - sz[axis]
        pos[axis] = ir(within[axis] + x + offset[axis])
    return pos


def position_sfc (sfc, dest, alignment = 0, pad = 0, offset = 0, rect = None,
                  within = None, blit_flags = 0):
    """Blit a surface onto another with alignment.

position_sfc(sfc, dest, alignment = 0, pad = 0, offset = 0,
             rect = sfc.get_rect(), within = dest.get_rect(), blit_flags = 0)

``alignment``, ``pad``, ``offset``, ``rect`` and ``within`` are as taken by
:func:`align_rect <engine.util.align_rect>`.  Only the portion of ``sfc``
within ``rect`` is copied.

:arg sfc: source surface to copy.
:arg dest: destination surface to blit to.
:arg blit_flags: the ``special_flags`` argument taken by
                 ``pygame.Surface.blit``.

"""
    if rect is None:
        rect = sfc.get_rect()
    if within is None:
        within = dest.get_rect()
    dest.blit(sfc, align_rect(rect, within, alignment, pad, offset), rect,
              blit_flags)


def has_alpha (sfc):
    """Return if the given surface has transparency of any kind."""
    return sfc.get_alpha() is not None or sfc.get_colorkey() is not None


def convert_sfc (sfc):
    """Convert a surface for blitting."""
    return sfc.convert_alpha() if has_alpha(sfc) else sfc.convert()


def combine_drawn (*drawn):
    """Combine the given drawn flags.

These are as returned by :meth:`engine.game.World.draw`.

"""
    if True in drawn:
        return True
    rects = sum((list(d) for d in drawn if d), [])
    return rects if rects else False


def blank_sfc (size):
    """Create a transparent surface with the given ``(width, height)`` size."""
    sfc = pg.Surface(size).convert_alpha()
    sfc.fill((0, 0, 0, 0))
    return sfc
