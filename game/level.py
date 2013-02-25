from conf import conf
from world import World
import gm


class Level (World):
    def __init__ (self, scheduler, evthandler):
        World.__init__(self, scheduler, evthandler)

    def update (self):
        pass
