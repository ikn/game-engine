Tutorial
========

.. highlight:: python
   :linenothreshold: 5

To show how parts of the engine work, I'll make a simple (boring) sliding block
game.  Before starting, you should have a working knowledge of both
`Python <http://www.python.org>`_ and `Pygame <http://www.pygame.org>`_.  I'll
be using Python 2 here, but Python 3 works just as well, provided you're using
an appropriate version of Pygame, and I haven't broken anything.

Setup
-----

Start by downloading the source from
`the GitHub repository <https://github.com/ikn/pygame-template>`_ and building
it using the instructions in the readme.  Instead of using the whole template,
we'll just use the engine here, so copy out the ``game/engine/`` package and
create a Python script in the same directory.  We need a little bit of code to
get everything running::

    import random

    import pygame as pg

    import engine
    from engine import conf, evt, gfx, util


    class Conf (object):
        # the width and height of the image we're working with
        IMG_SIZE = (500, 500)
        # the number of tiles, horizontally and vertically
        N_TILES = (5, 5)
        # the size of each actual tile graphic
        TILE_SIZE = (99, 99)
        # the gap between tiles and around the edge of the screen
        TILE_GAP = (1, 1)


    class Puzzle (engine.game.World):
        def init (self):
            pass


    if __name__ == '__main__':
        # add our settings to the main settings object
        conf.add(Conf)
        # set the window size
        conf.RES_W = (conf.IMG_SIZE[0] + conf.TILE_GAP[0],
                      conf.IMG_SIZE[1] + conf.TILE_GAP[1])
        # initialise the engine
        engine.init()
        # run with a Puzzle as the world
        engine.game.run(Puzzle)
        # now we're finished: quit the engine
        engine.quit()

This will show a blank window, which you can close like any other window.

- We won't use some of these imports for a while, but it's worth having them
  all together at the start.
- :meth:`World.init() <engine.game.World.init>` is where your world's
  initialisation code goes.
- The ``Conf`` object is not especially necessary, but it's nice to keep all
  the magic constants together.  It gets added to the global :mod:`conf`
  object, which makes it easy to save settings if we want to at a later date.

Graphics
--------

To start with, we need an image.  To make things simple and to avoid dwelling
on engine-independent stuff, let's assume a fixed size for the image: 500
pixels wide and high.  I'm using
`a lovely Toady Bloyster <_static/tut-img.jpg>`_.  Place the image in a
directory named ``img`` next to the script.

To load a Pygame surface from an image file, use the
:class:`ResourceManager <engine.res.ResourceManager>` available to the
world---working in the ``init`` method, we use::

    img = self.resources.img('img.jpg')

Most of the code to split the image up into tiles is basic Pygame.

.. code-block:: python
   :linenos:
   :emphasize-lines: 20

    # split up into tiles
    imgs = []
    alpha = util.has_alpha(img)
    nx, ny = conf.N_TILES
    gap_x, gap_y = conf.TILE_GAP
    tile_w, tile_h = conf.TILE_SIZE
    for i in xrange(nx):
        for j in xrange(ny):
            # create empty surface of the correct size and convert
            sfc = pg.Surface(conf.TILE_SIZE)
            if alpha:
                sfc = sfc.convert_alpha()
            else:
                sfc = sfc.convert()
            # copy the correct portion from the source image
            x = (tile_w + gap_x) * i
            y = (tile_h + gap_y) * j
            sfc.blit(img, (0, 0), (x, y, tile_w, tile_h))
            # wrap with a graphic
            imgs.append(((i, j), gfx.Graphic(sfc)))

In the last line, I create a :class:`Graphic <engine.gfx.graphic.Graphic>`
object and store it in the ``imgs`` list.  This wraps the surface, and allows
for automatic drawing once added to the graphics manager, which we'll do soon.
Converting the tile surfaces is necessary if the loaded image has transparency
(otherwise transparent areas will appear black).

For positioning the tiles easily, I'll create a
:class:`Grid <engine.util.Grid>`.  You can set the position of a graphic using
a number of attributes and methods; here, I use
:attr:`Graphic.pos <engine.gfx.graphic.Graphic.pos>`.  Again, the rest of this
code should contain nothing unfamiliar:

.. code-block:: python
   :linenos:
   :emphasize-lines: 7,19,24

    # randomise tile positions and remove one
    random.shuffle(imgs)
    missing = random.randrange(nx * ny)
    self.missing = [missing // ny, missing % ny]
    imgs[missing] = (imgs[missing][0], None)
    # create grid for positioning
    grid = util.Grid(conf.N_TILES, conf.TILE_SIZE, conf.TILE_GAP)
    self.grid = grid
    # position graphics
    # and turn the tile list into a grid for easier access
    self.tiles = tiles = []
    for i in xrange(nx):
        col = []
        tiles.append(col)
        for j in xrange(ny):
            orig_pos, graphic = imgs[i * ny + j]
            col.append((orig_pos, graphic))
            # get the tile's top-left corner from the grid
            x, y = grid.tile_pos(i, j)
            if graphic is not None:
                # and move the graphic there
                graphic.pos = (x + gap_x, y + gap_y)

The only thing left to do is add the graphics to the graphics manager.  This is
accessed through :attr:`World.graphics <engine.game.World.graphics>`, and has
an :meth:`add() <engine.gfx.container.GraphicsManager.add>` method.  I also add
a dark grey background; Pygame-style colours and ``0xrrggbbaa`` are supported
too.

.. code-block:: python
   :linenos:
   :emphasize-lines: 4,8

    # add to the graphics manager
    # make sure to remove the missing tile
    imgs.pop(missing)
    self.graphics.add(
        # a background to show up between the tiles and in the gap
        # '111' is a CSS-style colour (dark grey)
        # 1 is the layer, which is further back than the default 0
        gfx.Colour('111', self.graphics.rect, 1),
        *(graphic for orig_pos, graphic in imgs)
    )

And now the tiles show up on the screen.  Try
:doc:`the full code <tut-code/graphics>`.

Input
-----

The best way to do input handling is by creating a configuration file.  Create
an ``evt`` directory next to the script and create a file to store them in.
I'm calling it ``controls``, but if you're on Windows, you might want to add an
extension (like ``.txt``) to make it easier to edit.

First, let's add some more ways to quit the game.  We create a ``button`` event
that issues signals when it is pressed down, and attach a couple of keyboard
keys using same the names as Pygame:

.. code-block:: sh

    button quit DOWN
        # this is a comment
        kbd ESCAPE
        kbd BACKSPACE

The ``quit`` argument is the name we choose to give the event, and it is
required; we'll see its use soon.

For playing, what we want to do is move tiles in four directions: left, right,
up or down.  This corresponds to a ``button4`` event, so let's make one of
those:

.. code-block:: sh

    button4 move DOWN
        left kbd LEFT
        right kbd RIGHT
        up kbd UP
        down kbd DOWN

This time, we've used the ``left``, etc. keywords to define which 'component'
of the event each input is attached to.

Now let's use these definitions in our code.  Working in the ``init`` method
again, add::

    eh = self.evthandler
    eh.load('controls')

This loads the events we've defined into this world's event handler, and now
they're easy to access::

    eh['quit'].cb(lambda evts: conf.GAME.quit_world())
    eh['move'].cb(self.move)

(:data:`conf.GAME` contains the current running game.)  We've registered
callback functions for each event using
:meth:`BaseEvent.cb() <engine.evt.evts.BaseEvent.cb>`; the arguments these get
called with depends on the event type.  A ``button`` passes a single argument
containing information about the numbers of ``DOWN``, etc. events that occurred
in the last frame.  We only get called if there was at least one event, and
we've only registered for ``DOWN`` events, so we just ignore it here and quit
the world (this is the only running world, so it causes the game to end).

Now we need to define the ``move`` method we've referenced above.  First, let's
write the code that will just move a tile to the missing tile::

    def move_tile (self, start_x, start_y):
        """Move the given tile to the missing tile."""
        # set the tile's new position
        dest_x, dest_y = self.missing
        orig_pos, graphic = self.tiles[start_x][start_y]
        self.tiles[dest_x][dest_y] = (orig_pos, graphic)
        # mark the original position as missing
        self.missing = (start_x, start_y)
        self.tiles[start_x][start_y] = None

        # get graphic's new on-screen position
        screen_x, screen_y = self.grid.tile_pos(dest_x, dest_y)
        screen_x += conf.TILE_GAP[0]
        screen_y += conf.TILE_GAP[1]
        # move the graphic
        graphic.pos = (screen_x, screen_y)

Nothing here is new.

A ``button4`` calls callbacks with three arguments: the axis and direction:

+-----------+------+-----------+
| component | axis | direction |
+===========+======+===========+
| left      + 0    + -1        +
+-----------+------+-----------+
| right     + 0    + 1         +
+-----------+------+-----------+
| up        + 1    + -1        +
+-----------+------+-----------+
| down      + 1    + 1         +
+-----------+------+-----------+

and a ``dict`` with a key for each button mode (``DOWN``), giving numbers of
events in the last frame (like for ``button``).  We could just ignore the
numbers of events and assume we only got one to limit the number of moves to
one per frame, but I'll do it properly here:

.. code-block:: python
   :linenos:
   :emphasize-lines: 2

    def move (self, axis, dirn, evts):
        for i in xrange(evts[evt.bmode.DOWN]):
            # get the tile to move
            start = list(self.missing)
            start[axis] -= dirn
            x, y = start
            # check if the tile exists
            if x < 0 or x >= conf.N_TILES[0] or y < 0 or y >= conf.N_TILES[1]:
                # the tile is out of bounds
                return
            # move the tile
            self.move_tile(x, y)

The useful thing about the event system is that you can define lots of
different inputs to do the same thing.  Let's use the following:

.. code-block:: sh

    button4 move DOWN
        # arrow keys
        left kbd LEFT
        right kbd RIGHT
        up kbd UP
        down kbd DOWN
        # WASD
        left kbd a
        left kbd q
        right kbd d
        right kbd e
        up kbd w
        up kbd z
        up kbd COMMA
        down kbd s
        down kbd o
        # gamepad analogue sticks
        left right pad axis 0 .6 .4
        up down pad axis 1 .6 .4
        left right pad axis 3 .6 .4
        up down pad axis 4 .6 .4

This supports the ``WASD`` keys for a number of keyboard layouts, and the
analogue sticks on all connected gamepads (for an Xbox 360 controller and any
other controller with analogue sticks bound to the same axes).  For the
gamepads to work, we need a little more code (just standard Pygame stuff) in
the ``init`` method::

    pg.joystick.init()
    for i in xrange(pg.joystick.get_count()):
        pg.joystick.Joystick(i).init()

How about supporting mouse input too?  The obvious control scheme is to move
any clicked tile to the missing tile if it's next to it.  To support both left-
and right mouse buttons, write the event definition:

.. code-block:: sh

    button click DOWN
        mouse button LEFT
        mouse button RIGHT

attach it to a callback::

    eh['click'].cb(self.click)

and define the callback::

    def click (self, evts):
        # get the tile clicked on
        x, y = pg.mouse.get_pos()
        tile = self.grid.tile_at(x - conf.TILE_GAP[0], y - conf.TILE_GAP[1])
        if tile is None:
            # clicked on the gap between tiles, so do nothing
            return
        x, y = tile
        for i in xrange(evts[evt.bmode.DOWN]):
            if self.tiles[x][y] is None:
                # this is the missing tile
                break
            # make sure the clicked tile is next to the missing tile
            if tuple(self.missing) not in ((x - 1, y), (x, y - 1), (x + 1, y),
                                           (x, y + 1)):
                # it's not
                break
            self.move_tile(x, y)

The only new thing here is the call to
:meth:`Grid.tile_at() <engine.util.Grid.tile_at>`---it saves a bit of work,
and handles the edge cases for us.

You might notice you can't see the cursor.  This is the default behaviour, so
let's disable that.  This setting is actually configured on a per-world basis,
and what we want can be achieved by the following::

    if __name__ == '__main__':
        # make the mouse visible
        conf.MOUSE_VISIBLE[Puzzle.id] = True
        # ...

Try :doc:`the game in its current state <tut-code/input>`.

Interpolation
-------------

Instead of moving the tiles instantly to their destination, let's try sliding
them over a short period.  This is achieved using the 'interpolation' provided
in the :mod:`sched <engine.sched>` module.  First define the movement duration
in our ``Conf`` object, in seconds::

    MOVE_TIME = .2

In our ``move_tile`` method, replace ::

    def move_tile (self, start_x, start_y):
        # ...
        graphic.pos = (screen_x, screen_y)

with ::

    def move_tile (self, start_x, start_y):
        # ...
        self.scheduler.interp_simple(graphic, 'pos', (screen_x, screen_y),
                                     conf.MOVE_TIME)

This moves the graphic linearly to the destination position instead of setting
it straight away.  Try the game again and you'll see it in action.

Now, if you go a little crazy and try pressing lots of buttons at once, you
might end up with more than one missing tile.  This is because we're not
bothering to stop any already-running motions on the same graphic when we start
a new one.

To fix this, we can store a variable defining whether a graphic is moving, and
register a callback for the end of an interpolation.  We require a few changes:

.. code-block:: python
   :linenos:
   :emphasize-lines: 4,5

    def init (self):
        # ...
                    if graphic is not None:
                        # we'll use this for movement
                        graphic.timeout_id = None
                        # and move the graphic there
                        graphic.pos = (x + gap_x, y + gap_y)

.. code-block:: python
   :linenos:
   :emphasize-lines: 4-11

    def move_tile (self, start_x, start_y):
        # ...
        # move the graphic
        if graphic.timeout_id is not None:
            # graphic is currently moving, so stop it
            self.scheduler.rm_timeout(graphic.timeout_id)
        graphic.timeout_id = self.scheduler.interp_simple(
            graphic, 'pos', (screen_x, screen_y), conf.MOVE_TIME,
            # a function to call when the interpolation ends
            lambda: setattr(graphic, 'timeout_id', None)
        )

Here's :doc:`the final code <tut-code/interpolation>`.

Everything else (exercises!)
----------------------------

I've gone over the (currently) most developed systems in the engine
(:mod:`evt`, :mod:`gfx`, and interpolation in :mod:`sched <engine.sched>`).
The rest is fairly simple or just uses Pygame directly, but here I've detailed
a few more things it might be useful to know.

Audio
#####

At the moment, audio is fairly basic.  To play music, just create a ``music``
directory next to the script and put some files supported by Pygame in there,
set :attr:`conf.MUSIC_AUTOPLAY` to ``True``, and they'll just play when the
game starts.

Sound files go in a ``sound`` directory, named like ``name0.ogg``,
``name1.ogg``, etc. to randomly choose one each time sound ``'name'`` is
played.  Volume works with something like::

    conf.SOUND_VOLUMES['name'] = .3

It might be worth finding an appropriate sound effect and getting it to play
when a tile is moved (see :meth:`World.play_snd() <engine.game.World.play_snd>`).

Victory condition
#################

At the moment, it's not possible to win the game.  There are a number of ways
this could be implemented, but this wouldn't teach anything about the engine,
so I've left it as an exercise.  You might find the ``orig_pos`` part of each
entry in the ``tiles`` attribute we've defined useful.

After you've managed that, try putting together a victory message using
``World.resources.text`` via ``ResourceManager.text`` via
:func:`res.load_text <engine.res.load_text>` (take note of
:attr:`conf.REQUIRED_FONTS` and :attr:`conf.FONT_DIR`).

High scores
###########

Try timing a player's attempt by keeping a counter and adding the frame
duration (``World.scheduler.elapsed`` via
:attr:`Timer.elapsed <engine.sched.Timer.elapsed>`) to it each frame
(:meth:`World.update() <engine.game.World.update>`).

As mentioned earlier, the ``conf`` object could easily be used to save
settings.  Try tracking and saving a list of the best times (see
:meth:`SettingsManager.save() <engine.settings.SettingsManager.save>` and
:meth:`SettingsManager.dump() <engine.settings.SettingsManager.dump>`).
