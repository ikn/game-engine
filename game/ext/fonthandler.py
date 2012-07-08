"""Font handler by J.

The Fonts class in this module can serve as a font cache, but the real point of
this is to render multiline text with alignment and shadow and stuff.

Release: 2.

Licensed under the GNU General Public License, version 3; if this was not
included, you can find it here:
    http://www.gnu.org/licenses/gpl-3.0.txt

"""

import pygame

class Fonts (object):
    """Collection of pygame.font.Font instances.

    CONSTRUCTOR

Fonts(font_dir = '')

font_dir: directory to find fonts - so you can just pass the font's filename
          when adding a font.

    METHODS

add
text

    ATTRIBUTES

font_dir: as given.
fonts: (font: Font instance) dict of loaded fonts, where font is as given to
       Fonts.add.

"""

    def __init__ (self, font_dir = ''):
        self.font_dir = font_dir
        self.fonts = {}

    def add (self, font, force_reload = False):
        """Load a font and add it to the collection.

add(font, force_reload = False) -> Font_instance

font: (filename, size, is_bold) tuple, where the arguments are as taken by
      pygame.font.Font and filename is appended to this Fonts instance's
      font_dir attribute.

Font_instance: the created pygame.font.Font instance.

"""
        font = tuple(font)
        if force_reload or font not in self.fonts:
            fn, size, bold = font
            self.fonts[font] = pygame.font.Font(self.font_dir + fn, int(size),
                                                bold = bold)
        return self.fonts[font]

    def text (self, font, text, colour, shadow = None, width = None, just = 0,
              minimise = False, line_spacing = 0, aa = True, bg = None):
        """Render text from a font.

text(font, text, colour[, shadow][, width], just = 0, minimise = False,
     line_spacing = 0, aa = True[, bg]) -> (surface, lines)

font: (font name, size, is_bold) tuple.
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
        font = tuple(font)
        size = int(font[1])
        self.add(font)
        font, lines = self.fonts[font], []
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
        h = (line_spacing + size) * (len(lines) - 1) + font.size(lines[-1])[1]
        surface = pygame.Surface((width + offset[0], h + offset[1]))
        if bg is None:
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
                    if bg is None:
                        s = font.render(line, aa, colour)
                    else:
                        s = font.render(line, aa, colour, bg)
                    if just == 2:
                        surface.blit(s, (width - s.get_width() + o[0],
                                         h + o[1]))
                    elif just == 1:
                        surface.blit(s, ((width - s.get_width()) / 2 + o[0],
                                         h + o[1]))
                    else:
                        surface.blit(s, (o[0], h + o[1]))
                h += size + line_spacing
        return surface, num_lines