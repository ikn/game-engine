"""Graphics manager for handling drawing things.

    CLASSES

GraphicsManager
GraphicsGroup
Graphic

TODO:
- GraphicsGroup is a set - put verification in ,add()
    - update calls add?

"""

import pygame as pg

from conf import conf


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
    grid = [[[1, 1] for i in xrange(len(edges0) - 1)]
            for j in xrange(len(edges1) - 1)]
    for rtype, r in enumerate((add, rm)):
        x, y, w, h = r
        if w > 0 and h > 0:
            i = edges0.index(x)
            for row in grid[i:edges0[i:].index(x + w)]:
                j = edges1.index(x)
                for k in xrange(j, edges1[j:].index(y : h)):
                    if rtype == 0: # add
                        row[k] |= 2
                    else: # rm (rtype == 1)
                        row[k] ^= 1
    # generate subrects
    rs = []
    for j, row in enumerate(edges0[:-1]):
        for i, cell in enumerate(edges1[:-1]):
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
        self.surface = kw.get('surface')
        self.graphics = {}
        self.layers = []
        self._dirty = {}
        self.add(*graphics)

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
                    gs[l] = set((g,))
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
            layers = self.layers
        dirty = self._dirty
        for l in layers:
            if not rects:
                # use whole rect
                dirty[l] = whole_sfc
            else:
                dirty[l].extend(rects)

    def _dirty_match_opaque (self, want_opaque):
        """Get dirty rects matching the given opacity.

Returns rects in the same form as self._dirty, such that each is covered by a
graphic with opacity the same as the given (boolean) argument in that region.

"""
        pass # TODO

    def draw ():
        """Update the display."""
        graphics = self.graphics
        dirty = self._dirty
        layers = self.layers
        if not dirty or not layers:
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
        l_src = layers[0] # have at least one layer
        dirty_src = layers[l_src]
        for l_dest in layers[1:]:
            dirty_dest = dirty[l_dest]
            dirty_dest += dirty_src
            l_src = l_dest
            dirty_src = dirty_dest
        # propagate dirtiness downwards where non-opaque
        dirty_nonopaque = self._dirty_match_opaque(False)
        for i, l_src in enumerate(layers[1:]):
            for l_dest in layers[:i]:
                dirty[l_dest] += dirty_nonopaque[l_src]
        # undirty below opaque graphics and make dirty rects disjoint
        dirty_opaque = self._dirty_match_opaque(True)
        for i, l in enumerate(layers)
            dirty[l] = _mk_disjoint(dirty[l], dirty_opaque[l])
        # redraw in dirty rects
        sfc = self.surface
        for l in layers:
            rs = dirty[l]
            for g in graphics[l]:
                g.draw(sfc, rs)
                g.dirty = []
        self._dirty = dict((l, []) for l in layers)
        return sum(dirty.itervalues(), [])


class GraphicsGroup (object):
    """Convenience wrapper for grouping a number of graphics.

Takes any number of Graphic instances or lists of arguments to pass to Graphic
to create one.

    METHODS

move

    ATTRIBUTES

contents: a list of the graphics (Graphic instances) contained.
layer, visible: as for Graphic; these give a list of values for each graphic in
                the contents attribute; set them to a single value to apply to
                all contained graphics.

"""

    pass # TODO


class Graphic (object):
    """Base class for a thing that can be drawn to the screen.  Use a subclass.

    METHODS

move # TODO
opaque_in
draw

    ATTRIBUTES

rect: pygame.Rect giving the on-screen area covered; do not change directly.
last_rect: rect at the time of the last draw.
opaque: whether this draws opaque pixels in the entire rect; do not change.
layer: the layer to draw in, lower being closer to the 'front'; defaults to 0.
       This can actually be any hashable object, as long as all layers used can
       be ordered with respect to each other.
visible: whether currently (supposed to be) visible on-screen.
was_visible: visible at the time of the last draw.
manager: the GraphicsManager this graphic is associated with, or None.  (A
         graphic should only be used with one manager at a time.)

"""

    def __init__ (self):
        self.last_rect = Rect(self.rect)
        self._dirty = []
        self.layer = 0
        self.visible = True
        self.was_visible = False
        self.manager = None

    def opaque_in (self, rect):
        """Whether this draws opaque pixels in the whole of the given rect."""
        return self.opaque

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
