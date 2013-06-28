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
