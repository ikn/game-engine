"""Callback-based event and input handling.

---NODOC---

TODO:
    [ESSENTIAL]
 - button events should call once per event, not once per frame
    - and multi-button events should do it in order (might interleave between components)
 - eh.grab (and maybe have grab toggle for getting all input for a while)
 - eh.set_deadzones (can set by device var; can pass a default for other devices/ids)
 - auto pad(/other?) initialisation
 - double-click for buttons
    [CONFIG]
 - can do per-device, per-input name or global thresholds/bdy - and make them setters, and provide eh.set_{thresholds,bdys}
 - conffile.generate{,_s}, eh.save{,_s}
 - how do domain filenames work?  Do we try loading from a homedir one first, then fall back to the distributed one?  Do we save to the homedir one?
 - input groups for having the same inputs in different events, eg.

    [next]
        kbd ENTER
        kbd KP_RETURN
        kbd SPACE

    button next DOWN REPEAT .3 .1
        [next]
        kbd RIGHT

    button confirm DOWN
        [next]

    [FUTURE]
 - Scheme [NOTE]
 - generalised clickable things - define a rect (ClickRect, ClickArea subclass), has .click(cb(event_type), events_bitmask), .hover(cb(in/out))
    - have any number of moveable 'cursors' in eh, with .click() and .move(), and can attach these rects to them (or all/a subset of them)
    - can easily attach some event types to these?
 - tools for editing/typing text
 - input recording and playback (allow whitelisting/excluding by domain/registered event name)
 - eh.*monitor_deadzones
 - a way to register new input/event types (consider module data structures)
    - document using __str__ backends
    - working with config
 - joy ball (seems like RelAxisInput, but need a pad with a ball to test)
    - or maybe just do it and include a warning

---NODOC---

"""

from .handler import *
from .inputs import *
from .evts import *
from . import conffile
