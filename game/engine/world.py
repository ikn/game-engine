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

init
select
pause
update
draw

    ATTRIBUTES

scheduler, evthandler: as taken by the constructor.
graphics: a gm.GraphicsManager instance used for drawing by default.

"""

    #: A unique identifier used for some settings in :obj:`conf`; if ``None``,
    #: ``type(world).__name__.lower()`` will be used.
    id = None

    def __init__ (self, scheduler, evthandler):
        self.scheduler = scheduler
        self.evthandler = evthandler
        self.graphics = gm.GraphicsManager()
        self._initialised = False

    def _select (self):
        if not self._initialised:
            self.init()
            self._initialised = True
        self.select()

    def init (self):
        """Called when this first becomes the active world."""
        pass

    def select (self):
        """Called whenever this becomes the active world."""
        pass

    def pause (self):
        """Called to pause the game when the window loses focus."""
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
