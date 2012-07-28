import conf

class Level (object):
    def __init__ (self, game, event_handler):
        self.game = game

    def update (self):
        pass

    def draw (self, screen):
        return True