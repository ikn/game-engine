"""Multi-line text rendering."""

import pygame as pg

from .conf import conf
from .util import normalise_colour

#: default values for text rendering options
# be sure to update res._mk_text_keys if these change
option_defaults = {
    'colour': '000',
    'shadow': None,
    'width': None,
    'just': 0,
    'minimise': False,
    'line_spacing': 0,
    'aa': True,
    'bg': None,
    'pad': (0, 0, 0, 0)
}


class TextRenderer (object):
    """Render text to a surface.

TextRenderer(font, options={}, resource_pool=conf.DEFAULT_RESOURCE_POOL,
             resource_manager=conf.GAME.resources)

:arg font: font filename to use, under :data:`conf.FONT_DIR`.
:arg options: dict giving rendering parameters.  These act as default values in
              the same argument to :meth:`render`.
:arg resource_pool: :class:`ResourceManager <engine.res.ResourceManager>`
                    resource pool name to cache any loaded Pygame fonts in.
:arg resource_manager: :class:`ResourceManager <engine.res.ResourceManager>`
                       instance to use to load any Pygame fonts.

This is basically a way of storing a number of rendering paramaters for
rendering text by a reference to some name.

"""

    def __init__ (self, font, options={},
                  resource_pool=conf.DEFAULT_RESOURCE_POOL,
                  resource_manager=None):
        self._font = font
        self._defaults = option_defaults.copy()
        self._defaults.update(options)
        self._resource_pool = resource_pool
        self._resource_manager = resource_manager

    def mk_options (self, options={}, **kwargs):
        """Generate a full set of rendering options given an options dict.

mk_options(options={}, **kwargs) -> new_options

Arguments are as taken by :meth:`render`.

:return: The completed dict of rendering options, with defaults filled in.

"""
        opts = self._defaults.copy()
        opts.update(options, **kwargs)
        return opts

    def render (self, text, options={}, **kwargs):
        """Render text to a surface.

render(text, options={}, **kwargs) -> (surface, num_lines)

:arg text: text to render; may contain line breaks to display separate lines.
:arg options: dict giving rendering parameters; those omitted default to the
              value given in the ``options`` argument to the constructor, and
              then the values in :data:`option_defaults`.
:arg kwargs: options can also be passed as keyword arguments, with the option's
             name as the argument's name.  If an option is given both in
             ``options`` and as a keyword argument, the keyword argument takes
             precedence.

Options available:

:arg size: text size, in points.  This is the only required 'option'.
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

"""
        opts = self.mk_options(options, **kwargs)
        if 'size' not in opts:
            raise TypeError('\'size\' rendering option is required')
        if self._resource_manager is None:
            resources = conf.GAME.resources
        else:
            resources = self._resource_manager
        font = resources.pgfont(self._font, opts['size'],
                                pool=self._resource_pool)

        colour = normalise_colour(opts['colour'])
        if opts['shadow'] is None:
            shadow_colour = None
            offset = (0, 0)
        else:
            shadow_colour, offset = opts['shadow']
            shadow_colour = normalise_colour(shadow_colour)
        width = opts['width']
        minimise = opts['minimise']
        line_spacing = opts['line_spacing']
        bg = opts['bg']
        if bg is not None:
            bg = normalise_colour(bg)
        pad = opts['pad']
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
            lines = []
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
        # or fully transparent and want to minimise width
        if (len(lines) == 1 and pad == (0, 0, 0, 0) and
            shadow_colour is None and
            (bg is None or len(bg) == 3 or bg[3] in (0, 255)) and minimise):
            if bg is None:
                sfc = font.render(lines[0], True, colour)
            else:
                sfc = font.render(lines[0], True, colour, bg)
            return (sfc, 1)
        # else create surface to blit all the lines to
        size = font.get_height()
        h = (line_spacing + size) * (len(lines) - 1) + font.size(lines[-1])[1]
        sfc = pg.Surface((width + abs(offset[0]) + pad[0] + pad[2],
                          h + abs(offset[1]) + pad[1] + pad[3]))
        # to get transparency, need to be blitting to a converted surface
        sfc = sfc.convert_alpha()
        sfc.fill((0, 0, 0, 0) if bg is None else bg)
        # render and blit text
        todo = []
        if shadow_colour is not None:
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
                    s = font.render(line, opts['aa'], colour)
                    if opts['just'] == 2:
                        sfc.blit(s, (width - s.get_width() + o[0], h + o[1]))
                    elif opts['just'] == 1:
                        sfc.blit(s, ((width - s.get_width()) // 2 + o[0],
                                    h + o[1]))
                    else:
                        sfc.blit(s, (o[0], h + o[1]))
                h += size + line_spacing
        return (sfc, n_lines)
