from conf import conf


class Level (object):
    def __init__ (self, game, event_handler, stop = False):
        self.game = game

    def update (self):
        pass

    def draw (self, screen):
        if self.dirty:
            self.dirty = False
            return True
        else:
            return False