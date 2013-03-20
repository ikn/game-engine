import pygame as pg

from conf import conf
import game, world, gm, util, sched, evthandler, mltr

pg.mixer.pre_init(buffer = 1024)

def init ():
    """Initialise the game engine."""
    pg.init()
    if conf.WINDOW_ICON is not None:
        pg.display.set_icon(pg.image.load(conf.WINDOW_ICON))
    if conf.WINDOW_TITLE is not None:
        pg.display.set_caption(conf.WINDOW_TITLE)

def quit ():
    """Uninitialise the game engine."""
    pg.quit()
