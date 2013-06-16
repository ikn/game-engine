"""Specialised types of graphics.

---NODOC---

TODO:
 - Text
 - Animation(surface | filename[image])

---NODOC---

"""

from os.path import splitext

import pygame as pg
from pygame import Rect

from ..conf import conf
from ..util import normalise_colour, align_rect, blank_sfc
from .graphic import Graphic
from .util import Grid


class Colour (Graphic):
    """A solid rect of colour
(:class:`Graphic <engine.gfx.graphic.Graphic>` subclass).

Colour(colour, rect, layer = 0, blit_flags = 0)

:arg colour: a colour to draw, as accepted by
             :func:`engine.util.normalise_colour`.
:arg rect: ``(left, top, width, height)`` rect (of ints) to draw in (or
           anything taken by ``pygame.Rect``, like a ``Rect``, or
           ``((left, top), (width, height))``).
:arg layer, blit_flags: as taken by
                        :class:`Graphic <engine.gfx.graphic.Graphic>`.

:meth:`fill` corresponds to a builtin transform.

"""

    _i = Graphic._builtin_transforms.index('crop')
    _builtin_transforms = Graphic._builtin_transforms[:_i] + ('fill',) + \
                          Graphic._builtin_transforms[_i:]

    def __init__ (self, colour, rect, layer = 0, blit_flags = 0):
        rect = Rect(rect)
        # converts surface and sets opaque to True
        Graphic.__init__(self, pg.Surface(rect.size), rect.topleft, layer,
                         blit_flags)
        self._colour = (0, 0, 0)
        self.fill(colour)

    @property
    def colour (self):
        """As taken by constructor; set as necessary."""
        return self._colour

    @colour.setter
    def colour (self, colour):
        self.fill(colour)

    def _gen_mods_fill (self, src_sz, first_time, last_args, colour):
        if first_time or \
           normalise_colour(last_args[0]) != normalise_colour(colour):

            def apply_fn (g):
                g._colour = colour

            def undo_fn (g):
                g._colour = (0, 0, 0)

            mods = (apply_fn, undo_fn)
        else:
            mods = None
        return (mods, src_sz)

    def _fill (self, src, dest, dirty, last_args, colour):
        colour = normalise_colour(colour)
        if colour == (0, 0, 0, 255):
            return (src, dirty)
        if dest is not None and src.get_size() == dest.get_size():
            # we can reuse dest
            last_colour = normalise_colour(last_args[0])
            if last_colour[3] == 255 and colour[3] < 255:
                # newly transparent
                dest = dest.convert_alpha()
            if dirty is True or last_colour != colour:
                # need to refill everything
                dest.fill(colour)
                return (dest, True)
            elif dirty:
                # same colour, some areas changed
                for r in dirty:
                    dest.fill(colour, r)
                return (dest, dirty)
            else:
                # same as last time
                return (dest, False)
        # create new surface and fill
        new_sfc = pg.Surface(src.get_size())
        if colour[3] < 255:
            # non-opaque: need to convert to alpha
            new_sfc = new_sfc.convert_alpha()
        else:
            new_sfc = new_sfc.convert()
        new_sfc.fill(colour)
        return (new_sfc, True)

    def fill (self, colour):
        """Fill with the given colour (like :attr:`colour`)."""
        self.transform('fill', colour)
        self._colour = colour
        return self


class Tilemap (Graphic):
    """A :class:`Graphic <engine.gfx.graphic.Graphic>` subclass representing a
finite, flat grid of tiles.

Tilemap(grid, tile_data, tile_types, pos = (0, 0), layer = 0[, translate_type], cache_tile_data = False, blit_flags = 0)

:arg grid: a :class:`util.Grid <engine.gfx.util.Grid>` defining the size and
           shape of the tiles in the tilemap, or the ``tile_size`` argument to
           :class:`util.Grid <engine.gfx.util.Grid>` to create a new one with
           standard parameters.
:arg tile_data: a way of determining the tile type ID for each ``(x, y)`` tile
    in the grid, which is any object.  This can be:

        - a list of columns, where each column is a list of IDs;
        - a string with rows delimited by line breaks and each row a
          whitespace-delimited set of string IDs;
        - ``(s, col_delim, row_delim)`` to specify custom delimiter characters
          for a string ``s``, where either or both delimiters can be ``None``
          to split by whitespace/line breaks;
        - a filename from which to load a string with delimited IDs (the name
          may not contain whitespace);
        - ``(filename, col_delim, row_delim)`` for a custom-delimited string in
          a file;
        - a :class:`Graphic <engine.gfx.graphic.Graphic>`, Pygame surface or
          filename (may not contain whitespace) to load an image from, and use
          the ``(r, g, b[, a])`` colour tuples of the pixels in the surface as
          IDs;
        - if ``grid`` is a :class:`util.Grid <engine.gfx.util.Grid>`: a
          function that takes ``col`` and ``row`` arguments as column and row
          indices in the grid, and returns the corresponding tile type ID; or
        - if ``grid`` is not a :class:`util.Grid <engine.gfx.util.Grid>`,
          ``(get_tile_type, w, h)``, where get_tile_type is a function as
          defined previously, and ``w`` and ``h`` are the width and height of
          the grid, in tiles.

:arg tile_types: a ``tile_type_id -> tile_graphic`` mapping---either a function
    or an object that supports indexing.  ``tile_type_id`` is the tile type ID
    obtained from the ``tile_data`` argument.  ``tile_graphic`` determines how
    the tile should be drawn; it may be:

        - ``None`` for an an empty (transparent) tile;
        - a colour (as taken by :func:`engine.util.normalise_colour`) to fill
          with;
        - a :class:`Graphic <engine.gfx.graphic.Graphic>` or Pygame surface to
          copy aligned to the centre of the tile, clipped to fit; or
        - ``(graphic[, alignment][, rect])`` with ``alignment`` or ``rect`` in
          any order or omitted, and ``graphic`` as in the above form.
          ``alignment`` is as taken by :func:`engine.util.align_rect`, and
          ``rect`` is the Pygame-style rect within the source surface of
          ``graphic`` to copy from.  Regardless of ``alignment``, ``rect`` is
          clipped to fit in the tile around its centre.

    Note that indexing a :class:`util.Spritemap <engine.gfx.util.Spritemap>`
    instance gives a valid ``tile_graphic`` form, making them valid forms for
    this argument.

:arg pos, layer: as taken by :class:`Graphic <engine.gfx.graphic.Graphic>`.
:arg translate_type: a function that takes tile type IDs obtained from the
                     ``tile_data`` argument and returns the ID to use with the
                     ``tile_types`` argument in obtaining ``tile_graphic``.
:arg cache_graphic: whether to cache and reuse ``tile_graphic`` for each tile
                    type.  You might want to pass ``True`` if requesting
                    ``tile_graphic`` from ``tile_types`` generates a surface.
                    If ``True``, tile type IDs must be hashable (after
                    translation),
:arg blit_flags: as taken by :class:`Graphic <engine.gfx.graphic.Graphic>`.

This is meant to be used for static tilemaps---that is, where the appearance of
each tile type never changes.

"""

    def __init__ (self, grid, tile_data, tile_types, pos = (0, 0), layer = 0,
                  translate_type = None, cache_graphic = False,
                  blit_flags = 0):
        if not callable(tile_types):
            tile_types = lambda tile_type_id: tile_types[tile_type_id]
        self._type_to_graphic = tile_types
        if translate_type is None:
            translate_type = lambda tile_type_id: tile_type_id
        self._translate_type = translate_type
        self._cache_graphic = cache_graphic
        self._cache = {}
        self._tile_data, ncols, nrows = self._parse_data(tile_data, grid, True)
        if not isinstance(grid, Grid):
            grid = Grid(ncols * nrows, grid)
        #: The :class:`util.Grid <engine.gfx.util.Grid>` covered.
        self.grid = grid
        # apply initial data
        Graphic.__init__(self, blank_sfc(grid.size), pos, layer, blit_flags)
        update = self._update
        for i, col in enumerate(self._tile_data):
            for j, tile_type_id in enumerate(col):
                update(i, j, tile_type_id)

    def _parse_data (self, tile_data, grid, cache):
        # parse tile data
        if isinstance(tile_data, basestring):
            if len(tile_data.split()) == 1 and \
               splitext(tile_data)[1][1:] in ('png', 'jpg', 'jpeg', 'gif'):
                # image file
                tile_data = conf.GAME.img(tile_data, cache = cache)
            else:
                # string/text file
                tile_data = (tile_data, None, None)
        if isinstance(tile_data, Graphic):
            tile_data = tile_data.surface
        if isinstance(tile_data, pg.Surface):
            tile_data = [[tuple(c) for c in col]
                         for col in pg.surfarray.array3d(tile_data)]
        if isinstance(tile_data[0], basestring):
            s, col, row = tile_data
            if len(s.split()) == 1:
                with open(s) as f:
                    s = f.read(s)
            if row is None:
                s = s.splitlines()
            else:
                s = s.split(row)
            if col is None:
                tile_data = [l.split() for l in s]
            else:
                tile_data = [l.split(col) for l in s]
            # list of rows -> list of columns
            tile_data = zip(*tile_data)
        if callable(tile_data):
            if not isinstance(grid, Grid):
                raise ValueError('got function for tile_data, but grid is ' \
                                 'not a Grid instance')
            tile_data = (tile_data, grid.ncols, grid.nrows)
        if callable(tile_data[0]):
            f, ncols, nrows = tile_data
            tile_data = []
            for i in xrange(ncols):
                col = []
                tile_data.append(col)
                for j in xrange(nrows):
                    col.append(f(i, j))
        # now tile_data is a list of columns
        ncols = len(tile_data)
        nrows = len(tile_data[0])
        if isinstance(grid, Grid) and grid.ntiles != (ncols, nrows):
            msg = 'tile_data has invalid dimensions: got {0}, expected {1}'
            raise ValueError(msg.format((ncols, nrows), grid.ntiles))
        translate_type = self._translate_type
        tile_data = [[translate_type(tile_type_id) for tile_type_id in col]
                     for col in tile_data]
        return (tile_data, ncols, nrows)

    def _update (self, col, row, tile_type_id):
        if self._cache_graphic:
            if tile_type_id in self._cache:
                g = self._cache[tile_type_id]
            else:
                g = self._type_to_graphic(tile_type_id)
                self._cache[tile_type_id] = g
        else:
            g = self._type_to_graphic(tile_type_id)
        dest = self._orig_sfc
        tile_rect = self.grid.tile_rect(col, row)
        if isinstance(g, (Graphic, pg.Surface)):
            g = (g,)
        if isinstance(g[0], (Graphic, pg.Surface)):
            sfc = g[0]
            if isinstance(sfc, Graphic):
                sfc = sfc.surface
            if len(g) == 1:
                alignment = rect = None
            else:
                if isinstance(g[1], int) or len(g[1]) == 2:
                    alignment = g[1]
                    rect = None
                else:
                    alignment = None
                    rect = g[1]
                if len(g) == 3:
                    if rect is None:
                        rect = g[2]
                    else:
                        alignment = g[2]
            if alignment is None:
                alignment = 0
            if rect is None:
                rect = sfc.get_rect()
            # clip rect to fit in tile_rect
            dest_rect = Rect(rect)
            dest_rect.center = tile_rect.center
            fit = dest_rect.clip(tile_rect)
            rect = Rect(rect)
            rect.move_ip(fit.x - dest_rect.x, fit.y - dest_rect.y)
            rect.size = dest_rect.size
            # copy rect to tile_rect with alignment
            pos = align_rect(rect, tile_rect, alignment)
            dest.blit(sfc, pos, rect)
        else:
            if g is None:
                g = (0, 0, 0, 0)
            # now we have a colour
            dest.fill(normalise_colour(g), tile_rect)
        return tile_rect

    def __getitem__ (self, i):
        col, row = i
        return self._tile_data[col][row]

    def __setitem__ (self, i, tile_type_id):
        col, row = i
        tile_type_id = self._translate_type(tile_type_id)
        if tile_type_id != self._tile_data[col][row]:
            rect = self._update(col, row, tile_type_id)
            self._tile_data[col][row] = tile_type_id
            self.dirty(rect)

    def update_from (self, tile_data, from_disk = False):
        """Update tiles from a new set of data.

:arg tile_data: as taken by the constructor.
:arg from_disk: whether to force reloading from disk, if passing an image
                filename.

"""
        tile_data = self._parse_data(tile_data, self.grid, not from_disk)[0]
        for i, col in enumerate(tile_data):
            for j, tile_type_id in enumerate(col):
                self[(i, j)] = tile_type_id
