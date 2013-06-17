import pygame as pg

# - how do domain filenames work?  Do we try loading from a homedir one first, then fall back to the distributed one?  Do we save to the homedir one?
# - input recording and playback
# - a way to alter loaded events/schemes, and all associated parameters
# - a way to register new event types
# - can use part of an input, eg. for a button event, 'pad axis 0:0'; for an axis event, 'pos pad axis 2:1'
#    - might not be >2-component inputs, but can do, eg. for an axis event, 'neg pos pad axis 0:0,1'
# - error on names of events, schemes, domains clashing
# - some eh method to detect and set current held state of all attached ButtonInputs

evt_component_names = {
    1: ('button',),
    2: ('neg', 'pos'),
    4: ('left', 'right', 'up', 'down')
}


class Input (object):
    # .device_id: as taken by eh.assign_devices, or string for variable

    def __init__ (self):
        if hasattr(self, '_pgevts'):
            self.filters = {'type': set(self._pgevts)}
        else:
            self.filters = {}

    def handle (self, pgevt):
        self.pgevts.append(pgevt)

    def filter (self, attr, *vals):
        self.filters.setdefault(attr, set()).update(vals)
        return self


class ButtonInput (Input):
    components = 1

    def __init__ (self):
        self.held = False

    def down (self):
        self.held = True

    def up (self):
        self.held = False


class KbdKey (ButtonInput):
    device = 'kbd'
    name = 'key'
    _pgevts = (pg.KEYDOWN, pg.KEYUP)
    # use filtering somehow - to require pgevent.key == self.key

    def handle (self, pgevt):
        if pgevt.type == pg.KEYDOWN:
            self.down()
        else:
            self.up()


class MouseButton (ButtonInput):
    device = 'mouse'
    name = 'button'
    _pgevts = (pg.MOUSEBUTTONDOWN, pg.MOUSEBUTTONUP)


class PadButton (ButtonInput):
    device = 'pad'
    name = 'button'
    _pgevts = (pg.JOYBUTTONDOWN, pg.JOYBUTTONUP)


class AxisInput (Input):
    components = 2


class MouseAxis (AxisInput):
    device = 'mouse'
    name = 'axis'
    _pgevts = (pg.MOUSEMOTION,)


class PadAxis (AxisInput):
    device = 'pad'
    name = 'axis'
    _pgevts = (pg.JOYAXISMOTION,)


class Event (object):
    input_types = object
    # event filtering by attributes - equal to, contained in
    # sort filters by the amount they exclude
    # note cannot filter for None
    def __init__ (self):
        self.inputs = set()
        self.filtered_inputs = ('type', {None: set()})
        self._changed = False

    def _prefilter (self, filtered, filters, i):
        attr, filtered = filtered
        if attr in filters:
            vals = filters[attr]
            del filters[attr]
        else:
            vals = (None,)
        for val in vals:
            if val in filtered:
                child = filtered[val]
            else:
                # create new branch
                filtered[val] = child = set((i,))
            if isinstance(child, tuple):
                self._prefilter(child, filters, i)
            else:
                # reached the end of a branch: child is a set of inputs
                child.add(i)
                if filters:
                    # create new levels for each remaining filter
                    new_filtered = set()
                    for attr, vals in reversed(filters.iteritems()):
                        new_filtered = (attr, {None: new_filtered})
                    filtered[val] = new_filtered
                    for i in child:
                        self._prefilter(new_filtered, i.filters, i)

    def add (self, *inputs):
        # calls eh._add_inputs and put all this code and all filtering there;
        # have no Event.handle - that goes in eh too
        types = self.input_types
        filtered = self.filtered_inputs
        for i in inputs:
            if not isinstance(i, types):
                raise TypeError('{0} objects only accept inputs of type {1}' \
                                .format(type(self).__name__,
                                        tuple(t.__name__ for t in types))
            existing.add(i)
            self._prefilter(filtered, dict(i.filters), i)

    def rm (self, *inputs):
        pass

    def cb (self, *cbs):
        pass

    def handle (self, pgevt):
        # store data from event if relevant
        inputs = self.filtered_inputs
        while isinstance(inputs, tuple):
            inputs, attr = inputs
            val = getattr(pgevent, attr)
            if val in inputs:
                val = inputs[val]
            else:
                val = inputs[None]
        if inputs:
            self._changed = True
            for i in inputs:
                i.handle(pgevt)

    def respond (self):
        # parse stored data, call callbacks; this class calls callbacks with pgevt
        if self._changed:
            self._changed = False
            cbs = self.cbs
            for i in self.inputs:
                for pgevt in i.pgevts:
                    for cb in cbs:
                        cb(i)


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


#: A ``{cls.device: {cls.name: cls}}`` dict of usable named :class:`Input`
#: subclasses.
inputs_by_name = {}
for i in dict(vars()): # copy or it'll change size during iteration
    if isinstance(i, Input) and hasattr(i, name):
        inputs_by_name.setdefault(i.device, {})[i.name] = i
del i
#: A ``{cls.name: cls}`` dict of usable named :class:`Event` subclasses.
evts_by_name = dict((evt.name, name) for evt in vars()
                    if isinstance(evt, Event) and hasattr(evt, 'name'))
