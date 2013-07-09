"""World entities: multi-graphic positioning."""

# TODO:
# - .graphics a GraphicsGroup, so user adds graphics directly to that, it handles relative positions, can set layer for all, etc.
#   - in fact, all of the entity implementation as it stands (except .world) should be the new GraphicsGroup

from .gfx.graphic import GraphicView
from .util import ir


class Entity (object):
    """A thing that exists in the world.

Entity(x=0, y=0)

Arguments determine the entity's position (:attr:`pos`); unlike for graphics,
this may be floating-point.

Currently, an entity is just a container of graphics.

"""

    def __init__ (self, x=0, y=0):
        self._pos = [x, y]
        #: The :class:`World <engine.game.World>` this entity is in.  This is
        #: set by the world when the entity is added or removed.
        self.world = None
        #: ``{graphic: rel}``, where ``graphic`` is a
        #: :class:`GraphicView <engine.gfx.graphic.GraphicView>` instance and
        #: ``rel`` is the graphic's ``(x, y)`` position relative to this
        #: entity.
        self.graphics = {}
        self._gm = None

    @property
    def x (self):
        """``x`` co-ordinate of the entity's top-left corner."""
        return self._pos[0]

    @x.setter
    def x (self, x):
        self.pos = (x, self._pos[1])

    @property
    def y (self):
        """``y`` co-ordinate of the entity's top-left corner."""
        return self._pos[1]

    @x.setter
    def y (self, y):
        self.pos = (self._pos[0], y)

    @property
    def pos (self):
        """``[``:attr:`x` ``,`` :attr:`y` ``]``."""
        return self._pos

    @pos.setter
    def pos (self, pos):
        x, y = pos
        self._pos = [x, y]
        # move graphics
        x = ir(x)
        y = ir(y)
        for g, (rel_x, rel_y) in self.graphics.iteritems():
            # rel_{x,y} are ints
            g.pos = (x + rel_x, y + rel_y)

    def move_by (self, dx = 0, dy = 0):
        """Move by the given number of pixels."""
        self.pos = (self._pos[0] + dx, self._pos[1] + dy)

    def add (self, graphic, dx=0, dy=0):
        """Add a graphic.

add(graphic, x=0, y=0) -> graphic_view

:arg graphic: :class:`Graphic <engine.gfx.graphic.Graphic>` or
              :class:`GraphicView <engine.gfx.graphic.GraphicView>` to add.
:arg dx: ``x`` co-ordinate relative to the entity.
:arg dy: ``y`` co-ordinate relative to the entity.

:return: a created :class:`GraphicView <engine.gfx.graphic.GraphicView>` that
         points to ``graphic``.

If the ``graphic`` argument was previously returned by this function, its
relative position is changed.

"""
        if graphic not in self.graphics:
            # new graphic: create wrapper and add to graphics manager
            if isinstance(graphic, GraphicView):
                graphic = graphic.graphic
            graphic = GraphicView(graphic)
            if self._gm is not None:
                self._gm.add(graphic)
        # else already in graphics, in which case we still want to change its
        # relative position
        self.graphics[graphic] = rel = (ir(dx), ir(dy))
        graphic.pos = (ir(self._pos[0]) + rel[0], ir(self._pos[1]) + rel[1])
        return graphic

    def rm (self, *graphics):
        """Remove a graphic previously added using :meth:`add`.

Raises ``KeyError`` for missing graphics.

"""
        gm = self._gm
        for g in graphics:
            del self.graphics[g]
            if gm is not None:
                gm.rm(g)

    @property
    def gm (self):
        """The :class:`GraphicsManager <engine.gfx.container.GraphicsManager>`
to put graphics in."""
        return self._gm

    @gm.setter
    def gm (self, gm):
        if gm is self._gm:
            return
        if self._gm is not None:
            self._gm.rm(*self.graphics)
        if gm is not None:
            gm.add(*self.graphics)
        self._gm = gm
