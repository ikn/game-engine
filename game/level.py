import conf

class Level:
    def __init__ (self, game, event_handler):
        self.game = game
        self.event_handler = event_handler
        self.frame = conf.FRAME

    def update (self):
        pass

    def draw (self, screen):
        return True
