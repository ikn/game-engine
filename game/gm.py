"""Graphics manager for handling drawing things.

    CLASSES

GraphicsManager
Graphic
GraphicsGroup

"""

import pygame as pg

from conf import conf


class GraphicsManager (object):
    """Handles intelligently drawing things to a surface.

    CONSTRUCTOR

GraphicsManager(*graphics, surface = None)

graphics: any number of Graphic or GraphicsGroup instances.
surface (keyword-only): a pygame.Surface to draw to; if None, no drawing
                        occurs.

    METHODS

add
rm

    ATTRIBUTES

surface: as taken by constructor; set this directly (can be None).
graphics: {layer: graphics} dict, where graphics is a set of the graphics in
          the layer, each as taken by the add method.
layers: a list of layers that contain graphics, lowest first.
dirty: whether things need to be redrawn; set to True to force a full redraw,
       or to a rect to force a redraw in that rect.

"""

    def __init__ (self, *graphics, **kw):
        self.surface = kw.get('surface')
        self.graphics = {}
        self.layers = []
        self.dirty = True
        self.add(*graphics)

    def add (self, *graphics):
        """Add graphics.

Takes any number of Graphic or GraphicsGroup instances.

"""
        ls = set(self.layers)
        gs = self.graphics
        graphics = list(graphics)
        for g in graphics:
            if isinstance(g, Graphic):
                l = g.layer
                if l in ls:
                    gs[l].add(g)
                else:
                    gs[l] = set((g,))
                    ls.add(l)
            else: # GraphicsGroup
                graphics.extend(g.contents)
        self.layers = sorted(ls)

    def rm (self, *graphics):
        """Remove graphics.

Takes any number of Graphic or GraphicsGroup instances.

"""
        ls = set(self.layers)
        gs = self.graphics
        graphics = list(graphics)
        for g in graphics:
            if isinstance(g, Graphic):
                l = g.layer
                if l in ls:
                    this_gs = gs[l]
                    if g in this_gs:
                        this_gs.remove(g)
                        if not this_gs:
                            ls.remove(l)
                            del gs[l]
                # else not added: fail silently
            else: # GraphicsGroup
                graphics.extend(g.contents)
        self.layers = sorted(ls)


class GraphicsGroup (object):
    """Convenience wrapper for grouping a number of graphics.

Takes any number of Graphic instances or lists of arguments to pass to Graphic to
create one.

    METHODS

move

    ATTRIBUTES

contents: a list of the graphics (Graphic instances) contained.
dirty, layer, visible: as for Graphic; these give a list of values for each
                       graphic in the contents attribute; set them to a single
                       value to apply to all contained graphics.

"""

    pass


class Graphic (object):
    """Base class for a thing that can be drawn to the screen.  Use a subclass.

    METHODS

move
opaque_in

    ATTRIBUTES

rect: pygame.Rect giving the on-screen area covered.
opaque: whether this draws opaque pixels in the entire rect.
dirty: a rect in which redrawing is required, or True if needs to be fully
       redrawn; set to force a redraw.
layer: the layer to draw in, lower being closer to the 'front'; defaults to 0.
       This can actually be any hashable object, as long as all layers used can
       be ordered with respect to each other.
visible: whether currently (supposed to be) visible on-screen.

"""

    def opaque_in (self, rect):
        """Whether this draws opaque pixels in the whole of the given rect."""
        return self.opaque


# Colour(rect, colour)
# Image(surface | filename[image])
# AnimatedImage(surface | filename[image])
# Tilemap
#   (surface | filename[image])
#       uses colours to construct tiles
#   (tiles, data = None)
#       tiles: (size, surface) | (size, filename[image]) | list
#           list: (surface | filename[image] | colour)
#           size: tile (width, height) or width = height
#           surface/filename[image]: a spritemap
#       data: filename[text] | string | list | None (all first tile)
#           filename[text]/string: whitespace-delimited tiles indices; either also take width, or use \n\r for row delimiters, others for column delimiters
#           list: tiles indices; either also take width, or is list of rows
