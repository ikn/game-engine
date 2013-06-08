"""Graphics manager for handling drawing things.

---NODOC---

TODO:
 - is display.update much slower with duplicates?  If so, maybe merge layers' dirty rects.
 - in graphics, store n (5?) last # frames between changes to the surface (by transform or altering the original)
    - if the average > x or current length < n, do some things:
        - turn opacity into a list of rects the graphic is opaque in (x = 4?)
        - if a Colour, put into blit mode (also do so if transformed in a certain way) (x = 3?)
 - partial transforms
    - reimplement apply_fn/undo_fn (must happen when altering queue (.transform(), .untransform(), etc.)
    - rewrite builtin transforms
    - GM as graphic
 - ignore off-screen things
 - if GM is fully dirty or GM.busy, draw everything without any rect checks (but still nothing under opaque)
 - GraphicsManager.offset to offset the viewing window (Surface.scroll is fast?)
    - supports parallax: set to {layer: ratio} or (function(layer) -> ratio)
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

---NODOC---

"""

import sys
from math import sin, cos, pi

import pygame as pg
from pygame import Rect

from conf import conf
from util import ir, normalise_colour, combine_drawn
try:
    from _gm import fastdraw
except ImportError:
    print >> sys.stderr, 'error: couldn\'t import _gm; did you remember to `make\'?'
    sys.exit(1)


class Graphic (object):
    """Something that can be drawn to the screen.

Graphic(img, pos = (0, 0), layer = 0, blit_flags = 0)

:arg img: surface or filename (under :data:`conf.IMG_DIR`) to load.
:arg pos: initial ``(x, y)`` position.  The existence of a default is because
          you might use :meth:`align` immediately on adding to a
          :class:`GraphicsManager`.
:arg layer: the layer to draw in, lower being closer to the 'front'. This can
            actually be any hashable object except ``None``, as long as all
            layers used in the same :class:`GraphicsManager` can be ordered
            with respect to each other.
:arg blit_flags: when blitting the surface to the screen, this is passed as the
                 ``special_flags`` argument.

Many properties of a graphic, such as :attr:`pos` and :attr:`size`, can be
changed in two main ways: by setting the attribute directly, or by calling the
corresponding method.  The former is more natural, and is useful for
:meth:`sched.Scheduler.interp`, while the latter all return the graphic, and so
can be chained together.

Position and size can also be retrieved and altered using list indexing, like
with Pygame rects.

:meth:`resize`, :meth:`crop`, :meth:`flip` and :meth:`rotate` correspond to
builtin transforms (see :meth:`transform`).

"""

    _builtin_transforms = ('crop', 'flip', 'resize', 'rotate')

    def __init__ (self, img, pos = (0, 0), layer = 0, blit_flags = 0):
        if isinstance(img, basestring):
            #: Filename of the loaded image, or ``None`` if a surface was
            #: given.
            self.fn = img
            img = conf.GAME.img(img)
        else:
            self.fn = None
        self._orig_sfc = self._surface = img
        # postrot is the rect drawn in
        self._postrot_rect = self._rect = Rect(pos, img.get_size())
        self._last_postrot_rect = Rect(self._postrot_rect)
        #: :attr:`rect` at the time of the last draw.
        self.last_rect = Rect(self._rect)
        self._rot_offset = (0, 0) # postrot_pos = pos + rot_offset
        #: A list of transformations applied to the graphic.  Always contains
        #: the builtin transforms as strings (though they do nothing
        #: by default); other transforms are added through :meth:`transform`,
        #: and are functions.
        self.transforms = list(self._builtin_transforms)
        self._last_transforms = list(self.transforms)
        # {function: (args, previous_surface, resulting_surface)}
        self._transforms = {}
        # {function: args}
        self._queued_transforms = {}
        if img.get_alpha() is None and img.get_colorkey() is None:
            #: Whether this is opaque in the entire rect; do not change.
            self.opaque = True
        else:
            self.opaque = False
        self._manager = None
        self._layer = layer
        #: As taken by the constructor.
        self._last_blit_flags = self.blit_flags = blit_flags
        #: Whether currently (supposed to be) visible on-screen.
        self.visible = True
        #: Whether this graphic was visible at the time of the last draw; do
        #: not change.
        self.was_visible = False
        self._scale = (1, 1)
        self._cropped_rect = None
        self._flipped = (False, False)
        self._angle = 0
        #: Function to use for scaling; defaults to
        #: ``pygame.transform.smoothscale`` (and should have the same signature
        #: as this default).  If you change this, you may want to call
        #: :meth:`retransform`.
        self.scale_fn = pg.transform.smoothscale
        #: Function to use for rotating; uses ``pygame.transform.rotozoom`` by
        #: default.  Takes the surface and angle (as passed to :meth:`rotate`)
        # and returns the new rotated surface.  If you change this, you may
        # want to call :meth:`retransform`.
        self.rotate_fn = lambda sfc, angle: \
            pg.transform.rotozoom(sfc, angle * 180 / pi, 1)
        #: Only rotate when the angle changes by this much; defaults to
        #: ``2 * pi / 500``.  If you change this, you may want to call
        #: :meth:`retransform`.
        self.rotate_threshold = 2 * pi / 500
        self._orig_dirty = [] # where original surface is changed
        # where final surface is changed; gets used (and reset) by manager
        self._dirty = []

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

    @property
    def surface (self):
        """The (possibly transformed) surface that will be used for drawing.

Accessing this will cause all queued transformations to be applied.

"""
        self.render()
        return self._surface

    @property
    def orig_sfc (self):
        """The surface before any transforms."""
        return self._orig_sfc

    @orig_sfc.setter
    def orig_sfc (self, sfc):
        self._orig_sfc = sfc
        self._orig_dirty = True

    # appearance properties

    @property
    def rect (self):
        """``pygame.Rect`` giving the on-screen area covered.

May be set directly, but not altered in-place.

"""
        return self._rect

    @rect.setter
    def rect (self, rect):
        # need to set dirty in old and new rects (if changed)
        rect = Rect(rect)
        self._rect = Rect(rect.topleft, self._rect.size)
        if rect.size != self.last_rect.size:
            self.resize(*rect.size)

    @property
    def x (self):
        """``x`` co-ordinate of the top-left corner of :attr:`rect`."""
        return self._rect[0]

    @x.setter
    def x (self, x):
        r = Rect(self._rect)
        r[0] = x
        self.rect = r

    @property
    def y (self):
        """``y`` co-ordinate of the top-left corner of :attr:`rect`."""
        return self._rect[1]

    @y.setter
    def y (self, y):
        r = Rect(self._rect)
        r[1] = y
        self.rect = r

    @property
    def pos (self):
        """``(``:attr:`x` ``,`` :attr:`y` ``)``."""
        return self._rect.topleft

    @pos.setter
    def pos (self, pos):
        self.rect = (pos, self._rect[2:])

    @property
    def w (self):
        """Width of :attr:`rect`; uses :meth:`resize`."""
        return self._rect[2]

    @w.setter
    def w (self, w):
        r = Rect(self._rect)
        r[2] = w
        self.rect = r

    @property
    def h (self):
        """Height of :attr:`rect`; uses :meth:`resize`."""
        return self._rect[3]

    @h.setter
    def h (self, h):
        r = Rect(self._rect)
        r[3] = h
        self.rect = r

    @property
    def size (self):
        """``(``:attr:`w` ``,`` :attr:`h` ``)``."""
        return self._rect.size

    @size.setter
    def size (self, size):
        self.rect = (self._rect.topleft, size)

    @property
    def scale_x (self):
        """Scaling ratio of the graphic on the x-axis; uses :meth:`rescale`."""
        return self._scale[0]

    @scale_x.setter
    def scale_x (self, scale_x):
        self.rescale(scale_x, self._scale[1])

    @property
    def scale_y (self):
        """Scaling ratio of the graphic on the y-axis; uses :meth:`rescale`."""
        return self._scale[1]

    @scale_y.setter
    def scale_y (self, scale_y):
        self.rescale(self._scale[0], scale_y)

    @property
    def scale (self):
        """``(``:attr:`scale_x` ``,`` :attr:`scale_y` ``)``.

Can be set to a single number to scale by in both dimensions.

"""
        return self._scale

    @scale.setter
    def scale (self, scale):
        if isinstance(scale, (int, float)):
            self.rescale(scale, scale)
        else:
            self.rescale(*scale)

    @property
    def cropped_rect (self):
        """The rect currently cropped to."""
        if self._cropped_rect is None:
            return self.sfc_before_transform('crop').get_rect()
        else:
            return self._cropped_rect

    @cropped_rect.setter
    def cropped_rect (self, rect):
        self.crop(rect)

    @property
    def flipped_x (self):
        """Whether flipped on the x-axis."""
        return self._flipped[0]

    @flipped_x.setter
    def flipped_x (self, flipped_x):
        self.flip(flipped_x, self._flipped[1])

    @property
    def flipped_y (self):
        """Whether flipped on the y-axis."""
        return self._flipped[0]

    @flipped_x.setter
    def flipped_y (self, flipped_y):
        self.flip(self._flipped[0], flipped_y)

    @property
    def flipped (self):
        """``(``:attr:`flipped_x` ``,`` :attr:`flipped_y` ``)``.

Can be set to a single value to apply to both dimensions.

"""
        return self._flipped

    @flipped.setter
    def flipped (self, flipped):
        if isinstance(flipped, (bool, int)):
            self.flip(flipped, flipped)
        else:
            self.flip(*flipped)

    @property
    def angle (self):
        """Current rotation angle, anti-clockwise in radians.

Setting this rotates about the graphic's centre.

"""
        return self._angle

    @angle.setter
    def angle (self, angle):
        self.rotate(angle)

    # other properties

    @property
    def manager (self):
        """The :class:`GraphicsManager` this graphic is associated with.

May be ``None``.  This may be changed directly.  (A graphic should only be used with one manager at a time.)

"""
        return self._manager

    @manager.setter
    def manager (self, manager):
        if self._manager is not None:
            self._manager.rm(self)
        if manager is not None:
            manager.add(self) # changes value in _manager
        else:
            self._manager = None

    @property
    def layer (self):
        """As taken by the constructor."""
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

    def _opaque_in (self, rect):
        """Whether this draws opaque pixels in the whole of the given rect."""
        return self.opaque and self._postrot_rect.contains(rect)

    def snapshot (self):
        """Return a copy of this graphic.

The copy is shallow, which means the new graphic will not appear to be
transformed, even if this one is, but will be an exact copy of the *current
state*.

"""
        self.render()
        g = Graphic(self._surface, self._postrot_rect[:2], self._layer,
                    self.blit_flags)
        for attr in ('visible', 'scale_fn', 'rotate_fn', 'rotate_threshold'):
            setattr(g, attr, getattr(self, attr))
        return g

    # appearance methods

    def move_to (self, x = None, y = None):
        """Move to the given position.

move_to([x][, y]) -> self

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

:arg pos: ``(x, y)`` alignment; each is ``< 0`` for left-aligned, ``0`` for
          centred, ``> 0`` for right-aligned.  Can be just one number to use on
          both axes.
:arg pad: ``(x, y)`` padding to leave around the inner edge of ``rect``.  Can
          be negative to allow positioning outside of ``rect``, and can be just
          one number to use on both axes.
:arg offset: ``(x, y)`` amounts to offset by after all other positioning; can
             be just one number to use on both axes.
:arg rect: Pygame-style rect to align in.

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

:arg transform_fn: a function to apply a transform, or a string for a builtin
                   transform such as ``'resize'`` (see class documentation).
:arg args: passed to the transformation function as positional arguments, after
           compulsory arguments.
:arg position: a keyword-only argument giving the index in :attr:`transforms`
               to insert this transform at.  If not given, the transform is
               appended to the end if new (not in transforms already), else
               left where it is.
:arg before: (keyword-only) if ``position`` is not given, this gives the
             transform function (as in :attr:`transforms`) to insert this
             transform before.  If ``before`` is not in :attr:`transforms`, the
             transform is put at the end.
:arg after: (keyword-only) if ``position`` and ``before`` are not given, insert
            after this transform function, or at the end if it doesn't exist.

Builtin transforms should not be moved after rotation (``'rotate'``); behaviour
in this case is undefined.

Calls ``transform_fn(src, dest, last_args, args, dirty)`` to apply the
transformation, where:

- ``src`` is the surface before this transformation was last applied (or the
  current surface if it never has been).
- ``dest`` is the surface last produced by this transformation, or ``None`` if
  the transform is new.
- ``last_args`` is the ``args`` passed to this method when this transformation
  was last applied, as a tuple (or ``None`` if it never has been).
- ``args`` is as passed to this method.
- ``dirty`` defines what has changed in ``src`` since the last time this
  transform was applied - ``True`` if the whole surface has changed, or a list
  of rects, or ``False`` if nothing has changed.  This allows for partial
  transformations by altering ``dest``, if given.

``transform_fn`` should return ``(sfc, dirty)``, where:

- ``sfc`` is the resulting pygame Surface.
- ``dirty`` is a corresponding definition of changed areas in the resulting
  surface.

``src`` should never be altered, but may be returned as ``sfc`` if the
transform does nothing.  Possible modes of operation are:

- full transform: return ``(new_sfc, True)``.
- partial transform: return ``(dest, dirty)`` (``dirty`` might also be
  ``False`` here).
- do nothing: return ``(src, False)``.

If creating and returning a new surface, it should already be converted for
blitting.

"""
        # add to/reorder transforms list, and queue for transforming later
        ts = self.transforms
        q = self._queued_transforms
        i = kwargs.get('position')
        if i is None:
            fn = kwargs.get('before')
            if fn is not None:
                try:
                    i = ts.index(fn)
                except ValueError:
                    pass
            else:
                fn = kwargs.get('after')
                try:
                    i = ts.index(fn) + 1
                except ValueError:
                    pass
        if i is None:
            try:
                i = ts.index(transform_fn)
            except ValueError:
                pass
        if i is None or i == len(ts):
            ts.append(transform_fn)
        else:
            ts[i] = transform_fn
        q[transform_fn] = args

    def untransform (self, transform_fn):
        """Remove an applied transformation.

Takes a transformation function like :meth:`transform`.

"""
        for ts in (self._queued_transforms, self._transforms):
            if transform_fn in ts:
                del ts[transform_fn]
        if not isinstance(transform_fn, basestring):
            try:
                self.transforms.remove(transform_fn)
            except ValueError:
                pass

    def retransform (self, transform_fn):
        """Reapply the given transformation (if already applied).

Takes a transformation function like :meth:`transform`.

"""
        try:
            args = self._transforms[transform_fn][0]
        except KeyError:
            pass
        else:
            self._queued_transforms[transform_fn] = args

    def last_transform_args (self, transform_fn):
        """Return the last (tuple of) arguments passed to the given transform.

This is all arguments passed to the transform when it was last applied/queued.
Takes a transform function as taken by :meth:`transform`.  If it has not been
applied/queued yet, the return value is ``None`` (builtin transformations are
always applied).

"""
        try:
            return self._queued_transforms[transform_fn]
        except KeyError:
            try:
                return self._transforms[transform_fn][0]
            except KeyError:
                return None

    def sfc_before_transform (self, transform_fn):
        """Return the value of :attr:`surface` before the given transform.

Takes a transform function as taken by :meth:`transform`.  If it has not been
applied/queued yet, the return value is ``None`` (builtin transformations are
always applied).  Calling this causes all queued transformations to be applied.

"""
        self.render()
        t_ks = self.transforms
        ts = self._transforms
        if transform_fn in ts:
            return ts[transform_fn][1]
        else:
            if transform_fn in t_ks:
                # must be a default-valued builtin
                i = t_ks.index(transform_fn)
                return self._orig_sfc if i == 0 else ts[t_ks[i - 1]][1]
            else:
                return None

    def reload (self):
        """Reload from disk if possible.

If successful, all transformations are reapplied afterwards, if any.

"""
        if self.fn is not None:
            self.orig_sfc = conf.GAME.img(self.fn, cache = False)

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

:arg w: the new width.
:arg h: the new height.
:arg about: the ``(x, y)`` position relative to the top-left of the graphic to
            scale about.

No scaling occurs in omitted dimensions.

"""
        return self.transform('resize', w, h, about)

    def rescale (self, w = 1, h = 1, about = (0, 0)):
        """A convenience wrapper around resize to scale by a ratio.

rescale(w = 1, h = 1, about = (0, 0)) -> self

:arg w: the new width; ratio of the width before scaling.
:arg h: the new height; ratio of the height before scaling.
:arg about: the ``(x, y)`` position relative to the top-left of the graphic to
            scale about.

"""
        ow, oh = self.sfc_before_transform('resize').get_size()
        return self.resize(ir(w * ow), ir(h * oh), about)

    def resize_both (self, w = None, h = None, about = (0, 0)):
        """Resize with constant aspect ratio.

resize_both([w][, h], about = (0, 0)) -> self

:arg w, h: the new width/height; pass only one of these.
:arg about: the ``(x, y)`` position relative to the top-left of the graphic to
            scale about.

"""
        ow, oh = self.sfc_before_transform('resize').get_size()
        if w is None:
            w = ir(ow * float(h) / oh)
        else:
            h = ir(oh * float(w) / ow)
        return self.resize(w, h, about)

    def rescale_both (self, scale = 1, about = (0, 0)):
        """A convenience wrapper around rescale to scale the same on both axes.

rescale_both(scale = 1, about = (0, 0)) -> self

:arg scale: ratio to scale both width and height by.
:arg about: the ``(x, y)`` position relative to the top-left of the graphic to
            scale about.

"""
        return self.rescale(scale, scale, about)

    def _crop (self, sfc, last, rect):
        """Backend for crop."""
        start = sfc.get_rect()
        if last is not None and rect == last[0]:
            return (None, None, None)
        if rect == start:
            return (sfc, None, None)
        new_sfc = pg.Surface(rect.size)
        inside = start.contains(rect)
        if sfc.get_alpha() is None and sfc.get_colorkey() is None and \
           not inside:
            # was opaque before, not any more
            new_sfc = new_sfc.convert_alpha()
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

crop(rect) -> self

``rect`` need not be contained in the current surface rect.

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

:arg x: whether to flip over the x-axis.
:arg y: whether to flip over the y-axis.

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
        # if not already alpha, convert to alpha
        if sfc.get_alpha() is None and sfc.get_colorkey() is None:
            sfc = sfc.convert_alpha()
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

:arg angle: the angle in radians to rotate to, anti-clockwise from the original
            graphic.
:arg about: the ``(x, y)`` position relative to the top-left of the graphic to
            rotate about; defaults to the graphic's centre.

"""
        return self.transform('rotate', angle, about)

    def dirty (self, *rects):
        """Mark some or all of the graphic as changed.

This is to be used when you alter the original surface (:attr:`orig_sfc`) - do
not alter any other (transformed) surfaces.  Takes any number of rects to flag
as dirty.  If none are given, the whole of the graphic is flagged.

"""
        self._orig_dirty = combine_drawn(self._orig_dirty, rects)

    def render (self):
        """Update the final surface.

This propagates changes from queued transformations and changes to the original
surface.

"""
        t_ks = self.transforms
        last_t_ks = self._last_transforms
        q = self._queued_transforms
        ts = self._transforms
        self._queued_transforms = {}
        # work out where to start (re)applying transforms from
        dirty = self._orig_dirty
        if dirty:
            i = 0
        elif q:
            i = min(t_ks.index(fn) for fn in q)
            i = min(i, *(last_t_ks.index(fn) for fn in q if fn in last_t_ks))
        else:
            i = len(t_ks)
        # apply transforms
        before_rot = sfc = self._orig_sfc
        passed_rot = False
        for j, fn in enumerate(t_ks):
            if fn != last_t_ks[j]:
                # differ from last transform order at this point
                dirty = True
                i = j
            if not dirty and fn in ts:
                # nothing is different at this point
                # grab surface to start next transform at
                sfc = ts[fn][1]
                if not passed_rot:
                    before_rot = sfc
                    if fn == 'rotate':
                        passed_rot = True
            if j < i:
                continue
            if fn in ts:
                # done this transform before
                last_args, prev_sfc, dest = ts[fn]
            else:
                last_args = dest = None
            if fn in q:
                # got new args
                args = q[fn]
            elif last_args is not None:
                # transform with same args
                args = last_args
            else:
                # does nothing
                continue
            f = getattr(self, '_' + fn) if isinstance(fn, basestring) else fn
            new_sfc, dirty = f(sfc, dest, dirty, last_args, *args)
            if dirty or dest is None:
                # transformed for the first time or something changed in
                # retransforming
                ts[fn] = (args, sfc, new_sfc)
            sfc = new_sfc
        if len(last_t_ks) > len(t_ks):
            # might have just removed transforms from the end
            dirty = True

        self._last_transforms = list(t_ks)
        if dirty:
            self._dirty = combine_drawn(self._dirty, dirty)
            # change current surface and rect
            self._surface = sfc
            if sfc.get_alpha() is None and sfc.get_colorkey() is None:
                self.opaque = True
            else:
                self.opaque = False
            self._rect = r = Rect(self._rect.topleft, before_rot.get_size())
            self._postrot_rect = pr = r.move(self._rot_offset)
            pr.size = sfc.get_size()

    def _pre_draw (self):
        """Called by GraphicsManager before drawing."""
        self.render()
        dirty = self._dirty
        if self._rect != self.last_rect:
            dirty = True
        if self.blit_flags != self._last_blit_flags:
            dirty = True
            self._last_blit_flags = self.blit_flags
        if dirty:
            pr = self._postrot_rect
            if dirty is True:
                dirty = [self._last_postrot_rect, pr]
            else:
                # translate dirty rects
                dirty = [d_r.move(pr) for d_r in dirty]
            self._dirty = dirty
        else:
            dirty = [] # fastdraw needs list

    def _draw (self, dest, rects):
        """Draw the graphic.

_draw(dest, rects)

dest: pygame.Surface to draw to.
rects: list of rects to draw in.

Should never alter any state that is not internal to the graphic.

"""
        sfc = self._surface
        blit = dest.blit
        pr = self._postrot_rect
        offset = (-pr[0], -pr[1])
        for r in rects:
            blit(sfc, r, r.move(offset), self.blit_flags)
        self._last_postrot_rect = pr
        self.last_rect = self._rect


class GraphicsGroup (list):
    """Convenience wrapper for grouping a number of graphics in a simple way.

Takes any number of :class:`Graphic` instances or lists of arguments to pass to
:class:`Graphic` to create one.  This is a ``list`` subclass, containing
graphics, so add and remove graphics using list methods.

Has ``scale_fn``, ``manager``, ``layer``, ``blit_flags`` and ``visible``
properties as for :class:`Graphic`.  These give a list of values for each
contained graphic; set them to a single value to apply to all contained
graphics.

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

Returns ``True`` if any graphic draws opaque pixels in the whole of the given
rect.

"""
        return any(g.opaque_in(rect) for g in self)

    def move_by (self, *args, **kwargs):
        """Move each contained graphic by the given number of pixels.

move_by(dx = 0, dy = 0)

"""
        for g in self:
            g.move_by(*args, **kwargs)


class GraphicsManager (Graphic):
    """Draws things to a surface intelligently.  :class:`Graphic` subclass.

GraphicsManager(scheduler[, sfc], pos = (0, 0), layer = 0, blit_flags = 0)

:arg scheduler: a :class:`sched.Scheduler` instance this manager should use for
                timing.
:arg sfc: the surface to draw to; can be a ``(width, height)`` tuple to create
          a new transparent surface of this size.  If not given or ``None``,
          nothing is drawn.

Other arguments are as taken by :class:`Graphic`.  Since this is a Graphic
subclass, it can be added to other GraphicsManager and supports
transformations.

"""

    def __init__ (self, scheduler, sfc = None, pos = (0, 0), layer = 0,
                  blit_flags = 0):
        #: The ``scheduler`` argument passed to the constructor.
        self.scheduler = scheduler
        self._init_as_graphic = False
        self._init_as_graphic_args = (pos, layer, blit_flags)
        self._surface = None
        self.surface = sfc
        self._overlay = None
        self._fade_id = None
        #: ``{layer: graphics}`` dict, where ``graphics`` is a set of the
        #: graphics in layer ``layer``, each as taken by :meth:`add`.
        self.graphics = {}
        #: A list of layers that contain graphics, lowest first.
        self.layers = []
        self._gm_dirty = []

    @property
    def surface (self):
        """As taken by the constructor.

Set this directly (can be ``None`` to do nothing).

"""
        return self._surface

    @surface.setter
    def surface (self, sfc):
        if sfc is not None and not isinstance(sfc, pg.Surface):
            sfc = pg.Surface(sfc).convert_alpha()
            sfc.fill((0, 0, 0, 0))
        if sfc is not self._surface:
            self._surface = sfc
            if sfc is not None:
                self._rect = sfc.get_rect()
                self.dirty()
                if not self._init_as_graphic:
                    Graphic.__init__(self, sfc, *self._init_as_graphic_args)
                    self._init_as_graphic = True
                    del self._init_as_graphic_args

    @property
    def overlay (self):
        """A :class:`Graphic` which is always drawn on top, or ``None``.

There may only every be one overlay; changing this attribute removes any
previous overlay from the :class:`GraphicsManager`.

"""
        return self._overlay

    @overlay.setter
    def overlay (self, overlay):
        # remove any previous overlay
        if self._overlay is not None:
            self.rm(self._overlay)
        # set now since used in add()
        self._overlay = overlay
        if overlay is not None:
            # remove any current manager
            overlay.manager = None
            # put in the reserved layer None (sorts less than any other object)
            overlay._layer = None
            # add to this manager
            self.add(overlay)

    def add (self, *graphics):
        """Add graphics.

Takes any number of :class:`Graphic` or :class:`GraphicsGroup` instances.

"""
        all_gs = self.graphics
        ls = set(self.layers)
        graphics = list(graphics)
        for g in graphics:
            if isinstance(g, Graphic):
                # add to graphics
                l = g.layer
                if l is None and g is not self._overlay:
                    raise ValueError('a graphic\'s layer must not be None')
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

Takes any number of :class:`Graphic` or :class:`GraphicsGroup` instances.

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
                            self.dirty(g._last_postrot_rect)
                        # remove layer
                        if not all_gs:
                            del all_graphics[l]
                            ls.remove(l)
                # else not added: fail silently
            else: # GraphicsGroup
                graphics.extend(g.contents)
        self.layers = sorted(ls)

    def fade_to (self, colour, t):
        """Fade to a colour.

:arg colour: the ``(R, G, B[, A = 255])`` colour to fade to.
:arg t: how many seconds to take to reach ``colour``.

If already fading, the current colour is used as the initial colour; otherwise,
the initial colour is taken to be ``(R, G, B, 0)`` for the given value of
``colour``.  After fading, the overlay persists; set :attr:`overlay` to
``None`` to remove it.

"""
        colour = list(colour)
        if len(colour) < 4:
            colour.append(255)
        if self._fade_id is None:
            # doesn't already exist
            self.overlay = Colour(colour[:3] + [0], ((0, 0), self._rect.size))
        else:
            self.cancel_fade()
        self._fade_id = self.scheduler.interp_simple(self._overlay, 'colour',
                                                     colour, t,
                                                     round_val = True)

    def cancel_fade (self):
        """Cancel any currently running fade and remove the overlay."""
        if self._fade_id is not None:
            self.scheduler.rm_timeout(self._fade_id)
            self._fade_id = None
            self.overlay = None

    def dirty (self, *rects, **kw):
        """Force redrawing some or all of the screen.

dirty(*rects)

Takes any number of rects to flag as dirty.  If none are given, the whole of
the current surface is flagged.

"""
        if self._surface is None:
            # nothing to mark as dirty (happens in assigning a surface)
            return
        if rects:
            self._gm_dirty += [Rect(r) for r in rects]
        else:
            self._gm_dirty = [self._rect]

    def draw (self):
        """Update the display.

Returns ``True`` if the entire surface changed, or a list of rects that cover
changed parts of the surface, or ``False`` if nothing changed.

"""
        layers = self.layers
        sfc = self._surface
        if not layers or sfc is None:
            return False
        graphics = self.graphics
        dirty = self._gm_dirty
        self._gm_dirty = []
        return fastdraw(layers, sfc, graphics, dirty)

    def _pre_draw (self):
        # set surface to original surface
        ts = self._transforms
        if ts:
            t = ts.items()[0]
            self._surface = t[1][1]
        # draw to it
        drawn = self.draw()
        if drawn:
            # dirty as Graphic (might not happen in retransform)
            dirty = self._dirty
            pos = self._postrot_rect[:2]
            for r in drawn:
                dirty.append(r.move(pos))
            if ts:
                # reapply transforms, starting from the first
                self.retransform(t[0])


class Colour (Graphic):
    """A solid rect of colour (:class:`Graphic` subclass).

Colour(colour, rect, layer = 0, blit_flags = 0)

:arg colour: a Pygame-style ``(R, G, B[, A = 255])`` colour to draw.
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
        Graphic.__init__(self, pg.Surface(rect[2:]), rect[:2], layer,
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

    def _fill (self, sfc, dest, dirty, last_args, colour):
        colour = normalise_colour(colour)
        changed = True
        if last_args is not None:
            # compare colours
            if normalise_colour(last_args[0]) == colour:
                if not dirty:
                    return (dest or sfc, False)
                else:
                    changed = False
        if changed or dirty is True:
            # full fill
            sfc = pg.Surface(sfc.get_size())
            if colour[3] < 255:
                # non-opaque: need to convert to alpha
                sfc = sfc.convert_alpha()
            sfc.fill(colour)
            return (sfc, True)
        else:
            # partial fill
            for r in dirty:
                dest.fill(colour, r)

    def fill (self, colour):
        """Fill with the given colour (like :attr:`colour`)."""
        self.transform('fill', colour)
        self._colour = colour
        return self
