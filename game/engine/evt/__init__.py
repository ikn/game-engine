"""Callback-based event and input handling.

---NODOC---

TODO:
    [FIRST]
 - rather than checking requirements for is_mod in places, have .provides['button'], etc. (axis, mod), and Event/EventHandler checks for these
    [ESSENTIAL]
 - some eh method to detect and set current held state of all attached [%%] ButtonInputs - keys use pg.key.get_pressed() (works for mods/locks)
    - careful of _SneakyMultiKbdKey
 - auto joy(/other?) initialisation
 - autocapture/centre mouse?
 - eh.assign_devices
 - eh.grab (and maybe have grab toggle for getting all input for a while)
 - eh.set_deadzones
 - MultiEvent and use thereof (put in evts_by_name, use in conffile)
    [CONFIG]
 - document config format
 - how to do relaxis scale?
 - eh.{load, save}
 - how do domain filenames work?  Do we try loading from a homedir one first, then fall back to the distributed one?  Do we save to the homedir one?
 - mods like '[CTRL] [ALT] kbd a' - device omitted in modifier when same as main button - device IDs omitted since must be the same
    - and then put :mod:`game` keys in a config string
 - deadzones aren't per-input - can do per-device/axis or overall?
 - can omit axis-as-button thresholds and deadzones (global definitions in config file?)
    [FUTURE]
 - joy ball (seems like RelAxisInput, but need a pad with a ball to test)
 - eh.*monitor_deadzones
 - Scheme [NOTE]
 - tools for editing/typing text
 - input recording and playback (allow whitelisting/excluding by registered event name)
 - a way to register new input/event types (consider module data structures)
    - document using __str__ backends
    - working with config [^^]

---NODOC---

"""

from .handler import *
from .inputs import *
from .evts import *
from . import conffile
