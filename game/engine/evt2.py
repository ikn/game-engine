from collections import Sequence

import pygame as pg

# - how do domain filenames work?  Do we try loading from a homedir one first, then fall back to the distributed one?  Do we save to the homedir one?
# - input recording and playback (allow whitelisting/excluding by registered event name)
# - a way to alter loaded events/schemes, and all associated parameters
# - a way to register new input/event types (add to inputs_by_name/evts_by_name)
# - can use part of an input, eg. for a button event, 'pad axis 0:0'; for an axis event, 'pos pad axis 2:1'
#    - might not be >2-component inputs, but can do, eg. for an axis event, 'neg pos pad axis 0:0,1'
# - error on names of events, schemes, domains clashing
# - some eh method to detect and set current held state of all attached ButtonInputs
# - joy hat/ball
# - modifiers - buttons, both for buttons and axes

evt_component_names = {
    1: ('button',),
    2: ('neg', 'pos'),
    4: ('left', 'right', 'up', 'down')
}

DOWN = 0
UP = 1
HELD = 2
REPEAT = 3


class Input (object):
    invalid_device_id = -1
    device_var = None

    def __init__ (self, *pgevts):
        self.evt = None
        pgevts = set(pgevts)
        if hasattr(self, 'pgevts'):
            pgevts.update(self.pgevts)
        self.filters = {}
        if pgevts:
            self.filters['type'] = pgevts
        self._device_assigned = self.device_var is None

    def handle (self, pgevt):
        if not self._device_assigned:
            raise RuntimeError('an Input cannot be used if its device ID ' \
                               'corresponds to an unassigned variable')
        return False

    def filter (self, attr, *vals, **kw):
        # note cannot filter for None (have a module-wide UNFILTERABLE?)
        refilter = kw.get('refilter', False)
        if not vals:
            if refilter:
                # refilter to nothing, ie. remove all filtering
                self.unfilter(attr)
            # else nothing to do
            return self
        eh = None if self.evt is None or self.evt.eh is None else self.evt.eh
        if eh is not None:
            eh._rm_inputs(self)
        if refilter:
            self.filters[attr] = set(vals)
        else:
            self.filters.setdefault(attr, set()).update(vals)
        if eh is not None:
            eh._add_inputs(self)
        return self

    def unfilter (self, attr, *vals):
        if attr not in self.filters:
            return self
        eh = None if self.evt is None or self.evt.eh is None else self.evt.eh
        if eh is not None:
            eh._rm_inputs(self)
        got = self.filters[attr]
        if vals:
            got.difference_update(vals)
            if not got:
                del self.filters[attr]
        else:
            # remove all
            del self.filters[attr]
        if eh is not None:
            eh._add_inputs(self)
        return self

    def set_device_ids (self, ids):
        if hasattr(self, 'device_id_attr'):
            attr = self.device_id_attr
            if ids is True:
                self.filters.pop(attr, None)
            else:
                if ids is False:
                    ids = (self.invalid_device_id,)
                elif not isinstance(ids, Sequence):
                    ids = (ids,)
                self.filter(attr, *ids, refilter = True)
        else:
            raise TypeError('this Input type doesn\'t support device IDs')


class BasicInput (Input):
    def __init__ (self, *pgevts):
        Input.__init__(self, *pgevts)
        self.pgevts = []

    def handle (self, pgevt):
        Input.handle(self, pgevt)
        self.pgevts.append(pgevt)
        return True

    def reset (self):
        self.pgevts = []


class ButtonInput (Input):
    components = 1

    def __init__ (self):
        self.btnevts = []
        self.held = False

    def down (self):
        self.btnevts.append(DOWN)
        self.held = True

    def up (self):
        self.btnevts.append(UP)
        self.held = False

    def reset (self):
        self.btnevts = []


class KbdKey (ButtonInput):
    device = 'kbd'
    name = 'key'
    pgevts = (pg.KEYDOWN, pg.KEYUP)
    # use filtering somehow - to require pgevent.key == self.key

    def handle (self, pgevt):
        if pgevt.type == pg.KEYDOWN:
            self.down()
        else:
            self.up()


class MouseButton (ButtonInput):
    device = 'mouse'
    name = 'button'
    pgevts = (pg.MOUSEBUTTONDOWN, pg.MOUSEBUTTONUP)


class PadButton (ButtonInput):
    device = 'pad'
    name = 'button'
    device_id_attr = 'joy'
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
    device_id_attr = 'joy'
    pgevts = (pg.JOYAXISMOTION,)


class Event (object):
    input_types = BasicInput
    def __init__ (self, *inputs):
        self.eh = None
        self.inputs = set()
        self.add(*inputs)
        self.cbs = set()

    def add (self, *inputs):
        types = self.input_types
        self_add = self.inputs.add
        eh_add = None if self.eh is None else self.eh._add_inputs
        for i in inputs:
            if not isinstance(i, types):
                raise TypeError('{0} events only accept inputs of type {1}' \
                                .format(type(self).__name__,
                                        tuple(t.__name__ for t in types)))
            self_add(i)
            i.evt = self
            if eh_add is not None:
                eh_add(i)

    def rm (self, *inputs):
        pass

    def cb (self, *cbs):
        self.cbs.update(cbs)
        return self

    def respond (self):
        # maybe wrap with something else that handles the reset()
        cbs = self.cbs
        for i in self.inputs:
            for pgevt in i.pgevts:
                for cb in cbs:
                    cb(pgevt)
            i.reset()


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


class EventHandler (dict):
    # is {name: Event|Scheme}
    def __init__ (self):
        self._unnamed = set()
        self._inputs = set()
        self._filtered_inputs = ('type', {None: set()})

    def __contains__ (self, item):
        # can be event, scheme or name thereof
        return dict.__contains__(self, item) or item in self._unnamed

    def __setitem__ (self, item, val):
        self.add(**{item: val})

    def __delitem__ (self, item):
        self.rm(item)

    def add (self, *evts, **named_evts):
        """add(*evts, **named_evts, domain = None)"""
        # can call with existing event to change domain; error if name exists
        # events may be (*(pgevts|cbs)) to create an Event that just passes the pgevt to the cbs
        # returns list of created events for positional args
        unnamed = self._unnamed
        if 'domain' in named_evts:
            domain = named_evts['domain']
            if isinstance(domain, basestring):
                del named_evts['domain']
            else:
                domain = None
        else:
            domain = None
        # TODO: use domain
        for evts in (((None, evt) for evt in evts), named_evts.iteritems()):
            for name, evt in evts:
                if not isinstance(evt, Event): # TODO: also Scheme
                    # got (possibly mixed) list of pgevts/cbs
                    pgevts = []
                    cbs = []
                    for item in evt:
                        (cbs if callable(item) else pgevts).append(item)
                    evt = Event(BasicInput(*pgevts)).cb(*cbs)
                if evt.eh is not None:
                    if evt.eh is self:
                        # already own this event
                        prev_name = evt._regname
                        if name != prev_name:
                            # change registered name
                            # TODO: maybe need to let Scheme know about this
                            if prev_name is None:
                                unnamed.remove(evt)
                            else:
                                dict.__delitem__(self, prev_name)
                            evt._regname = name
                            if name is None:
                                unnamed.add(evt)
                            else:
                                dict.__setitem__(self, name, evt)
                    else:
                        # owned by another handler
                        raise RuntimeError('an Event should not be added to ' \
                                           'more than one EventHandler')
                else:
                    # new event
                    evt.eh = self
                    evt._regname = name
                    if name is None:
                        unnamed.add(evt)
                    else:
                        dict.__setitem__(self, name, evt)
                    self._add_inputs(*evt.inputs)

    def rm (self, *evts):
        # can be instances or names; if evt, call ._unset_eh
        unnamed = self._unnamed
        # TODO: use domain
        for evt in evts:
            if isinstance(evt, basestring):
                evt = self[evt] # raises KeyError
            if evt.eh is self:
                evt.eh = None
                if evt._regname is None:
                    unnamed.remove(evt)
                else:
                    dict.__delitem__(self, evt._regname)
                evt._regname = None
                self._rm_inputs(*evt.inputs)
            else:
                raise KeyError(evt)

    def _prefilter (self, filtered, filters, i):
        attr, filtered = filtered
        if attr in filters:
            vals = filters[attr] # Input guarantees that this is non-empty
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
                    for attr, vals in filters.iteritems():
                        new_filtered = (attr, {None: new_filtered})
                    filtered[val] = new_filtered
                    prefilter = self._prefilter
                    for i in child:
                        prefilter(new_filtered, i.filters, i)

    def _add_inputs (self, *inputs):
        add = self._inputs.add
        prefilter = self._prefilter
        filtered = self._filtered_inputs
        for i in inputs:
            add(i)
            prefilter(filtered, i.filters, i)

    def _rm_inputs (self, *inputs):
        pass

    def update (self):
        all_inputs = self._filtered_inputs
        changed = set()
        for pgevt in pg.event.get():
            inputs = all_inputs
            while isinstance(inputs, tuple):
                attr, inputs = inputs
                val = getattr(pgevt, attr)
                if val in inputs:
                    inputs = inputs[val]
                else:
                    inputs = inputs[None]
            for i in inputs:
                if i.handle(pgevt):
                    changed.add(i.evt)
        for evt in changed:
            evt.respond()

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
