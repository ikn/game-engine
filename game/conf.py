from os import sep

import pygame as pg

from util import dd

# paths
DATA_DIR = ''
IMG_DIR = DATA_DIR + 'img' + sep
SOUND_DIR = DATA_DIR + 'sound' + sep
MUSIC_DIR = DATA_DIR + 'music' + sep
FONT_DIR = DATA_DIR + 'font' + sep

# display
WINDOW_ICON = None #IMG_DIR + 'icon.png'
WINDOW_TITLE = ''
MOUSE_VISIBLE = dd(False) # per-backend
FLAGS = 0
FULLSCREEN = False
RESIZABLE = True # also determines whether fullscreen togglable
RES_W = (960, 540)
RES_F = pg.display.list_modes()[0]
MIN_RES_W = (320, 180)
ASPECT_RATIO = None

# timing
FPS = dd(60) # per-backend

# debug
PROFILE_STATS_FILE = '.profile_stats'
DEFAULT_PROFILE_TIME = 5

# input
KEYS_NEXT = (pg.K_RETURN, pg.K_SPACE, pg.K_KP_ENTER)
KEYS_BACK = (pg.K_ESCAPE, pg.K_BACKSPACE)
KEYS_MINIMISE = (pg.K_F10,)
KEYS_FULLSCREEN = (pg.K_F11, (pg.K_RETURN, pg.KMOD_ALT, True),
                   (pg.K_KP_ENTER, pg.KMOD_ALT, True))
KEYS_LEFT = (pg.K_LEFT, pg.K_a, pg.K_q)
KEYS_RIGHT = (pg.K_RIGHT, pg.K_d, pg.K_e)
KEYS_UP = (pg.K_UP, pg.K_w, pg.K_z, pg.K_COMMA)
KEYS_DOWN = (pg.K_DOWN, pg.K_s, pg.K_o)
KEYS_DIRN = (KEYS_LEFT, KEYS_UP, KEYS_RIGHT, KEYS_DOWN)

# audio
MUSIC_VOLUME = dd(.5) # per-backend
SOUND_VOLUME = .5
EVENT_ENDMUSIC = pg.USEREVENT
SOUNDS = {} # numbers of sound files
SOUND_VOLUMES = {}

# text rendering
USE_FONTS = False
# per-backend, each a {key: value} dict to update fonthandler.Fonts with
REQUIRED_FONTS = dd({})