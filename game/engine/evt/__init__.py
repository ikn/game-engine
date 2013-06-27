"""Callback-based event and input handling.

---NODOC---

TODO:
    [FIRST]
 - fix documentation/links
 - rather than checking requirements for is_mod in places, have .provides['button'], etc. (axis, mod), and Event/EventHandler checks for these
    [ESSENTIAL]
 - some eh method to detect and set current held state of all attached [%%] ButtonInputs - keys use pg.key.get_pressed() (works for mods/locks)
    - careful of _SneakyMultiKbdKey
 - auto joy(/other?) initialisation
 - autocapture/centre mouse?
 - eh.assign_devices
 - eh.grab (and maybe have grab toggle for getting all input for a while)
 - eh.set_deadzones
 - MultiEvent and use thereof (put in evts_by_name)
    [CONFIG]
 - how to do relaxis scale?
 - eh.{load, save, unload, disable, enable}
 - how do domain filenames work?  Do we try loading from a homedir one first, then fall back to the distributed one?  Do we save to the homedir one?
 - can use part of an input, eg. for a button event, 'pad axis:0 0'; for an axis event, 'pos pad axis:1 2'
    - might not be >2-component inputs, but can do, eg. for an axis event, 'neg pos pad axis:0,1 0'
 - deadzones aren't per-input - can do per-device/axis or overall?
 - can omit axis-as-button thresholds and deadzones (global definitions in config file?)
 - mods like '[CTRL] [ALT] kbd a' - device omitted in modifier when same as main button - varnames omitted since must be the same
 - document Input.name
 - document data structures used in config file [##]
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
