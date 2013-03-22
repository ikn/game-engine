from sys import argv
import os

if os.name == 'nt':
    # for Windows freeze support
    import pygame._view
from game import engine

from game.level import Level as entry_world

if __name__ == '__main__':
    engine.init()
    if len(argv) > 1 and argv[1] == 'profile':
        from cProfile import run
        from pstats import Stats
        if len(argv) >= 3:
            t = int(argv[2])
        else:
            t = 5
        fn = '.profile_stats'
        run('engine.game.run(entry_world, t = t)', fn, locals())
        Stats(fn).strip_dirs().sort_stats('cumulative').print_stats(30)
        os.unlink(fn)
    else:
        engine.game.run(entry_world)
    engine.quit()
