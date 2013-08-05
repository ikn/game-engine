"""Resource loading and caching."""

"""
TODO:
 - add to doc/ (and rebuild all so links work)
 - update tutorial to use this instead of conf.GAME.img
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
    """Loader for resources of type ``'img'``.

Takes the filename to load from, under :attr:`conf.IMG_DIR`.

"""
    return convert_sfc(pg.image.load(conf.IMG_DIR + fn))


def _mk_img_keys (fn):
    yield fn


def _measure_img (sfc):
    return img.get_bytesize() * img.get_width() * img.get_height()


def load_pgfont (fn, size, name=None):
    """Loader for resources of type ``'pgfont'``.

mk_font_keys(fn, size[, name])

:arg fn: font filename, under :data:`conf.FONT_DIR`.
:arg size: size this font should render at.
:arg name: if given, it is used as an alternative caching key---so if you know
           a font is cached, you can retrieve it using just the name, omitting
           all other arguments.

"""
    return pg.font.Font(conf.FONT_DIR + fn, size)


def _mk_pgfont_keys (fn=None, size=None, name=None):
    if fn is None and name is None:
        raise TypeError('name required if fn and size not given')
    if name is not None:
        yield name
    if fn is not None:
        yield (fn, int(size))


def load_text (text, font, colour, shadow=None, width=None, just=0,
               minimise=False, line_spacing=0, aa=True, bg=None,
               pad=(0, 0, 0, 0)):
    """Loader for resources of type ``'text'``.

load_text(text, font, colour[, shadow][, width], just=0, minimise=False,
          line_spacing=0, aa=True[, bg], pad=(0, 0, 0, 0))
    -> (surface, num_lines)

:arg text: text to render.
:arg font: ``pygame.font.Font`` instance, or the name a font is cached under in
           the the default pool.
:arg colour: text colour, as taken by
             :func:`util.normalise_colour <engine.util.normalise_colour>`.
:arg shadow: to draw a drop-shadow: ``(colour, offset)`` tuple, where
             ``offset`` is ``(x, y)``.
:arg width: maximum width of returned surface (wrap text).  ``ValueError`` is
        raised if any words are too long to fit in this width.
:arg just: if the text has multiple lines, justify: ``0`` = left, `1`` =
           centre, ``2`` = right.
:arg minimise: if width is set, treat it as a minimum instead of absolute width
               (that is, shrink the surface after, if possible).
:arg line_spacing: space between lines, in pixels.
:arg aa: whether to anti-alias the text.
:arg bg: background colour (``(R, G, B[, A])`` tuple); defaults to alpha.
:arg pad: ``(left, top, right, bottom)`` padding in pixels.  Can also be one
          number for all sides or ``(left_and_right, top_and_bottom)``.  This
          treats shadow as part of the text.

:return: ``surface`` is the ``pygame.Surface`` containing the rendered text and
         ``num_lines`` is the final number of lines of text.

Line breaks split the text into lines, as does the width restriction.

"""
    if isinstance(font, basestring):
        font = conf.GAME.resources.pgfont(name=font)
    lines = []
    colour = normalise_colour(colour)
    if shadow is None:
        offset = (0, 0)
    else:
        shadow_colour, offset = shadow
        shadow_colour = normalise_colour(shadow_colour)
    if isinstance(pad, int):
        pad = (pad, pad, pad, pad)
    elif len(pad) == 2:
        pad = tuple(pad)
        pad = pad + pad
    else:
        pad = tuple(pad)
    if width is not None:
        width -= pad[0] + pad[2]

    # split into lines
    text = text.splitlines()
    if width is None:
        width = max(font.size(line)[0] for line in text)
        lines = text
        minimise = True
    else:
        for line in text:
            if font.size(line)[0] > width:
                # wrap
                words = line.split(' ')
                # check if any words won't fit
                for word in words:
                    if font.size(word)[0] >= width:
                        e = '\'{0}\' doesn\'t fit on one line'.format(word)
                        raise ValueError(e)
                # build line
                build = ''
                for word in words:
                    temp = build + ' ' if build else build
                    temp += word
                    if font.size(temp)[0] < width:
                        build = temp
                    else:
                        lines.append(build)
                        build = word
                lines.append(build)
            else:
                lines.append(line)
    if minimise:
        width = max(font.size(line)[0] for line in lines)

    # simple case: just one line and no shadow or padding and bg is opaque
    # or fully transparent bg and want to minimise
    if (len(lines) == 1 and pad == (0, 0, 0, 0) and shadow is None and
        (bg is None or len(bg) == 3 or bg[3] in (0, 255)) and minimise):
        if bg is None:
            sfc = font.render(lines[0], True, colour)
        else:
            sfc = font.render(lines[0], True, colour, bg)
        return (sfc, 1)
    # else create surface to blit all the lines to
    size = font.get_height()
    h = (line_spacing + size) * (len(lines) - 1) + font.size(lines[-1])[1]
    sfc = pygame.Surface((width + abs(offset[0]) + pad[0] + pad[2],
                          h + abs(offset[1]) + pad[1] + pad[3]))
    # to get transparency, need to be blitting to a converted surface
    sfc = sfc.convert_alpha()
    sfc.fill((0, 0, 0, 0) if bg is None else bg)
    # render and blit text
    todo = []
    if shadow is not None:
        todo.append((shadow_colour, 1))
    todo.append((colour, -1))
    n_lines = 0
    for colour, mul in todo:
        o = (max(mul * offset[0] + pad[0], 0),
                max(mul * offset[1] + pad[1], 0))
        h = 0
        for line in lines:
            if line:
                n_lines += 1
                s = font.render(line, aa, colour)
                if just == 2:
                    sfc.blit(s, (width - s.get_width() + o[0], h + o[1]))
                elif just == 1:
                    sfc.blit(s, ((width - s.get_width()) // 2 + o[0],
                                 h + o[1]))
                else:
                    sfc.blit(s, (o[0], h + o[1]))
            h += size + line_spacing
    return (sfc, n_lines)


def _mk_text_keys (text, font, colour, shadow=None, width=None, just=0,
                   minimise=False, line_spacing=0, aa=True, bg=None,
                   pad=(0, 0, 0, 0)):
    # just use a tuple of arguments, normalised and made hashable
    if isinstance(font, basestring):
        font = conf.GAME.resources.pgfont(name=font)
    if width is not None:
        width = int(width)
    if shadow is not None:
        shadow = (normalise_colour(shadow[0]), tuple(shadow[1][:2]))
    if bg is not None:
        bg = normalise_colour(bg)
    if isinstance(pad, int):
        pad = (pad, pad, pad, pad)
    elif len(pad) == 2:
        pad = tuple(pad)
        pad = pad + pad
    else:
        pad = tuple(pad)
    return (text, text, normalise_colour(colour), shadow, width, just,
            bool(minimise), int(line_spacing), bool(aa), bg, pad)


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
        #: The resource loaders available to this manager.  This is a
        #: ``{type: (load, mk_keys, measure)}`` dict, where ``type`` is the
        #: loader identifier, and ``load``, ``mk_keys`` and ``measure`` are as
        #: taken by :meth:`register`.
        self.resource_loaders = {
            'img': (load_img, _mk_img_keys, _measure_img),
            'pgfont': (load_pgfont, _mk_pgfont_keys, _unit_measure),
            'text': (load_text, _mk_text_keys, _measure_text)
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
        cache = self.pools.setdefault(pool, ({}, set()))[0]
        cache = cache.setdefault(loader, {})
        # retrieve from cache, or load and store in cache
        load, mk_keys, measure = self.resource_loaders[loader]
        ks = set(mk_keys(*args, **kw))
        if force_load or not ks & set(cache.iterkeys()):
            resource = load(*args, **kw)
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
        self.resource_loaders[name] = (load, mk_keys, measure)

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
