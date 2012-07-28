import conf

class Level (object):
    def __init__ (self, game, event_handler):
        self.game = game
        self.n = 0

    def update (self):
        self.n += 1
        print self.n

    def draw (self, screen):
        if self.dirty:
            self.dirty = False
            return True
        else:
            return False