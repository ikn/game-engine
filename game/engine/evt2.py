import pygame as pg

# - how do domain filenames work?  Do we try loading from a homedir one first, then fall back to the distributed one?  Do we save to the homedir one?
# - input recording and playback
# - a way to alter loaded events/schemes, and all associated parameters
# - a way to register new event types
# - can use part of an input, eg. for a button event, 'pad axis 0:0'; for an axis event, 'pos pad axis 2:1'
#    - might not be >2-component inputs, but can do, eg. for an axis event, 'neg pos pad axis 0:0,1'
# - error on names of events, schemes, domains clashing

evt_component_names = {
    1: ('button',),
    2: ('neg', 'pos'),
    4: ('left', 'right', 'up', 'down')
}


class Input (object):
    # .device_id: number, or string for variable
    def handle (self, pgevt):
        pass


class ButtonInput (Input):
    components = 1

    def down (self):
        pass

    def up (self):
        pass


class KbdKey (ButtonInput):
    device = 'kbd'
    name = 'key'
    pgevts = (pg.KEYDOWN, pg.KEYUP)


class MouseButton (ButtonInput):
    device = 'mouse'
    name = 'button'
    pgevts = (pg.MOUSEBUTTONDOWN, pg.MOUSEBUTTONUP)


class PadButton (ButtonInput):
    device = 'pad'
    name = 'button'
    pgevts = (pg.JOYBUTTONDOWN, pg.JOYBUTTONUP)


class AxisInput (Input):
    components = 2


class MouseAxis (AxisInput):
    device = 'mouse'
    name = 'axis'
    pgevts = (pg.MOUSEMOTION,)


class PadAxis (AxisInput):
    device = 'pad'
    name = 'axis'
    pgevts = (pg.JOYAXISMOTION,)


class Event (object):
    def cb (self, *cbs):
        pass

    def handle (self, pgevt):
        # store data from event if relevant; this class just calls callbacks with pgevt
        pass

    def respond (self):
        # parse stored data, call callbacks; this class does nothing
        pass


class MultiEvent (Event):
    # to get cb args, calls static method _merge_args with cb args for each Event
    pass


class Button (Event):
    name = 'button'
    components = 1
    input_types = (ButtonInput, AxisInput)


class Button2 (MultiEvent):
    child = Button
    multiple = 2


class Button4 (MultiEvent):
    child = Button
    multiple = 4


class Axis (Event):
    name = 'axis'
    components = 2
    input_types = (ButtonInput, AxisInput)


class Axis2 (MultiEvent):
    child = Axis
    multiple = 2


class Relaxis (Event):
    # each input takes a scaling argument, and mouse events have no limits like with Axis
    name = 'relaxis'
    components = 2
    inputs = (ButtonInput, AxisInput)


class Relaxis2 (MultiEvent):
    child = Relaxis
    multiple = 2


class EventHandler (object):
    def __contains__ (self, item):
        # can be event, scheme or name thereof
        pass

    def __getitem__ (self, item):
        pass

    def __setitem__ (self, item, val):
        pass

    def __delitem__ (self, item):
        pass

    def add (self, *evts, **named_evts):
        # kwargs contains domain=None
        # can call with existing event to change domain; error if name exists
        # events may be (pgevt, *cbs) to create an Event that just passes the pgevt to the cbs
        # returns list of created events for positional args
        # detect if domain kwarg was meant to be domain or event by its type
        pass

    def rm (self, *evts):
        # can be instances or names
        pass

    def load (self, filename, domain = None):
        pass

    def save (self, filename, domain):
        # save everything in the domain to file
        pass

    def unload(self, domain):
        pass

    def disable (self, domain):
        pass

    def enable (self, domain):
        pass

    def assign_devices (**devices):
        # takes {varname: devices}, devices False for none, True for all, device or list of devices
        pass

    def grab (self, cb, *types):
        # grabs next 'on'-type event from given devices/types and passes it to cb
        # types are device name or (device, type_name)
        pass

    def monitor_deadzones (self):
        pass

    def stop_monitor_deadzones (self):
        # returns {(device, id, *args): deadzone}, args is axis for pad
        # can register other deadzone events?
        pass

    def set_deadzones (self, deadzones):
        # takes stop_monitor_deadzones result
        pass


#: A ``{cls.name: cls}`` dict of usable named :class:`Event` subclasses.
evts_by_name = dict((evt.name, name) for evt in vars()
                    if isinstance(evt, Event) and hasattr(evt, 'name'))
#: A ``{cls.device: {cls.name: cls}}`` dict of usable :class:`Input`
#: subclasses.
inputs_by_name = {}
for i in dict(vars()): # copy or it'll change size during iteration
    if isinstance(i, Input) and hasattr(i, name):
        inputs_by_name.setdefault(i.device, {})[i.name] = i
del i
