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
    # the number of seconds tiles take to slide to a new position
    MOVE_TIME = .2


class Puzzle (engine.game.World):
    def init (self):
        # initialise gamepads
        pg.joystick.init()
        for i in xrange(pg.joystick.get_count()):
            pg.joystick.Joystick(i).init()
        # register input handlers
        eh = self.evthandler
        eh.load('controls')
        eh['quit'].cb(lambda evts: conf.GAME.quit_world())
        eh['move'].cb(self.move)
        eh['click'].cb(self.click)

        # load image
        img = conf.GAME.img('img.jpg')

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

        # randomise tile positions and remove one
        random.shuffle(imgs)
        missing = random.randrange(nx * ny)
        self.missing = [missing // ny, missing % ny]
        imgs[missing] = (imgs[missing][0], None)
        # create grid for positioning
        grid = gfx.util.Grid(conf.N_TILES, conf.TILE_SIZE, conf.TILE_GAP)
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
                    # we'll use this for movement
                    graphic.timeout_id = None
                    # and move the graphic there
                    graphic.pos = (x + gap_x, y + gap_y)

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
        if graphic.timeout_id is not None:
            # graphic is currently moving, so stop it
            self.scheduler.rm_timeout(graphic.timeout_id)
        graphic.timeout_id = self.scheduler.interp_simple(
            graphic, 'pos', (screen_x, screen_y), conf.MOVE_TIME,
            # a function to call when the interpolation ends
            lambda: setattr(graphic, 'timeout_id', None)
        )

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

    def click (self, evts):
        # get the tile clicked on
        x, y = pg.mouse.get_pos()
        x -= conf.TILE_GAP[0]
        y -= conf.TILE_GAP[1]
        tile_w, tile_h = conf.TILE_SIZE
        if x % conf.N_TILES[0] >= tile_w or y % conf.N_TILES[1] >= tile_h:
            # clicked on the gap between tiles, so do nothing
            return
        x //= tile_w
        y //= tile_h
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


if __name__ == '__main__':
    # add our settings to the main settings object
    conf.add(Conf)
    # set the window size
    conf.RES_W = (conf.IMG_SIZE[0] + conf.TILE_GAP[0],
                  conf.IMG_SIZE[1] + conf.TILE_GAP[1])
    # make the mouse visible
    conf.MOUSE_VISIBLE[engine.game.get_world_id(Puzzle)] = True
    # initialise the engine
    engine.init()
    # run with a Puzzle as the world
    engine.game.run(Puzzle)
    # now we're finished: quit the engine
    engine.quit()
