"""Graphics manager for handling drawing things.

    CLASSES

GraphicsManager
GraphicsGroup
Graphic
Colour

TODO:
 - integrate into Game
 - GraphicsManager.draw_all()
 - Graphic subclasses:
Image(surface | filename[image])
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
        # get dirty rects from graphics
        for gs in graphics.itervalues():
            for g in gs:
                for flag, bdy in ((g.was_visible, g.last_rect),
                                  (g.visible, g.rect)):
                    if flag:
                        dirty += [r.clip(bdy) for r in g.dirty]
                g.was_visible = g.visible
        if not dirty:
            return False
        # get opaque regions of dirty rects by layer
        dirty_opaque = {}
        for l, gs in graphics.iteritems():
            dirty_opaque[l] = l_dirty_opaque = []
            for r in dirty:
                for g in gs:
                    r = r.clip(g.rect)
                    if r and g.opaque_in(r):
                        l_dirty_opaque.append(r)
        # undirty below opaque graphics and make dirty rects disjoint
        dirty_by_layer = {}
        dirty_opaque_sum = []
        for l in layers:
            dirty_by_layer[l] = _mk_disjoint(dirty, dirty_opaque_sum)
            dirty_opaque_sum += dirty_opaque[l]
        # redraw in dirty rects
        for l in reversed(layers):
            rs = dirty_by_layer[l]
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
        self._dirty = []
        return sum(dirty_by_layer.itervalues(), [])


class GraphicsGroup (object):
    """Convenience wrapper for grouping a number of graphics.

Takes any number of Graphic instances or lists of arguments to pass to Graphic
to create one.

    METHODS

move

    ATTRIBUTES

graphics: a set of the Graphic instances contained.
layer, visible: as for Graphic; these give a list of values for each graphic in
                the graphics attribute; set them to a single value to apply to
                all contained graphics.

"""

    pass # TODO; layer, visible need getters, setters


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
        self._rect = Rect(rect)
        self.last_rect = Rect(self.rect)
        self._layer = 0
        self.visible = True
        self.was_visible = False
        self.manager = None
        self.dirty = []

    @property
    def rect (self):
        return self._rect

    @rect.setter
    def rect (self, rect):
        # need to set dirty in old and new rects (if changed)
        last = self._rect
        rect = Rect(rect)
        if rect != last:
            self.dirty.append(last)
            self.last_rect = last
            self.dirty.append(rect)
            self._rect = rect

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

    def opaque_in (self, rect):
        """Whether this draws opaque pixels in the whole of the given rect."""
        return self.opaque and self.rect.contains(rect)


class Colour (Graphic):
    """A solid rect of colour.

    CONSTRUCTOR

Colour(rect, colour)

rect: as taken by Graphic; may be set directly (but not altered in-place).
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
            c = self._colour
            for r in rects:
                sfc.fill(c, r)
        else:
            c_sfc = self._sfc
            for r in rects:
                sfc.blit(c_sfc, r, ((0, 0), r.size))



    #def fade (self, fn, time = None, persist = False):
        #"""Fade an overlay on the current world.

#fade(fn[, time], persist = False)

#fn: a function that takes the time since the fade started and returns the
    #overlay to use, as taken by Game.set_overlay.
#time: fade duration in seconds; this is rounded to the nearest frame.  If None
      #or not given, fade_fn may return None to end the fade.
#persist: whether to continue to show the current overlay when the fade ends
         #(else it is set to False).

#Calling this cancels any current fade, and calling Game.set_overlay during the
#fade will not have any effect.

#"""
        #self.fading = True
        #self._fade_data = {'core': [fn, time, persist, 0]}

    #def cancel_fade (self, persist = True):
        #"""Cancel any running fade on the current world.

#Takes the persist argument taken by Game.fade (defaults to True).

#"""
        #self.fading = False
        #self._fade_data = None
        #if not persist:
            #self.set_overlay(False)

    #def _colour_fade_fn (self, t):
        #"""Fade function for Game.colour_fade."""
        #f, os, ts = self._fade_data['colour']
        #t = f(t)
        ## get waypoints we're between
        #i = bisect(ts, t)
        #if i == 0:
            ## before start
            #return os[0]
        #elif i == len(ts):
            ## past end
            #return os[-1]
        #o0, o1 = os[i - 1:i + 1]
        #t0, t1 = ts[i - 1:i + 1]
        ## get ratio of the way between waypoints
        #if t1 == t0:
            #r = 1
        #else:
            #r = float(t - t0) / (t1 - t0)
        #assert 0 <= r <= 1
        #o = []
        #for x0, x1 in zip(o0, o1):
            ## if one is no overlay, use the other's colours
            #if x0 is None:
                #if x1 is None:
                    ## both are no overlay: colour doesn't matter
                    #o.append(0)
                #else:
                    #o.append(x1)
            #elif x1 is None:
                #o.append(x0)
            #else:
                #o.append(x0 + r * (x1 - x0))
        #return o

    #def colour_fade (self, fn, time, *ws, **kwargs):
        #"""Start a fade between colours on the current world.

#colour_fade(fn, time, *waypoints, persist = False)

#fn: a function that takes the time since the fade started and returns the
    #'time' to use in bisecting the waypoints to determine the overlay to use.
#time: as taken by Game.fade.  This is the time as passed to fn, not as returned
      #by it.
#waypoints: two or more points to fade to, each (overlay, time).  overlay is as
           #taken by Game.set_overlay, but cannot be a surface, and time is the
           #time in seconds at which that overlay should be reached.  Times must
           #be in order and all >= 0.

           #For the first waypoint, time is ignored and set to 0, and the
           #waypoint may just be the overlay.  For any waypoint except the first
           #or the last, time may be None, or the waypoint may just be the
           #overlay.  Any group of such waypoints are spaced evenly in time
           #between the previous and following waypoints.
#persist: keyword-only, as taken by Game.fade.

#See Game.fade for more details.

#"""
        #os, ts = zip(*((w, None) if w is False or len(w) > 2 else w \
                     #for w in ws))
        #os = list(os)
        #ts = list(ts)
        #ts[0] = 0
        ## get groups with time = None
        #groups = []
        #group = None
        #for i, (o, t) in enumerate(zip(os, ts)):
            ## sort into groups
            #if t is None:
                #if group is None:
                    #group = [i]
                    #groups.append(group)
            #else:
                #if group is not None:
                    #group.append(i)
                #group = None
            ## turn into RGBA
            #if o is False:
                #o = (None, None, None, 0)
            #else:
                #o = tuple(o)
                #if len(o) == 3:
                    #o += (255,)
                #else:
                    #o = o[:4]
            #os[i] = o
        ## assign times to waypoints in groups
        #for a, b in groups:
            #assert a != b
            #t0 = ts[a - 1]
            #dt = float(ts[b] - t0) / (b - (a - 1))
            #for i in xrange(a, b):
                #ts[i] = t0 + dt * (i - (a - 1))
        ## start fade
        #persist = kwargs.get('persist', False)
        #self.fade(self._colour_fade_fn, time, persist)
        #self._fade_data['colour'] = (fn, os, ts)

    #def linear_fade (self, *ws, **kwargs):
        #"""Start a linear fade on the current world.

#Takes the same arguments as Game.colour_fade, without fn and time.

#"""
        #self.colour_fade(lambda x: x, ws[-1][1], *ws, **kwargs)
