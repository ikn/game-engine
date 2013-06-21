from collections import Sequence

import pygame as pg

"""

TODO:
    [FIRST]
 - nice __str__ for inputs (include mods)
 - joy hat/ball
 - rather than checking requirements for is_mod in places, have .provides['button'], etc. (axis, mod), and Event/EventHandler checks for these
 - domains (eh.{add, rm})
    [ESSENTIAL]
 - how do domain filenames work?  Do we try loading from a homedir one first, then fall back to the distributed one?  Do we save to the homedir one?
 - some eh method to detect and set current held state of all attached ButtonInputs - keys use pg.key.get_pressed() (works for mods/locks)
    - careful of _SneakyMultiKbdKey
 - auto joy(/other?) initialisation
 - autocapture mouse?
 - eh.assign_devices
 - eh.grab (and maybe have grab toggle for getting all input for a while)
 - eh.set_deadzones
 - doc/comments
 - MultiEvent and use thereof
    [CONFIG]
 - eh.{load, save, unload, disable, enable}
 - can use part of an input, eg. for a button event, 'pad axis 0:0'; for an axis event, 'pos pad axis 2:1'
    - might not be >2-component inputs, but can do, eg. for an axis event, 'neg pos pad axis 0:0,1'
 - deadzones aren't per-input - can do per-device/axis or overall?
 - can omit axis-as-button thresholds and deadzones (global definitions in config file?)
 - mods like '[CTRL] [ALT] kbd a' - device omitted in modifier when same as main button - varnames omitted since must be the same
    [FUTURE]
 - eh.*monitor_deadzones
 - Scheme
 - tools for editing/typing text
 - input recording and playback (allow whitelisting/excluding by registered event name)
 - a way to register new input/event types (consider module data structures)

"""


class Input (object):
    components = 0
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

    def __init__ (self, device_id = None, button = None, *mods):
        self._held = [False] * self.components
        self.is_mod = False
        self.btn_components = ()
        Input.__init__(self)
        if hasattr(self, 'device_id_attr'):
            self.device_id = device_id
        if hasattr(self, 'button_attr'):
            if button is None:
                raise TypeError('expected button argument')
            self.filter(self.button_attr, button)
        self.button = button
        mods = list(mods)
        mods_parsed = []
        for m in mods:
            if isinstance(m, Input):
                m = (m, 0)
            elif len(m) == 1:
                m = (m[0], 0)
            if isinstance(m[1], Input):
                mods.extend(m)
            else:
                mods_parsed.append(m)
        if any(m.mods for m, c in mods_parsed):
            raise ValueError('modifiers cannot have modifiers')
        ds = mod_devices[self.device]
        if any(m.device not in ds for m, c in mods_parsed):
            raise TypeError(
                'the modifier {0} is for device {1}, which is not ' \
                'compatible with {2} instances'.format(m, m.device,
                                                       type(self).__name__)
            )
        self.mods = mods = []
        for m, c in mods_parsed:
            if c < 0 or c >= m.components:
                raise ValueError('{0} has no component {1}'.format(m, c))
            m.is_mod = self
            m.btn_components = (c,)
            mods.append(m)

    @property
    def held (self):
        return [self._held[c] for c in self.btn_components]

    def down (self, component = 0):
        self._held[component] = True
        if not self.is_mod:
            if component in self.btn_components:
                assert self.evt is not None
                self.evt.down(self, component)
            return True
        return False

    def up (self, component = 0):
        if self._held[component]:
            self._held[component] = False
            if not self.is_mod:
                if component in self.btn_components:
                    assert self.evt is not None
                    self.evt.up(self, component)
                return True
        return False

    def handle (self, pgevt, mods_match):
        rtn = Input.handle(self, pgevt)
        if hasattr(self, 'down_pgevts'):
            if pgevt.type in self.down_pgevts:
                if mods_match:
                    rtn |= self.down()
            else:
                rtn |= self.up()
        return rtn


class KbdKey (ButtonInput):
    device = 'kbd'
    name = 'key'
    pgevts = (pg.KEYDOWN, pg.KEYUP)
    button_attr = 'key'
    down_pgevts = (pg.KEYDOWN,)

    def __init__ (self, key, *mods):
        ButtonInput.__init__(self, None, key, *mods)


class _SneakyMultiKbdKey (KbdKey):
    def __init__ (self, button, *buttons):
        KbdKey.__init__(self, buttons[0])
        self.filter(self.button_attr, *buttons[1:])
        self.button = button
        self._held_multi = dict.fromkeys(buttons, False)

    def handle (self, pgevt, mods_match):
        self._held_multi[pgevt.key] = pgevt.type in self.down_pgevts
        self._held[0] = any(self._held_multi.itervalues())
        return False


class MouseButton (ButtonInput):
    device = 'mouse'
    name = 'button'
    pgevts = (pg.MOUSEBUTTONDOWN, pg.MOUSEBUTTONUP)
    button_attr = 'button'
    down_pgevts = (pg.MOUSEBUTTONDOWN,)

    def __init__ (self, button, *mods):
        ButtonInput.__init__(self, None, button, *mods)


class PadButton (ButtonInput):
    device = 'pad'
    name = 'button'
    pgevts = (pg.JOYBUTTONDOWN, pg.JOYBUTTONUP)
    device_id_attr = 'joy'
    button_attr = 'button'
    down_pgevts = (pg.JOYBUTTONDOWN,)


class AxisInput (ButtonInput):
    components = 2

    def __init__ (self, device_id = None, axis = None, thresholds = None,
                  *mods):
        self.pos = [0] * self.components
        if mods and thresholds is None:
            raise TypeError('an AxisInput must have thresholds defined to ' \
                            'have modifiers')
        ButtonInput.__init__(self, device_id, None, *mods)
        if hasattr(self, 'axis_attr'):
            if axis is None:
                raise TypeError('expected axis argument')
            self.filter(self.axis_attr, axis)
        self.axis = axis
        self.thresholds = thresholds
        self.deadzone = 0

    @property
    def deadzone (self):
        return self.deadzone

    @deadzone.setter
    def deadzone (self, dz):
        n = self.components / 2
        if isinstance(dz, (int, float)):
            dz = (dz,) * n
        else:
            dz = tuple(dz)
        if len(dz) != n:
            raise ValueError('{0} deadzone must have {1} components'
                             .format(type(self).__name__, n))
        if any(x < 0 or x >= 1 for x in dz):
            raise ValueError('require 0 <= deadzone < 1')
        self._deadzone = dz

    def axis_motion (self, mods_match, axis, apos):
        pos = [0, 0]
        if apos > 0:
            pos[1] = apos
        else:
            pos[0] = -apos
        dz = self._deadzone
        for i in (0, 1):
            pos[i] = max(0, pos[i] - dz[axis]) / (1 - dz[axis]) # know dz != 1
        imn = 2 * axis
        imx = 2 * (axis + 1)
        old_pos = self.pos
        if pos != old_pos[imn:imx]:
            if self.thresholds is not None:
                # act as button
                down, up = self.thresholds[imn:imx]
                l = list(zip(xrange(imn, imx), old_pos[imn:imx], pos))
                for i, old, new in l:
                    if self._held[i] and old > up and new <= up:
                        self.up(i)
                if mods_match:
                    for i, old, new in l:
                        if old < down and new >= down:
                            self.down(i)
            elif self.is_mod:
                raise TypeError('an AxisInput must have thresholds ' \
                                'defined to be a modifier')
            for i, j in enumerate(xrange(imn, imx)):
                old_pos[j] = pos[i]
            return True
        else:
            return False

    def handle (self, pgevt, mods_match):
        rtn = Input.handle(self, pgevt)
        if hasattr(self, 'axis_val_attr'):
            apos = getattr(pgevt, self.axis_val_attr)
            return self.axis_motion(mods_match, 0, apos) or rtn
        else:
            return rtn


class PadAxis (AxisInput):
    device = 'pad'
    name = 'axis'
    device_id_attr = 'joy'
    pgevts = (pg.JOYAXISMOTION,)
    axis_attr = 'axis'
    axis_val_attr = 'value'


class RelAxis2Input (AxisInput):
    components = 4

    def __init__ (self, device_id = None, relaxis = None, bdy = None,
                  thresholds = None, *mods):
        self.rel = [0, 0, 0, 0]
        AxisInput.__init__(self, device_id, None, thresholds, *mods)
        if hasattr(self, 'relaxis_attr'):
            if relaxis is None:
                raise TypeError('expected relaxis argument')
            self.filter(self.relaxis_attr, relaxis)
        self.relaxis = relaxis
        if bdy is not None and any(b <= 0 for b in bdy):
            raise ValueError('all bdy elements must be greater than zero')
        self.bdy = bdy

    def handle (self, pgevt, mods_match):
        rtn = Input.handle(self, pgevt)
        if hasattr(self, 'relaxis_val_attr'):
            rpos = getattr(pgevt, self.relaxis_val_attr)
            rel = self.rel
            for i in (0, 1):
                if rpos[i] > 0:
                    rel[2 * i + 1] = rpos[i]
                else:
                    rel[2 * i] = -rpos[i]
            if self.bdy is not None:
                # act as axis
                for i, (bdy, rpos) in enumerate(zip(self.bdy, rpos)):
                    apos = float(rpos) / bdy + self.pos[2 * i + 1] - \
                           self.pos[2 * i]
                    sgn = 1 if apos > 0 else -1
                    apos = sgn * min(sgn * apos, 1)
                    rtn |= self.axis_motion(mods_match, i, apos)
            elif self.is_mod:
                raise TypeError('a RelAxis2Input must have bdy defined to ' \
                                'be a modifier')
            else:
                rtn |= any(rpos)
        return rtn

    def reset (self):
        self.rel = [0, 0, 0, 0]


class MouseAxis (RelAxis2Input):
    device = 'mouse'
    name = 'axis'
    pgevts = (pg.MOUSEMOTION,)
    relaxis_val_attr = 'rel'

    def __init__ (self, bdy = None, thresholds = None, *mods):
        if isinstance(bdy, int):
            bdy = (bdy, bdy)
        if thresholds is not None and len(thresholds) == 2:
            thresholds *= 2
        RelAxis2Input.__init__(self, None, None, bdy, thresholds, *mods)


class Event (object):
    components = 0
    input_types = BasicInput

    def __init__ (self, *inputs):
        self.eh = None
        self.inputs = {}
        self.add(*inputs)
        self.cbs = set()

    def add (self, *inputs):
        types = self.input_types
        components = self.components
        self_add = self.inputs.__setitem__
        eh_add = None if self.eh is None else self.eh._add_inputs
        new_inputs = []
        for i in inputs:
            # work out components and perform checks
            if isinstance(i, Input):
                if i.components != components:
                    raise ValueError(
                        '{0} got a non-{1}-component input but no component ' \
                        'data'.format(type(self).__name__, components)
                    )
                i = (i,)
            if len(i) == 1:
                i = (i[0], range(components))
            if len(i) == 2:
                i = (i[0], i[1], range(i[0].components))
            i, evt_components, input_components = i
            if not isinstance(i, types):
                raise TypeError('{0} events only accept inputs of type {1}' \
                                .format(type(self).__name__,
                                        tuple(t.__name__ for t in types)))
            if isinstance(evt_components, int):
                evt_components = (evt_components,)
            if isinstance(input_components, int):
                input_components = (input_components,)
            for ec in evt_components:
                if ec < 0 or ec >= components:
                    raise ValueError('{0} has no component {1}'
                                     .format(self, ec))
            for ic in input_components:
                if ic < 0 or ic >= i.components:
                    raise ValueError('{0} has no component {1}'.format(i, ic))
            if len(evt_components) != len(input_components):
                raise ValueError('component mismatch: {0}'
                                 .format(i, evt_components, input_components))
            # add if not already added
            if i.evt is not self:
                if i.evt is not None:
                    i.evt.rm(i)
                self_add(i, (evt_components, input_components))
                new_inputs.append(i)
                i.evt = self
                i.btn_components = input_components
                if eh_add is not None:
                    eh_add(i)
        return new_inputs

    def rm (self, *inputs):
        self_rm = self.inputs.__delitem__
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

    # dummy methods that inputs use

    def down (self, i, component):
        pass

    def up (self, i, component):
        pass


class MultiEvent (Event):
    # to get cb args, calls static method _merge_args with cb args for each Event
    pass


class Button (Event):
    name = 'button'
    components = 1
    input_types = ButtonInput

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

    def down (self, i, component):
        if component in self.inputs[i][1]:
            self._downevts += 1

    def up (self, i, component):
        if component in self.inputs[i][1]:
            self._upevts += 1
            if self.modes & REPEAT and not any(i.held[0] for i in self.inputs):
                # stop repeating if let go of all buttons at any point
                self._repeating = False

    def respond (self, changed):
        modes = self.modes
        if modes & (HELD | REPEAT):
            held = any(i.held[0] for i in self.inputs)
        else:
            held = False
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
    input_types = (AxisInput, ButtonInput)

    def __init__ (self, *inputs):
        Event.__init__(self, *inputs)
        self._pos = 0

    def respond (self, changed):
        if changed:
            pos = 0
            for i, (evt_components, input_components) \
                in self.inputs.iteritems():
                if isinstance(i, AxisInput):
                    for ec, ic in zip(evt_components, input_components):
                        pos += (2 * ec - 1) * i.pos[ic]
                else: # i is ButtonInput
                    btn_components = i.btn_components
                    for ec, ic in zip(evt_components, input_components):
                        if ic in btn_components and i._held[ic]:
                            pos += 2 * ec - 1
            self._pos = pos = min(1, max(-1, pos))
        else:
            pos = self._pos
        for cb in self.cbs:
            cb(pos)


class Axis2 (MultiEvent):
    child = Axis
    multiple = 2


class RelAxis (Event):
    # each input takes a scaling argument, and mouse events have no limits like with Axis
    name = 'relaxis'
    components = 2
    input_types = (RelAxis2Input, AxisInput, ButtonInput)

    def __init__ (self, *inputs):
        self.input_scales = {}
        Event.__init__(self, *inputs)

    def add (self, *inputs):
        real_inputs = []
        scale = self.input_scales
        for i in inputs:
            scale[i[1]] = i[0]
            real_inputs.append(i[1:])
        Event.add(self, *real_inputs)

    def rm (self, *inputs):
        Event.rm(self, *inputs)
        scale = self.input_scales
        for i in inputs:
            del scale[i]

    def respond (self, changed):
        rel = 0
        scale = self.input_scales
        for i, (evt_components, input_components) \
            in self.inputs.iteritems():
            this_rel = 0
            if isinstance(i, RelAxis2Input):
                for ec, ic in zip(evt_components, input_components):
                    this_rel += (2 * ec - 1) * i.rel[ic]
                i.reset()
            elif isinstance(i, AxisInput):
                for ec, ic in zip(evt_components, input_components):
                    this_rel += (2 * ec - 1) * i.pos[ic]
            else: # i is ButtonInput
                btn_components = i.btn_components
                for ec, ic in zip(evt_components, input_components):
                    if ic in btn_components and i._held[ic]:
                        this_rel += 2 * ec - 1
            rel += this_rel * scale[i]
        if rel:
            for cb in self.cbs:
                cb(rel)


class RelAxis2 (MultiEvent):
    child = RelAxis
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
        # NOTE: can call with existing event to change domain
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
                if not isinstance(evt, Event): # NOTE: also Scheme
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
                            # NOTE: maybe need to let Scheme know about this
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
                    for device in mod_devices[i.device]:
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
                    for device in mod_devices[i.device]:
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
                args = ()
                if isinstance(i, ButtonInput):
                    is_mod = i.is_mod
                    if is_mod:
                        args = (True,)
                    else:
                        assert ids
                        this_mods = i.mods

                        def check_mods ():
                            for device in mod_devices[i.device]:
                                for m in mods.get(device, {}).get(i.device_id,
                                                                  ()):
                                    yield m.held[0] == (m in this_mods)

                        args = (all(check_mods()),)
                else:
                    is_mod = False
                if i.handle(pgevt, *args) and not is_mod:
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

evt_component_names = {
    0: (),
    1: ('button',),
    2: ('neg', 'pos'),
    4: ('left', 'right', 'up', 'down')
}

mod_devices = {
    'kbd': ('kbd',),
    'mouse': ('kbd', 'mouse'),
    'pad': ('pad',)
}

class mod:
    CTRL = (_SneakyMultiKbdKey(pg.KMOD_CTRL, pg.K_LCTRL, pg.K_RCTRL))
    SHIFT = (_SneakyMultiKbdKey(pg.KMOD_SHIFT, pg.K_LSHIFT, pg.K_RSHIFT))
    ALT = (_SneakyMultiKbdKey(pg.KMOD_ALT, pg.K_LALT, pg.K_RALT))
    META = (_SneakyMultiKbdKey(pg.KMOD_META, pg.K_LMETA, pg.K_RMETA))

DOWN = 1
UP = 2
HELD = 4
REPEAT = 8
