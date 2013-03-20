"""Graphics manager for handling drawing things.

    CLASSES

GraphicsManager
GraphicsGroup
Graphic
ResizableGraphic
Colour
Image

TODO:
 - resize, rotate don't transform if only 'about' changes - return (sfc, new_apply_fn, new_undo_fn)
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
 - Graphic.opacity (as a transform)
 - Graphic subclasses:
Text
Animation(surface | filename[image])
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

from math import sin, cos, pi
from collections import OrderedDict

import pygame as pg
from pygame import Rect

from conf import conf
from util import ir, convert_sfc, blank_sfc
from _gm import fastdraw


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
    """Convenience wrapper for grouping a number of graphics in a simple way.

Takes any number of Graphic instances or lists of arguments to pass to Graphic
to create one.  This is a list subclass, containing graphics, so add and remove
graphics using list methods.

    METHODS

opaque_in
move_by

    ATTRIBUTES

scale_fn, manager, layer, blit_flags, visible:
    as for Graphic; these give a list of values for each contained graphic; set
    them to a single value to apply to all contained graphics.

"""

    def __init__ (self, *graphics):
        list.__init__(self, (g if isinstance(g, Graphic) else Graphic(*g)
                             for g in graphics))

    def __getattr__ (self, attr):
        if attr in ('scale_fn', 'manager', 'layer', 'blit_flags', 'visible'):
            return [getattr(g, attr) for g in self]
        else:
            return list.__getattr__(self, attr)

    def __setattr__ (self, attr, val):
        if attr in ('scale_fn', 'manager', 'layer', 'blit_flags', 'visible'):
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

Graphic(img, pos, layer = 0, blit_flags = 0)

img: surface or filename (under conf.IMG_DIR) to load.
pos: initial (x, y) position.
layer: the layer to draw in, lower being closer to the 'front'. This can
       actually be any hashable object, as long as all layers used in the same
       GraphicsManager can be ordered with respect to each other.
blit_flags: when blitting the surface to the screen, this is passed as the
            special_flags argument.

    METHODS

opaque_in
snapshot
move_to
move_by
align
transform
undo_transforms
reapply_transform
sfc_before_transform
resize [builtin transform]
rescale
crop [builtin transform]
flip [builtin transform]
rotate [builtin transform]
reload

    ATTRIBUTES

fn: filename of the loaded image, or None if a surface was given.
surface: the (possibly transformed) surface that will be used for drawing.
rect: pygame.Rect giving the on-screen area covered; may be set directly, but
      not altered in-place.
last_rect: rect at the time of the last draw.
x, y: co-ordinates of the top-left corner of rect.
pos: (x, y).
w, h: width and height of rect; they use the resize method.
size: (w, h).
scale_x, scale_y: scaling ratio of the image on each axis; thy use the rescale
                  method.
scale: (scale_x, scale_y).  Can be set to a single number to scale both
       dimensions by.
scale_fn: function to use for scaling; defaults to pygame.transform.smoothscale
          (and should have the same signature as this default).  If you change
          this, you may want to call the reapply_transform method.
cropped_rect: the rect currently cropped to.
flipped_x, flipped_y: whether flipped on each axis.
flipped: (flipped_x, flipped_y).  Can be set to a single value to apply to both
         dimensions.
angle: current rotation angle, anti-clockwise in radians.  Setting this rotates
       about the graphic's centre.
rotate_fn: function to use for rotating; uses pygame.transform.rotozoom by
           default.  Takes the surface and angle (as passed to the rotate
           method) and returns the new rotated surface.  If you change this,
           you may want to call the reapply_transform method.
rotate_threshold: only rotate when the angle changes by this much; defaults to
                  2 * pi / 500.  If you change this, you may want to call the
                  reapply_transform method.
transforms: a list of transformations applied to the graphic.  This always
            contains the builtin transforms as strings (though they do nothing
            by default); other transforms are added through the transform
            method, and are functions.
manager: the GraphicsManager this graphic is associated with, or None; this may
         be changed directly.  (A graphic should only be used with one manager
         at a time.)
layer, blit_flags: as taken by constructor.
visible: whether currently (supposed to be) visible on-screen.
was_visible: visible at the time of the last draw; do not change.
opaque: whether this draws opaque pixels in the entire rect; do not change.

"""

    _builtin_transforms = ('crop', 'flip', 'resize', 'rotate')

    def __init__ (self, img, pos, layer = 0, blit_flags = 0):
        if isinstance(img, basestring):
            self.fn = img
            img = conf.GAME.img(img)
        else:
            self.fn = None
        self._scale = (1, 1)
        self._cropped_rect = None
        self._flipped = (False, False)
        # postrot is the rect drawn in
        self._rect = self._postrot_rect = Rect(pos, img.get_size())
        self._rot_offset = (0, 0) # postrot_pos = pos + rot_offset
        self._transforms = OrderedDict() # required by _set_sfc
        self._set_sfc(img)
        self.last_rect = self._last_postrot_rect = Rect(self._rect)
        # {function: (args, previous_surface, apply_fn, undo_fn)}
        self._transforms = OrderedDict.fromkeys(
            self._builtin_transforms, (None, self.surface, None, None)
        )
        # for manager
        self.scale_fn = pg.transform.smoothscale
        self.rotate_fn = lambda sfc, angle: \
            pg.transform.rotozoom(sfc, angle * 180 / pi, 1)
        self.rotate_threshold = 2 * pi / 500
        self._manager = None
        self._layer = layer
        self._blit_flags = blit_flags
        self.visible = True
        self.was_visible = False
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
                # handled in resize
                self._rect = rect
                self._postrot_rect = Rect(rect.move(self._rot_offset)[:2],
                                          self._postrot_rect[2:])
                self._mk_dirty()

    @property
    def x (self):
        return self._rect[0]

    @x.setter
    def x (self, x):
        r = Rect(self._rect)
        r[0] = x
        self.rect = r

    @property
    def y (self):
        return self._rect[1]

    @y.setter
    def y (self, y):
        r = Rect(self._rect)
        r[1] = y
        self.rect = r

    @property
    def pos (self):
        return self._rect.topleft

    @pos.setter
    def pos (self, pos):
        self.rect = (pos, self._rect[2:])

    @property
    def w (self):
        return self._rect[2]

    @w.setter
    def w (self, w):
        r = Rect(self._rect)
        r[2] = w
        self.rect = r

    @property
    def h (self):
        return self._rect[3]

    @h.setter
    def h (self, h):
        r = Rect(self._rect)
        r[3] = h
        self.rect = r

    @property
    def size (self):
        return self._rect.size

    @size.setter
    def size (self, size):
        self.rect = (self._rect.topleft, size)

    @property
    def scale_x (self):
        return self._scale[0]

    @scale_x.setter
    def scale_x (self, scale_x):
        self.rescale(scale_x, self._scale[1])

    @property
    def scale_y (self):
        return self._scale[1]

    @scale_y.setter
    def scale_y (self, scale_y):
        self.rescale(self._scale[0], scale_y)

    @property
    def scale (self):
        return self._scale

    @scale.setter
    def scale (self, scale):
        if isinstance(scale, (int, float)):
            self.rescale(scale, scale)
        else:
            self.rescale(*scale)

    @property
    def cropped_rect (self):
        if self._cropped_rect is None:
            return self.sfc_before_transform('crop').get_rect()
        else:
            return self._cropped_rect

    @cropped_rect.setter
    def cropped_rect (self, rect):
        self.crop(rect)

    @property
    def flipped_x (self):
        return self._flipped[0]

    @flipped_x.setter
    def flipped_x (self, flipped_x):
        self.flip(flipped_x, self._flipped[1])

    @property
    def flipped_y (self):
        return self._flipped[0]

    @flipped_x.setter
    def flipped_y (self, flipped_y):
        self.flip(self._flipped[0], flipped_y)

    @property
    def flipped (self):
        return self._flipped

    @flipped.setter
    def flipped (self, flipped):
        if isinstance(flipped, (bool, int)):
            self.flip(flipped, flipped)
        else:
            self.flip(*flipped)

    @property
    def angle (self):
        return self._angle

    @angle.setter
    def angle (self, angle):
        self.rotate(angle)

    @angle.setter

    # other properties

    @property
    def transforms (self):
        return self._transforms.keys()

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
        if layer != self._layer:
            # change layer in gm by removing, setting attribute, then adding
            m = self.manager
            if m is not None:
                m.rm(self)
            self._layer = layer
            if m is not None:
                m.add(self)

    @property
    def blit_flags (self):
        return self._blit_flags

    @blit_flags.setter
    def blit_flags (self, blit_flags):
        if blit_flags != self._blit_flags:
            self._blit_flags = blit_flags
            self._mk_dirty()

    def opaque_in (self, rect):
        """Whether this draws opaque pixels in the whole of the given rect."""
        return self.opaque and self._rect.contains(rect)

    def snapshot (self):
        """Return a copy of this graphic.

The copy is shallow, which means the new graphic will not appear to be
transformed, even if this one is, but will be an exact copy.

"""
        g = Graphic(self.surface, self._postrot_rect[:2], self._layer,
                    self.blit_flags)
        g.visible = self.visible
        g.scale_fn = self.scale_fn
        return g

    def _set_sfc (self, sfc):
        """Set new surface and opacity and modify rects."""
        if sfc.get_alpha() is None and sfc.get_colorkey() is None:
            sfc = sfc.convert()
            self.opaque = True
        else:
            sfc = sfc.convert_alpha()
            self.opaque = False
        self.surface = sfc
        self._rect = r = Rect(self._rect[:2],
                              self.sfc_before_transform('rotate').get_size())
        self._postrot_rect = Rect(r.move(self._rot_offset)[:2], sfc.get_size())

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
        self.rect = r
        return self

    def move_by (self, dx = 0, dy = 0):
        """Move by the given number of pixels.

move_by(dx = 0, dy = 0) -> self

"""
        self.rect = self._rect.move(dx, dy)
        return self

    def align (self, pos = 0, pad = 0, offset = 0, rect = None):
        """Position this graphic within a rect.

align(pos = 0, pad = 0, offset = 0, rect = self.manager.surface.get_rect())
    -> self

pos: (x, y) alignment; each is < 0 for left-aligned, 0 for centred, > 0 for
     right-aligned.  Can be just one number to use on both axes.
pad: (x, y) padding to leave around the inner edge of the rect.  Can be
     negative to allow positioning outside of the rect, and can be just one
     number to use on both axes.
pos: (x, y) amounts to offset by after all other positioning; can be just one
     number to use on both axes.
rect: Pygame-style rect to align in.

"""
        pos = [pos, pos] if isinstance(pos, (int, float)) else list(pos)
        if isinstance(pad, (int, float)):
            pad = (pad, pad)
        if isinstance(offset, (int, float)):
            offset = (offset, offset)
        if rect is None:
            rect = self._manager.surface.get_rect()
        else:
            rect = Rect(rect)
        rect = rect.inflate(-2 * pad[0], -2 * pad[1])
        sz = self._rect[2:]
        for axis in (0, 1):
            align = pos[axis]
            if align < 0:
                x = 0
            elif align == 0:
                x = (rect[2 + axis] - sz[axis]) / 2.
            else: # align > 0
                x = rect[2 + axis] - sz[axis]
            pos[axis] = ir(rect[axis] + x + offset[axis])
        self.rect = (pos, sz)
        return self

    # transform

    def transform (self, transform_fn, *args, **kwargs):
        """Apply a transformation to the graphic.

transform(transform_fn, *args[, position][, before][, after]) -> self

transform_fn: a function to apply a transform, or a string for a builtin
              transform such as 'resize' (see method list in class
              documentation).
position: a keyword-only argument giving the index in the transforms attribute
          to insert this transform at.  If this is omitted, the transform is
          appended to the end if new (not in transforms already), else left
          where it is.
before: (keyword-only) if position is not given, this gives the transform
        function (as in the transforms attribute) to insert this transform
        before.  If not in transforms, append to the end.
after: (keyword-only) if position and before are not given, insert after this
       transform function (or at the end).

Builtin transforms should not be moved after rotation; behaviour in this case
is undefined.

Calls transform_fn(sfc, last_args, *args) to apply the transformation, where:

sfc: surface before this transformation was last applied (or the current
     surface if it never has been).
last_args: the args passed to this method when this transformation was last
           applied, as a tuple (or None if it never has been).

and transform_fn should return the new surface after transforming.  The passed
surface should not be altered: the new surface should be a new instance, or the
unaltered surface if the transformation would do nothing.

If the results of the transformation would be exactly the same with last_args
as with args, transform_fn may return None to indicate this.

"""
        # determine position
        ts = self._transforms
        ks = ts.keys()
        exist = transform_fn in ts
        position = kwargs.get('position')
        if position is None:
            before = kwargs.get('before')
            after = kwargs.get('after')
            if before is not None:
                position = ks.index(before) if before in ks else None
            elif after is not None:
                position = ks.index(after) + 1 if after in ks else None
            elif exist:
                position = ks.index(transform_fn)
        elif position >= len(ks):
            position = None
        # get previous surface and args, and the last resulting surface, if any
        if position is not None:
            # grab data previous to requested position and undo up to it
            last_args, sfc, apply_fn, undo_fn = ts[ks[position]]
            if position == len(ks) - 1:
                # last transform: last result is current surface
                last_new_sfc = self.surface
            else:
                last_new_sfc = ts[ks[position + 1]][1]
            for i, (this_args, this_sfc, this_apply_fn, this_undo_fn) \
                in reversed(list(enumerate(ts.values()))[position:]):
                if this_undo_fn is not None:
                    this_undo_fn(self)
            if ks[position] != transform_fn:
                # insert in transforms and _transforms
                ts = ts.items()
                # value for this position gets set below
                ts = ts[:position] + (position, None) + ts[position:]
                self._transforms = ts = OrderedDict(ts)
        else:
            # use current data
            last_new_sfc = sfc = self.surface
            last_args = apply_fn = undo_fn = None
        builtin = isinstance(transform_fn, basestring)
        if builtin:
            new_sfc, new_apply_fn, new_undo_fn = \
                getattr(self, '_' + transform_fn)(sfc, last_args, *args)
            if new_apply_fn is not None:
                apply_fn = new_apply_fn
            if new_undo_fn is not None:
                undo_fn = new_undo_fn
        else:
            new_sfc = transform_fn(sfc, last_args, *args)
        if new_sfc is sfc:
            # transformation would do nothing
            if not exist:
                # add to transforms anyway
                ts[transform_fn] = (args, sfc, None, None)
        else:
            if builtin:
                if apply_fn is not None:
                    apply_fn(self) # must not modify surface or _rect.size
            if new_sfc is None:
                # didn't do anything
                new_sfc = last_new_sfc
                assert last_args is not None, 'transform function should ' \
                                              'only return None if it was ' \
                                              'passed last_args'
                args = last_args
            self._set_sfc(new_sfc)
            ts[transform_fn] = (args, sfc, apply_fn, undo_fn)
            if position is not None:
                # reapply from this transform onwards: call after setting
                # surface and _rect so we end up at the outermost call with the
                # final values set last
                ts = ts.items()
                self._transforms = OrderedDict(ts[:position + 1])
                for fn, (args, sfc, apply_fn, undo_fn) in ts[position + 1:]:
                    if args is not None:
                        self.transform(fn, *args)
            self._mk_dirty()
        return self

    def undo_transforms (self, upto):
        """Undo transforms up and including the given transform function.

Argument may be an index in the transforms attribute, a function, or a string
for a builtin.

"""
        ts = self._transforms
        if upto in ts:
            upto = ts.keys().index(upto)
        if isinstance(upto, int):
            if upto >= len(ts):
                upto = None
        else:
            upto = None
        if upto is None:
            # nothing to do
            return
        ts = ts.items()
        self._transforms = OrderedDict(ts[:upto])
        for fn, (args, sfc, apply_fn, undo_fn) in reversed(ts[upto:]):
            if undo_fn is not None:
                undo_fn(self)
        # we know upto < len(ts) so we looped at least once and sfc exists
        self._set_sfc(sfc)

    def reapply_transform (self, start = 0):
        """Reapply the given transformation (index or function).

Index is the order the transform was applied, 0 first; function is as passed
to the transform method.

"""
        ts = self._transforms
        if isinstance(start, basestring):
            start = getattr(self, '_' + start)
        if callable(start):
            if start not in ts:
                return
            start = ts.keys().index(start)
        ts = ts.items()
        # removes from _transforms and transforms; transform will add them back
        self.undo_transforms(start)
        self._transforms = OrderedDict(ts[:start])
        ts = ts[start:]
        if ts:
            args, sfc = ts[0]
            self.surface = sfc
            self._rect = Rect(self._rect[:2], sfc.get_size())
            # if any transforms do anything, they will set opaque, etc. (else
            # the surface won't change and we just keep the current values)
            for fn, (args, sfc, apply_fn, undo_fn) in ts[start:]:
                self.transform(fn, *args)

    def sfc_before_transform (self, transform_fn):
        """Return surface before the given transform.

Takes a transform function as taken by the transform method that may or may not
have been applied yet.

"""
        ts = self._transforms
        if transform_fn in ts:
            return ts[transform_fn][1]
        else:
            return self.surface

    def _resize (self, sfc, last, w, h, about = (0, 0)):
        """Backend for resize."""
        start_w, start_h = start_sz = sfc.get_size()
        if w is None:
            w = start_w
        if h is None:
            h = start_h
        sz = (w, h)
        about = (about[0], about[1])
        if last is not None:
            last_w, last_h, (last_ax, last_ay) = last
            if sz == (last_w, last_h) and about == (last_ax, last_ay):
                # no change to arguments
                return (None, None, None)
        if sz == start_sz and about == (0, 0):
            return (sfc, None, None)
        scale = (float(w) / start_w, float(h) / start_h)
        offset = (ir((1 - scale[0]) * about[0]),
                    ir((1 - scale[1]) * about[1]))

        def apply_fn (g):
            g._scale = scale
            x, y, gw, gh = g._rect
            g._rect = Rect(x + offset[0], y + offset[1], gw, gh)

        def undo_fn (g):
            g._scale = (1, 1)
            x, y, gw, gh = g._rect
            g._rect = Rect(x - offset[0], y - offset[1], gw, gh)

        return (self.scale_fn(sfc, sz), apply_fn, undo_fn)

    def resize (self, w = None, h = None, about = (0, 0)):
        """Resize the graphic.

resize([w][, h], about = (0, 0)) -> self

w, h: the new width and height.  No scaling occurs in omitted dimensions.
about: the (x, y) position relative to the top-left of the graphic to scale
       about.

"""
        return self.transform('resize', w, h, about)

    def rescale (self, w = None, h = None, about = (0, 0)):
        """A convenience wrapper around resize to scale by a ratio.

Arguments are as taken by resize, but w and h are ratios of the size before
scaling.

"""
        if w is None:
            w = 1
        if h is None:
            h = 1
        ow, oh = self.sfc_before_transform('resize').get_size()
        return self.resize(ir(w * ow), ir(h * oh), about)

    def _crop (self, sfc, last, rect):
        """Backend for crop."""
        start = sfc.get_rect()
        if last is not None and rect == last[0]:
            return (None, None, None)
        if rect == start:
            return (sfc, None, None)
        new_sfc = pg.Surface(rect.size)
        inside = start.contains(rect)
        if sfc.get_alpha() is None and sfc.get_colorkey() is None and inside:
            new_sfc = new_sfc.convert()
        else:
            new_sfc = new_sfc.convert_alpha()
            if not inside:
                # fill with alpha so area outside borders is transparent
                new_sfc.fill((0, 0, 0, 0))
        dx, dy = rect[:2]
        new_sfc.blit(sfc, rect.move(-dx, -dy), rect)

        def apply_fn (g):
            g._rect = g._rect.move(dx, dy)
            g._cropped_rect = rect

        def undo_fn (g):
            g._rect = g._rect.move(-dx, -dy)
            g._cropped_rect = None

        return (new_sfc, apply_fn, undo_fn)

    def crop (self, rect):
        """Crop the surface to the given rect.

The rect need not be contained in the current surface rect.

Returns self.

"""
        return self.transform('crop', Rect(rect))

    def _flip (self, sfc, last, x, y):
        """Backend for flip."""
        if last is not None and last == (x, y):
            return (None, None, None)
        if not x and not y:
            return (sfc, None, None)
        new_sfc = pg.transform.flip(sfc, x, y)

        def apply_fn (g):
            g._flipped = (x, y)

        def undo_fn (g):
            g._flipped = (False, False)

        return (new_sfc, apply_fn, undo_fn)

    def flip (self, x = False, y = False):
        """Flip the graphic over either axis.

flip(x = False, y = False) -> self

x, y: whether to flip over this axis.

"""
        return self.transform('flip', bool(x), bool(y))

    def _rotate (self, sfc, last, angle, about):
        """Backend for rotate."""
        w_old, h_old = sfc.get_size()
        cx, cy = w_old / 2., h_old / 2.
        about = (cx, cy) if about is None else (about[0], about[1])
        if last is not None:
            last_angle, last_about = last
            last_about = (cx, cy) if last_about is None \
                         else (last_about[0], last_about[1])
            if abs(angle - last_angle) < self.rotate_threshold and about == last_about:
                # no change to arguments
                return (None, None, None)
        if abs(angle) < self.rotate_threshold:
            return (sfc, None, None)
        new_sfc = self.rotate_fn(sfc, angle)
        # compute draw offset
        w_new, h_new = new_sfc.get_size()
        # v = c_new - about
        vx = cx - about[0]
        vy = cy - about[1]
        # c - about_new = v.rotate(angle)
        s = sin(angle)
        c = cos(angle)
        ax_new = w_new / 2. - (c * vx + s * vy)
        ay_new = h_new / 2. - (-s * vx + c * vy)
        # about = offset + about_new
        offset = (ir(about[0] - ax_new), ir(about[1] - ay_new))

        def apply_fn (g):
            g._angle = angle
            g._rot_offset = offset

        def undo_fn (g):
            g._angle = 0
            g._rot_offset = (0, 0)

        return (new_sfc, apply_fn, undo_fn)

    def rotate (self, angle, about = None):
        """Rotate the graphic.

rotate(angle[, about]) -> self

angle: the angle in radians to rotate to, anti-clockwise from the original
       graphic.
about: the (x, y) position relative to the top-left of the graphic to rotate
       about; defaults to the graphic's centre.

"""
        return self.transform('rotate', angle, about)

    def reload (self):
        """Reload from disk if possible.

If successful, all transformations are reapplied afterwards.

"""
        if self.fn is not None:
            sfc = conf.GAME.img(self.fn, cache = False)
            self._set_sfc(sfc)
            self._mk_dirty()
            ts = self._transforms
            self._transforms = OrderedDict()
            for fn, (args, sfc) in ts:
                self.transform(fn, *args)

    def _mk_dirty (self):
        """Mark as dirty."""
        self._dirty = [self._last_postrot_rect, self._postrot_rect]

    def _draw (self, dest, rects):
        """Draw the graphic.

_draw(dest, rects)

dest: pygame.Surface to draw to.
rects: list of rects to draw in.

Should never alter any state that is not internal to the graphic.

"""
        sfc = self.surface
        blit = dest.blit
        flags = self._blit_flags
        offset = (-self._postrot_rect[0], -self._postrot_rect[1])
        for r in rects:
            blit(sfc, r, r.move(offset), flags)
        self._last_postrot_rect = self._postrot_rect
        self.last_rect = self._rect


class Colour (Graphic):
    """A solid rect of colour (Graphic subclass).

    CONSTRUCTOR

Colour(colour, rect, layer = 0, blit_flags = 0)

colour: a Pygame-style (R, G, B[, A = 255]) colour to draw.
rect: (left, top, width, height) rect (of ints) to draw in (or anything taken
      by pygame.Rect, like a Rect, or ((left, top), (width, height))).
layer, blit_flags: as taken by Graphic.

    METHODS

fill [builtin transform]

    ATTRIBUTES

colour: as taken by constructor; set as necessary.

"""

    _i = Graphic._builtin_transforms.index('crop')
    _builtin_transforms = Graphic._builtin_transforms[:_i] + ('fill',) + \
                          Graphic._builtin_transforms[_i:]

    def __init__ (self, colour, rect, layer = 0, blit_flags = 0):
        rect = Rect(rect)
        # converts surface and sets opaque to True
        Graphic.__init__(self, pg.Surface(rect[2:]), rect[:2], layer,
                         blit_flags)
        self._colour = (0, 0, 0)
        self.fill(colour)

    @property
    def colour (self):
        return self._colour

    @colour.setter
    def colour (self, colour):
        self.fill(colour)

    def _fill (self, sfc, last_args, colour):
        if last_args is not None:
            # compare colours
            lcolour = last_args[0]
            lr, lg, lb = lcolour
            la = 255 if len(lcolour) < 4 else lcolour[3]
            r, g, b = colour
            a = 255 if len(colour) < 4 else colour[3]
            if (lr, lg, lb, la) == (r, g, b, a):
                return
        # need a new surface anyway
        sfc = pg.Surface(sfc.get_size())
        if len(colour) == 4 and colour[3] < 255:
            # non-opaque: need to convert to alpha
            sfc = sfc.convert_alpha()
        sfc.fill(colour)
        return (sfc, None, None)

    def fill (self, colour):
        self.transform('fill', colour)
        self._colour = colour
        return self
