"""Graphics handling for drawing things.

---NODOC---

TODO:
 - make it possible for GM to have transparent BG (only if orig_sfc has alpha)
 - make GG force same layer/manager/etc., and allow for transforms and movement of the graphics in the same way
 - in graphics, store n (5?) last # frames between changes to the surface (by transform or altering the original)
    - if the average > x or current length < n, do some things:
        - turn opacity into a list of rects the graphic is opaque in (x = 4?)
        - if a Colour, put into blit mode (also do so if transformed in a certain way) (x = 3?)
 - ignore off-screen things
 - if GM is fully dirty or GM.busy, draw everything without any rect checks (but still nothing under opaque)
 - GraphicsManager.offset to offset the viewing window (Surface.scroll is fast?)
    - supports parallax: set to {layer: ratio} or (function(layer) -> ratio)
    - implementation:
        - in first loop, for each graphic, offset _rect by -offset
        - when using, offset old graphic dirty rects by -last_offset, current by -offset
        - after drawing, for each graphic, offset _rect by offset
 - tint transform (as fade, which uses tint with (255, 255, 255, opacity))
 - Graphic subclasses:
Text
Animation(surface | filename[image])
Tilemap
    - need:
        - w, h
        - x, y -> tile_type_id
        - tile_type_id -> tile_data
        - a way of drawing a tile based on tile_data
    (tiles, data = None)
        tiles: (size, surface) | (size, filename[image]) | list
            list: (surface | filename[image] | colour)
            size: tile (width, height) or width = height
            surface/filename[image]: a spritemap
        data: filename[text] | string | list | None (all first tile)
            filename[text] (has no whitespace)/string: whitespace-delimited ids; either also take width, or use \n\r for row delimiters, others for column delimiters
            list: ids; either also take width, or is list of rows

---NODOC---

"""

from container import GraphicsManager, GraphicsGroup
from graphic import Graphic
from graphicsub import Colour

#__all__ = ('Graphic', 'GraphicsManager', 'GraphicsGroup', 'Colour')
