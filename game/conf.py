import os

from .engine import conf


class Conf (object):
    IDENT = 'game'
    WINDOW_TITLE = ''
    #WINDOW_ICON = os.path.join(conf.IMG_DIR, 'icon.png')
    RES_W = (960, 540)


conf.add(Conf)
