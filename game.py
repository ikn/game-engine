from sys import argv
import os
from time import time
from random import choice

d = os.path.dirname(argv[0])
if d: # else current dir
    os.chdir(d)
from game import conf

import pygame
from pygame.time import wait
if os.name == 'nt':
    # for Windows freeze support
    import pygame._view
from game.ext import evthandler as eh
if conf.USE_FONTS:
    from game.ext.fonthandler import Fonts

pygame.mixer.pre_init(buffer = 1024)
pygame.init()

from game.level import Level

ir = lambda x: int(round(x))

def get_backend_id (backend):
    """Return the computed identifier of the given backend.

See Game.create_backend for details.

"""
    try:
        return backend.id
    except AttributeError:
        return type(backend).__name__.lower()


class Game (object):
    """Handles backends.

Takes the same arguments as the create_backend method and passes them to it.

    METHODS

create_backend
select_backend
start_backend
get_backends
quit_backend
img
play_snd
find_music
play_music
quit
run
restart
refresh_display
toggle_fullscreen
minimise

    ATTRIBUTES

running: set to False to exit the main loop (run method).
imgs: image cache.
files: loaded image cache (before resize).
music: filenames for known music.
fonts: a Fonts instance, or None if conf.USE_FONTS is False.
backend: the current running backend.
backends: a list of previous (nested) backends, most 'recent' last.
frame: the current target duration of a frame, in seconds.

"""

    def __init__ (self, *args, **kwargs):
        self.running = False
        self.files = {}
        self.imgs = {}
        # start playing music
        pygame.mixer.music.set_volume(conf.MUSIC_VOLUME * .01)
        pygame.mixer.music.set_endevent(conf.EVENT_ENDMUSIC)
        self.find_music()
        self.play_music()
        # load display settings
        self.refresh_display()
        self.fonts = Fonts(conf.FONT_DIR) if conf.USE_FONTS else None
        # start first backend
        self.backends = []
        self.start_backend(*args, **kwargs)

    def create_backend (self, cls, *args, **kwargs):
        """Create a backend.

create_backend(cls, *args, **kwargs) -> backend

cls: the backend class to instantiate.
args, kwargs: positional- and keyword arguments to pass to the constructor.

backend: the created backend.

Backends handle pretty much everything, including drawing, and must have update
and draw methods, as follows:

update(): handle input and make any necessary calculations.
draw(screen) -> drawn: draw anything necessary to screen; drawn is True if the
                       whole display needs to be updated, something falsy if
                       nothing needs to be updated, else a list of rects to
                       update the display in.

A backend is also given a dirty attribute, which indicates whether its draw
method should redraw everything (it should set it to False when it does so).
It may define an id attribute, which is a unique identifier used for some
settings in conf; if none is set, type(backend).__name__.lower() will be used
(for this to make sense, the backend must be a new-style class).

A backend is constructed via:

    cls(game, event_handler, *args, **kwargs)

game is this Game instance; event_handler is the EventHandler instance the
backend should use for input, and is stored in its event_handler attribute.

"""
        # create event handler for this backend
        h = eh.MODE_HELD
        event_handler = eh.EventHandler({
            pygame.ACTIVEEVENT: self._active_cb,
            pygame.VIDEORESIZE: self._resize_cb,
            conf.EVENT_ENDMUSIC: self.play_music
        }, [
            (conf.KEYS_FULLSCREEN, self.toggle_fullscreen, eh.MODE_ONDOWN),
            (conf.KEYS_MINIMISE, self.minimise, eh.MODE_ONDOWN)
        ], False, self.quit)
        # instantiate class
        backend = cls(self, event_handler, *args)
        backend.event_handler = event_handler
        return backend

    def select_backend (self, backend):
        """Set the given backend as the current backend."""
        self.backend = backend
        backend.dirty = True
        self._update_again = True
        i = get_backend_id(backend)
        pygame.mouse.set_visible(conf.MOUSE_VISIBLE[i])
        self.frame = 1. / conf.FPS[i]

    def start_backend (self, *args, **kwargs):
        """Start a new backend.

Takes the same arguments as create_backend; see that method for details.

Returns the started backend.

"""
        # store current backend in history, if any
        try:
            self.backends.append(self.backend)
        except AttributeError:
            pass
        # create backend
        backend = self.create_backend(*args, **kwargs)
        self.select_backend(backend)
        return backend

    def switch_backend (self, *args, **kwargs):
        """Close the current backend and start a new one.

Takes the same arguments as create_backend and returns the created backend.

"""
        backend = self.create_backend(*args, **kwargs)
        self.select_backend(backend)
        return backend

    def get_backends (self, ident, current = True):
        """Get a list of running backends, filtered by ID.

get_backends(ident, current = True) -> backends

ident: the backend identifier to look for (see create_backend for details).
current: include the current backend in the search.

backends: the backend list, in order of time started, most recent last.

"""
        backends = []
        for backend in self.backends + ([self.backend] if current else []):
            if get_backend_id(backend) == ident:
                backends.append(backend)

    def quit_backend (self, depth = 1):
        """Quit the currently running backend.

quit_backend(depth = 1)

depth: quit this many (nested) backends.

If the running backend is the last (root) one, exit the game.

"""
        if depth < 1:
            return
        try:
            backend = self.backends.pop()
        except IndexError:
            self.quit()
        else:
            self.select_backend(backend)
        self.quit_backend(depth - 1)

    def convert_img (self, img):
        """Convert an image for blitting."""
        if img.get_alpha() is None and img.get_colorkey() is None:
            img = img.convert()
        else:
            img = img.convert_alpha()
        return img

    def img (self, data, size = None):
        """Load or render an image, or retrieve it from cache.

img(data[, size]) -> surface

data: if rendering text, a tuple of args to pass to Fonts.text, else a filename
      to load.
size: scale the image.  Can be an (x, y) size, a rect (in which case its
      dimension is used), or a number to scale by.  Ignored if rendering text.
      If (x, y), either x or y can be None to scale to the other with aspect
      ratio preserved.

"""
        text = not isinstance(data, basestring)
        if text:
            data = tuple(tuple(x) if isinstance(x, list) else x for x in data)
        if size is not None:
            try:
                if len(size) == 4:
                    # rect
                    size = size[2:]
                size = tuple(size)
            except TypeError:
                # number
                pass
        key = (data, size)
        if key in self.imgs:
            return self.imgs[key]
        got_size = size is not None and size != 1 and not text
        # else new: load/render
        if text:
            if self.fonts is None:
                raise ValueError('conf.USE_FONTS is False: text rendering '
                                 'isn\'t supported')
            img, lines = self.fonts.text(*data)
            img = img.convert_alpha()
        else:
            # also cache loaded images to reduce file I/O
            data = conf.IMG_DIR + data
            if data in self.files:
                img = self.files[data]
            else:
                img = pygame.image.load(data)
                # convert first
                img = self.convert_img(img)
                self.files[data] = img
        # scale
        if got_size:
            current_size = img.get_size()
            if not isinstance(size, tuple):
                size = (ir(size * current_size[0]), ir(size * current_size[1]))
            # handle None
            for i in (0, 1):
                if size[i] is None:
                    size = list(size)
                    scale = float(size[not i]) / current_size[not i]
                    size[i] = ir(current_size[i] * scale)
                    size = tuple(size)
            img = pygame.transform.smoothscale(img, size)
        else:
            # speed up blitting (if not resized, this is already done)
            img = self.convert_img(img)
        result = (img, lines) if text else img
        if got_size or text:
            # add to cache (if not resized, this is in the file cache)
            self.imgs[key] = result
        return result

    def play_snd (self, base_ID, volume = 1):
        """Play a sound.

play_snd(base_ID, volume = 1)

base_ID: the ID of the sound to play (we look for base_ID + i for a number i,
         as many sounds as conf.SOUNDS[base_ID]).
volume: float to scale volume by.

"""
        try:
            n = conf.SOUNDS[base_ID]
        except KeyError:
            return
        IDs = [base_ID + str(i) for i in xrange(n)]
        ID = choice(IDs)
        # load sound
        snd = conf.SOUND_DIR + ID + '.ogg'
        snd = pygame.mixer.Sound(snd)
        if snd.get_length() < 10 ** -3:
            # no way this is valid
            return
        snd.set_volume(conf.SOUND_VOLUME * conf.SOUND_VOLUMES.get(base_ID, 1) * volume * .01)
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
            pygame.mixer.music.load(f)
            pygame.mixer.music.play()
        else:
            # stop currently playing music if there's no music to play
            pygame.mixer.music.stop()

    def quit (self, event = None):
        """Quit the game."""
        self.running = False

    def _update (self):
        """Run the backend's update method."""
        self.backend.event_handler.update()
        # if a new backend was created during the above call, we'll end up
        # updating twice before drawing
        if not self._update_again:
            self.backend.update()

    def _draw (self):
        """Run the backend's draw method and update the screen."""
        draw = self.backend.draw(self.screen)
        if draw is True:
            pygame.display.flip()
        elif draw:
            pygame.display.update(draw)

    def run (self, n = 0):
        """Main loop."""
        self.running = True
        update = self._update
        draw = self._draw
        t0 = time()
        while self.running:
            # update
            self._update_again = False
            update()
            if self._update_again:
                self._update_again = False
                update()
            # draw
            draw()
            # wait
            t1 = time()
            t0 = t1 + wait(int(1000 * (self.frame - t1 + t0))) / 1000.
            # counter
            n -= 1
            if n == 0:
                break

    def restart (self, *args):
        """Restart the game."""
        global restarting
        restarting = True
        self.quit()

    def refresh_display (self, *args):
        """Update the display mode from conf, and notify the backend."""
        # get resolution and flags
        flags = conf.FLAGS
        if conf.FULLSCREEN:
            flags |= pygame.FULLSCREEN
            r = conf.RES_F
        else:
            w = max(conf.MIN_RES_W[0], conf.RES_W[0])
            h = max(conf.MIN_RES_W[1], conf.RES_W[1])
            r = (w, h)
        if conf.RESIZABLE:
            flags |= pygame.RESIZABLE
        ratio = conf.ASPECT_RATIO
        if ratio is not None:
            # lock aspect ratio
            r = list(r)
            r[0] = min(r[0], r[1] * ratio)
            r[1] = min(r[1], r[0] / ratio)
        conf.RES = r
        self.screen = pygame.display.set_mode(conf.RES, flags)
        try:
            self.backend.dirty = True
        except AttributeError:
            pass
        # clear image cache (very unlikely we'll need the same sizes)
        self.imgs = {}

    def toggle_fullscreen (self, *args):
        """Toggle fullscreen mode."""
        if conf.RESIZABLE:
            conf.FULLSCREEN = not conf.FULLSCREEN
            self.refresh_display()

    def minimise (self, *args):
        """Minimise the display."""
        pygame.display.iconify()

    def _active_cb (self, event):
        """Callback to handle window focus loss."""
        if event.state == 2 and not event.gain:
            try:
                self.backend.pause()
            except AttributeError:
                pass

    def _resize_cb (self, event):
        """Callback to handle a window resize."""
        conf.RES_W = (event.w, event.h)
        self.refresh_display()


if __name__ == '__main__':
    if conf.WINDOW_ICON is not None:
        pygame.display.set_icon(pygame.image.load(conf.WINDOW_ICON))
    if conf.WINDOW_TITLE is not None:
        pygame.display.set_caption(conf.WINDOW_TITLE)
    if len(argv) >= 2 and argv[1] == 'profile':
        # profile
        from cProfile import run
        from pstats import Stats
        if len(argv) >= 3:
            t = int(argv[2])
        else:
            t = conf.DEFAULT_PROFILE_TIME
        t *= conf.FPS
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

pygame.quit()
