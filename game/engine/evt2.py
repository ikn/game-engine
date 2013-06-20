from collections import Sequence

import pygame as pg

# - tools for editing/typing text
# - how do domain filenames work?  Do we try loading from a homedir one first, then fall back to the distributed one?  Do we save to the homedir one?
# - input recording and playback (allow whitelisting/excluding by registered event name)
# - a way to register new input/event types (add to inputs_by_name/evts_by_name)
# - can use part of an input, eg. for a button event, 'pad axis 0:0'; for an axis event, 'pos pad axis 2:1'
#    - might not be >2-component inputs, but can do, eg. for an axis event, 'neg pos pad axis 0:0,1'
# - error on names of events, schemes, domains clashing
# - some eh method to detect and set current held state of all attached ButtonInputs - keys use pg.key.get_pressed() (works for mods/locks) (careful of _SneakyMultiKbdKey)
# - joy hat/ball
# - auto joy(/other?) initialisation?
# - printable input names (including mods)
# - mods in config file (like '[CTRL] [ALT] kbd a' - device omitted in modifier when same as main button - varnames omitted since must be the same)
# - in config file, can omit axis-as-button thresholds and deadzones (global definitions in config file?)

# - domains
# - axis inputs
# - axis events

evt_component_names = {
    1: ('button',),
    2: ('neg', 'pos'),
    4: ('left', 'right', 'up', 'down')
}

DOWN = 1
UP = 2
HELD = 4
REPEAT = 8


class Input (object):
    device = None
    invalid_device_id = -1

    def __init__ (self, *pgevts):
        self.device_var = None
        self.evt = None
        pgevts = set(pgevts)
        if hasattr(self, 'pgevts'):
            pgevts.update(self.pgevts)
        self.filters = {}
        if pgevts:
            self.filters['type'] = pgevts
        self._device_id = None

    def handle (self, pgevt):
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

    @property
    def device_id (self):
        return self._device_id

    @device_id.setter
    def device_id (self, device_id):
        if hasattr(self, 'device_id_attr'):
            if device_id is None:
                ids = (self.invalid_device_id,)
            else:
                ids = (device_id,)
            self.filter(self.device_id_attr, *ids, refilter = True)
            self._device_id = device_id
        else:
            raise TypeError('this Input type doesn\'t support device IDs')


class BasicInput (Input):
    def __init__ (self, pgevt):
        Input.__init__(self, pgevt)
        self.pgevts = []

    def handle (self, pgevt):
        Input.handle(self, pgevt)
        self.pgevts.append(pgevt)
        return True

    def reset (self):
        self.pgevts = []


class ButtonInput (Input):
    components = 1

    def __init__ (self, button = None, mods = (), device_id = None):
        Input.__init__(self)
        self.held = False
        self.is_mod = False
        if hasattr(self, 'button_attr'):
            if button is None:
                raise TypeError('expected button argument')
            self.filter(self.button_attr, button)
            self.button = button
        if isinstance(mods, Input):
            mods = (mods,)
        mod_args = mods
        mods = []
        for m in mod_args:
            if isinstance(m, ButtonInput):
                mods.append(m)
            else:
                mods.extend(m)
        if any(m.mods for m in mods):
            raise ValueError('modifiers may not have modifiers')
        ds = self.mod_devices
        if any(m.device not in ds for m in mods):
            raise TypeError(
                'the modifier {0} is for device {1}, which is not ' \
                'compatible with {2} instances'.format(m, m.device,
                                                       type(self).__name__)
            )
        for m in mods:
            m.is_mod = self
        self.mods = mods
        if hasattr(self, 'device_id_attr'):
            self.device_id = device_id

    def down (self):
        self.held = True
        if not self.is_mod:
            assert self.evt is not None
            return self.evt.down()
        return False

    def up (self):
        if self.held:
            self.held = False
            if not self.is_mod:
                assert self.evt is not None
                return self.evt.up()
        return False

    def handle (self, pgevt):
        rtn = Input.handle(self, pgevt)
        if hasattr(self, 'down_pgevts'):
            if pgevt.type in self.down_pgevts:
                return self.down() or rtn
            else:
                return self.up() or rtn
        else:
            return rtn


class KbdKey (ButtonInput):
    device = 'kbd'
    name = 'key'
    pgevts = (pg.KEYDOWN, pg.KEYUP)
    button_attr = 'key'
    down_pgevts = (pg.KEYDOWN,)
    mod_devices = ('kbd',)


class _SneakyMultiKbdKey (KbdKey):
    def __init__ (self, button, *buttons):
        KbdKey.__init__(self, buttons[0])
        self.filter(self.button_attr, *buttons[1:])
        self.button = button
        self._held = dict.fromkeys(buttons, False)

    def handle (self, pgevt):
        self._held[pgevt.key] = pgevt.type in self.down_pgevts
        self.held = any(self._held.itervalues())
        return False


class MouseButton (ButtonInput):
    device = 'mouse'
    name = 'button'
    pgevts = (pg.MOUSEBUTTONDOWN, pg.MOUSEBUTTONUP)
    button_attr = 'button'
    down_pgevts = (pg.MOUSEBUTTONDOWN,)
    mod_devices = ('kbd', 'mouse')


class PadButton (ButtonInput):
    device = 'pad'
    name = 'button'
    pgevts = (pg.JOYBUTTONDOWN, pg.JOYBUTTONUP)
    device_id_attr = 'joy'
    button_attr = 'button'
    down_pgevts = (pg.JOYBUTTONDOWN,)
    mod_devices = ('pad',)


class AxisInput (Input):
    components = 2

    def __init__ (self, axis = None, deadzone = 0, device_id = None):
        Input.__init__(self)
        self.pos = 0
        if hasattr(self, 'axis_attr'):
            if axis is None:
                raise TypeError('expected axis argument')
            self.filter(self.axis_attr, axis)
            self.axis = axis
        self.deadzone = deadzone
        if hasattr(self, 'device_id_attr'):
            self.device_id = device_id
        print self.filters

    def handle (self, pgevt):
        rtn = Input.handle(self, pgevt)
        if hasattr(self, 'axis_val_attr'):
            pos = getattr(pgevt, self.axis_val_attr)
            sgn = 1 if pos > 0 else -1
            dz = self.deadzone
            pos = sgn * (1 - dz) * max(sgn * pos - dz, 0)
            if pos != self.pos:
                self.pos = pos
                return True
        else:
            return rtn


class PadAxis (AxisInput):
    device = 'pad'
    name = 'axis'
    device_id_attr = 'joy'
    pgevts = (pg.JOYAXISMOTION,)
    axis_attr = 'axis'
    axis_val_attr = 'value'


class Relaxis2Input (Input):
    components = 4

    def __init__ (self):
        # (max_x, max_y)
        self.threshold = threshold


class MouseAxis (Relaxis2Input):
    device = 'mouse'
    name = 'axis'
    pgevts = (pg.MOUSEMOTION,)


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
            if i.evt is not self:
                if i.evt is not None:
                    i.evt.rm(i)
                self_add(i)
                i.evt = self
                if eh_add is not None:
                    eh_add(i)

    def rm (self, *inputs):
        self_rm = self.inputs.rm
        eh_rm = None if self.eh is None else self.eh._rm_inputs
        for i in inputs:
            if i.evt is self:
                # not necessary, but a good sanity check
                assert i in self.inputs
                self_rm(i)
                i.evt = None
                if eh_rm is not None:
                    eh_rm(i)
            else:
                raise KeyError(i)

    def cb (self, *cbs):
        self.cbs.update(cbs)
        return self

    def respond (self, changed):
        if changed:
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
    # TODO: work for AxisInput too - also calls some function of this class
    name = 'button'
    components = 1
    input_types = (ButtonInput, AxisInput)

    def __init__ (self, *items, **kw):
        modes = 0
        inputs = []
        for item in items:
            if isinstance(item, int):
                modes |= item
            else:
                inputs.append(item)
        Event.__init__(self, *inputs)
        self.modes = modes
        self._downevts = self._upevts = 0
        self.initial_delay = kw.get('initial_delay')
        self.repeat_delay = kw.get('repeat_delay')
        if modes & REPEAT and (self.initial_delay is None or
                               self.repeat_delay is None):
            raise TypeError('initial_delay and repeat_delay arguments are ' \
                            'required if given the REPEAT mode')
        self._repeating = False

    def down (self):
        self._downevts += 1
        return True

    def up (self):
        self._upevts += 1
        if self.modes & REPEAT and not any(i.held for i in self.inputs):
            # stop repeating if let go of all buttons at any point in any frame
            self._repeating = False
        return True

    def respond (self, changed):
        modes = self.modes
        if modes & (HELD | REPEAT):
            held = any(i.held for i in self.inputs)
        if not changed and not held:
            return
        evts = {}
        if modes & DOWN:
            evts[DOWN] = self._downevts
        if modes & UP:
            evts[UP] = self._upevts
        self._downevts = self._upevts = 0
        if modes & HELD:
            evts[HELD] = held
        if modes & REPEAT:
            n_repeats = 0
            if self._repeating:
                if held:
                    # continue repeating
                    if self.eh is None:
                        raise RuntimeError('cannot respond properly if not ' \
                                           'attached to an EventHandler')
                    t = self._repeat_remain
                    t -= self.eh.scheduler.frame
                    while t < 0:
                        n_repeats += 1
                        t += self.repeat_delay
                    self._repeat_remain = t
                else:
                    # stop reapeating
                    self._repeating = False
            elif held:
                # start repeating
                self._repeating = True
                self._repeat_remain = self.initial_delay
            evts[REPEAT] = n_repeats
        if any(evts.itervalues()):
            for cb in self.cbs:
                cb(evts)


class Button2 (MultiEvent):
    child = Button
    multiple = 2


class Button4 (MultiEvent):
    child = Button
    multiple = 4


class Axis (Event):
    name = 'axis'
    components = 2
    input_types = (ButtonInput, AxisInput, Relaxis2Input)

    def __init__ (self, *args):
        Event.__init__(self, *args)
        self._pos = 0

    def respond (self, changed):
        if changed:
            self._pos = pos = min(1, max(-1, sum(i.pos for i in self.inputs)))
        else:
            pos = self._pos
        for cb in self.cbs:
            cb(pos)


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
    def __init__ (self, scheduler):
        self.scheduler = scheduler
        self._named = set()
        self._unnamed = set()
        self._inputs = set()
        self._filtered_inputs = ('type', {None: set()})
        self._mods = {}

    def __contains__ (self, item):
        # can be event, scheme or name thereof
        return dict.__contains__(self, item) or item in self._named or \
               item in self._unnamed

    def __setitem__ (self, item, val):
        self.add(**{item: val})

    def __delitem__ (self, item):
        self.rm(item)

    def add (self, *evts, **named_evts):
        """add(*evts, **named_evts, domain = None)"""
        # TODO: use domain (can call with existing event to change domain)
        created = []
        named = self._named
        unnamed = self._unnamed
        if 'domain' in named_evts:
            domain = named_evts['domain']
            if isinstance(domain, basestring):
                del named_evts['domain']
            else:
                domain = None
        else:
            domain = None
        for evts in (((None, evt) for evt in evts), named_evts.iteritems()):
            for name, evt in evts:
                if not isinstance(evt, Event): # TODO: also Scheme
                    # got (possibly mixed) list of pgevts/cbs
                    pgevts = []
                    cbs = []
                    for item in evt:
                        (cbs if callable(item) else pgevts).append(item)
                    inputs = [BasicInput(pgevt) for pgevt in pgevts]
                    evt = Event(*inputs).cb(*cbs)
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
                                named.remove(evt)
                                dict.__delitem__(self, prev_name)
                            evt._regname = name
                            if name is None:
                                unnamed.add(evt)
                            else:
                                named.add(evt)
                                dict.__setitem__(self, name, evt)
                    else:
                        # owned by another handler
                        raise RuntimeError('an Event should not be added to ' \
                                           'more than one EventHandler')
                else:
                    # new event
                    evt.eh = self
                    evt._changed = False
                    evt._regname = name
                    if name is None:
                        unnamed.add(evt)
                        created.append(evt)
                    else:
                        named.add(evt)
                        dict.__setitem__(self, name, evt)
                    self._add_inputs(*evt.inputs)
        return created

    def rm (self, *evts):
        named = self._named
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
                    named.remove(evt)
                    dict.__delitem__(self, evt._regname)
                evt._regname = None
                self._rm_inputs(*evt.inputs)
            else:
                raise KeyError(evt)

    def _prefilter (self, filtered, filters, i):
        attr, filtered = filtered
        filters = dict(filters)
        # Input guarantees that this is non-empty
        vals = filters.pop(attr, (None,))
        for val in vals:
            if val in filtered:
                child = filtered[val]
            else:
                # create new branch
                filtered[val] = child = set()
            # add input to child
            if isinstance(child, tuple):
                self._prefilter(child, filters, i)
            else:
                # reached the end of a branch: child is a set of inputs
                if filters:
                    # create new levels for each remaining filter
                    for attr, vals in filters.iteritems():
                        child = (attr, {None: child})
                    filtered[val] = child
                    self._prefilter(child, filters, i)
                else:
                    child.add(i)

    def _unprefilter (self, filtered, filters, i):
        attr, filtered = filtered
        # Input guarantees that this is non-empty
        vals = filters.pop(attr, (None,))
        for val in vals:
            assert val in filtered
            child = filtered[val]
            if isinstance(child, tuple):
                self._unprefilter(child, filters, i)
                child = child[1]
            else:
                # reached the end of a branch: child is a set of inputs
                assert i in child
                child.remove(i)
            if not child:
                # child is now empty
                if val is None:
                    # retain the None branch
                    filtered[val] = set()
                else:
                    del filtered[val]
        if attr != 'type' and not any(filtered.itervalues()):
            # all branches are empty (but always retain the 'type' branch)
            filtered.clear()

    def _add_inputs (self, *inputs):
        add = self._inputs.add
        prefilter = self._prefilter
        filtered = self._filtered_inputs
        mods = self._mods
        for i in inputs:
            add(i)
            if isinstance(i, ButtonInput):
                for m in i.mods:
                    added = False
                    for device in i.mod_devices:
                        this_mods = mods.setdefault(device, {}) \
                                        .setdefault(i.device_id, {})
                        if m in this_mods:
                            this_mods[m].add(i)
                        else:
                            this_mods[m] = set((i,))
                            if not added:
                                added = True
                                self._add_inputs(m)
            prefilter(filtered, i.filters, i)

    def _rm_inputs (self, *inputs):
        filtered = self._filtered_inputs
        rm = self._inputs.remove
        mods = self._mods
        for i in inputs:
            assert i in self._inputs
            rm(i) # raises KeyError
            if isinstance(i, ButtonInput):
                for m in i.mods:
                    for device in i.mod_devices:
                        d1 = mods[device]
                        d2 = d1[i.device]
                        d3 = d2[m]
                        assert i in d3
                        d3.remove(i)
                        if not d3:
                            del d3[m]
                            self._rm_inputs(m)
                            if not d2:
                                del d1[i.device]
                                if not d1:
                                    del mods[device]
            self._unprefilter(filtered, i.filters, i)

    def update (self):
        all_inputs = self._filtered_inputs
        changed = set()
        unchanged = set()
        mods = self._mods
        for pgevt in pg.event.get():
            inputs = all_inputs
            while isinstance(inputs, tuple):
                attr, inputs = inputs
                val = getattr(pgevt, attr) if hasattr(pgevt, attr) else None
                inputs = inputs[val if val is None or val in inputs else None]
            for i in inputs:
                if isinstance(i, ButtonInput) and not i.is_mod:
                    assert ids
                    this_mods = i.mods

                    def check_mods ():
                        for device in i.mod_devices:
                            for m in mods.get(device, {}).get(i.device_id, ()):
                                yield m.held == (m in this_mods)

                    if not all(check_mods()):
                        # mods don't match: don't call
                        continue
                if i.handle(pgevt):
                    i.evt._changed = True
        for evts in (self._named, self._unnamed):
            for evt in evts:
                changed = evt._changed
                evt._changed = False
                evt.respond(changed)

    def load (self, filename, domain = None):
        # doesn't add events used in schemes - they _only_ go in the scheme
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
        # takes {varname: device_ids}, device_ids False for none, True for all, id or list of ids
        pass

    def grab (self, cb, *types):
        # grabs next 'on'-type event from given devices/types and passes it to cb
        # types are device name or (device, type_name)
        pass

    def monitor_deadzones (self, *deadzones):
        # takes list of  (device, id, *args); do for all if none given
        pass

    def stop_monitor_deadzones (self):
        # returns {(device, id, *args): deadzone}, args is axis for pad
        # can register other deadzone events?
        pass

    def set_deadzones (self, deadzones):
        # takes stop_monitor_deadzones result
        pass


class mod:
    CTRL = (_SneakyMultiKbdKey(pg.KMOD_CTRL, pg.K_LCTRL, pg.K_RCTRL))
    SHIFT = (_SneakyMultiKbdKey(pg.KMOD_SHIFT, pg.K_LSHIFT, pg.K_RSHIFT))
    ALT = (_SneakyMultiKbdKey(pg.KMOD_ALT, pg.K_LALT, pg.K_RALT))
    META = (_SneakyMultiKbdKey(pg.KMOD_META, pg.K_LMETA, pg.K_RMETA))


#: A ``{cls.device: {cls.name: cls}}`` dict of usable named :class:`Input`
#: subclasses.
inputs_by_name = {}
for i in dict(vars()): # copy or it'll change size during iteration
    if isinstance(i, Input) and hasattr(i, name):
        inputs_by_name.setdefault(i.device, {})[i.name] = i
del i
#: A ``{cls.name: cls}`` dict of usable named :class:`Event` subclasses.
evts_by_name = dict((evt.name, name) for evt in vars()
                    if (isinstance(evt, Event) and hasattr(evt, 'name')) or
                       (isinstance(evt, MultiEvent) and
                        hasattr(evt.child, 'name')))
