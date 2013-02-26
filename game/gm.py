"""Graphics manager for handling drawing things.

    CLASSES

GraphicsManager
GraphicsGroup
Graphic
ResizableGraphic
Colour
Image

TODO:
 - Graphic.blit_flags to pass to blit
 - Graphic.transform(transform_fn, *args, **kwargs) which registers transform_fn as a transform and calls it as necessary:
    transform_fn(surface, pos, origin) -> (new_surface, new_pos, new_origin) - must copy surface
 - GM stuff to make it act as a Graphic, so it can be transformed and added to another GM, for multi-Graphic transforms
 - GraphicsManager.overlay, .fade
 - performance:
    - updating in rects is slow with lots of rects
    - ignore off-screen things
    - reduce number of rects created by mk_disjoint
    - if GM is fully dirty, draw everything without any rect checks (but still nothing under opaque)
    - something to duplicate a graphic, changing position only?  Maybe only images?
    - GM.busy to redraw all every frame
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

from collections import OrderedDict

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
                # add to graphics
                l = g.layer
                if l in ls:
                    all_gs[l].add(g)
                else:
                    all_gs[l] = set((g,))
                    ls.add(l)
                g._manager = self
                # don't draw over any possible previous location
                g.was_visible = False
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
                        # remove from graphics
                        all_gs.remove(g)
                        g._manager = None
                        # draw over previous location
                        if g.was_visible:
                            self.dirty(g.last_rect)
                        # remove layer
                        if not all_gs:
                            del all_graphics[l]
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
    """Something that can be drawn to the screen.

Many properties of a graphic, such as its position and size, can be changed in
two main ways: by setting the attribute directly, or by calling the
corresponding method.  The former is more natural, and is useful for
sched.interp, while the latter all return the graphic, and so can be chained
together.

Position and size can also be retrieved and altered using list indexing, like
with Pygame rects.

    CONSTRUCTOR

Graphic(img, pos, layer = 0)

img: surface or filename (under conf.IMG_DIR) to load.
pos: initial (x, y) position.
layer: the layer to draw in, lower being closer to the 'front'. This can
       actually be any hashable object, as long as all layers used in the same
       GraphicsManager can be ordered with respect to each other.

    METHODS

opaque_in
move_to
move_by
reload

    ATTRIBUTES

fn: filename of the loaded image, or None if a surface was given.
surface: the (possibly transformed) surface that will be used for drawing.
rect: pygame.Rect giving the on-screen area covered; may be set directly, but
      not altered in-place.
last_rect: rect at the time of the last draw.
x, y: co-ordinates of the top-left corner of rect.
pos: (x, y).
w, h: width and height of rect.
size: (w, h).
scale_fn: function to use for scaling; defaults to pygame.transform.smoothscale
          (and should have this signature).  If you change this, you may want
          to call the reload method.
manager: the GraphicsManager this graphic is associated with, or None; this may
         be changed directly.  (A graphic should only be used with one manager
         at a time.)
layer: as taken by constructor.
visible: whether currently (supposed to be) visible on-screen.
was_visible: visible at the time of the last draw.
opaque: whether this draws opaque pixels in the entire rect.

"""

    def __init__ (self, img, pos, layer = 0):
        if isinstance(img, basestring):
            self.fn = img
            img = conf.GAME.img(img)
        else:
            self.fn = None
            img = convert_sfc(img)
        self.surface = img
        self._rect = Rect(pos, img.get_size())
        self.last_rect = Rect(self._rect)
        # {method: (data, previous_surface, previous_rect, does_something)}
        self._transforms = OrderedDict()
        self.scale_fn = pg.transform.smoothscale
        self._manager = None
        self._layer = layer
        self.visible = True
        self.was_visible = False
        self.opaque = img.get_alpha() is None and img.get_colorkey() is None
        self._dirty = [] # gets used (and reset) by GraphicsManager

    def __getitem__ (self, i):
        if isinstance(i, slice):
            # Rect is weird and only accepts slices through slice syntax
            # this is the easiest way around it
            r = self._rect
            return [r[i] for i in range(4)[i]]
        else:
            return self._rect[i]

    def __setitem__ (self, i, v):
        r = Rect(self._rect)
        if isinstance(i, slice):
            for v_i, r_i in enumerate(range(4)[i]):
                r[r_i] = v[v_i]
        else:
            r[i] = v
        self.rect = r

    # appearance properties

    @property
    def rect (self):
        return self._rect

    @rect.setter
    def rect (self, rect):
        # need to set dirty in old and new rects (if changed)
        last = self.last_rect
        rect = Rect(rect)
        if rect != last:
            sz = rect.size
            if sz != last.size:
                self.resize(*sz)
            else:
                # done in resize
                self._rect = rect
                self._mk_dirty()

    @property
    def x (self):
        return self._rect[0]

    @x.setter
    def x (self, x):
        r = Rect(self._rect)
        r[0] = x
        self._rect = r

    @property
    def y (self):
        return self._rect[1]

    @y.setter
    def y (self, y):
        r = Rect(self._rect)
        r[1] = y
        self._rect = r

    @property
    def pos (self):
        return self._rect.topleft

    @pos.setter
    def pos (self, pos):
        self.rect = self._rect.move(pos)

    @property
    def w (self):
        return self._rect[2]

    @w.setter
    def w (self, w):
        r = Rect(self._rect)
        r[2] = w
        self._rect = r

    @property
    def h (self):
        return self._rect[3]

    @h.setter
    def h (self, h):
        r = Rect(self._rect)
        r[3] = h
        self._rect = r

    @property
    def size (self):
        return self._rect.size

    @size.setter
    def size (self, size):
        self.rect = (self._rect.topleft, size)

    # for the manager

    @property
    def manager (self):
        return self._manager

    @manager.setter
    def manager (self, manager):
        if self._manager is not None:
            self._manager.rm(self)
        manager.add(self) # changes value in _manager

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
        return self.opaque and self._rect.contains(rect)

    # appearance methods

    def move_to (self, x = None, y = None):
        """Move to the given postition.

move([x][, y]) -> self

Omitted arguments are unchanged.

"""
        r = Rect(self._rect)
        if x is not None:
            r[0] = x
        if y is not None:
            r[1] = y
        self._rect = r
        return self

    def move_by (self, dx = 0, dy = 0):
        """Move by the given number of pixels.

move_by(dx = 0, dy = 0) -> self

"""
        self.rect = self._rect.move(dx, dy)
        return self

    # transform

    def _transform_sfc (self, method):
        """Return surface before given transform method was applied."""
        ts = self._transforms
        if method in ts:
            return ts[method][1]
        else:
            # use original surface
            return ts.values()[0][1] if ts else self.surface

    def _to_transform_if_changed (self, method, args):
        """Revert surface and rect to before a transform if args changed.

_to_transform_if_changed(method, args) -> changed

method, args: transform method/arguments.

changed: whether args changed.

"""
        ts = self._transforms
        if method in ts:
            old_args, sfc, rect, changed = ts[method]
            if old_args == args:
                return False
            self.surface = sfc
            self._rect = rect
        # else didn't exist: do nothing
        return True

    def _add_transform (self, method, args, sfc, rect, changed = True):
        """Register a transformation.

_add_transform(method, args, sfc, rect, changed = True)

method, args: method name that was called with arguments args to apply the
              transformation.
sfc, rect: surface and rect before transforming.
changed: whether the transform changed anything (surface or rect).

Should be called after the surface and rect have been set.

"""
        ts = self._transforms
        existed = method in ts
        ts[method] = (args, sfc, rect, changed)
        if existed:
            # reapply from this transform onwards
            self._reapply_transforms(ts.keys().index(method) + 1)
        # _reapply_transforms will call transform functions which will call
        # this method; we end up at the outermost call with self._rect set to
        # the final value
        if changed:
            self._mk_dirty

    def resize (self, w = None, h = None):
        """Resize the image.

resize([w][, h]) -> self

w, h: the new width and height.  No scaling occurs in omitted dimensions.

"""
        orig_w, orig_h = self._transform_sfc('resize').get_size()
        if w is None:
            w = orig_w
        if h is None:
            h = orig_h
        sz = (w, h)
        if self._to_transform_if_changed('resize', sz):
            r = self._rect
            prev_w, prev_h = r.size
            sfc = self.surface
            changed = False
            if w != prev_w or h != prev_h or w != orig_w or h != orig_h:
                    self.surface = self.scale_fn(sfc, sz)
                    self._rect = Rect(r.topleft, sz)
                    changed = True
            # else no scaling or already scaled like this
            self._add_transform('resize', sz, sfc, r, changed)
        return self

    def rescale (self, w = None, h = None):
        """A convenience wrapper around resize to scale by a ratio.

rescale([w][, h]) -> self

w, h: new width and height as ratios of the original size.  No scaling occurs
      in omitted dimensions.

"""
        ow, oh = self.surface.get_size()
        if w is None:
            w = 1
        if h is None:
            h = 1
        return self.resize(ir(w * ow), ir(h * oh))

    def _reapply_transforms (self, start = 0):
        """Reapply transformations starting from the given index or method."""
        ts = self._transforms.items()
        if isinstance(start, basestring):
            start = ts.keys().index(start)
        self._transforms = OrderedDict(ts[:start])
        first = True
        for method, (args, sfc, rect, change) in ts[start:]:
            if first:
                self._rect = rect # any transformations will do the dirtying
                first = False
            getattr(self, method)(*args)

    def reload (self, from_disk = True):
        """Reload from disk if necessary, then reapply transformations.

reload(from_disk = True)

from_disk: whether to load from disk (if possible).  If False, only reapply
           transformations.

"""
        if from_disk and self.fn is not None:
            self.surface = conf.GAME.img(self.fn)
            self._rect
            self._mk_dirty()
        self._reapply_transforms()

    def _mk_dirty (self):
        """Mark as dirty."""
        self._dirty = [self.last_rect, self._rect]

    def _draw (self, dest, rects):
        """Draw the graphic.

_draw(dest, rects)

dest: pygame.Surface to draw to.
rects: list of rects to draw in.

Should never alter any state that is not internal to the graphic.

"""

        sfc = self.surface
        blit = dest.blit
        offset = (-self._rect[0], -self._rect[1])
        for r in rects:
            blit(sfc, r, r.move(offset))
        self.last_rect = self._rect


#class Colour (ResizableGraphic):
    #"""A solid rect of colour (ResizableGraphic subclass).

    #CONSTRUCTOR

#Colour(rect, colour)

#rect: as taken by Graphic.
#colour: a Pygame-style (R, G, B[, A = 255]) colour to draw.

    #ATTRIBUTES

#colour: as taken by constructor; set as necessary.

#"""

    #def __init__ (self, rect, colour):
        #Graphic.__init__(self, rect)
        #self.colour = colour

    #@ResizableGraphic.rect.setter
    #def rect (self, rect):
        #last_size = self._rect.size
        #ResizableGraphic.rect.fset(self, rect)
        #size = self._rect.size
        #if last_size != size and hasattr(self, '_sfc'):
            ## size changed: resize surface (just create a new one)
            #self._sfc = pg.Surface(size).convert_alpha()
            #self._sfc.fill(self._colour)

    #@property
    #def colour (self):
        #return self._colour

    #@colour.setter
    #def colour (self, colour):
        #if not hasattr(self, '_colour') or colour != self._colour:
            #self._colour = colour
            #self.opaque = len(colour) == 3 or colour[3] == 255
            #if self.opaque or colour[3] == 0:
                #if hasattr(self, '_sfc'):
                    #del self._sfc
            #else:
                ## have to use a surface: can't fill an alpha colour to a
                ## non-alpha surface directly
                #if not hasattr(self, '_sfc'):
                    #self._sfc = pg.Surface(self._rect.size).convert_alpha()
                #self._sfc.fill(colour)
            #self._dirty.append(self._rect)


#class Image (ResizableGraphic):
    #"""A Pygame surface (ResizableGraphic subclass).

#Changing the size scales the surface using the resize method.

    #CONSTRUCTOR

#Image(pos, img)

#pos: (x, y) initial position.
#img: surface or filename (under conf.IMG_DIR) to load.

    #METHODS

#resize
#rescale

    #ATTRIBUTES

#scale: (scale_x, scale_y); uses the rescale method.  Can be set to a single
       #number to scale both dimensions by.
#scale_x, scale_y: scaling ratio of the image on each axis.

#"""

    #@property
    #def scale (self):
        #return (self.scale_x, self.scale_y)

    #@scale.setter
    #def scale (self, scale):
        #if isinstance(scale, (int, float)):
            #self.rescale(scale, scale)
        #else:
            #self.rescale(*scale)

    #@property
    #def scale_x (self):
        #return float(self._rect[2]) / self._base_size[0]

    #@scale_x.setter
    #def scale_x (self, scale_x):
        #self.resize(ir(scale_x * self.base_surface.get_width()), self._rect[3])

    #@property
    #def scale_y (self):
        #return float(self._rect[3]) / self._base_size[1]

    #@scale_y.setter
    #def scale_y (self, scale_y):
        #self.resize(self.rect[2], ir(scale_y * self.base_surface.get_height()))
