"""Graphics manager for handling drawing things.

    CLASSES

GraphicsManager
GraphicsGroup
Graphic

"""

import pygame as pg
from pygame import Rect

from conf import conf
from util import blank_sfc


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
                i = edges0.index(x)
                for row in grid[i:edges0[i:].index(x + w)]:
                    j = edges1.index(x)
                    for k in xrange(j, edges1[j:].index(y + h)):
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

GraphicsManager(*graphics, surface = None)

graphics: any number of Graphic or GraphicsGroup instances.
surface (keyword-only): a pygame.Surface to draw to; if None, no drawing
                        occurs.

    METHODS

add
rm
dirty
draw

    ATTRIBUTES

surface: as taken by constructor; set this directly (can be None).
graphics: {layer: graphics} dict, where graphics is a set of the graphics in
          the layer, each as taken by the add method.
layers: a list of layers that contain graphics, lowest first.

"""

    def __init__ (self, *graphics, **kw):
        self.graphics = {}
        self.layers = []
        self._dirty = {}
        self._all_dirty = [] # dirty in every layer (not everywhere)
        self.surface = kw.get('surface')
        self.add(*graphics)

    @property
    def surface (self):
        return self._surface

    @surface.setter
    def surface (self, sfc):
        self._surface = sfc
        if sfc is not None:
            self.dirty()

    def add (self, *graphics):
        """Add graphics.

Takes any number of Graphic or GraphicsGroup instances.

"""
        all_gs = self.graphics
        ls = set(self.layers)
        dirty = self._dirty
        graphics = list(graphics)
        for g in graphics:
            if isinstance(g, Graphic):
                l = g.layer
                if l in ls:
                    all_gs[l].add(g)
                else:
                    all_gs[l] = set((g,))
                    ls.add(l)
                    dirty[l] = []
                g.manager = self
            else: # GraphicsGroup
                graphics.extend(g.contents)
        self.layers = sorted(ls)

    def rm (self, *graphics):
        """Remove graphics.

Takes any number of Graphic or GraphicsGroup instances.

"""
        all_graphics = self.graphics
        ls = set(self.layers)
        dirty = self._dirty
        graphics = list(graphics)
        for g in graphics:
            if isinstance(g, Graphic):
                l = g.layer
                if l in ls:
                    all_gs = all_graphics[l]
                    if g in all_gs:
                        all_gs.remove(g)
                        del g.manager
                        if not all_gs:
                            del all_gs[l]
                            ls.remove(l)
                            del dirty[l]
                # else not added: fail silently
            else: # GraphicsGroup
                graphics.extend(g.contents)
        self.layers = sorted(ls)

    def dirty (self, *rects, **kw):
        """Force redrawing some or all of the screen.

dirty(*rects, layer = None, layers = [])

rects: rects to flag as dirty.  If none are given, the whole screen is flagged.
layer, layers: keyword-only.  A specific layer or list of layers to restrict
               dirtying to.  If neither is given, all layers are affected; both
               may be given.

"""
        if self.surface is None:
            # nothing to mark as dirty (happens in assigning a surface)
            return
        whole_sfc = self.surface.get_rect()
        layers = []
        if 'layer' in kw:
            layers.append(kw['layer'])
        layers.extend(kw.get('layers', []))
        if not layers:
            # great hack: make a note in case layers are added before drawing
            layers = ('_all_dirty',)
            dirty = self.__dict__
        else:
            dirty = self._dirty
        for l in layers:
            if not rects:
                # use whole rect
                dirty[l] = [whole_sfc]
            else:
                dirty[l].extend(Rect(r) for r in rects)

    def _dirty_match_opaque (self, want_opaque):
        """Get dirty rects matching the given opacity.

Returns rects in the same form as self._dirty, such that each is covered by a
graphic with opacity the same as the given (boolean) argument in that region.

"""
        match = {}
        dirty = self._dirty
        for l, gs in self.graphics.iteritems():
            this_dirty = dirty[l]
            match[l] = this_match = []
            for r in this_dirty:
                for g in gs:
                    r = r.clip(g.rect)
                    if r and g.opaque_in(r) == want_opaque:
                        this_match.append(r)
        return match

    def draw (self):
        """Update the display.

Returns a list of rects that cover changed parts of the surface, or False if
nothing changed.

"""
        graphics = self.graphics
        dirty = self._dirty
        all_dirty = self._all_dirty
        layers = self.layers
        sfc = self.surface
        if not dirty or not layers or sfc is None:
            return False
        # get dirty rects for each layer
        for l, gs in graphics.iteritems():
            l_dirty = dirty[l]
            for g in gs:
                for flag, bdy in ((g.was_visible, g.last_rect),
                                (g.visible, g.rect)):
                    if flag:
                        l_dirty += [r.clip(bdy) for r in g.dirty]
        # propagate dirtiness upwards
        l_src = layers[-1] # have at least one layer
        dirty_src = dirty[l_src]
        for l_dest in reversed(layers[:-1]):
            dirty_dest = dirty[l_dest]
            dirty_dest += dirty_src
            l_src = l_dest
            dirty_src = dirty_dest
        # propagate dirtiness downwards where non-opaque
        dirty_nonopaque = self._dirty_match_opaque(False)
        for i, l_src in enumerate(layers[1:]):
            for l_dest in layers[:i]:
                dirty[l_dest] += dirty_nonopaque[l_src]
        # undirty below opaque graphics, add _all_dirty and make dirty rects
        # disjoint
        dirty_opaque = self._dirty_match_opaque(True)
        dirty_opaque_sum = []
        for l in layers:
            dirty[l] = _mk_disjoint(dirty[l] + all_dirty, dirty_opaque_sum)
            dirty_opaque_sum += dirty_opaque[l]
        # redraw in dirty rects
        for l in reversed(layers):
            rs = dirty[l]
            for g in graphics[l]:
                r = g.rect
                this_rs = []
                for d in rs:
                    d = r.clip(d)
                    if d:
                        this_rs.append(d)
                if this_rs:
                    g.draw(sfc, this_rs)
                g.dirty = []
        self._dirty = dict((l, []) for l in layers)
        self._all_dirty = []
        return sum(dirty.itervalues(), [])


class GraphicsGroup (object):
    """Convenience wrapper for grouping a number of graphics.

Takes any number of Graphic instances or lists of arguments to pass to Graphic
to create one.

    METHODS

move

    ATTRIBUTES

contents: a set of the graphics (Graphic instances) contained.
layer, visible: as for Graphic; these give a list of values for each graphic in
                the contents attribute; set them to a single value to apply to
                all contained graphics.

"""

    pass # TODO; layer, visible need setters


class Graphic (object):
    """Base class for a thing that can be drawn to the screen.  Use a subclass.

Subclasses should implement:

    draw(surface, rects): draw the graphic.
        surface: surface to draw to.
        rects: rects to draw in; guaranteed to be disjoint and contained by the
               graphic's rect.

    opaque: whether this draws opaque pixels in the entire rect; do not change.

    CONSTRUCTOR

Graphic(rect)

rect: boundary rect that this graphic is contained in.

    METHODS

move # TODO
opaque_in

    ATTRIBUTES

rect: pygame.Rect giving the on-screen area covered; do not change directly.
last_rect: rect at the time of the last draw.
layer: the layer to draw in, lower being closer to the 'front'; defaults to 0.
       This can actually be any hashable object, as long as all layers used can
       be ordered with respect to each other.
visible: whether currently (supposed to be) visible on-screen.
was_visible: visible at the time of the last draw.
manager: the GraphicsManager this graphic is associated with, or None.  (A
         graphic should only be used with one manager at a time.)
dirty: a list of rects that need to be updated; for internal use.

"""

    def __init__ (self, rect):
        self.rect = Rect(rect)
        self.last_rect = Rect(self.rect)
        self._layer = 0
        self.visible = True
        self.was_visible = False
        self.manager = None
        self.dirty = []

    @property
    def layer (self):
        return self._layer

    @layer.setter
    def layer (self, layer):
        # change layer in gm by removing, setting attribute, then adding
        m = self.manager
        if m is not None:
            m.rm(self)
        self._layer = layer
        if m is not None:
            m.add(self)

    def opaque_in (self, rect):
        """Whether this draws opaque pixels in the whole of the given rect."""
        return self.opaque and self.rect.contains(rect)

    def _mk_dirty (self, *rects):
        """Force redrawing.

_mk_dirty(*rects)

rects: rects to flag as dirty.  If none are given, the whole (current) rect is
       flagged.

"""

        dirty = self._dirty
        if rects:
            dirty.extend(rects)
        else:
            dirty.append(self.rect)
        dirty.extend(rects)
        self._dirty = _mk_disjoint(dirty)


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


class Colour (Graphic):
    """A solid rect of colour.

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

    @property
    def colour (self):
        return self._colour

    @colour.setter
    def colour (self, colour):
        self._colour = colour
        self.opaque = len(colour) == 3 or colour[3] == 255
        if self.opaque:
            if hasattr(self, '_sfc'):
                del self._sfc
        else:
            # have to use a surface: can't fill an alpha colour to a non-alpha
            # surface directly
            self._sfc = blank_sfc(self.rect.size)
            self._sfc.fill(colour)

    def draw (self, sfc, rects):
        if self.opaque:
            c = self.colour
            for r in rects:
                sfc.fill(c, r)
        else:
            c_sfc = self._sfc
            for r in rects:
                sfc.blit(c_sfc, r, ((0, 0), r.size))
