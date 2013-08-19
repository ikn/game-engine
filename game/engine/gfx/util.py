"""Utilities for graphics."""

import pygame as pg
from pygame import Rect

from ..conf import conf
from ..util import align_rect, has_alpha, blank_sfc
from .graphic import Graphic


class Grid (object):
    """A representation of a 2D grid of rectangular integer-sized tiles.

Used for aligning graphics on a grid.

Grid(ntiles, tile_size, gap = 0)

:arg ntiles: ``(x, y)`` number of tiles in the grid, or a single number for a
             square grid.
:arg tile_size: ``(tile_width, tile_height)`` integers giving the size of every
                tile, or a single number for square tiles.  ``tile_width`` and
                ``tile_height`` can also be functions that take the column/row
                index and return the width/height of that column/row
                respectively, or lists (or anything supporting indexing) that
                perform the same task.
:arg gap: ``(col_gap, row_gap)`` integers giving the gap between columns and
          rows respectively, or a single number for the same gap in both cases.
          As with ``tile_size``, this can be a tuple of functions (or lists)
          which take the index of the preceding column/row and return the gap
          size.

``col`` and ``row`` arguments to all methods may be negative to wrap from the
end of the row/column, like list indices.

"""

    def __init__ (self, ntiles, tile_size, gap = 0):
        if isinstance(ntiles, int):
            ntiles = (ntiles, ntiles)
        else:
            ntiles = tuple(ntiles[:2])
        #: The ``(x, y)`` number of tiles in the grid.
        self.ntiles = ntiles

        def expand (obj, length):
            # expand an int/list/function to the given length
            if isinstance(obj, int):
                return (obj,) * length
            elif callable(obj):
                return tuple(obj(i) for i in xrange(length))
            else:
                return tuple(obj[:length])

        if isinstance(tile_size, int) or callable(tile_size):
            tx = ty = tile_size
        else:
            tx, ty = tile_size
        self._tile_size = (expand(tx, ntiles[0]), expand(ty, ntiles[1]))
        if isinstance(gap, int) or callable(tile_size):
            gx = gy = gap
        else:
            gx, gy = gap
        self._gap = (expand(gx, ntiles[0] - 1), expand(gy, ntiles[1] - 1))

    @property
    def ncols (self):
        """The number of tiles in a row."""
        return self.ntiles[0]

    @property
    def nrows (self):
        """The number of tiles in a column."""
        return self.ntiles[1]

    def _size (self, axis):
        return sum(self._tile_size[axis]) + sum(self._gap[axis])

    @property
    def w (self):
        """The total width of the grid."""
        return self._size(0)

    @property
    def h (self):
        """The total height of the grid."""
        return self._size(1)

    @property
    def size (self):
        """The total ``(width, height)`` size of the grid."""
        return (self.w, self.h)

    def _tile_pos (self, axis, index):
        return sum(ts + gap for ts, gap in zip(self._tile_size[axis][:index],
                                               self._gap[axis][:index]))

    def tile_x (self, col):
        """Get the x position of the tile in the column with the given index.

This is the position of the left side of the tile relative to the left side of
the grid.

"""
        return self._tile_pos(0, col)

    def tile_y (self, row):
        """Get the y position of the tile in the row with the given index.

This is the position of the top side of the tile relative to the top side of
the grid.

"""
        return self._tile_pos(1, row)

    def tile_pos (self, col, row):
        """Get the ``(x, y)`` position of the tile in the given column and row.

This is the top-left corner of the tile relative to the top-left corner of the
grid.

"""
        return (self.tile_x(col), self.tile_y(row))

    def tile_size (self, col, row):
        """Get the ``(width, height)`` size of the given tile."""
        return (self._tile_size[0][col], self._tile_size[1][row])

    def tile_rect (self, col, row):
        """Get a Pygame rect for the tile in the given column and row.

This is relative to the top-left corner of the grid.

"""
        return Rect(self.tile_pos(col, row), self.tile_size(col, row))

    def tile_at (self, x, y):
        """Return the ``(col, row)`` tile at the point ``(x, y)``, or
``None``."""
        if x < 0 or y < 0:
            return None
        pos = (x, y)
        tile = []
        for axis, pos in enumerate((x, y)):
            current_pos = 0
            ts = self._tile_size[axis]
            gap = self._gap[axis] + (0,)
            for i in xrange(self.ntiles[axis]):
                current_pos += ts[i]
                # now we're at the end of a tile
                if current_pos > pos:
                    # pos is within the previous tile
                    tile.append(i)
                    break
                current_pos += gap[i]
                # now we're at the start of a tile
                if current_pos > pos:
                    # pos is within the previous gap
                    return None
            else:
                # didn't find a tile: point is past the end
                return None
        return tuple(tile)

    def align (self, graphic, col, row, alignment=0, pad=0, offset=0):
        """Align a graphic or surface within a tile.

align(self, graphic, col, row, alignment=0, pad=0, offset=0) -> aligned_rect

``alignment``, ``pad`` and ``offset`` are as taken by
:func:`engine.util.align_rect`.

:arg graphic: a :class:`Graphic <engine.gfx.graphic.Graphic>` instance or a
              Pygame surface.  In the former case, the graphic is moved (but it
              is not cropped to fit in the tile).
:arg col: column of the tile.
:arg row: row of the tile.

:return: a Pygame rect clipped within the tile giving the area the graphic
         should be put in.

"""
        if isinstance(graphic, Graphic):
            rect = graphic.rect
        else:
            rect = graphic.get_rect()
        pos = align_rect(rect, self.tile_rect(col, row), alignment, pad,
                         offset)
        if isinstance(graphic, Graphic):
            graphic.pos = pos
        return Rect(pos, rect.size)


class Spritemap (object):
    """A wrapper for spritesheets.

Spritemap(img[, ncols][, nrows][, sw][, sh], pad=0[, nsprites],
          pool=conf.DEFAULT_RESOURCE_POOL, res_mgr=conf.GAME.resources)

:arg img: a surface or filename to load from; this is a grid of sprites with
          the same size.
:arg ncols,sw: determines the the number of columns in the spritesheet;
               ``ncols`` is the number of columns and ``sw`` is the width of
               individual sprites, in pixels.  Only one is required, and both
               may be omitted if the spritesheet is a single column.
:arg nrows,sh: determines the the number of rows in the spritesheet; ``nrows``
               is the number of rows and ``sh`` is the height of individual
               sprites.  Only one is required, and both may be omitted if the
               spritesheet is a single row.
:arg pad: padding in pixels between each sprite.  This may be
          ``(col_gap, row_gap)``, or a single number for the same gap in both
          cases.
:arg nsprites: the number of sprites in the spritesheet.  If omitted, this is
               taken to be the maximum number of sprites that could fit on the
               spritesheet; if passed, and smaller than the maximum, the last
               sprites are ignored (see below for ordering).
:arg pool: :class:`ResourceManager <engine.res.ResourceManager>` resource pool
           name to cache any loaded images in.
:arg res_mgr: :class:`ResourceManager <engine.res.ResourceManager>` instance to
              use to load any images.

A spritemap provides ``__len__`` and ``__getitem__`` to obtain sprites, and so
iterating over all sprites is also supported.  Sprites are obtained from top to
bottom, left to right, in that order, and slices are as follows::

    spritemap[sprite_index] -> (sfc, rect)
    spritemap[col, row] -> (sfc, rect)

where ``sfc`` is a surface containing the sprite.  (The latter form is an
implicit ``tuple``, so ``spritemap[(col, row)]`` works as well.)

"""

    def __init__ (self, img, ncols=None, nrows=None, sw=None, sh=None, pad=0,
                  nsprites=None, pool=conf.DEFAULT_RESOURCE_POOL,
                  res_mgr=None):
        if isinstance(img, basestring):
            if res_mgr is None:
                res_mgr = conf.GAME.resources
            img = res_mgr.img(img, pool=pool)
        img_sz = img.get_size()
        if isinstance(pad, int):
            pad = (pad, pad)
        if pad[0] < 0 or pad[1] < 0:
            raise ValueError('padding must be positive')
        # get number of columns and rows and sprite size
        ncells = [ncols, nrows]
        ss = [sw, sh]
        for axis in (0, 1):
            n = ncells[axis]
            s_sz = ss[axis]
            i_sz = img_sz[axis]
            p = pad[axis]
            if n is not None:
                if (i_sz + p) % n != 0:
                    raise ValueError(
                        'invalid image size (dimension {0}): expected '
                        '({1}n-{2}), got {3}'.format(axis, n, p, i_sz)
                    )
                ss[axis] = (i_sz + p) // n - p
            elif s_sz is not None:
                if (i_sz + p) % (s_sz + p) != 0:
                    raise ValueError(
                        'invalid image size (dimension {0}): expected '
                        '({1}n-{2}), got {3}'.format(axis, s_sz + p, p, i_sz)
                    )
                ncells[axis] = (i_sz + p) // (s_sz + p)
            else:
                ncells[axis] = 1
                ss[axis] = i_sz
        self._ncells = ncells
        ncols, nrows = ncells
        ncells = ncols * nrows
        if nsprites is None or nsprites > ncells:
            nsprites = ncells
        #: The width of each sprite, in pixels.
        self.sprite_w = ss[0]
        #: The height of each sprite, in pixels.
        self.sprite_h = ss[1]
        #: ``(``:attr:`sprite_w` ``,`` :attr:`sprite_h` ``)``.
        self.sprite_size = tuple(ss)
        # copy to separate surfaces
        self._sfcs = sfcs = []
        tile_rect = Grid(ncells, ss, pad).tile_rect
        mk_sfc = blank_sfc if has_alpha(img) else pg.Surface
        for i in xrange(nsprites):
            rect = tile_rect(i % ncols, i // ncols)
            sfc = mk_sfc(rect.size)
            sfc.blit(img, (0, 0), rect)
            sfcs.append(sfc)

    def __len__ (self):
        return len(self._sfcs)

    def __getitem__ (self, i):
        ncols, nrows = self._ncells
        if not isinstance(i, int):
            col, row = i
            if col < 0:
                col += ncols
            if row < 0:
                row += nrows
            if (col < 0 or col >= ncols or row < 0 or row >= nrows):
                raise IndexError('spritemap index out of bounds')
            i = row * ncols + col
        return self._sfcs[i]
