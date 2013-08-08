"""Resource loading and caching."""

"""

TODO:
 - limits:
    - .limits: {type: amount}
    - .priorities: {pool: priority} - for determining what to unload if reach limits
    - .set_limits(**{type: amount}) - None for no limit
    - in .load(), drop least frequently+recently used resources from cache if go over limits (print warnings if this happens often)

"""

import pygame as pg

from .conf import conf
from .util import convert_sfc, normalise_colour


def _unit_measure (resource):
    return 1


def load_img (fn):
    """:class:`ResourceManager` loader for images (``'img'``).

Takes the filename to load from, under :attr:`conf.IMG_DIR`.

"""
    return convert_sfc(pg.image.load(conf.IMG_DIR + fn))


def _mk_img_keys (fn):
    yield fn


def _measure_img (sfc):
    return sfc.get_bytesize() * sfc.get_width() * sfc.get_height()


def load_pgfont (fn, size):
    """:class:`ResourceManager` loader for Pygame fonts (``'pgfont'``).

mk_font_keys(fn, size)

:arg fn: font filename, under :data:`conf.FONT_DIR`.
:arg size: size this font should render at.

"""
    return pg.font.Font(conf.FONT_DIR + fn, size)


def _mk_pgfont_keys (fn, size):
    yield (fn, int(size))


"""
:arg name: if given, it is used as an alternative caching key---so if you know
           a font is cached, you can retrieve it using just the name, omitting
           all other arguments.
"""


def load_text (text, renderer, options={}, **kwargs):
    """:class:`ResourceManager` loader for rendering text (``'text'``).

load_text(text, renderer, options={}, **kwargs) -> (surface, num_lines)

:arg renderer: :class:`text.TextRenderer <engine.text.TextRenderer>` instance
               or the name a renderer is stored under in
               :attr:`Game.text_renderers <engine.game.Game.text_renderers>`.

Other arguments are as taken by and the return value is as given by
:meth:`TextRenderer.render <engine.text.TextRenderer.render>`.

"""
    if isinstance(renderer, basestring):
        renderer = conf.GAME.text_renderers[renderer]
    return renderer.render(text, options, **kwargs)


def _mk_text_keys (text, renderer, options={}, **kwargs):
    if isinstance(renderer, basestring):
        renderer = conf.GAME.text_renderers[renderer]
    opts = renderer.mk_options(options, **kwargs)
    # just use a tuple of arguments, normalised and made hashable
    if opts.get('colour') is not None:
        opts['colour'] = normalise_colour(opts['colour'])
    shadow = opts.get('shadow')
    if shadow is not None:
        shadow = (normalise_colour(shadow[0]), tuple(shadow[1][:2]))
    if opts.get('width') is not None:
        opts['width'] = int(opts['width'])
    if opts.get('minimise') is not None:
        opts['minimise'] = bool(opts['minimise'])
    if opts.get('line_spacing') is not None:
        opts['line_spacing'] = int(opts['line_spacing'])
    if opts.get('aa') is not None:
        opts['aa'] = bool(opts['aa'])
    if opts.get('bg') is not None:
        opts['bg'] = normalise_colour(opts['bg'])
    pad = opts.get('pad')
    if pad is not None:
        if isinstance(pad, int):
            pad = (pad, pad, pad, pad)
        elif len(pad) == 2:
            pad = tuple(pad)
            pad = pad + pad
        else:
            pad = tuple(pad)
    return (text, opts.get('colour'), shadow, opts.get('width'),
            opts.get('just'), opts.get('minimise'), opts.get('line_spacing'),
            opts.get('aa'), opts['bg'], pad)


def _measure_text (text):
    # first element is surface
    return _measure_img(text[0])


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
        # {name: (load, mk_keys, measure)}
        self._loaders = {
            'img': (load_img, _mk_img_keys, _measure_img),
            'pgfont': (load_pgfont, _mk_pgfont_keys, _unit_measure),
            'text': (load_text, _mk_text_keys, _measure_text)
        }
        # {name: (cache, users)}, where cache is {loader: {cache_key: data}}
        # and users is a set
        self._pools = {}

    @property
    def resource_loaders (self):
        """A list of the resource loaders available to this manager."""
        return self._loaders.keys()

    @property
    def pools (self):
        """A list of the resource pools contained by this manager."""
        return self._pools.keys()

    def __getattr__ (self, attr):
        if attr in self._loaders:
            # generate and return resource loader wrapper
            return lambda *args, **kw: self.load(attr, *args, **kw)
        else:
            return object.__getattribute__(self, attr)

    def load (self, loader, *args, **kw):
        """Load a resource.

load(loader, *args, **kwargs, pool=conf.DEFAULT_RESOURCE_POOL,
     force_load=False) -> data

:arg loader: resource loader to use, as found in :attr:`resource_loaders`.
:arg args: positional arguments to pass to the resource loader.
:arg kwargs: keyword arguments to pass the the resource loader.
:arg pool: keyword-only argument giving the pool to cache the resource in.
:arg force_load: whether to bypass the cache and reload the object through
                 ``loader``.

:return: the loaded resource data.

This is equivalent to
``getattr(manager, loader)(*args, **kwargs, pool=conf.DEFAULT_RESOURCE_POOL)``.

"""
        pool = kw.pop('pool', conf.DEFAULT_RESOURCE_POOL)
        force_load = kw.pop('force_load', False)
        # create pool and cache dicts if they don't exist, since they will soon
        cache, users = self._pools.setdefault(pool, ({}, set()))
        cache = cache.setdefault(loader, {})
        # retrieve from cache, or load and store in cache
        load, mk_keys, measure = self._loaders[loader]
        ks = set(mk_keys(*args, **kw))
        if force_load or not ks & set(cache.iterkeys()):
            resource = load(*args, **kw)
            # only cache if the pool has users
            if users:
                for k in ks:
                    cache[k] = resource
        else:
            resource = cache[ks.pop()]
        return resource

    def register (self, name, load, mk_keys, measure=_unit_measure):
        """Register a new resource loader.

register(name, load, mk_keys[, measure])

:arg name: the name to give the loader, as used in :attr:`resource_loaders`;
           must be hashable, and must be a string and a valid variable name if
           you want to be able to load resources like
           ``ResourceManager.img()``.  If already used, the existing loader is
           replaced.
:arg load: a function to load a resource.  Takes whatever arguments are
           necessary (you'll pass these to :meth:`load` or the generated
           dedicated method).
:arg mk_keys: a function to generate hashable caching keys for a resource,
              given the same arguments as ``load``.  It should return an
              iterable object of keys, and the resource will be cached under
              all of them.
:arg measure: a function to measure a resource's size.  Takes a resource as
              returned by ``load``, and returns its size as a number.  The
              default is to return ``1`` for any resource.

"""
        self._loaders[name] = (load, mk_keys, measure)

    def use (self, pool, user):
        """Add a user to a pool, if not already added.

If a pool ever has no users, all resources cached in it are removed.

The pool need not already exist.

"""
        self._pools.setdefault(pool, ({}, set()))[1].add(user)

    def drop (self, pool, user):
        """Drop a user from a pool, if present.

The pool need not already exist.

"""
        if pool in self._pools:
            cache, users = self._pools[pool]
            try:
                users.remove(user)
            except KeyError:
                pass
            else:
                # remove pool if now has no users (even if cached resources
                # remain)
                if not users:
                    del self._pools[pool]

    def pool_users (self, pool):
        """Get a set of users using the given pool."""
        # freeze so can't modify it
        return frozenset(self._pools.get(pool, (None, frozenset()))[1])

    def measure (self, *pools):
        """Measure the resources cached in the given pools.

:return: ``{loader: size}`` dict giving the total size of the resources cached
         for each loader, summed over all pools given.  Missing loaders have no
         cached resources in these pools.

"""
        sizes = {}
        all_pools = self._pools
        for pool in pools:
            if pool in all_pools:
                for loader, cache in all_pools[pool][0].iteritems():
                    measure_fn = self._loaders[loader][2]
                    size = sum(measure_fn(resource)
                               for resource in cache.itervalues())
                    if loader in sizes:
                        sizes[loader] += size
                    else:
                        sizes[loader] = size
        return sizes
