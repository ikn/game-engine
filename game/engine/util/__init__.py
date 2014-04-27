# coding=utf-8
"""A number of utility functions."""

from random import random, randrange
from collections import defaultdict
from bisect import bisect

import pygame as pg
from pygame import Rect

from . import cb, grid

# be sure to change util.rst
__all__ = ('dd', 'ir', 'sum_pos', 'pos_in_rect', 'normalise_colour',
           'call_in_nest', 'bezier', 'OwnError', 'Owned', 'randsgn', 'rand0',
           'weighted_rand', 'align_rect', 'position_sfc', 'convert_sfc',
           'combine_drawn', 'blank_sfc')


# abstract


def dd (default, items = {}, **kwargs):
    """Create a ``collections.defaultdict`` with a static default.

dd(default[, items], **kwargs) -> default_dict

:arg default: the default value.
:arg items: dict or dict-like to initialise with.
:arg kwargs: extra items to initialise with.

:return: the created ``defaultdict``.

"""
    items = items.copy()
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


def pos_in_rect (pos, rect, round_val=False):
    """Return the position relative to ``rect`` given by ``pos``.

:arg pos: a position identifier.  This can be:

    - ``(x, y)``, where each is either a number relative to ``rect``'s
      top-left, or the name of a property of ``pygame.Rect`` which returns a
      number.
    - a single number ``x`` that is the same as ``(x, x)``.
    - the name of a property of ``pygame.Rect`` which returns an ``(x, y)`` 
      sequence of numbers.

:arg rect: a Pygame-style rect, or just a ``(width, height)`` size to assume a
           rect with top-left ``(0, 0)``.
:arg round_val: whether to round the resulting numbers to integers before
                returning.

:return: the qualified position relative to ``rect``'s top-left, as ``(x, y)``
         numbers.

"""
    if len(rect) == 2 and isinstance(rect[0], (int, float)):
        # got a size
        rect = ((0, 0), rect)
    rect = Rect(rect)
    if isinstance(pos, basestring):
        x, y = getattr(rect, pos)
        x -= rect.left
        y -= rect.top
    elif isinstance(pos, (int, float)):
        x = y = pos
    else:
        x, y = pos
        if isinstance(x, basestring):
            x = getattr(rect, x) - rect.left
        if isinstance(y, basestring):
            y = getattr(rect, y) - rect.top
    return (ir(x), ir(y)) if round_val else (x, y)


def normalise_colour (c):
    """Turn a colour into ``(R, G, B, A)`` format with each number from ``0``
to ``255``.

Accepts 3- or 4-item sequences (if 3, alpha is assumed to be ``255``), or an
integer whose hexadecimal representation is ``0xrrggbbaa``, or a CSS-style
colour in a string (``'#rgb'``, ``'#rrggbb'``, ``'#rgba'``, ``'#rrggbbaa'``
- or without the leading ``'#'``).

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


def call_in_nest (f, *args):
    """Collapse a number of similar data structures into one.

Used in ``interp_*`` functions.

call_in_nest(f, *args) -> result

:arg f: a function to call with elements of ``args``.
:arg args: each argument is a data structure of nested lists with a similar
           format.

:return: a new structure in the same format as the given arguments with each
         non-list object the result of calling ``f`` with the corresponding
         objects from each arg.

For example::

    >>> f = lambda n, c: str(n) + c
    >>> arg1 = [1, 2, 3, [4, 5], []]
    >>> arg2 = ['a', 'b', 'c', ['d', 'e'], []]
    >>> call_in_nest(f, arg1, arg2)
    ['1a', '2b', '3c', ['4d', '5e'], []]

One argument may have a list where others do not.  In this case, those that do
not have the object in that place passed to ``f`` for each object in the
(possibly further nested) list in the argument that does.  For example::

    >>> call_in_nest(f, [1, 2, [3, 4]], [1, 2, 3], 1)
    [f(1, 1, 1), f(2, 2, 1), [f(3, 3, 1),  f(4, 3, 1)]]

However, in arguments with lists, all lists must be the same length.

"""
    # Rect is a sequence but isn't recognised as collections.Sequence, so test
    # this way
    is_list = [(hasattr(arg, '__len__') and hasattr(arg, '__getitem__') and
                not isinstance(arg, basestring))
               for arg in args]
    if any(is_list):
        n = len(args[is_list.index(True)])
        # listify non-list args (assume all lists are the same length)
        args = (arg if this_is_list else [arg] * n
                for this_is_list, arg in zip(is_list, args))
        return [call_in_nest(f, *inner_args) for inner_args in zip(*args)]
    else:
        return f(*args)


# better for smaller numbers of points
def _bezier_recursive (t, *pts):
    if len(pts) > 3:
        return ((1 - t) * _bezier_recursive(t, *pts[:-1]) +
                t * _bezier_recursive(t, *pts[1:]))
    elif len(pts) == 3:
        a, b, c = pts
        ti = 1 - t
        return ti * ti * a + 2 * t * ti * b + t * t * c
    elif len(pts) == 2:
        return (1 - t) * pts[0] + t * pts[1]
    else:
        return pts[0]


# better for larger numbers of points
def _bezier_flat (t, *pts):
    n_pts = n = len(pts) - 1
    ti = 1 - t
    b = 0
    choose = 1

    # generate terms in pairs
    for i in xrange(n_pts // 2 + 1):
        b += choose * ti ** n * t ** i * pts[i]
        if i != n: # else this is the 'middle' term, which has no pair
            b += choose * ti ** i * t ** n * pts[n]
        choose = choose * n // (i + 1)
        n -= 1
    return b


def bezier (t, *pts):
    """Compute a 1D Bézier curve point.

:arg t: curve parameter.
:arg pts: points defining the curve.

"""
    if len(pts) >= 5: # empirical
        return _bezier_flat(t, *pts)
    elif pts:
        return _bezier_recursive(t, *pts)
    else:
        raise ValueError('expected at least one point')


class OwnError (RuntimeError):
    """Raised when taking ownership of an :class:`Owned <engine.util.Owned>`
instance fails."""

    pass


class Owned (object):
    """Manage 'owners' of an object.

Owned([max_owners], on_full='throw')

:arg max_owners: the maximum number of owners that this object can have
                 (greater than zero).
:arg on_full: behaviour when taking ownership is attempted but the limited
    specified by ``max_owners`` has been reached.  One of:

        - ``'throw'``: raise an :class:`OwnError <engine.util.OwnError>`
          exception.
        - ``'ignore'``: don't add the owner.
        - ``'replace'``: remove another owner (choice of owner to remove is
          undefined).

"""

    def __init__ (self, max_owners=None, on_full='throw'):
        #: As passed to the constructor.
        self.max_owners = max_owners
        if on_full not in ('throw', 'ignore', 'replace'):
            raise ValueError('unknown value for on_full: {}'.format(on_full))
        self._on_full = on_full
        # {owner_id: release_cb}
        self._owners = {}

    @property
    def max_owners (self):
        """As passed to the constructor.

Decreasing this value below the current number of owners does not cause owners
to be removed.

"""
        return self._max_owners

    @max_owners.setter
    def max_owners (self, max_owners):
        if max_owners is not None:
            max_owners = int(max_owners)
            if max_owners <= 0:
                raise ValueError('max_owners must be greater than zero')
        self._max_owners = max_owners

    @property
    def owners (self):
        """Set-like container of owner identifiers as passed to
:meth:`own <engine.util.Owned.own>`."""
        return self._owners.viewkeys()

    @property
    def owner (self):
        """Identifier for any single owner of this instance, or ``None``."""
        try:
            owner = next(self._owners.iterkeys())
        except StopIteration:
            owner = None
        return owner

    def own (self, owner_id, release_cb=None):
        """Attempt to take ownership of this instance.

own(owner_id[, release_cb]) -> success

:arg owner_id: non-``None`` hashable identifier for the owner, used for later
               removal.
:arg release_cb: optional function to call when this owner is removed (through
                 :meth:`release <engine.util.Owned.release>`, or by being
                 replaced by another owner if this instance allows it).  This
                 is called like ``release_cb(owned_instance, owner_id)``; if it
                 is determined that the function cannot take any arguments, it
                 is not given any.

:return: whether the attempt succeeded.  If not,
         :class:`OwnError <engine.util.OwnError>` may be raised instead,
         depending on the ``on_full`` argument passed to the constructor.

"""
        if owner_id is None:
            raise ValueError('owner_id cannot be None')
        success = False
        owners = self._owners
        if release_cb is not None:
            release_cb = cb.wrap_fn(release_cb)

        if owner_id not in owners:
            max_owners = self.max_owners

            if max_owners is not None and len(owners) >= max_owners:
                # reached owner limit
                if self._on_full == 'throw':
                    raise OwnError('{} already has the maximum number of '
                                   'owners ({})'.format(self, max_owners))
                elif self._on_full == 'replace':
                    # len(owners) >= max_owners > 0, so this is safe
                    self.release(next(owners.iterkeys()))
                    owners[owner_id] = release_cb
                    success = True
                # else ignore: success = False

            else:
                owners[owner_id] = release_cb
                success = True

        return success

    def release (self, owner_id):
        """Relinquish ownership of this instance.

:arg owner_id: identifier passed to :meth:`own <engine.util.Owned.own>`.

"""
        release_cb = self._owners.pop(owner_id, None)
        if release_cb is not None:
            release_cb(self, owner_id)


# random


def randsgn ():
    """Randomly return ``1`` or ``-1``."""
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
:arg alignment: ``(x, y)`` alignment; each is ``< 0`` for left-/top-aligned,
                ``0`` for centred, ``> 0`` for right-/bottom-aligned.  Can be
                just one number to use on both axes.
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
    rect = Rect(rect)
    sz = rect.size
    within = Rect(within)
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
