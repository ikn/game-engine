"""Entities: things that exist in the world."""

from .gfx import GraphicsGroup
from .util import ir


class Entity (object):
    """A thing that exists in the world.

Entity(x=0, y=0)

Arguments are passed to
:class:`GraphicsGroup <engine.gfx.container.GraphicsGroup>` when creating
:attr:`graphics`.

Currently, an entity is just a container of graphics.

"""

    def __init__ (self, x=0, y=0):
        #: The :class:`World <engine.game.World>` this entity is in.  This is
        #: set by the world when the entity is added or removed.
        self.world = None
        #: :class:`GraphicsGroup <engine.gfx.container.GraphicsGroup>`
        #: containing the entity's graphics.
        self.graphics = GraphicsGroup(x, y)

    def added (self):
        """Called whenever the entity is added to a world.

This is called after :attr:`world` has been changed to the new world.

"""
        pass

    def update (self):
        """Called every frame to makes any necessary changes."""
        pass
