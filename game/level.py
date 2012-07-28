import conf

class Level (object):
    def __init__ (self, game, event_handler):
        self.game = game
        game.set_overlay((255, 255, 255, 50))
        self.r = (800, 130, 50, 350)
        self.n = 0

    def update (self):
        self.n += 1

    def draw (self, screen):
        if self.dirty:
            screen.fill((0, 0, 0))
            screen.fill((255, 255, 255), (150, 50, 450, 100))
            if self.n % 30 < 15:
                screen.fill((255, 0, 0), self.r)
            self.dirty = False
            return True
        elif self.n % 30 == 0:
            screen.fill((255, 0, 0), self.r)
            return [self.r]
        elif self.n % 30 == 15:
            screen.fill((0, 0, 0), self.r)
            return [self.r]
        else:
            return False