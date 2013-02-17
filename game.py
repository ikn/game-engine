from sys import argv
import os
from time import time
from random import choice, randrange
from bisect import bisect

d = os.path.dirname(argv[0])
if d: # else current dir
    os.chdir(d)

import pygame as pg
from pygame.time import wait
if os.name == 'nt':
    # for Windows freeze support
    import pygame._view

pg.mixer.pre_init(buffer = 1024)
pg.init()

from game.conf import conf
from game.ext.sched import Scheduler
from game.ext import evthandler as eh
if conf.USE_FONTS:
    from game.ext.fonthandler import Fonts
from game.util import ir, convert_sfc
from game.world import World
from game.level import Level


def get_world_id (world):
    """Return the computed identifier of the given world (or world type).

See Game.create_world for details.

"""
    if hasattr(world, 'id'):
        return world.id
    else:
        if not isinstance(world, type):
            world = type(world)
        return world.__name__.lower()


class Game (object):
    """Handles worlds.

Takes the same arguments as the create_world method and passes them to it.
Only one game should ever exist, and it stores itself in conf.GAME.

    METHODS

create_world
start_world
get_worlds
quit_world
img
render_text
clear_caches
play_snd
find_music
play_music
run
quit
restart
refresh_display
toggle_fullscreen
minimise

    ATTRIBUTES

world: the current running world.
worlds: a list of previous (nested) worlds, most 'recent' last.
file_cache, img_cache, text_cache: caches for loaded image cache (before
                                   resize), images and rendered text
                                   respectively.
fonts: a fonthandler.Fonts instance, or None if conf.USE_FONTS is False.
music: filenames for known music.
screen: the main Pygame surface.

"""

    def __init__ (self, *args, **kwargs):
        conf.GAME = self
        self._quit = False
        self._update_again = False
        # initialise caches
        self.file_cache = {}
        self.img_cache = {}
        self.text_cache = {}
        # load display settings
        self.refresh_display()
        self.fonts = Fonts(conf.FONT_DIR) if conf.USE_FONTS else None
        # start first world
        self.worlds = []
        self.start_world(*args, **kwargs)
        # start playing music
        pg.mixer.music.set_endevent(conf.EVENT_ENDMUSIC)
        self.find_music()
        self.play_music()
        if not conf.MUSIC_AUTOPLAY:
            pg.mixer.music.pause()

    # world handling

    def create_world (self, cls, *args, **kwargs):
        """Create a world.

create_world(cls, *args, **kwargs) -> world

cls: the world class to instantiate.
args, kwargs: positional- and keyword arguments to pass to the constructor.

world: the created world; must be a world.World subclass.

Optional world attributes:

    pause(): called when the window loses focus to pause the game.
    id: a unique identifier used for some settings in conf; if none is set,
        type(world).__name__.lower() will be used.

A world is constructed by:

    cls(scheduler, evthandler, *args, **kwargs)

where scheduler and evthandler are as taken by world.World (and should be
passed to that base class).

"""
        scheduler = Scheduler()
        scheduler.add_timeout(self._update, frames = 1, repeat_frames = 1)
        evthandler = eh.EventHandler({
            pg.ACTIVEEVENT: self._active_cb,
            pg.VIDEORESIZE: self._resize_cb,
            conf.EVENT_ENDMUSIC: self.play_music
        }, [
            (conf.KEYS_FULLSCREEN, self.toggle_fullscreen, eh.MODE_ONDOWN),
            (conf.KEYS_MINIMISE, self.minimise, eh.MODE_ONDOWN)
        ], False, self.quit)
        # instantiate class
        world = cls(scheduler, evthandler, *args)
        scheduler.fps = conf.FPS[get_world_id(world)]
        return world

    def _select_world (self, world):
        """Set the given world as the current world."""
        if hasattr(self, 'world'):
            self._update_again = True
            self.world.scheduler.stop()
        self.world = world
        world.graphics.surface = self.screen
        world.graphics.dirty()
        i = get_world_id(world)
        # set some per-world things
        if conf.USE_FONTS:
            fonts = self.fonts
            for k, v in conf.REQUIRED_FONTS[i].iteritems():
                fonts[k] = v
        pg.mouse.set_visible(conf.MOUSE_VISIBLE[i])
        pg.mixer.music.set_volume(conf.MUSIC_VOLUME[i])
        world.select()

    def start_world (self, *args, **kwargs):
        """Store the current world (if any) and switch to a new one.

Takes a World instance, or the same arguments as create_world to create a new
one (see that method for details).

Returns the new current world.

"""
        if hasattr(self, 'world'):
            self.worlds.append(self.world)
        return self.switch_world(*args, **kwargs)

    def switch_world (self, world, *args, **kwargs):
        """Close the current world and start a new one.

Arguments and return value are the same as for start_world.

"""
        if not isinstance(world, World):
            world = self.create_world(world, *args, **kwargs)
        self._select_world(world)
        return world

    def get_worlds (self, ident, current = True):
        """Get a list of running worlds, filtered by ID.

get_worlds(ident, current = True) -> worlds

ident: the world identifier to look for (see create_world for details).
current: include the current world in the search.

worlds: the world list, in order of time started, most recent last.

"""
        worlds = []
        current = [{'world': self.world}] if current else []
        for data in self.worlds + current:
            world = data['world']
            if get_world_id(world) == ident:
                worlds.append(world)
        return worlds

    def quit_world (self, depth = 1):
        """Quit the currently running world.

quit_world(depth = 1) -> worlds

depth: quit this many (nested) worlds.

worlds: a list of worlds that were quit.

If this quits the last (root) world, exit the game.

"""
        if depth < 1:
            return []
        old_world = self.world
        if self.worlds:
            self._select_world(self.worlds.pop())
        else:
            self.quit()
        return [old_world] + self.quit_world(depth - 1)

    # media

    def img (self, filename, size = None, cache = True):
        """Load or scale an image, or retrieve it from cache.

img(filename[, size], cache = True) -> surface

data: a filename to load.
size: scale the image.  Can be an (x, y) size, a rect (in which case its
      dimension is used), or a number to scale by.  If (x, y), either x or y
      can be None to scale to the other with aspect ratio preserved.
cache: whether to store this image in the cache if not already stored.

"""
        # get standardised cache key
        if size is not None:
            if isinstance(size, (int, float)):
                size = float(size)
            else:
                if len(size) == 4:
                    # rect
                    size = size[2:]
                size = tuple(size)
        key = (filename, size)
        if key in self.img_cache:
            return self.img_cache[key]
        # else new: load/render
        filename = conf.IMG_DIR + filename
        # also cache loaded images to reduce file I/O
        if filename in self.file_cache:
            img = self.file_cache[filename]
        else:
            img = convert_sfc(pg.image.load(filename))
            if cache:
                self.file_cache[filename] = img
        # scale
        if size is not None and size != 1:
            current_size = img.get_size()
            if not isinstance(size, tuple):
                size = (ir(size * current_size[0]), ir(size * current_size[1]))
            # handle None
            for i in (0, 1):
                if size[i] is None:
                    size = list(size)
                    scale = float(size[not i]) / current_size[not i]
                    size[i] = ir(current_size[i] * scale)
            img = pg.transform.smoothscale(img, size)
            # speed up blitting (if not resized, this is already done)
            img = convert_sfc(img)
            if cache:
                # add to cache (if not resized, this is in the file cache)
                self.img_cache[key] = img
        return img

    def render_text (self, *args, **kwargs):
        """Render text and cache the result.

Takes the same arguments as fonthandler.Fonts.render, plus a keyword-only
'cache' argument.  If passed, the text is cached under this hashable value, and
can be retrieved from cache by calling this function with the same value for
this argument.

Returns the same value as fonthandler.Fonts

"""
        if self.fonts is None:
            raise ValueError('conf.USE_FONTS is False: text rendering isn\'t'
                             'supported')
        cache = 'cache' in kwargs
        if cache:
            key = kwargs['cache']
            del kwargs['cache']
            if key in self.text_cache:
                return self.text_cache[key]
        # else new: render
        img, lines = self.fonts.render(*args, **kwargs)
        img = convert_sfc(img)
        result = (img, lines)
        if cache:
            self.text_cache[key] = result
        return result

    def clear_caches (self, *caches):
        """Clear image caches.

    Takes any number of strings 'file', 'image' and 'text' as arguments, which
    determine whether to clear the file_cache, img_cache and text_cache
    attributes respectively (see class documentation).  If none is given, all
    caches are cleared.

    """
        if not caches:
            caches = ('file', 'image', 'text')
        if 'file' in caches:
            self.file_cache = {}
        if 'image' in caches:
            self.img_cache = {}
        if 'text' in caches:
            self.text_cache = {}

    def play_snd (self, base_ID, volume = 1):
        """Play a sound.

play_snd(base_ID, volume = 1)

base_ID: the ID of the sound to play (we look for base_ID + i for a number i,
         as many sounds as conf.SOUNDS[base_ID]).
volume: float to scale volume by.

"""
        ID = randrange(conf.SOUNDS[base_ID])
        # load sound
        snd = conf.SOUND_DIR + base_ID + str(ID) + '.ogg'
        snd = pg.mixer.Sound(snd)
        if snd.get_length() < 10 ** -3:
            # no way this is valid
            return
        volume *= conf.SOUND_VOLUME * conf.SOUND_VOLUMES[base_ID]
        snd.set_volume(volume)
        snd.play()

    def find_music (self):
        """Store a list of music files."""
        d = conf.MUSIC_DIR
        try:
            files = os.listdir(d)
        except OSError:
            # no directory
            self.music = []
        else:
            self.music = [d + f for f in files if os.path.isfile(d + f)]

    def play_music (self, event = None):
        """Play next piece of music."""
        if self.music:
            f = choice(self.music)
            pg.mixer.music.load(f)
            pg.mixer.music.play()
        else:
            # stop currently playing music if there's no music to play
            pg.mixer.music.stop()

    # display

    def refresh_display (self, *args):
        """Update the display mode from conf, and notify the world."""
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
        if hasattr(self, 'world'):
            self.world.graphics.dirty()
        # clear image cache (very unlikely we'll need the same sizes)
        self.img_cache = {}

    def toggle_fullscreen (self, *args):
        """Toggle fullscreen mode."""
        if conf.RESIZABLE:
            conf.FULLSCREEN = not conf.FULLSCREEN
            self.refresh_display()

    def minimise (self, *args):
        """Minimise the display."""
        pg.display.iconify()

    def _active_cb (self, event):
        """Callback to handle window focus loss."""
        if event.state == 2 and not event.gain:
            try:
                self.world.pause()
            except (AttributeError, TypeError):
                pass

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
                self._update_again = False
                self.world.update()
        drawn = self.world.draw()
        # update display
        if drawn is True:
            pg.display.flip()
        elif drawn:
            pg.display.update(drawn)
        return True

    # running

    def run (self, t = None):
        """Main loop."""
        while not self._quit and (t is None or t > 0):
            t = self.world.scheduler.run(seconds = t)

    def quit (self, *args):
        """Quit the game."""
        self.world.scheduler.stop()
        self._quit = True

    def restart (self, *args):
        """Restart the game."""
        global restarting
        restarting = True
        self.quit()


if __name__ == '__main__':
    if conf.WINDOW_ICON is not None:
        pg.display.set_icon(pg.image.load(conf.WINDOW_ICON))
    if conf.WINDOW_TITLE is not None:
        pg.display.set_caption(conf.WINDOW_TITLE)
    if len(argv) >= 2 and argv[1] == 'profile':
        # profile
        from cProfile import run
        from pstats import Stats
        if len(argv) >= 3:
            t = int(argv[2])
        else:
            t = conf.DEFAULT_PROFILE_TIME
        fn = conf.PROFILE_STATS_FILE
        run('Game(Level).run(t)', fn, locals())
        Stats(fn).strip_dirs().sort_stats('cumulative').print_stats(20)
        os.unlink(fn)
    else:
        # run normally
        restarting = True
        while restarting:
            restarting = False
            Game(Level).run()

pg.quit()
