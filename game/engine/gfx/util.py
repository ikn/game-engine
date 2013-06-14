"""Utilities for graphics.

---NODOC---

TODO:
 - static:Grid.fit(rect; 2 of ntiles, tile_size, gap); tile_size, gap can be True for homogeneous sizes, in which case shrink to fit
 - allow negative column/row indices
 - Spritemap: takes Surface/image file, sprite_width, sprite_height = image_height
    - Spritemap[index] -> (Surface, rect)

---NODOC---

"""

import pygame as pg
from pygame import Rect

from ..util import align_rect
from .graphic import Graphic


class Grid (object):
    """A representation of a 2D grid of rectangular integer-sized tiles.

Used for aligning graphics on a grid.

Grid(ntiles, tile_size, gap = 0)

:arg ntiles: ``(x, y)`` number of tiles in the grid, or just ``x`` for a square
             grid.
:arg tile_size: ``(tile_width, tile_height)`` integers giving the size of every
                tile, or just ``tile_width`` for square tiles.  ``tile_width``
                and ``tile_height`` can also be functions that take the
                column/row index and return the width/height of that column/row
                respectively, or lists (or anything supporting indexing) that
                perform the same task.
:arg gap: ``(col_gap, row_gap)`` integers giving the gap between columns and
          rows respectively, or just ``col_gap`` for the same gap in both
          cases.  As with ``tile_size``, this can be a tuple of functions (or
          lists) which take the index of the preceding column/row and return
          the gap size.

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
                tuple(obj(i) for i in xrange(length))
            else:
                return tuple(obj[:length])

        if isinstance(tile_size, int):
            tx = ty = tile_size
        else:
            tx, ty = tile_size
        self._tile_size = (expand(tx, ntiles[0]), expand(ty, ntiles[1]))
        if isinstance(gap, int):
            gx = gy = gap
        else:
            gx, gy = gap
        self._gap = (expand(gx, ntiles[0] - 1), expand(gy, ntiles[1] - 1))

    @property
    def nx (self):
        """The number of tiles in a row."""
        return self.ntiles[0]

    @property
    def ny (self):
        """The number of tiles in a column."""
        return self.ntiles[1]

    def _size (self, axis):
        return sum(ts + gap for ts, gap in zip(self._tile_size[axis],
                                               self._gap[axis]))

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
        return self._tile_pos(0, row)

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

    def align (self, graphic, col, row, alignment = 0, pad = 0, offset = 0):
        """Align a graphic or surface within a tile.

align(self, graphic, col, row, alignment = 0, pad = 0, offset = 0)
    -> aligned_rect

``alignment``, ``pad`` and ``offset`` are as taken by
:func:`engine.util.align_rect`.

:arg graphic: a :class:`graphic.Graphic` instance or a Pygame surface.  In the
              former case, the :meth:`graphic.Graphic.align` method is called
              (but the graphic is not cropped to fit in the tile).
:arg col, row: column and row of the tile.

:return: a Pygame rect clipped within the tile giving the area the graphic
         should be put in, relative to the grid's top-left corner.

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
