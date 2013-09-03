"""Main loop and world handling.

Only one :class:`Game` instance should ever exist, and it stores itself in
:data:`conf.GAME`.  Start the game with :func:`run` and use the :class:`Game`
instance for changing worlds, handling the display and playing audio.

"""

import os
from random import choice, randrange

import pygame as pg
from pygame.display import update as update_display

from .conf import conf
from .sched import Scheduler
from . import evt, gfx, res, text
from .util import ir, convert_sfc


def run (*args, **kwargs):
    """Run the game.

Takes the same arguments as :class:`Game`, with an optional keyword-only
argument ``t`` to run for this many seconds.

"""
    t = kwargs.pop('t', None)
    global restarting
    restarting = True
    while restarting:
        restarting = False
        Game(*args, **kwargs).run(t)


class _ClassProperty (property):
    """Decorator to create a static property."""

    def __get__(self, cls, owner):
        return self.fget.__get__(None, owner)()


class World (object):
    """A world base class; to be subclassed.

World(scheduler, evthandler)

:arg scheduler: the :class:`sched.Scheduler <engine.sched.Scheduler>` instance
                this world should use for timing.
:arg evthandler: the
                 :class:`evt.EventHandler <engine.evt.handler.EventHandler>`
                 instance this world should use for input.  Event names
                 prefixed with ``_game`` are reserved.
:arg resources: the :class:`res.ResourceManager <engine.res.ResourceManager>`
                instance this world should use for loading resources.

.. attribute:: id

   A unique identifier used for some settings in :mod:`conf`.

   This is a class property---it is independent of the instance.

   A subclass may define an ``_id`` class attribute (not instance attribute).
   If so, that is returned; if not, ``world_class.__name__.lower()`` is
   returned.

"""

    def __init__ (self, scheduler, evthandler, resources, *args, **kwargs):
        #: :class:`sched.Scheduler <engine.sched.Scheduler>` instance taken by
        #: the constructor.
        self.scheduler = scheduler
        #: :class:`evt.EventHandler <engine.evt.handler.EventHandler>` instance
        #: taken by the constructor.
        self.evthandler = evthandler
        #: :class:`gfx.GraphicsManager <engine.gfx.container.GraphicsManager>`
        #: instance used for drawing by default.
        self.graphics = gfx.GraphicsManager(scheduler)
        #: :class:`res.ResourceManager <engine.res.ResourceManager>` instance
        #: taken by the constructor.
        self.resources = resources
        #: ``set`` of :class:`Entity <engine.entity.Entity>` instances in this
        #: world.
        self.entities = set()

        self._initialised = False
        self._extra_args = (args, kwargs)
        self._avg_draw_time = scheduler.frame
        self._since_last_draw = 0

    @_ClassProperty
    @classmethod
    def id (cls):
        # doc is in the class(!)
        if hasattr(cls, '_id'):
            return cls._id
        else:
            return cls.__name__.lower()

    @property
    def fps (self):
        """The current draw rate, an average based on
:data:`conf.FPS_AVERAGE_RATIO`.

If this is less than :data:`conf.FPS`, then we're dropping frames.

For the current update FPS, use the
:attr:`Timer.current_fps <engine.sched.Timer.current_fps>` of
:attr:`scheduler`.  (If this indicates the scheduler isn't running at full
speed, it may mean the draw rate (:attr:`fps`) is dropping to
:data:`conf.MIN_FPS`.)

"""
        return 1 / self._avg_draw_time

    def init (self):
        """Called when this first becomes the active world.

This receives the extra arguments passed in constructing the world through the
:class:`Game` instance.

"""
        pass

    def select (self):
        """Called whenever this becomes the active world."""
        pass

    def _select (self):
        """Called by the game when becomes the active world."""
        if not self._initialised:
            self.init(*self._extra_args[0], **self._extra_args[1])
            self._initialised = True
            del self._extra_args
        self.evthandler.normalise_buttons()
        self.select()

    def quit (self):
        """Called when this is removed from the currently running worlds.

Called before removal---when the :attr:`Game.world` is still this world.

"""
        pass

    def add (self, *entities):
        """Add any number of :class:`Entity <engine.entity.Entity>` instances
to the world.

An entity may be in only one world at a time.  If a given entity is already in
another world, it is removed from that world.

Each entity passed may also be a sequence of entities to add.

"""
        entities = list(entities)
        all_entities = self.entities
        for e in entities:
            if hasattr(e, '__len__') and hasattr(e, '__getitem__'):
                entities.extend(e)
            else:
                all_entities.add(e)
                if e.world is not None:
                    e.world.rm(e)
                elif e.graphics.manager is not None:
                    # has no world, so manager was explicitly set, so don't
                    # change it
                    pass
                else:
                    e.graphics.manager = self.graphics
                e.world = self
                e.added()

    def rm (self, *entities):
        """Remove any number of entities from the world.

Missing entities are ignored.

Each entity passed may also be a sequence of entities to remove.

"""
        entities = list(entities)
        all_entities = self.entities
        for e in entities:
            if hasattr(e, '__len__') and hasattr(e, '__getitem__'):
                entities.extend(e)
            else:
                if e in all_entities:
                    all_entities.remove(e)
                e.world = None
                # unset gm even if it's not this world's main manager
                e.graphics.manager = None

    def use_pools (self, *pools):
        """Tell the resource manager that this world is using the given pools.

This means the resources in the pool will not be removed from cache until this
world drops the pool.

"""
        for pool in pools:
            self.resources.use(pool, self)

    def drop_pools (self, *pools):
        """Stop using the given pools of the resource manager."""
        for pool in pools:
            self.resources.drop(pool, self)

    def update (self):
        """Called every frame to makes any necessary changes."""
        pass

    def _update (self):
        """Called by the game to update."""
        for e in self.entities:
            e.update()
        self.update()

    def _handle_slowdown (self):
        """Return whether to draw this frame."""
        s = self.scheduler
        elapsed = s.elapsed
        if elapsed is None:
            # haven't completed a frame yet
            return True
        frame_t = s.current_frame_time
        target_t = s.frame
        # compute rolling frame average for drawing, but don't store it just
        # yet
        r = conf.FPS_AVERAGE_RATIO
        draw_t = ((1 - r) * self._avg_draw_time +
                  r * (self._since_last_draw + elapsed))

        if frame_t <= target_t or abs(frame_t - target_t) / target_t < .1:
            # running at (near enough (within 1% of)) full speed, so draw
            draw = True
        else:
            if draw_t >= 1. / conf.MIN_FPS[self.id]:
                # not drawing would make the draw FPS too low, so draw anyway
                draw = True
            else:
                draw = False
        draw |= not conf.DROP_FRAMES
        if draw:
            # update rolling draw frame average
            self._avg_draw_time = draw_t
            self._since_last_draw = 0
        else:
            # remember frame time for when we next draw
            self._since_last_draw += elapsed
        return draw

    def pause (self):
        """Called to pause the game when the window loses focus."""
        pass

    def draw (self):
        """Draw to the screen.

:return: a flag indicating what changes were made: ``True`` if the whole
         display needs to be updated, something falsy if nothing needs to be
         updated, else a list of rects to update the display in.

This method should not change the state of the world, because it is not
guaranteed to be called every frame.

"""
        dirty = self.graphics.draw(False)
        return dirty


class Game (object):
    """Handles worlds.

Takes the same arguments as :meth:`create_world` and passes them to it.

"""

    def __init__ (self, *args, **kwargs):
        conf.GAME = self
        conf.RES_F = pg.display.list_modes()[0]
        self._quit = False
        self._update_again = False
        #: The currently running world.
        self.world = None
        #: A list of previous (nested) worlds, most 'recent' last.
        self.worlds = []

        # load display settings
        #: The main Pygame surface.
        self.screen = None
        self.refresh_display()
        #: :class:`res.ResourceManager <engine.res.ResourceManager>` instance
        #: used for caching resources.
        self.resources = res.ResourceManager()
        self.resources.use(conf.DEFAULT_RESOURCE_POOL, self)
        self._using_pool = conf.DEFAULT_RESOURCE_POOL
        #: ``{name: renderer}`` dict of
        #: :class:`text.TextRenderer <engine.text.TextRenderer>` instances
        #: available for referral by name in the ``'text'`` resource loader.
        self.text_renderers = {}

        self._init_cbs()
        # start first world
        self.start_world(*args, **kwargs)
        # start playing music
        pg.mixer.music.set_endevent(conf.EVENT_ENDMUSIC)
        #: Filenames for known music.
        self.music = []
        self.find_music()
        self.play_music()
        if not conf.MUSIC_AUTOPLAY:
            pg.mixer.music.pause()

    def _init_cbs (self):
        # set up settings callbacks
        conf.on_change('DEFAULT_RESOURCE_POOL', self._change_resource_pool,
                       source=self)
        conf.on_change('FULLSCREEN', self.refresh_display,
                       lambda: conf.RESIZABLE, source=self)

        def change_res_w ():
            if not conf.FULLSCREEN:
                self.refresh_display()

        conf.on_change('RES_W', change_res_w, source=self)

        def change_res_f ():
            if conf.FULLSCREEN:
                self.refresh_display()

        conf.on_change('RES_F', change_res_f, source=self)

    # world handling

    def create_world (self, cls, *args, **kwargs):
        """Create a world.

create_world(cls, *args, **kwargs) -> world

:arg cls: the world class to instantiate; must be a :class:`World` subclass.
:arg args: positional arguments to pass to the constructor.
:arg kwargs: keyword arguments to pass to the constructor.

:return: the created world.

A world is constructed by::

    cls(scheduler, evthandler, *args, **kwargs)

where ``scheduler`` and ``evthandler`` are as taken by :class:`World` (and
should be passed to that base class).

"""
        scheduler = Scheduler()
        scheduler.add_timeout(self._update, frames=1)
        eh = evt.EventHandler(scheduler)
        eh.add(
            (pg.QUIT, self.quit),
            (pg.ACTIVEEVENT, self._active_cb),
            (pg.VIDEORESIZE, self._resize_cb),
            (conf.EVENT_ENDMUSIC, self.play_music)
        )
        eh.load_s(conf.GAME_EVENTS)
        eh['_game_quit'].cb(self.quit)
        eh['_game_minimise'].cb(self.minimise)
        eh['_game_fullscreen'].cb(self._toggle_fullscreen)
        # instantiate class
        world = cls(scheduler, eh, self.resources, *args, **kwargs)
        scheduler.fps = conf.FPS[world.id]
        return world

    def _select_world (self, world):
        """Set the given world as the current world."""
        if self.world is not None:
            self._update_again = True
            self.world.scheduler.stop()
        self.world = world
        world.graphics.orig_sfc = self.screen
        world.graphics.dirty()
        ident = world.id
        # set some per-world things
        for name, r in conf.TEXT_RENDERERS[ident].iteritems():
            if isinstance(r, basestring):
                r = (r,)
            if not isinstance(r, text.TextRenderer):
                r = text.TextRenderer(*r)
            self.text_renderers[name] = r
        pg.event.set_grab(conf.GRAB_EVENTS[ident])
        pg.mouse.set_visible(conf.MOUSE_VISIBLE[ident])
        pg.mixer.music.set_volume(conf.MUSIC_VOLUME[ident])
        world._select()

    def start_world (self, *args, **kwargs):
        """Store the current world (if any) and switch to a new one.

Takes a :class:`World` instance, or the same arguments as :meth:`create_world`
to create a new one.

:return: the new current world.

"""
        if self.world is not None:
            self.worlds.append(self.world)
        return self.switch_world(*args, **kwargs)

    def switch_world (self, world, *args, **kwargs):
        """End the current world and start a new one.

Takes a :class:`World` instance, or the same arguments as :meth:`create_world`
to create a new one.

:return: the new current world.

"""
        if not isinstance(world, World):
            world = self.create_world(world, *args, **kwargs)
        self._select_world(world)
        return world

    def get_worlds (self, ident, current = True):
        """Get a list of running worlds, filtered by identifier.

get_worlds(ident, current = True) -> worlds

:arg ident: the world identifier (:attr:`World.id`) to look for.
:arg current: include the current world in the search.

:return: the world list, in order of time started, most recent last.

"""
        worlds = []
        current = [{'world': self.world}] if current else []
        for data in self.worlds + current:
            world = data['world']
            if world.id == ident:
                worlds.append(world)
        return worlds

    def quit_world (self, depth = 1):
        """Quit the currently running world.

quit_world(depth = 1) -> worlds

:arg depth: quit this many (nested) worlds.

:return: a list of worlds that were quit, in the order they were quit.

If this quits the last (root) world, exit the game.

"""
        if depth < 1:
            return []
        old_world = self.world
        old_world.quit()
        if self.worlds:
            self._select_world(self.worlds.pop())
        else:
            self.quit()
        return [old_world] + self.quit_world(depth - 1)

    # resources

    def _change_resource_pool (self, new_pool):
        # callback: after conf.DEFAULT_RESOURCE_POOL change
        self.resources.drop(self._using_pool, self)
        self.resources.use(new_pool, self)
        self._using_pool = new_pool

    def play_snd (self, base_id, volume = 1):
        """Play a sound.

play_snd(base_id, volume = 1)

:arg base_id: the identifier of the sound to play (we look for ``base_id + i``
              for a number ``i``---there are as many sounds as set in
              :data:`conf.SOUNDS`).
:arg volume: amount to scale the playback volume by.

"""
        ident = randrange(conf.SOUNDS[base_id])
        # load sound
        snd = conf.SOUND_DIR + base_id + str(ident) + '.ogg'
        snd = pg.mixer.Sound(snd)
        if snd.get_length() < 10 ** -3:
            # no way this is valid
            return
        volume *= conf.SOUND_VOLUME * conf.SOUND_VOLUMES[base_id]
        snd.set_volume(volume)
        snd.play()

    def find_music (self):
        """Store a list of the available music files in :attr:`music`."""
        d = conf.MUSIC_DIR
        try:
            files = os.listdir(d)
        except OSError:
            # no directory
            self.music = []
        else:
            self.music = [d + f for f in files if os.path.isfile(d + f)]

    def play_music (self):
        """Play the next piece of music, chosen randomly from :attr:`music`."""
        if self.music:
            f = choice(self.music)
            pg.mixer.music.load(f)
            pg.mixer.music.play()
        else:
            # stop currently playing music if there's no music to play
            pg.mixer.music.stop()

    # display

    def refresh_display (self):
        """Update the display mode from :mod:`conf`."""
        # get resolution and flags
        flags = conf.FLAGS
        if conf.FULLSCREEN:
            flags |= pg.FULLSCREEN
            r = conf.RES_F
        else:
            w = max(conf.MIN_RES_W[0], conf.RES_W[0])
            h = max(conf.MIN_RES_W[1], conf.RES_W[1])
            r = (w, h)
        if conf.RESIZABLE:
            flags |= pg.RESIZABLE
        ratio = conf.ASPECT_RATIO
        if ratio is not None:
            # lock aspect ratio
            r = list(r)
            r[0] = min(r[0], r[1] * ratio)
            r[1] = min(r[1], r[0] / ratio)
        conf.RES = r
        self.screen = pg.display.set_mode(conf.RES, flags)
        if self.world is not None:
            self.world.graphics.dirty()

    def toggle_fullscreen (self):
        """Toggle fullscreen mode."""
        conf.FULLSCREEN = not conf.FULLSCREEN

    def _toggle_fullscreen (self, *args):
        # callback: keyboard shortcut pressed
        if conf.RESIZABLE:
            self.toggle_fullscreen()

    def minimise (self):
        """Minimise the display."""
        pg.display.iconify()

    def _active_cb (self, event):
        """Callback to handle window focus loss."""
        if event.state == 2 and not event.gain:
            self.world.pause()

    def _resize_cb (self, event):
        """Callback to handle a window resize."""
        conf.RES_W = (event.w, event.h)
        self.refresh_display()

    def _update (self):
        """Update worlds and draw."""
        self._update_again = True
        while self._update_again:
            self._update_again = False
            self.world.evthandler.update()
            # if a new world was created during the above call, we'll end up
            # updating twice before drawing
            if not self._update_again:
                self.world._update()
        if self.world._handle_slowdown():
            drawn = self.world.draw()
            # update display
            if drawn is True:
                update_display()
            elif drawn:
                if len(drawn) > 60: # empirical - faster to update everything
                    update_display()
                else:
                    update_display(drawn)
        return True

    # running

    def run (self, t = None):
        """Main loop.

run([t])

:arg t: stop after this many seconds (else run forever).

"""
        self.resources.use(conf.DEFAULT_RESOURCE_POOL, self)
        self._using_pool = conf.DEFAULT_RESOURCE_POOL
        self._init_cbs()
        while not self._quit and (t is None or t > 0):
            t = self.world.scheduler.run(seconds = t)
        self.resources.drop(conf.DEFAULT_RESOURCE_POOL, self)
        self._using_pool = None
        conf.rm_cbs(self)

    def quit (self):
        """Quit the game."""
        self.world.scheduler.stop()
        self._quit = True

    def restart (self):
        """Restart the game."""
        global restarting
        restarting = True
        self.quit()
