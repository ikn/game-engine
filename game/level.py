from conf import conf
from world import World
import gm


class Level (World):
    def __init__ (self, evthandler):
        World.__init__(self, evthandler)

    def update (self):
        pass
