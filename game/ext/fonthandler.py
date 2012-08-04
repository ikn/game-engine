"""Font handler by Joseph Lansdowne.

The Fonts class in this module can serve as a font cache, but the real point of
this is to render multi-line text with alignment and shadow and stuff.

Release: 3.

Licensed under the GNU General Public License, version 3; if this was not
included, you can find it here:
    http://www.gnu.org/licenses/gpl-3.0.txt

"""

from os.path import isfile, abspath, sep as path_sep, join as join_path

import pygame


class Fonts (dict):
    """Collection of pygame.font.Font instances.

    CONSTRUCTOR

Fonts(*font_dirs)

font_dirs: directories to find fonts - so you can just pass the font's filename
           when adding a font.

Use the dict interface to register fonts:

    fonts['some name'] = (filename, size[, bold = False])

where the arguments are as taken by pygame.font.Font.  All directories in
font_dirs are searched for the filename, unless it contains a path separator.
If so, or if the search yields no results, it is used as the whole path
(absolute or relative).

Retrieving the font again yields a pygame.font.Font instance.  Assigning two
different names to the same set of arguments makes the same instance available
under both without loading the file twice.

    METHODS

render

    ATTRIBUTES

font_dirs: as given.  You may alter this list directly.

"""

    def __init__ (self, *font_dirs):
        self.font_dirs = list(font_dirs)
        self._fonts_by_args = {}

    def __setitem__ (self, name, data):
        # standardise data so we can be sure whether we already have it
        if len(data) == 2:
            fn, size = data
            bold = False
        else:
            fn, size, bold = data
        size = int(size)
        bold = bool(bold)
        # find font file
        orig_fn, fn = fn, None
        temp_fn = None
        if path_sep not in orig_fn:
            # search registered dirs
            for d in self.font_dirs:
                temp_fn = join_path(d, orig_fn)
                if isfile(temp_fn):
                    fn = temp_fn
                    break
        if fn is None:
            # wasn't in any registered dirs
            fn = orig_fn
        fn = abspath(fn)
        # load this font if we haven't already
        data = (fn, size, bold)
        font = self._fonts_by_args.get(data, None)
        if font is None:
            font = pygame.font.Font(fn, size, bold = bold)
            self._fonts_by_args[data] = font
        # store
        dict.__setitem__(self, name, font)

    def render (self, font, text, colour, shadow = None, width = None,
                just = 0, minimise = False, line_spacing = 0, aa = True,
                bg = None):
        """Render text from a font.

render(font, text, colour[, shadow][, width], just = 0, minimise = False,
       line_spacing = 0, aa = True[, bg]) -> (surface, lines)

font: name of a registered font.
text: text to render.
colour: (R, G, B[, A]) tuple.
shadow: to draw a drop-shadow: (colour, offset) tuple, where offset is (x, y).
width: maximum width of returned surface (wrap text).  ValueError is raised if
       any words are too long to fit in this width.
just: if the text has multiple lines, justify: 0 = left, 1 = centre, 2 = right.
minimise: if width is set, treat it as a minimum instead of absolute width
          (that is, shrink the surface after, if possible).
line_spacing: space between lines, in pixels.
aa: whether to anti-alias the text.
bg: background colour; defaults to alpha.

surface: pygame.Surface containing the rendered text.
lines: final number of lines of text.

Newline characters split the text into lines (along with anything else caught
by str.splitlines), as does the width restriction.

"""
        font = self[font]
        lines = []
        if shadow is None:
            offset = (0, 0)
        else:
            shadow_colour, offset = shadow

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

        # if just one line and no shadow, create and return that
        if len(lines) == 1 and shadow is None:
            if bg is None:
                sfc = font.render(lines[0], True, colour)
            else:
                sfc = font.render(lines[0], True, colour, bg)
            return sfc, 1
        # else create surface to blit all the lines to
        size = font.get_height()
        h = (line_spacing + size) * (len(lines) - 1) + font.size(lines[-1])[1]
        surface = pygame.Surface((width + offset[0], h + offset[1]))
        # to get transparency, need to be blitting to a converted surface
        surface = surface.convert_alpha()
        surface.fill((0, 0, 0, 0) if bg is None else bg)
        # render and blit text
        todo = []
        if shadow is not None:
            todo.append((shadow_colour, 1))
        todo.append((colour, -1))
        num_lines = 0
        for colour, mul in todo:
            o = (max(mul * offset[0], 0), max(mul * offset[1], 0))
            h = 0
            for line in lines:
                if line:
                    num_lines += 1
                    s = font.render(line, aa, colour)
                    if just == 2:
                        surface.blit(s, (width - s.get_width() + o[0],
                                         h + o[1]))
                    elif just == 1:
                        surface.blit(s, ((width - s.get_width()) / 2 + o[0],
                                         h + o[1]))
                    else:
                        surface.blit(s, (o[0], h + o[1]))
                h += size + line_spacing
        return (surface, num_lines)