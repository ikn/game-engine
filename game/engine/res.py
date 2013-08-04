"""Resource loading and caching."""

"""
 - add to doc/
 - update tutorial to use this instead of conf.GAME.img
 - .register()
 - graphics take optional pool and manager, use 'global'/the game's one by default (search conf.GAME.resources.img)
 - remove Game.fonts, make it load them into the resource manager
    - and simplify mod:txt - maybe make it just a function
 - text, font loaders
    - text can take a font, or font_name as registered with the font loader
    - to make this work, the font loader's args are name[, file, size, is_bold], and mk_key returns name if given no other args, to get used as the cache key
 - limits:
    - .limits: {type: amount}
    - .priorities: {pool: priority} - for determining what to unload if reach limits
    - .set_limits(**{type: amount}) - None for no limit

"""

import pygame as pg

from .conf import conf
from .util import convert_sfc


def load_img (fn):
    """Loader for resources of type ``'img'``.

Takes the filename to load from, under :attr:`conf.IMG_DIR`.

"""
    return convert_sfc(pg.image.load(conf.IMG_DIR + fn))

def mk_img_key (fn):
    """Caching key generator for resources of type ``'img'``."""
    return fn

def measure_img (sfc):
    """Measurement function for resources of type ``'img'``."""
    return img.get_bytesize() * img.get_width() * img.get_height()


class ResourceManager (object):
    """Manage the loading and caching of resources.

Builtin resources loaders are in :attr:`resource_loaders`; to load a resource,
you can use :meth:`load`, or you can do, eg.

::

    manager.img('border.png', pool='gui')

Documentation for builtin loaders is found in the ``load_<loader>`` functions
in this module.

"""

    def __init__ (self):
        #: The resource loaders available to this manager.  This is a
        #: ``{type: (load, mk_key, measure)}`` dict, where ``type`` is the
        #: loader identifier, and ``load``, ``mk_key`` and ``measure`` are as
        #: taken by :meth:`register`.
        self.resource_loaders = {
            'img': (load_img, mk_img_key, measure_img)
        }
        #: The resource pools contained by this manager.  This is a
        #: ``{name: (cache, users)}`` dict, where ``users`` is a set of users
        #: claiming to be using the pool (probably :class:`ResourceProxy`
        #: instances), and ``cache`` is ``{loader: {cache_key: data}}`` giving
        #: the resources cached in the pool.
        self.pools = {}

    def __getattr__ (self, attr):
        if attr in self.resource_loaders:
            # generate and return resource loader wrapper
            return lambda *args, **kw: self.load(attr, *args, **kw)
        else:
            return object.__getattr__(self, attr)

    def load (self, loader, *args, **kw):
        """Load a resource.

load(loader, *args, **kwargs, pool='global') -> data

:arg loader: resource loader to use, as found in :attr:`resource_loaders`.
:arg args: positional arguments to pass to the resource loader.
:arg kwargs: keyword arguments to pass the the resource loader.
:arg pool: keyword-only argument giving the pool to cache the resource in.

:return: the loaded resource data.

This is equivalent to
``getattr(manager, loader)(*args, **kwargs, pool='global')``.

"""
        # TODO: drop least frequently+recently used resources from cache if go over limits (print warnings if this happens often)
        pool = kw.pop('pool', 'global')
        # create pool and cache dicts if they don't exist, since they will soon
        cache = self.pools.setdefault(pool, ({}, set()))[0]
        cache = cache.setdefault(loader, {})
        # retrieve from cache, or load and store in cache
        load, mk_key, measure = self.resource_loaders[loader]
        k = mk_key(*args, **kw)
        if k in cache:
            resource = cache[k]
        else:
            resource = load(*args, **kw)
            cache[k] = resource
        return resource

    def register (self, name, load, mk_key, measure = lambda resource: 1):
        """Register a new resource loader.

register(name, load, mk_key, [, measure])

:arg name: the name to give the loader, as used in :attr:`resource_loaders`;
           must be hashable, and must be a string and a valid variable name if
           you want to be able to load resources like
           ``ResourceManager.img()``.  If already used, the existing loader is
           replaced.
:arg load: a function to load a resource.  Takes whatever arguments are
           necessary (you'll pass these to :meth:`load` or the generated
           dedicated method).
:arg mk_key: a function to generate a hashable caching key for a resource,
             given the same arguments as ``load``.
:arg measure: a function to measure a resource's size.  Takes a resource as
              returned by ``load``, and returns its size as a number.  The
              default is to return ``1`` for any resource.

"""
        pass

    def use (self, pool, user):
        """Add a user to a pool (see :attr:`pools`), if not already added.

The pool need not already exist.

"""
        self.pools.setdefault(pool, ({}, []))[1].add(user)

    def drop (self, pool, user):
        """Drop a user from a pool (see :attr:`pools`), if present.

The pool need not already exist.

"""
        if pool in self.pools:
            cache, users = self.pools[pool]
            try:
                users.remove(user)
            except KeyError:
                pass
            else:
                # remove pool if now empty
                if not cache and not users:
                    del self.pools[pool]
