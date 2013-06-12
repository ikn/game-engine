"""Graphics manager for handling drawing things.

---NODOC---

TODO:
 - make it possible for GM to have transparent BG (only if orig_sfc has alpha)
 - make GG force same layer/manager/etc., and allow for transforms and movement of the graphics in the same way
 - in graphics, store n (5?) last # frames between changes to the surface (by transform or altering the original)
    - if the average > x or current length < n, do some things:
        - turn opacity into a list of rects the graphic is opaque in (x = 4?)
        - if a Colour, put into blit mode (also do so if transformed in a certain way) (x = 3?)
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
from util import ir, normalise_colour, has_alpha, blank_sfc, combine_drawn
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
with Pygame rects.  Altering size in any way applies the :meth:`resize`
transformation.

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
        self._must_apply_rot = False
        #: A list of transformations applied to the graphic.  Always contains
        #: the builtin transforms as strings (though they do nothing
        #: by default); other transforms are added through :meth:`transform`,
        #: and are functions.
        self.transforms = list(self._builtin_transforms)
        self._last_transforms = list(self.transforms)
        # {function: (args, previous_surface, resulting_surface, apply_fn,
        #             undo_fn)}
        # last 2 None for non-builtins
        self._transforms = {}
        # {function: (args, previous_size, resulting_size, apply_fn, undo_fn)}
        # last 4 None for non-builtins
        self._queued_transforms = {}
        #: Whether this is opaque in the entire rect; do not change.
        self.opaque = not has_alpha(img)
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
        self._scale_fn = pg.transform.smoothscale
        self._rotate_fn = lambda sfc, angle: \
            pg.transform.rotozoom(sfc, angle * 180 / pi, 1)
        self._rotate_threshold = 2 * pi / 500
        self._orig_dirty = False # where original surface is changed
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
    def orig_sfc (self):
        """The surface before any transforms."""
        return self._orig_sfc

    @orig_sfc.setter
    def orig_sfc (self, sfc):
        if self._orig_sfc.get_size() != sfc.get_size():
            if self.transforms:
                self._undo_transforms(0)
                self._apply_transforms(0, True)
        self._orig_sfc = sfc
        self._orig_dirty = True

    @property
    def surface (self):
        """The (possibly transformed) surface that will be used for drawing.

Accessing this will cause all queued transformations to be applied.

"""
        self.render()
        return self._surface

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
            return Rect((0, 0), self.sz_before_transform('crop'))
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

    @property
    def scale_fn (self):
        """Function to use for scaling.

Defaults to ``pygame.transform.smoothscale`` (and should have the same
signature as this default).

"""
        return self._scale_fn

    @scale_fn.setter
    def scale_fn (self, scale_fn):
        self._scale_fn = scale_fn
        self.retransform('resize')

    @property
    def rotate_fn (self):
        """Function to use for rotating.

Uses ``pygame.transform.rotozoom`` by default.  Takes the surface and angle (as
passed to :meth:`rotate`) and returns the new rotated surface.

"""
        return self._rotate_fn

    @rotate_fn.setter
    def rotate_fn (self, rotate_fn):
        self._rotate_fn = rotate_fn
        self.retransform('rotate')

    @property
    def rotate_threshold (self):
        """Only rotate when the angle changes by this much.

Defaults to ``2 * pi / 500``."""
        return self._rotate_threshold

    @rotate_threshold.setter
    def rotate_threshold (self, rotate_threshold):
        self._rotate_threshold = rotate_threshold
        self.retransform('rotate')

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

    # movement

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

    """Doc for _gen_mods_* methods.

Each builtin transform requires a _gen_mods_<transform> method, as follows:

_gen_mods_<transform>(src_sz, first_time, last_args, *args)
    -> ((apply_fn, undo_fn), dest_sz)

src_sz: size before the transform.
first_time: whether this is the first time these modifiers have been generated.
last_args: transform arguments at the time of the last modifier generation, or
           None.  Guaranteed to be non-None if first_time is False

If first_time is False and the modifiers would not be different from
previously, the return value may be None.

apply_fn, undo_fn: functions that take the Graphic instance and apply or undo
                   modifiers that the transform requires (such as setting
                   transform attributes like angle).
dest_sz: the size after the transform.

"""

    def last_transform_args (self, transform_fn):
        """Return the last (tuple of) arguments passed to the given transform.

This is all arguments passed to the transform when it was last applied/queued.
Takes a transform function as taken by :meth:`transform`.  If it has not been
applied/queued yet, the return value is ``None`` (builtin transformations are
always applied).

"""
        try:
            return self._queued_transforms[transform_fn][0]
        except KeyError:
            try:
                return self._transforms[transform_fn][0]
            except KeyError:
                return None

    def _sfc_before_transform (self, transform_fn):
        """Get queued/applied previous surface (size) for a transform function.

Loops backwards until the transform in question is not an unapplied builtin.
Transform may be an index in transforms.

Returns (sfc, is_size), or (None, None) if the transform doesn't exist.

"""
        t_ks = self.transforms
        if isinstance(transform_fn, int):
            i = transform_fn
            if i < 0 or i >= len(self.transforms):
                return (None, None)
        else:
            try:
                i = self.transforms.index(transform_fn)
            except ValueError:
                return (None, None)
        q = self._queued_transforms
        ts = self._transforms
        while True:
            if i == 0:
                # first transform
                return (self._orig_sfc, False)
            else:
                # use previous transform's final surface
                i -= 1
                fn = t_ks[i]
                if fn in q:
                    if isinstance(fn, basestring):
                        return (q[fn][1], True)
                    # else doesn't store size: continue
                elif fn in ts:
                    return (ts[fn][1], False)
                # else continue

    def sfc_before_transform (self, transform_fn):
        """Return the value of :attr:`surface` before the given transform.

Takes a transform function as taken by :meth:`transform`, or an index in
:attr:`transforms`.  If it has not been applied/queued yet, the return value is
``None`` (builtin transformations are always applied).  Calling this causes all
queued transformations to be applied.

"""
        self.render()
        # now queue is empty, so is_size will be False
        sfc, is_size = self._sfc_before_transform(transform_fn)
        return sfc

    def sz_before_transform (self, transform_fn):
        """Return the value of :attr:`size` before the given transform.

Takes a transform function as taken by :meth:`transform`.  If it has not been
applied/queued yet, the return value is ``None`` (builtin transformations are
always applied).  Unlike :meth:`sfc_before_transform`, calling this does not
apply queued transformations.

"""
        sz, is_size = self._sfc_before_transform(transform_fn)
        if sz is not None and not is_size:
            sz = sz.get_size()
        return sz

    def _undo_transforms (self, transform_fn, include = True):
        """Undo modifiers up to the given transform.

transform_fn may be an index in transforms.

include: whether to undo for the given transform.

"""
        t_ks = self.transforms
        q = self._queued_transforms
        ts = self._transforms
        if isinstance(transform_fn, int):
            i = transform_fn
        else:
            i = t_ks.index(transform_fn)
        if not include:
            i += 1
        for fn in reversed(t_ks[i:]):
            if isinstance(fn, basestring):
                if fn in q:
                    q[fn][4](self)
                elif fn in ts:
                    ts[fn][4](self)
                # else non-applied builtin
            # else non-builtin: nothing to undo

    def _apply_transforms (self, transform_fn, regen, include = True):
        """Apply modifiers from the given transforms.

transform_fn may be an index in transforms.

regen: whether to force regeneration of transform modifiers.
include: whether to apply for the given transform.

"""
        t_ks = self.transforms
        q = self._queued_transforms
        ts = self._transforms
        if isinstance(transform_fn, int):
            i = transform_fn
        else:
            i = t_ks.index(transform_fn)
        if not include:
            i += 1
        src_sz = self.sz_before_transform(i)
        for fn in t_ks[i:]:
            if isinstance(fn, basestring):
                if fn in q:
                    pool = q
                elif fn in ts:
                    pool = ts
                else:
                    # non-applied builtin
                    continue
                args, src, dest, apply_fn, undo_fn = pool[fn]
                if regen:
                    gen_mods = getattr(self, '_gen_mods_' + fn)
                    mods, dest_sz = gen_mods(src_sz, False, args, *args)
                    if mods is not None:
                        apply_fn, undo_fn = mods
                elif pool == q:
                    dest_sz = dest
                else:
                    dest_sz = dest.get_size()
                apply_fn(self)
                # update in transform store
                if pool == q:
                    src = src_sz
                    dest = dest_sz
                pool[fn] = (args, src, dest, apply_fn, undo_fn)
                src_sz = dest_sz
            # else non-builtin: nothing to apply

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

Calls ``transform_fn(src, dest, dirty, last_args, *args)`` to apply the
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
- partial transform: return ``(dest, new_dirty)`` (``dirty`` might also be
  ``False`` here).
- do nothing: return ``(src, dirty)``.

If creating and returning a new surface, it should already be converted for
blitting.

"""
        # add to/reorder transforms list, and queue for transforming later
        t_ks = self.transforms
        q = self._queued_transforms
        ts = self._transforms
        exists = True
        try:
            last_index = t_ks.index(transform_fn)
        except ValueError:
            exists = False
        else:
            if transform_fn in q:
                data = q[transform_fn]
                self.untransform(transform_fn)
            elif transform_fn in ts:
                data = ts[transform_fn]
                self.untransform(transform_fn)
            else:
                exists = False
            if transform_fn in t_ks:
                # has to be a builtin: untransform won't remove it
                t_ks.pop(last_index)
        # determine index
        i = kwargs.get('position')
        if i is None:
            fn = kwargs.get('before')
            if fn is not None:
                try:
                    i = t_ks.index(fn)
                except ValueError:
                    pass
            else:
                fn = kwargs.get('after')
                try:
                    i = t_ks.index(fn) + 1
                except ValueError:
                    pass
        if i is None:
            i = last_index if last_index is not None else len(t_ks)
        # generate modifiers
        builtin = isinstance(transform_fn, basestring)
        if builtin:
            src_sz = self.sz_before_transform(i)
            gen_mods = getattr(self, '_gen_mods_' + transform_fn)
            mods, dest_sz = gen_mods(src_sz, not exists,
                                     data[0] if exists else None, *args)
            if mods is None:
                # retrieve from queue/transforms
                apply_fn = data[3]
                undo_fn = data[4]
            else:
                apply_fn, undo_fn = mods
        else:
            src_sz = dest_sz = apply_fn = undo_fn = None
        # add the transform
        q[transform_fn] = (args, src_sz, dest_sz, apply_fn, undo_fn)
        if i == len(t_ks):
            t_ks.append(transform_fn)
            if builtin:
                # apply modifier
                apply_fn(self)
        else:
            if builtin:
                # undo modifiers up to insertion point
                self._undo_transforms(i)
            t_ks.insert(i, transform_fn)
            if builtin:
                # apply modifier, then reapply following modifiers
                apply_fn(self)
                self._apply_transforms(i, src_sz != dest_sz, False)
        return self

    def retransform (self, transform_fn):
        """Reapply the given transformation (if already applied).

Takes a transformation function like :meth:`transform` and returns self.

"""
        try:
            args, src, dest, apply_fn, undo_fn = self._transforms[transform_fn]
        except KeyError:
            # either doesn't exist or already queued
            pass
        else:
            # no need to regenerate modifiers - nothing changed
            if isinstance(transform, basestring):
                self._queued_transforms[transform_fn] = \
                    (args, src.get_size(), dest.get_size(), apply_fn, undo_fn)
            else:
                self._queued_transforms[transform_fn] = \
                    (args, None, None, None, None)
        return self

    def untransform (self, transform_fn):
        """Remove an applied transformation.

Takes a transformation function like :meth:`transform` and returns self.

"""
        t_ks = self.transforms
        ts = self._transforms
        q = self._queued_transforms
        if transform_fn not in ts and transform_fn not in q:
            return
        if isinstance(transform_fn, basestring):
            # no need to handle mods if not builtin, since then _gen_mods args
            # don't change for any builtins
            self._undo_transforms(transform_fn)
            if transform_fn in q:
                src_sz, dest_sz = q[transform_fn][1:3]
            else:
                src_sz, dest_sz = ts[transform_fn][1:3]
            self._apply_transforms(transform_fn, src_sz != dest_sz, False)
        else:
            # don't remove builtins from transforms list
            self.transforms.remove(transform_fn)
        # remove data
        if transform_fn in ts:
            del ts[transform_fn]
        if transform_fn in q:
            del q[transform_fn]
        return self

    def reload (self):
        """Reload from disk if possible.

If successful, all transformations are reapplied afterwards, if any.

"""
        if self.fn is not None:
            # this calls a setter
            self.orig_sfc = conf.GAME.img(self.fn, cache = False)

    def _gen_mods_resize (self, src_sz, first_time, last_args, w, h,
                          about = (0, 0)):
        # mods are size-dependent, so they always change
        ax, ay = about
        scale = (float(w) / src_sz[0], float(h) / src_sz[1])
        ox = ir((1 - scale[0]) * ax)
        oy = ir((1 - scale[1]) * ay)

        def apply_fn (g):
            g._scale = scale
            x, y, gw, gh = g._rect
            g._rect = Rect(x + ox, y + oy, gw, gh)

        def undo_fn (g):
            g._scale = (1, 1)
            x, y, gw, gh = g._rect
            g._rect = Rect(x - ox, y - oy, gw, gh)

        return ((apply_fn, undo_fn), (w, h))

    def _resize (self, src, dest, dirty, last_args, w, h, about):
        start_w, start_h = src.get_size()
        if w is None:
            w = start_w
        if h is None:
            h = start_h
        ax, ay = about
        if w == start_w and h == start_h:
            # transform does nothing
            return (src, dirty)
        if not dirty and last_args is not None:
            last_w, last_h, (last_ax, last_ay) = last
            if w == last_w and h == last_h and ax == last_ax and ay == last_ay:
                # same as last time
                return (dest, False)
        # full transform
        return (self.scale_fn(src, (w, h)), True)

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
        ow, oh = self.sz_before_transform('resize')
        return self.resize(ir(w * ow), ir(h * oh), about)

    def resize_both (self, w = None, h = None, about = (0, 0)):
        """Resize with constant aspect ratio.

resize_both([w][, h], about = (0, 0)) -> self

:arg w, h: the new width/height; pass only one of these.
:arg about: the ``(x, y)`` position relative to the top-left of the graphic to
            scale about.

"""
        ow, oh = self.sz_before_transform('resize')
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

    def _gen_mods_crop (self, src_sz, first_time, last_args, rect):
        rect = Rect(rect)
        if first_time or Rect(last_args[0]) != rect:

            def apply_fn (g):
                g._rect = g._rect.move(rect.x, rect.y)
                g._cropped_rect = rect

            def undo_fn (g):
                g._rect = g._rect.move(-rect.x, -rect.y)
                g._cropped_rect = None

            mods = (apply_fn, undo_fn)
        else:
            mods = None
        return (mods, rect.size)

    def _crop (self, src, dest, dirty, last_args, rect):
        start = src.get_rect()
        rect = Rect(rect)
        if start == rect:
            # no cropping occurs
            return (src, dirty)
        if dirty is not True and last_args is not None:
            last = Rect(last_args[0])
            if last == rect:
                # same size as last time
                if dirty:
                    # clip dirty rects inside cropped rect; if there's a
                    # border, it remains empty as before, so isn't dirtied
                    new_dirty = []
                    for r in dirty:
                        r = r.clip(rect)
                        if r:
                            new_dirty.append(r)
                    return (dest, new_dirty)
                else:
                    return (dest, False)
        # do a full transform
        if start.contains(rect) and not has_alpha(src):
            new_sfc = pg.Surface(rect.size).convert()
        else:
            # not (no longer) opaque
            new_sfc = blank_sfc(rect.size)
        new_sfc.blit(src, ((0, 0), rect.size), rect)
        return (new_sfc, True)

    def crop (self, rect):
        """Crop the surface to the given rect.

crop(rect) -> self

``rect`` need not be contained in the current surface rect.

"""
        return self.transform('crop', Rect(rect))

    def _gen_mods_flip (self, src_sz, first_time, last_args, x, y):
        if first_time or last_args != (x, y):

            def apply_fn (g):
                g._flipped = (x, y)

            def undo_fn (g):
                g._flipped = (False, False)

            mods = (apply_fn, undo_fn)
        else:
            mods = None
        return (mods, src_sz)

    def _flip (self, src, dest, dirty, last_args, x, y):
        if not x and not y:
            return (src, dirty)
        if dirty is not True and last_args is not None and last_args == (x, y):
            if dirty:
                # check if a partial transform would be quicker
                w, h = src.get_rect().size
                alpha = has_alpha(src)
                k = 5 if alpha else 3.5
                if k * sum(r.w * r.h for r in dirty) ** .75 < w * h ** .75:
                    # it would (this is all empirical and quite rough)
                    new_dirty = []
                    flip = pg.transform.flip
                    for r in dirty:
                        # copy this rect to a new surface
                        sfc = pg.Surface(r.size)
                        if alpha:
                            sfc = sfc.convert_alpha()
                        sfc.blit(src, (0, 0), r)
                        # transform the rect
                        r = Rect((w - r.x if x else r.x,
                                  h - r.y if y else r.y), r.size)
                        new_dirty.append(r)
                        # flip and blit to destination
                        dest.blit(flip(sfc, x, y), r)
                    return (dest, new_dirty)
            else:
                return (dest, False)
        # do a full transform
        new_sfc = pg.transform.flip(src, x, y)
        return (new_sfc, True)

    def flip (self, x = False, y = False):
        """Flip the graphic over either axis.

flip(x = False, y = False) -> self

:arg x: whether to flip over the x-axis.
:arg y: whether to flip over the y-axis.

"""
        return self.transform('flip', bool(x), bool(y))

    def _gen_mods_rotate (self, src_sz, first_time, last_args, angle, about):
        # - dest_sz will never get used: all following transforms are
        #   guaranteed to be non-builtins, if the user does nothing silly
        # - mods are size-dependent, so they always change
        # - computation of rot_offset happens at draw time, since it's only
        #   needed then, and only internally

        def apply_fn (g):
            g._angle = angle
            g._must_apply_rot = True

        def undo_fn (g):
            g._angle = 0
            g._rot_offset = (0, 0)
            g._must_apply_rot = False

        return ((apply_fn, undo_fn), src_sz)

    def _rotate (self, src, dest, dirty, last_args, angle, about):
        if abs(angle) < self.rotate_threshold:
            # transform does nothing
            return (src, dirty)
        w, h = src.get_size()
        cx, cy = w / 2., h / 2.
        ax, ay = (cx, cy) if about is None else about
        if not dirty and last_args is not None:
            last_angle, last_about = last_args
            # if last_angle == angle, then surface size didn't change, so
            # neither did the centre point
            last_ax, last_ay = (cx, cy) if last_about is None else last_about
            if abs(angle - last_angle) < self.rotate_threshold and \
            (ax, ay) == (last_ax, last_ay):
                # no change to result
                return (dest, False)
        # do a full transform
        # if not already alpha and we might end up with borders, convert to
        # alpha
        if angle % (pi / 2) != 0 and not has_alpha(src):
            src = src.convert_alpha()
        new_sfc = self.rotate_fn(src, angle)
        return (new_sfc, True)

    def rotate (self, angle, about = None):
        """Rotate the graphic.

rotate(angle[, about]) -> self

:arg angle: the angle in radians to rotate to, anti-clockwise from the original
            graphic.
:arg about: the ``(x, y)`` position relative to the top-left of the graphic to
            rotate about; defaults to the graphic's centre.

"""
        return self.transform('rotate', angle, about)

    # drawing

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

    def dirty (self, *rects):
        """Mark some or all of the graphic as changed.

This is to be used when you alter the original surface (:attr:`orig_sfc`) - do
not alter any other (transformed) surfaces.  Takes any number of rects to flag
as dirty.  If none are given, the whole of the graphic is flagged.

"""
        if not rects:
            rects = True
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
        self._orig_dirty = False
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
                sfc = ts[fn][2]
                if not passed_rot:
                    before_rot = sfc
                    if fn == 'rotate':
                        passed_rot = True
            if j < i:
                continue
            if fn in ts:
                # done this transform before
                last_args, src, dest, apply_fn, undo_fn = ts[fn]
            else:
                last_args = dest = None
            if fn in q:
                # got new args
                args, src_sz, dest_sz, apply_fn, undo_fn = q[fn]
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
                # have modifier functions following code above
                ts[fn] = (args, sfc, new_sfc, apply_fn, undo_fn)
            sfc = new_sfc
        if len(last_t_ks) > len(t_ks):
            # might have just removed transforms from the end
            dirty = True

        self._last_transforms = list(t_ks)
        if self._must_apply_rot:
            self._must_apply_rot = False
            # compute draw offset due to rotation
            angle, about = ts['rotate'][0]
            w_orig, h_orig = before_rot.get_size()
            cx, cy = w_orig / 2., h_orig / 2.
            w, h = sfc.get_size()
            ax, ay = (cx, cy) if about is None else about
            # v = c - about
            vx = cx - ax
            vy = cy - ay
            # c_new - about_new = v.rotate(angle)
            s = sin(angle)
            c = cos(angle)
            ax_new = w / 2. - (c * vx + s * vy)
            ay_new = h / 2. - (-s * vx + c * vy)
            # about = offset + about_new
            self._rot_offset = (ir(ax - ax_new), ir(ay - ay_new))
        if dirty:
            self._dirty = combine_drawn(self._dirty, dirty)
            # change current surface and rect
            self._surface = sfc
            self.opaque = not has_alpha(sfc)
            self._rect = r = Rect(self._rect.topleft, before_rot.get_size())
            self._postrot_rect = pr = r.move(self._rot_offset)
            pr.size = sfc.get_size()

    def _pre_draw (self):
        """Called by GraphicsManager before drawing."""
        self.render()
        dirty = self._dirty
        if self._rect != self.last_rect:
            dirty = True
            self._postrot_rect = Rect(
                self._rect.move(self._rot_offset).topleft, 
                self._postrot_rect.size
            )
        if self.blit_flags != self._last_blit_flags:
            dirty = True
            self._last_blit_flags = self.blit_flags
        # fastdraw needs dirty to be a list
        if dirty:
            pr = self._postrot_rect
            if dirty is True:
                dirty = [self._last_postrot_rect, pr]
            else:
                # translate dirty rects
                pr = pr.topleft
                dirty = [d_r.move(pr) for d_r in dirty]
        else:
            dirty = []
        self._dirty = dirty

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
          nothing is drawn.  This becomes :attr:`orig_sfc` and can be changed
          using this attribute.

Other arguments are as taken by :class:`Graphic`.  Since this is a
:class:`Graphic` subclass, it can be added to other :class:`GraphicsManager`
instances and supports transformations.  None of this can be done until the
manager has a surface, however, and transformations are only applied in
:attr:`Graphic.surface`, not in :attr:`orig_sfc`.

"""

    def __init__ (self, scheduler, sfc = None, pos = (0, 0), layer = 0,
                  blit_flags = 0):
        #: The ``scheduler`` argument passed to the constructor.
        self.scheduler = scheduler
        self._init_as_graphic = False
        self._init_as_graphic_args = (pos, layer, blit_flags)
        self._orig_sfc = None
        self.orig_sfc = sfc # calls setter
        self._gm_dirty = False
        self._overlay = None
        self._fade_id = None
        #: ``{layer: graphics}`` dict, where ``graphics`` is a set of the
        #: graphics in layer ``layer``, each as taken by :meth:`add`.
        self.graphics = {}
        #: A list of layers that contain graphics, lowest first.
        self.layers = []

    @property
    def orig_sfc (self):
        """Like :attr:`Graphic.orig_sfc`.

This is the ``sfc`` argument passed to the constructor.  Retrieving this causes
all graphics to be drawn/updated first.

"""
        self.draw()
        return Graphic.orig_sfc.fget()

    @orig_sfc.setter
    def orig_sfc (self, sfc):
        if sfc is not None and not isinstance(sfc, pg.Surface):
            sfc = blank_sfc(sfc)
        if sfc is not self._orig_sfc:
            self._orig_sfc = sfc
            if sfc is not None:
                if self._init_as_graphic:
                    Graphic.orig_sfc.fset(sfc)
                else:
                    Graphic.__init__(self, sfc, *self._init_as_graphic_args)
                    self._init_as_graphic = True
                    del self._init_as_graphic_args

    @property
    def orig_sz (self):
        """The size of the surface before any transforms."""
        return self._orig_sfc.get_size()

    @property
    def overlay (self):
        """A :class:`Graphic` which is always drawn on top, or ``None``.

There may only ever be one overlay; changing this attribute removes any
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
            else: # GraphicsGroup: add to queue
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

    def dirty (self, *rects):
        """:meth:`Graphic.dirty`"""
        if self._surface is None:
            # nothing to mark as dirty
            return
        if not rects:
            rects = True
        self._gm_dirty = combine_drawn(self._gm_dirty, rects)

    def draw (self, handle_dirty = True):
        """Update the display (:attr:`orig_sfc`).

:arg handle_dirty: whether to propagate changed areas to the transformation
                   pipeline implemented by :class:`Graphic`.  Pass ``False`` if
                   you don't intend to use this manager as a graphic.

Returns ``True`` if the entire surface changed, or a list of rects that cover
changed parts of the surface, or ``False`` if nothing changed.

"""
        layers = self.layers
        sfc = self._orig_sfc
        if not layers or sfc is None:
            return False
        graphics = self.graphics
        dirty = self._gm_dirty
        self._gm_dirty = []
        if dirty is True:
            dirty = [sfc.get_rect()]
        elif dirty is False:
            dirty = []
        dirty = fastdraw(layers, sfc, graphics, dirty)
        if dirty and handle_dirty:
            Graphic.dirty(self, *dirty)
        return dirty

    def render (self):
        """:meth:`Graphic.render`"""
        self.draw()
        Graphic.render(self)


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
