"""Graphics manager for handling drawing things.

    CLASSES

GraphicsManager
GraphicsGroup
Graphic
ResizableGraphic
Colour
Image

TODO:
 - GraphicsManager.overlay, .fade
 - performance:
    - reduce number of rects created by mk_disjoint
    - if GM is fully dirty, draw everything without any rect checks
 - GraphicsManager.offset to offset the viewing window (Surface.scroll is fast?)
    - supports parallax: set to {layer: ratio} or (function(layer) -> ratio)
    - can set/unset a scroll function to call every draw
    - implementation:
        - in first loop, for each graphic, offset _rect by -offset
        - when using, offset old graphic dirty rects by -last_offset, current by -offset
        - after drawing, for each graphic, offset _rect by offset
 - Graphic.opacity?
 - Graphic subclasses:
AnimatedImage(surface | filename[image])
Tilemap
  (surface | filename[image])
      uses colours to construct tiles
  (tiles, data = None)
      tiles: (size, surface) | (size, filename[image]) | list
          list: (surface | filename[image] | colour)
          size: tile (width, height) or width = height
          surface/filename[image]: a spritemap
      data: filename[text] | string | list | None (all first tile)
          filename[text]/string: whitespace-delimited tiles indices; either also take width, or use \n\r for row delimiters, others for column delimiters
          list: tiles indices; either also take width, or is list of rows

"""

import pygame as pg
from pygame import Rect

from conf import conf
from util import ir, convert_sfc, blank_sfc
from gmdraw import fastdraw


def _mk_disjoint (add, rm = []):
    """Make a list of rects disjoint.

_mk_disjoint(add, rm = []) -> rects

add: rects to make disjoint ('positive rects').
rm: rects to remove (cut out).

rects: the resulting list of disjoint rects.

"""
    # get sorted edges
    edges = []
    rs = add + rm
    for axis in (0, 1):
        es = set()
        for r in rs:
            x = r[axis]
            w = r[axis + 2]
            es.add(x)
            es.add(x + w)
        edges.append(sorted(es))
    # generate grid of subrects and mark contents
    # each has 2 if add, has no 1 if rm
    edges0, edges1 = edges
    grid = [[1] * (len(edges0) - 1) for j in xrange(len(edges1) - 1)]
    for rtype, rs in enumerate((add, rm)):
        for r in rs:
            x, y, w, h = r
            if w > 0 and h > 0:
                j = edges1.index(y)
                for row in grid[j:j + edges1[j:].index(y + h)]:
                    i = edges0.index(x)
                    for k in xrange(i, i + edges0[i:].index(x + w)):
                        if rtype == 0: # add
                            row[k] |= 2
                        else: # rm (rtype == 1)
                            row[k] ^= 1
    # generate subrects
    rs = []
    for j, row in enumerate(grid):
        for i, cell in enumerate(row):
            if cell == 3: # add and not rm
                x0 = edges0[i]
                y0 = edges1[j]
                rs.append(Rect(x0, y0, edges0[i + 1] - x0,
                          edges1[j + 1] - y0))
    return rs


class GraphicsManager (object):
    """Handles intelligently drawing things to a surface.

Graphics are meant to be used with only one GraphicsManager at a time.

    CONSTRUCTOR

GraphicsManager(*graphics[, surface])

graphics: any number of Graphic or GraphicsGroup instances.
surface (keyword-only): a pygame.Surface to draw to; if not given, no drawing
                        occurs.

    METHODS

add
rm
dirty
draw

    ATTRIBUTES

surface: as taken by constructor; set this directly (can be None to do nothing).
graphics: {layer: graphics} dict, where graphics is a set of the graphics in
          the layer, each as taken by the add method.
layers: a list of layers that contain graphics, lowest first.

"""

    def __init__ (self, *graphics, **kw):
        self.graphics = {}
        self.layers = []
        self._dirty = []
        self._surface = None
        self.surface = kw.get('surface')
        self.add(*graphics)

    @property
    def surface (self):
        return self._surface

    @surface.setter
    def surface (self, sfc):
        if sfc is not self._surface:
            self._surface = sfc
            if sfc is not None:
                self._rect = sfc.get_rect()
                self.dirty()

    def add (self, *graphics):
        """Add graphics.

Takes any number of Graphic or GraphicsGroup instances.

"""
        all_gs = self.graphics
        ls = set(self.layers)
        graphics = list(graphics)
        for g in graphics:
            if isinstance(g, Graphic):
                l = g.layer
                if l in ls:
                    all_gs[l].add(g)
                else:
                    all_gs[l] = set((g,))
                    ls.add(l)
                g._manager = self
            else: # GraphicsGroup
                graphics.extend(g.contents)
        self.layers = sorted(ls)

    def rm (self, *graphics):
        """Remove graphics.

Takes any number of Graphic or GraphicsGroup instances.

"""
        all_graphics = self.graphics
        ls = set(self.layers)
        graphics = list(graphics)
        for g in graphics:
            if isinstance(g, Graphic):
                l = g.layer
                if l in ls:
                    all_gs = all_graphics[l]
                    if g in all_gs:
                        all_gs.remove(g)
                        g._manager = None
                        if not all_gs:
                            del all_gs[l]
                            ls.remove(l)
                # else not added: fail silently
            else: # GraphicsGroup
                graphics.extend(g.contents)
        self.layers = sorted(ls)

    def dirty (self, *rects, **kw):
        """Force redrawing some or all of the screen.

Takes any number of rects to flag as dirty.  If none are given, the whole of
the current surface is flagged.

"""
        if self._surface is None:
            # nothing to mark as dirty (happens in assigning a surface)
            return
        if rects:
            self._dirty += [Rect(r) for r in rects]
        else:
            self._dirty = [self._rect]

    def draw (self):
        """Update the display.

Returns a list of rects that cover changed parts of the surface, or False if
nothing changed.

"""
        layers = self.layers
        sfc = self._surface
        if not layers or sfc is None:
            return False
        graphics = self.graphics
        dirty = self._dirty
        self._dirty = []
        return fastdraw(layers, sfc, graphics, dirty)


class GraphicsGroup (list):
    """Convenience wrapper for grouping a number of graphics.

Takes any number of Graphic instances or lists of arguments to pass to Graphic
to create one.  This is a list subclass, containing graphics, so add and remove
graphics using list methods.

    METHODS

opaque_in
move_by

    ATTRIBUTES

layer, visible, manager:
    as for Graphic; these give a list of values for each contained graphic; set
    them to a single value to apply to all contained graphics.

"""

    def __init__ (self, *graphics):
        list.__init__(self, (g if isinstance(g, Graphic) else Graphic(*g)
                             for g in graphics))

    def __getattr__ (self, attr):
        if attr in ('layer', 'visible', 'manager'):
            return [getattr(g, attr) for g in self]
        else:
            return list.__getattr__(self, attr)

    def __setattr__ (self, attr, val):
        if attr in ('layer', 'visible', 'manager'):
            for g in self:
                setattr(g, attr, val)
        else:
            return list.__setattr__(self, attr, val)

    def opaque_in (self, rect):
        """Whether the contained graphics are opaque in the given rect.

Returns True if any graphic draws opaque pixels in the whole of the given rect.

"""
        return any(g.opaque_in(rect) for g in self)

    def move_by (self, *args, **kwargs):
        """Move each contained graphic by the given number of pixels.

move_by(dx = 0, dy = 0)

"""
        for g in self:
            g.move_by(*args, **kwargs)


class Graphic (object):
    """Base class for a thing that can be drawn to the screen.  Use a subclass.

Subclasses should implement:

    draw(surface, rects): draw the graphic (should never alter any state that
                          is not internal to the graphic).
        surface: surface to draw to.
        rects: rects to draw in; guaranteed to be disjoint pygame.Rect
               instances that are contained by the graphic's rect.

    opaque: whether this draws opaque pixels in the entire rect.

    CONSTRUCTOR

Graphic(rect)

rect: boundary rect that this graphic is contained in.

    METHODS

opaque_in
move_by

    ATTRIBUTES

rect: pygame.Rect giving the on-screen area covered; do not change directly.
pos: (x, y).
x, y: co-ordinates of the top-left corner of rect.
last_rect: rect at the time of the last draw.
layer: the layer to draw in, lower being closer to the 'front'; defaults to 0.
       This can actually be any hashable object, as long as all layers used can
       be ordered with respect to each other.
visible: whether currently (supposed to be) visible on-screen.
was_visible: visible at the time of the last draw.
manager: the GraphicsManager this graphic is associated with, or None; this may
         be changed directly.  (A graphic should only be used with one manager
         at a time.)
dirty: a list of rects that need to be updated; for internal use.

"""

    def __init__ (self, rect):
        self._rect = Rect(rect)
        self.last_rect = Rect(self._rect)
        self._layer = 0
        self.visible = True
        self.was_visible = False
        self._manager = None
        self.dirty = []

    @property
    def rect (self):
        return self._rect

    @rect.setter
    def rect (self, rect):
        # need to set dirty in old and new rects (if changed)
        last = self.last_rect
        rect = Rect(rect)
        if rect != last:
            self.dirty.append(last)
            self.dirty.append(rect)
            self._rect = rect

    @property
    def pos (self):
        return self._rect.topleft

    @pos.setter
    def pos (self, pos):
        self.rect = (pos, self._rect.size)

    @property
    def x (self):
        return self._rect[0]

    @x.setter
    def x (self, x):
        self.pos = (x, self._rect[1])

    @property
    def y (self):
        return self._rect[1]

    @y.setter
    def y (self, y):
        self.pos = (self._rect[0], y)

    @property
    def layer (self):
        return self._layer

    @layer.setter
    def layer (self, layer):
        if layer != self.layer:
            # change layer in gm by removing, setting attribute, then adding
            m = self.manager
            if m is not None:
                m.rm(self)
            self._layer = layer
            if m is not None:
                m.add(self)

    @property
    def manager (self):
        return self._manager

    @manager.setter
    def manager (self, manager):
        if self._manager is not None:
            self._manager.rm(self)
        manager.add(self) # changes value in _manager

    def opaque_in (self, rect):
        """Whether this draws opaque pixels in the whole of the given rect."""
        return self.opaque and self._rect.contains(rect)

    def move_by (self, dx = 0, dy = 0):
        """Move by the given number of pixels.

move_by(dx = 0, dy = 0)

"""
        self.rect = self._rect.move(dx, dy)

    def draw (self):
        self.last_rect = self._rect


class ResizableGraphic (Graphic):
    """Base class for resizeable graphics (Graphics subclass).

The rect attribute may be set directly (but not altered in-place).

    ATTRIBUTES

size: (w, h).
w, h: width and height of rect.

"""

    @property
    def size (self):
        return self._rect.size

    @size.setter
    def size (self, size):
        self.rect = (self._rect.topleft, size)

    @property
    def w (self):
        return self._rect[2]

    @w.setter
    def w (self, w):
        self.size = (w, self._rect[3])

    @property
    def h (self):
        return self._rect[3]

    @h.setter
    def h (self, h):
        self.size = (self._rect[2], h)


class Colour (ResizableGraphic):
    """A solid rect of colour (ResizableGraphic subclass).

    CONSTRUCTOR

Colour(rect, colour)

rect: as taken by Graphic.
colour: a Pygame-style (R, G, B[, A = 255]) colour to draw.

    ATTRIBUTES

colour: as taken by constructor; set as necessary.

"""

    def __init__ (self, rect, colour):
        Graphic.__init__(self, rect)
        self.colour = colour

    @ResizableGraphic.rect.setter
    def rect (self, rect):
        last_size = self._rect.size
        ResizableGraphic.rect.fset(self, rect)
        size = self._rect.size
        if last_size != size and hasattr(self, '_sfc'):
            # size changed: resize surface (just create a new one)
            self._sfc = pg.Surface(size).convert_alpha()
            self._sfc.fill(self._colour)

    @property
    def colour (self):
        return self._colour

    @colour.setter
    def colour (self, colour):
        if not hasattr(self, '_colour') or colour != self._colour:
            self._colour = colour
            self.opaque = len(colour) == 3 or colour[3] == 255
            if self.opaque or colour[3] == 0:
                if hasattr(self, '_sfc'):
                    del self._sfc
            else:
                # have to use a surface: can't fill an alpha colour to a
                # non-alpha surface directly
                if not hasattr(self, '_sfc'):
                    self._sfc = pg.Surface(self._rect.size).convert_alpha()
                self._sfc.fill(colour)
            self.dirty.append(self._rect)

    def draw (self, dest, rects):
        Graphic.draw(self)
        if self.opaque:
            c = self._colour
            if len(c) == 3 or c[3] != 0:
                fill = dest.fill
                for r in rects:
                    fill(c, r)
        else:
            sfc = self._sfc
            blit = dest.blit
            for r in rects:
                blit(sfc, r, ((0, 0), r.size))


class Image (ResizableGraphic):
    """A Pygame surface (ResizableGraphic subclass).

Changing the size scales the surface using the resize method.

    CONSTRUCTOR

Image(pos, img)

pos: (x, y) initial position.
img: surface or filename (under conf.IMG_DIR) to load.

    METHODS

resize
rescale

    ATTRIBUTES

surface: the surface that will be drawn.
base_surface: the original surface that was given/loaded.  surface may be a
              scaled version of this.
scale: (scale_x, scale_y); uses the rescale method.
scale_x, scale_y: scaling ratio of the image on each axis.

"""

    def __init__ (self, pos, sfc):
        if isinstance(sfc, basestring):
            sfc = conf.GAME.img(sfc)
        else:
            sfc = convert_sfc(sfc)
        self.base_surface = self.surface = sfc
        self._base_size = sfc.get_size()
        Graphic.__init__(self, (pos, sfc.get_size()))
        self.opaque = sfc.get_alpha() is None and sfc.get_colorkey() is None

    @Graphic.rect.setter
    def rect (self, rect):
        last_size = self._rect.size
        ResizableGraphic.rect.fset(self, rect)
        size = self._rect.size
        if last_size != size:
            # size changed
            self.resize(*size)

    @property
    def scale (self):
        return (self.scale_x, self.scale_y)

    @scale.setter
    def scale (self, scale):
        self.rescale(*scale)

    @property
    def scale_x (self):
        return float(self._rect[2]) / self._base_size[0]

    @scale_x.setter
    def scale_x (self, scale_x):
        self.rescale(scale_x)

    @property
    def scale_y (self):
        return float(self._rect[3]) / self._base_size[1]

    @scale_y.setter
    def scale_y (self, scale_y):
        self.rescale(h = scale_y)

    def resize (self, w = None, h = None, scale = pg.transform.smoothscale):
        """Resize the image.

resize([w][, h], scale = pygame.transform.smoothscale)

w, h: the new width and height.  If not given, each defaults to the original
      width and height of this image.
scale: a function to do the scaling:
    scale(surface, (width, height)) -> new_surface.

"""
        ow, oh = self._base_size
        r = self._rect
        cw, ch = r.size
        if w is None:
            w = ow
        if h is None:
            h = oh
        if w != cw or h != ch:
            if w == ow and h == oh:
                # no scaling
                self.surface = self.base_surface
            else:
                self.surface = scale(self.base_surface, (w, h))
            self.rect = (r[0], r[1], w, h)

    def rescale (self, w = None, h = None, scale = pg.transform.smoothscale):
        """A convenience wrapper around resize to scale by a ratio.

Arguments are as for resize, but w and h are ratios of the original size.

"""
        ow, oh = self.base_surface.get_size()
        if w is None:
            w = 1
        if h is None:
            h = 1
        self.resize(ir(w * ow), ir(h * oh), scale)

    def draw (self, dest, rects):
        Graphic.draw(self)
        sfc = self.surface
        blit = dest.blit
        offset = (-self._rect[0], -self._rect[1])
        for r in rects:
            blit(sfc, r, r.move(offset))
