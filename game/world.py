"""A world base class (World).

Would be in game, if importing from there were easy.

"""

import gm


class World (object):
    """A world base class; to be subclassed.

    CONSTRUCTOR

World(scheduler, evthandler)

scheduler: the sched.Scheduler instance this world should use for timing.
evthandler: the evthandler.EventHandler instance this world should use for
            input.

    METHODS

select
update
draw

    ATTRIBUTES

scheduler, evthandler: as taken by the constructor.
graphics: a gm.GraphicsManager instance used for drawing by default.

"""

    def __init__ (self, scheduler, evthandler):
        self.scheduler = scheduler
        self.evthandler = evthandler
        self.graphics = gm.GraphicsManager()

    def select (self):
        """Called when this becomes the active world."""
        pass

    def update (self):
        """Called every frame to makes any necessary changes."""
        pass

    def draw (self):
        """Draw to the screen.

Returns a flag indicating what changes were made: True if the whole display
needs to be updated, something falsy if nothing needs to be updated, else a
list of rects to update the display in.

This should not change the state of the world, because it is not guaranteed to
be called every frame.

"""
        return self.graphics.draw()
