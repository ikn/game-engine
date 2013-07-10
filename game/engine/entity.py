"""Entities: things that exist in the world."""

from .gfx import GraphicsGroup
from .util import ir


class Entity (object):
    """A thing that exists in the world.

Entity(x=0, y=0)

Arguments determine the entity's position (:attr:`pos`), as for
:class:`GraphicsGroup <engine.gfx.container.GraphicsGroup>` (unlike for
graphics, this may be floating-point).

Currently, an entity is just a container of graphics.

"""

    def __init__ (self, x=0, y=0):
        #: The :class:`World <engine.game.World>` this entity is in.  This is
        #: set by the world when the entity is added or removed.
        self.world = None
        #: :class:`GraphicsGroup <engine.gfx.container.GraphicsGroup>`
        #: containing the entity's graphics.
        self.graphics = GraphicsGroup(x, y)
