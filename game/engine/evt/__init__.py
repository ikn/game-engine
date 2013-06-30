"""Callback-based event and input handling.

---NODOC---

TODO:
    [FIRST]
 - rather than checking requirements for is_mod in places, have .provides['button'], etc. (axis, mod), and Event/EventHandler checks for these
    [ESSENTIAL]
 - autocapture/centre mouse?
 - eh.normalise_buttons() to detect and set current held state of all attached ButtonInputs
    - takes an arg to send through btn.down()s
    - keys use pg.key.get_pressed()
    - refer to it in eh.add(), eh.load(), eh.enable()
    - careful of _SneakyMultiKbdKey and MultiEvent
 - eh.assign_devices
 - eh.grab (and maybe have grab toggle for getting all input for a while)
 - eh.set_deadzones
 - auto joy(/other?) initialisation
    [CONFIG]
 - can do per-device/axis or overall deadzones/thresholds (uses eh.set_deadzones)
 - conffile.generate{,_s}, eh.save{,_s}
 - how do domain filenames work?  Do we try loading from a homedir one first, then fall back to the distributed one?  Do we save to the homedir one?
    [FUTURE]
 - Scheme [NOTE]
 - tools for editing/typing text
 - input recording and playback (allow whitelisting/excluding by domain/registered event name)
 - eh.*monitor_deadzones
 - a way to register new input/event types (consider module data structures)
    - document using __str__ backends
    - working with config
 - joy ball (seems like RelAxisInput, but need a pad with a ball to test)

---NODOC---

"""

from .handler import *
from .inputs import *
from .evts import *
from . import conffile
