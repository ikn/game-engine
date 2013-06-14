"""Specialised types of graphics.

---NODOC---

TODO:
 - accept colours from hex (add to normalise_colour and use this)
 - Text
 - Animation(surface | filename[image])
 - Tilemap
    - need:
        - x, y -> tile_type_id (determines w, h)
            - list: of ids (with width, or list of lists)
            - string/text file: delimited string ids (with width, or different row delimeters)
            - Graphic/Surface/image file: pixels are (r, g, b, a) ids
            - w, h, fn(x, y) -> type
        - tile_type_id -> tile_data
            - type: all this type
            - anything with __getitem__ (like Spritemap)
            - fn(type) -> data
        - Grid (or tile size for standard grid)
        - a way of drawing a tile based on tile_data
            - None: empty tile
            - colour: fill
            - Graphic | Surface: blit rect from source's top-left
            - (Graphic | Surface[, alignment][, rect]): blit with alignment using source rect (alignment/rect in any order)

---NODOC---

"""


import pygame as pg
from pygame import Rect

from ..util import normalise_colour
from .graphic import Graphic


class Colour (Graphic):
    """A solid rect of colour (:class:`Graphic` subclass).

Colour(colour, rect, layer = 0, blit_flags = 0)

:arg colour: a colour to draw, as accepted by
             :func:`engine.util.normalise_colour`.
:arg rect: ``(left, top, width, height)`` rect (of ints) to draw in (or
           anything taken by ``pygame.Rect``, like a ``Rect``, or
           ``((left, top), (width, height))``).
:arg layer: as taken by :class:`Graphic`.
:arg blit_flags: as taken by :class:`Graphic`.

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
