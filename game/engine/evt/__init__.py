"""Callback-based event and input handling.

---NODOC---

TODO:
    [ESSENTIAL]
 - eh.grab (and maybe have grab toggle for getting all input for a while)
 - eh.detect_pads() (re-initialise already-initialised ones)
 - eh.set_{thresholds,bdys} like deadzones (but also allow global, and same with deadzones)
    - make them setters
    - think of a nicer system for it (some sort of InputFilter, then {filter: value}?)
    [CONFIG]
 - can do (per-device, per-device_id/var or global) deadzones/thresholds/bdy (can already do per-input, right?)
 - conffile.generate{,_s}, eh.save{,_s}
 - domain filenames
    - try loading from a homedir one first, then fall back to the distributed one
    - save to the homedir one
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
 - generalised input areas
    - define a rect (InputRect, InputArea subclass), has .click(cb(event_type), events_bitmask), .hover(cb(in/out))
    - have any number of moveable 'cursors' in eh, with .click(), .move_by(), .move_to, and can attach these areas to all/a subset of them
    - can easily attach some event types to these?  (.click(btn_evt_arg=None), .move_by(relaxis2_evt_arg=None), .move_to(axis2_evt_arg=None))
 - tools for editing/typing text
 - input recording and playback (allow white/blacklisting by domain/registered event name)
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
