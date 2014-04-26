"""Abstract grid representations."""

from pygame import Rect


class Grid (object):
    """A representation of a 2D grid of rectangular integer-sized tiles.

Used for aligning mouse input, graphics, etc. on a grid.

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

    def tile_rects (self, pos=False):
        """Iterator over :meth:`tile_rect` for all tiles.

:arg pos: whether to yield ``(col, row, tile_rect)`` instead of just
          ``tile_rect``.

"""
        ts = self._tile_size
        gap = self._gap
        x = 0
        # add extra element to gap so we iterate over the last tile
        for col, (w, gap_x) in enumerate(zip(ts[0], gap[0] + (0,))):
            y = 0
            for row, (h, gap_y) in enumerate(zip(ts[1], gap[1] + (0,))):
                r = Rect(x, y, w, h)
                yield (col, row, r) if pos else r
                y += h + gap_y
            x += w + gap_x

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
:func:`align_rect <engine.util.align_rect>`.

:arg graphic: a :class:`gfx.Graphic <engine.gfx.graphic.Graphic>` instance or a
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


class InfiniteGrid (object):
    """A representation of an infinite 2D grid of rectangular tiles.

InfiniteGrid(tile_size, gap=0)

:arg tile_size: ``(tile_width, tile_height)`` numbers giving the size of every
                tile, or a single number for square tiles.
:arg gap: ``(col_gap, row_gap)`` numbers giving the gap between columns and
          rows respectively, or a single number for the same gap in both cases.

The grid expands in all directions, so ``col`` and ``row`` arguments to methods
may be negative, and tile/gap sizes may be floats.

"""

    def __init__ (self, tile_size, gap=0):
        if isinstance(tile_size, (int, float)):
            tile_size = (tile_size, tile_size)
        else:
            tile_size = tuple(tile_size[:2])
        if any(x < 0 for x in tile_size):
            raise ValueError('tile sizes must be positive')
        #: ``tile_size`` as taken by the constructor.
        self.tile_size = tile_size
        if isinstance(gap, (int, float)):
            gap = (gap, gap)
        else:
            gap = tuple(gap[:2])
        if any(g < 0 for g in gap):
            raise ValueError('tile gaps must be positive')
        #: ``gap`` as taken by the constructor.
        self.gap = gap

    def tile_x (self, col):
        """Get the x position of the tile in the column with the given index.

This is the position of the left side of the tile relative to the left side of
column ``0``.

"""
        return (self.tile_size[0] * self.gap[0]) * col

    def tile_y (self, row):
        """Get the y position of the tile in the row with the given index.

This is the position of the top side of the tile relative to the top side of
row ``0``.

"""
        return (self.tile_size[1] * self.gap[1]) * row

    def tile_pos (self, col, row):
        """Get the ``(x, y)`` position of the tile in the given column and row.

This is the top-left corner of the tile relative to the top-left corner of the
tile ``(0, 0)``.

"""
        return (self.tile_x(col), self.tile_y(row))

    def tile_rect (self, col, row):
        """Get a Pygame-style rect for the tile in the given column and row.

This is relative to tile ``(0, 0)``, and elements can be floats.

"""
        return self.tile_pos(col, row) + self.tile_size

    def tile_rects (self, rect, pos=False):
        """Iterator over :meth:`tile_rect` for tiles that intersect ``rect``.

:arg rect: ``(x, y, w, h)`` with elements possibly floats.
:arg pos: whether to yield ``(col, row, tile_rect)`` instead of just
          ``tile_rect``.

"""
        ts = self.tile_size
        gap = self.gap
        # compute offsets
        x0 = (rect[0] // (ts[0] + gap[0])) * (ts[0] + gap[0])
        y0 = (rect[1] // (ts[1] + gap[1])) * (ts[1] + gap[1])
        # do the loop
        xr = rect[0] + rect[2]
        yb = rect[1] + rect[3]
        x = x0
        col = 0
        while True:
            y = y0
            row = 0
            while True:
                yield (col, row, r) if pos else r
                y += ts[1] + gap[1]
                if y >= yb:
                    break
                row += 1
            x += ts[0] + gap[0]
            if x >= xr:
                break
            col += 1

    def tile_at (self, x, y):
        """Return the ``(col, row)`` tile at the point ``(x, y)``, or
``None``.

Returns ``None`` within gaps between tiles.

"""
        ts = self.tile_size
        gap = self.gap
        pos = (x, y)
        tile = []
        for axis in (0, 1):
            this_tile, offset = divmod(pos[axis], float(ts[axis] + gap[axis]))
            if offset < ts[axis]:
                # in the tile
                tile.append(this_tile)
            else:
                # in the gap
                return None
        return tuple(tile)

    def align (self, graphic, col, row, alignment=0, pad=0, offset=0):
        """Align a graphic or surface within a tile.

align(self, graphic, col, row, alignment=0, pad=0, offset=0) -> aligned_rect

``alignment``, ``pad`` and ``offset`` are as taken by
:func:`align_rect <engine.util.align_rect>`.

:arg graphic: a :class:`gfx.Graphic <engine.gfx.graphic.Graphic>` instance or a
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
