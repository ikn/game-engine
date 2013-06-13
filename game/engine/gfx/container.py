"""Graphics containers: :class:`GraphicsGroup` and :class:`GraphicsManager`."""

import sys

import pygame as pg

from ..util import blank_sfc, combine_drawn
try:
    from _gm import fastdraw
except ImportError:
    print >> sys.stderr, 'error: couldn\'t import _gm; did you remember to `make\'?'
    sys.exit(1)
from .graphic import Graphic


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
