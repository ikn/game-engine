"""Callback-based event and input handling.

---NODOC---

TODO:
    [FIRST]
 - comments (L850)
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
 - MultiEvent and use thereof
    [CONFIG]
 - eh.{load, save, unload, disable, enable}
 - can use part of an input, eg. for a button event, 'pad axis 0:0'; for an axis event, 'pos pad axis 2:1'
    - might not be >2-component inputs, but can do, eg. for an axis event, 'neg pos pad axis 0:0,1'
 - deadzones aren't per-input - can do per-device/axis or overall?
 - can omit axis-as-button thresholds and deadzones (global definitions in config file?)
 - mods like '[CTRL] [ALT] kbd a' - device omitted in modifier when same as main button - varnames omitted since must be the same
 - document Input.name
 - document data structures used in config file [##]
    [FUTURE]
 - joy ball (seems like RelAxisInput, but need a pad with a ball to test)
 - eh.*monitor_deadzones
 - Scheme
 - tools for editing/typing text
 - input recording and playback (allow whitelisting/excluding by registered event name)
 - a way to register new input/event types (consider module data structures)
    - document using __str__ backends

---NODOC---

"""

from collections import Sequence

import pygame as pg


class Input (object):
    """Base class for handling events.  By itself, this class does nothing.

Input(*pgevts)

:arg pgevts: Pygame event IDs to listen for.

If a subclass has a ``pgevts`` attribute, this is a list of events to add to
the argument at initialisation.

"""

    #: Number of components ('directions'/'button-likes') represented by this
    #: input.
    components = 0
    #: The string device name that this input type corresponds to (see
    #: :data:`inputs_by_name`).
    device = None
    #: A value that the device ID will never take (see :attr:`device_id`).
    invalid_device_id = -1

    def __init__ (self, *pgevts):
        #: Variable representing the current device ID; may be a string as a
        #: variable name, or ``None`` (see :meth:`EventHandler.assign_devices`
        #: for details).
        self.device_var = None
        #: The :class:`Event` instance that contains this input, or ``None``.
        self.evt = None
        pgevts = set(pgevts)
        if hasattr(self, 'pgevts'):
            pgevts.update(self.pgevts)
        #: A ``{pgevt_attr: val}`` dict that represents how events are filtered
        #: before being passed to this input (see :meth:`filter`).
        self.filters = {}
        if pgevts:
            self.filters['type'] = pgevts
        self._device_id = None

    def _str_dev_id (self):
        # device id/var for printing
        dev_id = self._device_id
        if dev_id is None and self.device_var is not None:
            dev_id = '<{0}>'.format(self.device_var)

    def _str (self, arg):
        # string representation with some contained data
        return '{0}({1})'.format(type(self).__name__, arg)

    def __str__ (self):
        return self._str(self.filters)

    def __repr__ (self):
        return str(self)

    def handle (self, pgevt):
        """Called by :class:`EventHandler` with a ``pygame.event.Event``.

The passed event matches :attr:`filters`.

:return: whether anything in the input's state changed.

"""
        return False

    def filter (self, attr, *vals, **kw):
        """Filter events passed to this input.

filter(attr, *vals, refilter = False) -> self

:arg attr: Pygame event attribute to filter by.
:arg vals: allowed values of the given attribute for filtered events.
:arg refilter: if ``True``, replace previous filtering by ``attr`` with the
               given ``vals``, else add to the values already filtered by.

Note that due to the implementation, there is a value that cannot be filtered
for: :data:`UNFILTERABLE`.

"""
        refilter = kw.get('refilter', False)
        if not vals:
            if refilter:
                # refilter to nothing, ie. remove all filtering
                self.unfilter(attr)
            # else nothing to do
            return self
        eh = None if self.evt is None or self.evt.eh is None else self.evt.eh
        # wrap with removal from/readdition to handler
        if eh is not None:
            eh._rm_inputs(self)
        if UNFILTERABLE in vals:
            raise ValueError('cannot filter for {0}'.format(UNFILTERABLE))
        if refilter:
            self.filters[attr] = set(vals)
        else:
            self.filters.setdefault(attr, set()).update(vals)
        if eh is not None:
            eh._add_inputs(self)
        return self

    def unfilter (self, attr, *vals):
        """Remove filtering by the given attribute.

:arg attr: Pygame event attribute to modify filtering for.
:arg vals: values to remove filtering for.  If none are given, all filtering
           by ``attr`` is removed.

"""
        if attr not in self.filters:
            return self
        eh = None if self.evt is None or self.evt.eh is None else self.evt.eh
        # wrap with removal from/readdition to handler
        if eh is not None:
            eh._rm_inputs(self)
        got = self.filters[attr]
        if vals:
            # remove given values
            got.difference_update(vals)
            if not got:
                # no longer filtering by this attribute
                del self.filters[attr]
        else:
            # remove all
            del self.filters[attr]
        if eh is not None:
            eh._add_inputs(self)
        return self

    @property
    def device_id (self):
        """The particular device that this input captures input for.

May be ``None``, in which case no input will be registered; this is done by
filtering by :attr:`invalid_device_id`.

Subclasses may set an attribute ``device_id_attr``, in which case setting this
attribute filters using ``device_id_attr`` as the event attribute and the set
value as the attribute value to filter by.  If a subclass does not provide
``device_id_attr`` and does not override the setter, this operation raises
``TypeError``.

"""
        return self._device_id

    @device_id.setter
    def device_id (self, device_id):
        if hasattr(self, 'device_id_attr'):
            if device_id is None:
                # sort by an invalid ID to make sure we get no events
                ids = (self.invalid_device_id,)
            else:
                ids = (device_id,)
            self.filter(self.device_id_attr, *ids, refilter = True)
            self._device_id = device_id
        else:
            raise TypeError('this Input type doesn\'t support device IDs')


class BasicInput (Input):
    """An input that handles Pygame events of a single type.

BasicInput(pgevt)

:arg pgevt: Pygame event ID to listen for.

"""

    def __init__ (self, pgevt):
        #: Pygame event ID as passed to the constructor.
        self.pgevt = pgevt
        Input.__init__(self, pgevt)
        # stored Pygame events, used by :class:`Event`
        self._pgevts = []

    def __str__ (self):
        return self._str(pg.event.event_name(self.pgevt).upper())

    def handle (self, pgevt):
        """:meth:`Input.handle`."""
        Input.handle(self, pgevt)
        self._pgevts.append(pgevt)
        return True

    def reset (self):
        """Clear cached Pygame events.

Called by the owning :class:`Event`.

"""
        self._pgevts = []


class ButtonInput (Input):
    """Abstract base class representing a button-like action (:class:`Input`
subclass).

ButtonInput([button], *mods)

:arg button: button ID to listen for.  To use this, subclasses must set a
             ``button_attr`` property to filter by that Pygame event attribute
             with this ID as the value.  Otherwise, they must implement
             filtering themselves.
:arg mods: inputs to use as modifiers.  Each may be a :class:`ButtonInput`, a
           sequence of them, or ``(input, component)`` giving the component of
           the input to use (from ``0`` to ``input.components - 1``).

Subclasses must have a :attr:`device <Input.device>` in :data:`mod_devices`,
which restricts allowed devices of modifiers.

"""

    components = 1

    def __init__ (self, button = None, *mods):
        self._held = [False] * self.components
        #: Whether this input is acting as a modifier.
        self.is_mod = False
        #: A sequence of the components of this input that are being used.
        #: This is set by a container when the input is registered with one
        #: (such as an :class:`Event`, or another :class:`ButtonInput` as a
        #: modifier).
        self.used_components = ()
        Input.__init__(self)
        if hasattr(self, 'button_attr'):
            if button is None:
                raise TypeError('expected button argument')
            self.filter(self.button_attr, button)
        #: The button ID this input represents, as taken by the constructor.
        self.button = button

        mods = list(mods)
        mods_parsed = []
        for m in mods:
            # default to using component 0 of the modifier
            if isinstance(m, Input):
                m = (m, 0)
            elif len(m) == 1:
                m = (m[0], 0)
            # now we have a sequence
            if isinstance(m[1], Input):
                # sequence of mods
                mods.extend(m)
            else:
                # (mod, component)
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
        #: List of modifiers (:class:`ButtonInput` instances) that affect this
        #: input.
        self.mods = mods = []
        for m, c in mods_parsed:
            if c < 0 or c >= m.components:
                raise ValueError('{0} has no component {1}'.format(m, c))
            # we're now the mod's container
            m.is_mod = self
            m.used_components = (c,)
            mods.append(m)

    def __str__ (self):
        if hasattr(self, '_btn_name'):
            # make something like [mod1]...[modn]self to pass to Input._str
            # _btn_name should give form for displaying within type wrapper
            s = self._btn_name()
            for m in self.mods:
                if hasattr(m, '_mod_btn_name'):
                    # _mod_btn_name should give form for displaying as a mod
                    mod_s = m._mod_btn_name()
                else:
                    mod_s = str(m)
                s = '[{0}]{1}'.format(mod_s, s)
            return self._str(s)
        else:
            return Input.__str__(self)

    @property
    def held (self):
        """A list of the held state of this button for used component.

Each item is a bool corresponds to the component in the same position in
:attr:`used_components`.

"""
        return [self._held[c] for c in self.used_components]

    def down (self, component = 0):
        """Set the given component's button state to down."""
        self._held[component] = True
        # mods don't have events
        if not self.is_mod:
            if component in self.used_components:
                assert self.evt is not None
                self.evt.down(self, component)
            return True
        return False

    def up (self, component = 0):
        """Set the given component's button state to up."""
        # don't allow an up without a down
        if self._held[component]:
            self._held[component] = False
            # mods don't have events
            if not self.is_mod:
                if component in self.used_components:
                    assert self.evt is not None
                    self.evt.up(self, component)
                return True
        return False

    def handle (self, pgevt, mods_match):
        """:meth:`Input.handle`.

:arg mods_match: whether the modifiers attached to this button are currently
                 active.

If a subclass has a ``down_pgevts`` attribute, this sets the button down on
component ``0`` for Pygame events with IDs in this list, and up on component
``0`` for all other events.  Otherwise, it does nothing.

"""
        rtn = Input.handle(self, pgevt)
        if hasattr(self, 'down_pgevts'):
            if pgevt.type in self.down_pgevts:
                if mods_match:
                    rtn |= self.down()
            else:
                rtn |= self.up()
        return rtn


class KbdKey (ButtonInput):
    """:class:`ButtonInput` subclass representing a keyboard key.

The ``button`` argument is required, and is the key code.

"""

    device = 'kbd'
    name = 'key'
    pgevts = (pg.KEYDOWN, pg.KEYUP)
    button_attr = 'key'
    down_pgevts = (pg.KEYDOWN,)

    def __init__ (self, key, *mods):
        ButtonInput.__init__(self, key, *mods)

    def _btn_name (self):
        return pg.key.name(self.button).upper()

    _mod_btn_name = _btn_name


class _SneakyMultiKbdKey (KbdKey):
    # KbdKey wrapper to handle multiple keys, for use as a modifier (held if
    # any key is held) - only for module.mod

    def __init__ (self, button, *buttons):
        KbdKey.__init__(self, buttons[0])
        self.filter(self.button_attr, *buttons[1:])
        self.button = button
        # track each key's held state
        self._held_multi = dict.fromkeys(buttons, False)

    def _btn_name (self):
        # grab name from attribute name in module.mod
        for attr, val in vars(mod).iteritems():
            if val is self:
                return attr

    _mod_btn_name = _btn_name

    def handle (self, pgevt, mods_match):
        self._held_multi[pgevt.key] = pgevt.type in self.down_pgevts
        self._held[0] = any(self._held_multi.itervalues())
        return False


class MouseButton (ButtonInput):
    """:class:`ButtonInput` subclass representing a mouse button.

The ``button`` argument is required, and is the mouse button ID.

"""

    device = 'mouse'
    name = 'button'
    pgevts = (pg.MOUSEBUTTONDOWN, pg.MOUSEBUTTONUP)
    button_attr = 'button'
    down_pgevts = (pg.MOUSEBUTTONDOWN,)

    def __init__ (self, button, *mods):
        ButtonInput.__init__(self, button, *mods)

    def _btn_name (self):
        return '{0}'.format(self.button)

    def _mod_btn_name (self):
        return 'mouse button {0}'.format(self.button)


class PadButton (ButtonInput):
    """:class:`ButtonInput` subclass representing a gamepad button.

PadButton(device_id, button, *mods)

:arg device_id: the gamepad's device ID, either a variable
                (:attr:`device_var <Input.device_var>`), a non-string ID
                (:attr:`device_id <Input.device_id>`) or ``None``.
:arg button, mods: as taken by :class:`ButtonInput`.

"""

    device = 'pad'
    name = 'button'
    pgevts = (pg.JOYBUTTONDOWN, pg.JOYBUTTONUP)
    device_id_attr = 'joy'
    button_attr = 'button'
    down_pgevts = (pg.JOYBUTTONDOWN,)

    def __init__ (self, device_id, button, *mods):
        ButtonInput.__init__(self, button, *mods)
        if isinstance(device_id, basestring):
            self.device_var = device_id
        else:
            self.device_id = device_id

    def _btn_name (self):
        return '{0}, {1}'.format(self._str_dev_id(), self.button)

    def _mod_btn_name (self):
        return 'pad {0} button {1}'.format(self._str_dev_id(), self.button)


class AxisInput (ButtonInput):
    """Abstract base class representing 2-component axes
(:class:`ButtonInput` subclass).

AxisInput([axis][, thresholds], *mods)

:arg axis: axis ID to listen for.  To use this, subclasses must set an
           ``axis_attr`` property to filter by that Pygame event attribute with
           this ID as the value, and with an attribute giving the axis's value.
           Otherwise, they must implement filtering themselves.
:arg thresholds: required if the axis is to act as a button.  For each axis
                 (that is, for each pair of :attr:`Input.components`), this
                 list has two elements: ``down`` followed by ``up``, positive
                 numbers giving the magnitude of the value of the axis in
                 either direction that triggers a button down or up event.  For
                 example, a 2-component axis might have ``(.6, .4)``.

                 A subclass with more than 2 components may pass a length-2
                 sequence here, which is expanded by assuming the same
                 thresholds for each axis.
:arg mods: as taken by :class:`ButtonInput`.  Only used if this axis is treated
           as a button.

Subclasses must have an even number of components.

"""

    components = 2

    def __init__ (self, axis = None, thresholds = None, *mods):
        #: Position (magnitude) in each direction of each axis, eg. for a
        #: single axis at ``-.3``, this is ``[.3, 0]``.
        self.pos = [0] * self.components
        if mods and thresholds is None:
            raise TypeError('an AxisInput must have thresholds defined to ' \
                            'have modifiers')
        ButtonInput.__init__(self, None, *mods)
        if hasattr(self, 'axis_attr'):
            if axis is None:
                raise TypeError('expected axis argument')
            self.filter(self.axis_attr, axis)
        #: Axis ID, as passed to the constructor.
        self.axis = axis
        # same threshold for each axis if only given for one
        if thresholds is not None and len(thresholds) == 2:
            thresholds *= (self.components / 2)
        #: As passed to the constructor.
        self.thresholds = thresholds
        self.deadzone = 0

    @property
    def deadzone (self):
        """Axis value magnitude below which the value is mapped to ``0``.

Above this value, the mapped value increases linearly from ``0``.

"""
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
        """Signal a change in axis position.

:arg mods_match: as taken by :meth:`handle`.
:arg axis: the index of the axis to modify (a 2-component :class:`AxisInput`
           has one axis, with index ``0``).
:arg apos: the new axis position (``-1 <= apos <= 1``).

"""
        # get magnitude in each direction
        pos = [0, 0]
        if apos > 0:
            pos[1] = apos
        else:
            pos[0] = -apos
        # apply deadzone (linear scale up from it)
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
                # all up (towards 0/centre) first, then all down, to end up
                # held if move down
                for i, old, new in l:
                    if self._held[i] and old > up and new <= up:
                        self.up(i)
                if mods_match:
                    for i, old, new in l:
                        if old < down and new >= down:
                            self.down(i)
            elif self.is_mod:
                # mod, but can't act as a button
                raise TypeError('an AxisInput must have thresholds ' \
                                'defined to be a modifier')
            for i, j in enumerate(xrange(imn, imx)):
                old_pos[j] = pos[i]
            return True
        else:
            # neither magnitude changed
            return False

    def handle (self, pgevt, mods_match):
        """:meth:`ButtonInput.handle`.

If a subclass has an ``axis_val_attr`` attribute, this value of this attribute
in the Pygame event is used as a list of axis positions (or just one, if a
number).  Otherwise, this method does nothing.

"""
        rtn = Input.handle(self, pgevt)
        if hasattr(self, 'axis_val_attr'):
            apos = getattr(pgevt, self.axis_val_attr)
            if isinstance(apos, (int, float)):
                apos = (apos,)
            if len(apos) != self.components / 2:
                raise ValueError(
                    'the event attribute given by the axis_val_attr ' \
                    'attribute has the wrong number of components'
                )
            for i, apos in enumerate(apos):
                rtn |= self.axis_motion(mods_match, i, apos)
        return rtn


class PadAxis (AxisInput):
    """:class:`AxisInput` subclass representing a gamepad axis.

PadAxis(device_id, axis[, thresholds], *mods)

:arg device_id: the gamepad's device ID, either a variable
                (:attr:`device_var <Input.device_var>`), a non-string ID
                (:attr:`device_id <Input.device_id>`) or ``None``.
:arg axis, thresholds: as taken by :class:`AxisInput`.
:arg mods: as taken by :class:`ButtonInput`.

"""

    device = 'pad'
    name = 'axis'
    device_id_attr = 'joy'
    pgevts = (pg.JOYAXISMOTION,)
    axis_attr = 'axis'
    axis_val_attr = 'value'

    def __init__ (self, device_id, axis, thresholds = None, *mods):
        AxisInput.__init__(self, axis, thresholds, *mods)
        if isinstance(device_id, basestring):
            self.device_var = device_id
        else:
            self.device_id = device_id

    def _mod_btn_name (self):
        return 'pad {0} axis {1}'.format(self._str_dev_id(), self.axis)

    def __str__ (self):
        return self._str('{0}, {1}'.format(self._str_dev_id(), self.axis))


class PadHat (AxisInput):
    """:class:`AxisInput` subclass representing a gamepad axis.

PadHat(device_id, axis[, thresholds], *mods)

:arg device_id: the gamepad's device ID, either a variable
                (:attr:`device_var <Input.device_var>`), a non-string ID
                (:attr:`device_id <Input.device_id>`) or ``None``.
:arg hat: the hat ID to listen for.
:arg thresholds: as taken by :class:`AxisInput`.
:arg mods: as taken by :class:`ButtonInput`.

"""

    components = 4
    device = 'pad'
    name = 'hat'
    device_id_attr = 'joy'
    pgevts = (pg.JOYHATMOTION,)
    axis_attr = 'hat'
    axis_val_attr = 'value'

    def __init__ (self, device_id, hat, thresholds = None, *mods):
        AxisInput.__init__(self, hat, thresholds, *mods)
        if isinstance(device_id, basestring):
            self.device_var = device_id
        else:
            self.device_id = device_id

    def _mod_btn_name (self):
        return 'pad {0} hat {1}'.format(self._str_dev_id(), self.axis)

    def __str__ (self):
        return self._str('{0}, {1}'.format(self._str_dev_id(), self.axis))


class RelAxisInput (AxisInput):
    """Abstract base class representing 2-component relative axes
(:class:`AxisInput` subclass).

RelAxisInput([relaxis][, bdy][, thresholds][, mods])

:arg relaxis: axis ID to listen for.  To use this, subclasses must set a
              ``relaxis_attr`` property to filter by that Pygame event
              attribute with this ID as the value, and with an attribute giving
              the axis's value.  Otherwise, they must implement filtering
              themselves.
:arg bdy: required if the relative axis is to act as an axis.  For each axis
          (each 2 components), this sequence contains a positive number giving
          the maximum magnitude of the axis.  The normalised axis position is
          then obtained by dividing by this value.
:arg thresholds: as taken by :class:`AxisInput`.
:arg mods: as taken by :class:`ButtonInput`.

A relative axis is one where events convey a change in the axis's value, rather
than its absolute position.  Subclasses must have an even number of components.

"""

    components = 2

    def __init__ (self, relaxis = None, bdy = None, thresholds = None, *mods):
        #: The change in each component since last :meth:`reset`.
        self.rel = [0, 0] * (self.components / 2)
        AxisInput.__init__(self, None, thresholds, *mods)
        if hasattr(self, 'relaxis_attr'):
            if relaxis is None:
                raise TypeError('expected relaxis argument')
            self.filter(self.relaxis_attr, relaxis)
        #: Axis ID, as passed to the constructor.
        self.relaxis = relaxis
        if bdy is not None:
            if isinstance(bdy, (int, float)):
                bdy = (bdy,) * (self.components / 2)
            if any(b <= 0 for b in bdy):
                raise ValueError('all bdy elements must be greater than zero')
        #: As taken by the constructor.
        self.bdy = bdy

    def handle (self, pgevt, mods_match):
        """:class:`ButtonInput.handle`."""
        rtn = Input.handle(self, pgevt)
        if hasattr(self, 'relaxis_val_attr'):
            rpos = getattr(pgevt, self.relaxis_val_attr)
            rel = self.rel
            # split relative axis motion into magnitudes in each direction
            for i in xrange(self.components / 2):
                if rpos[i] > 0:
                    rel[2 * i + 1] = rpos[i]
                else:
                    rel[2 * i] = -rpos[i]
            if self.bdy is not None:
                # act as axis (add relative pos to current pos)
                for i, (bdy, rpos) in enumerate(zip(self.bdy, rpos)):
                    # normalise and restrict magnitude to 1
                    apos = float(rpos) / bdy + self.pos[2 * i + 1] - \
                           self.pos[2 * i]
                    sgn = 1 if apos > 0 else -1
                    apos = sgn * min(sgn * apos, 1)
                    rtn |= self.axis_motion(mods_match, i, apos)
            elif self.is_mod:
                raise TypeError('a RelAxisInput must have bdy defined to be ' \
                                'a modifier')
            else:
                rtn |= any(rpos)
        return rtn

    def reset (self):
        """Reset values in :attr:`rel` to ``0``.

Called by the owning :class:`Event`.

"""
        self.rel = [0, 0] * (self.components / 2)


class MouseAxis (RelAxisInput):
    """:class:`RelAxisInput` subclass representing both mouse axes.

MouseAxis([bdy][, thresholds], *mods)

:arg bdy: as taken by :class:`RelAxisInput`.
:arg thresholds: as taken by :class:`AxisInput`.
:arg mods: as taken by :class:`ButtonInput`.

"""

    components = 4
    device = 'mouse'
    name = 'axis'
    pgevts = (pg.MOUSEMOTION,)
    relaxis_val_attr = 'rel'

    def __init__ (self, bdy = None, thresholds = None, *mods):
        if isinstance(bdy, int):
            bdy = (bdy, bdy)
        RelAxisInput.__init__(self, None, bdy, thresholds, *mods)

    def _mod_btn_name (self):
        return 'mouse axis'

    def __str__ (self):
        return self._str('')


class Event (object):
    """Connects inputs and callbacks.

Takes any number of inputs like :meth:`add`.

This event type calls callbacks with a single ``pygame.event.Event`` instance,
once for each event gathered by the inputs.

"""

    #: Like :attr:`Input.components`---the number of components the event can
    #: handle.
    components = 0
    #: A sequence of classes or a single class giving the input types accepted
    #: by this event type.
    input_types = BasicInput

    def __init__ (self, *inputs):
        #: Containing :class:`EventHandler`, or ``None``.
        self.eh = None
        #: ``{input: (evt_components, input_components)}`` (see :meth:`add`).
        self.inputs = {}
        self.add(*inputs)
        #: ``set`` of functions to call on input.  Change this directly if you
        #: want.
        self.cbs = set()

    def add (self, *inputs):
        """Add inputs to this event.

Takes any number of inputs matching :attr:`input_types`, or
``(input[, evt_components][, input_components])`` tuples.

 - ``evt_components`` is a sequence of the component indices (or a single
   component index) of this event that this input provides data for.  Defaults
   to every component, in order.
 - ``input_components`` is a sequence of the component indices of (or a single
   component index) of the input to match up to ``evt_components``.  Defaults
   to every component of the input, in order.

If there is a mismatch in numbers of components, ``ValueError`` is raised.

"""
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
                i.used_components = input_components
                if eh_add is not None:
                    eh_add(i)
        return new_inputs

    def rm (self, *inputs):
        """Remove inputs from this event.

Takes any number of :class:`Input` instances and raises ``KeyError`` if
missing.

"""
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
        """Add any number of callbacks to :attr:`cbs`.

cb(*cbs) -> self

"""
        self.cbs.update(cbs)
        return self

    def rm_cbs (self, *cbs):
        """Remove any number of callbacks from :attr:`cbs`.

rm_cbs(*cbs) -> self

Missing items are ignored.

"""
        self.cbs.difference_update(cbs)
        return self

    def respond (self, changed):
        """Handle inputs and call callbacks.

:arg changed: whether any inputs changed in any way.

Called by the containing :class:`EventHandler`.

"""
        if changed:
            cbs = self.cbs
            for i in self.inputs:
                for pgevt in i._pgevts:
                    for cb in cbs:
                        cb(pgevt)
                i.reset()

    # dummy methods that inputs use

    def down (self, i, component):
        """Used by subclasses to handle :class:`ButtonInput` instances.

:arg i: the calling input.
:arg component: the input's component that has been toggled down.

"""
        pass

    def up (self, i, component):
        """Used by subclasses to handle :class:`ButtonInput` instances.

:arg i: the calling input.
:arg component: the input's component that has been toggled up.

"""
        pass


class MultiEvent (Event):
    """Not implemented."""
    # to get cb args, calls static method _merge_args with cb args for each Event
    pass


class Button (Event):
    """:class:`Event` subclass representing a button.

Button(*items[, initial_delay][, repeat_delay])

:arg items: each item is either an input as taken by :class:`Event`, or a
            button mode (one of :data:`DOWN`, :data:`UP`, :data:`HELD` and
            :data:`REPEAT`) or a bitwise-OR of button modes.
:arg initial_delay: keyword-only argument.  If the :data:`REPEAT` mode is
                    given, this is the initial delay in seconds before a button
                    starts repeating while held.
:arg repeat_delay: like initial_delay, the time between repeats in seconds.

Callbacks are called with ``{mode: count}`` for each ``mode`` given, where
``count`` is the number of occurrences of events corresponding to that mode
that have happened within the last frame.  The ``count`` for :data:`HELD` is
only ever ``0`` or ``1``, and indicates whether the button was held at the end
of the frame.  The ``count`` for :data:`REPEAT` may only be ``> 1`` if either
repeat rate is greater than the current framerate.

"""

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
        #: A bitwise-OR of all button modes passed to the constructor.
        self.modes = modes
        self._downevts = self._upevts = 0
        #: As passed to the constructor.
        self.initial_delay = kw.get('initial_delay')
        #: As passed to the constructor.
        self.repeat_delay = kw.get('repeat_delay')
        if modes & REPEAT and (self.initial_delay is None or
                               self.repeat_delay is None):
            raise TypeError('initial_delay and repeat_delay arguments are ' \
                            'required if given the REPEAT mode')
        self._repeating = False

    def down (self, i, component):
        """:meth:`Event.down`."""
        if component in self.inputs[i][1]:
            self._downevts += 1

    def up (self, i, component):
        """:meth:`Event.up`."""
        if component in self.inputs[i][1]:
            self._upevts += 1
            if self.modes & REPEAT and not any(i.held[0] for i in self.inputs):
                # stop repeating if let go of all buttons at any point
                self._repeating = False

    def respond (self, changed):
        """:meth:`Event.respond`."""
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
    """Not implemented."""
    child = Button
    multiple = 2


class Button4 (MultiEvent):
    """Not implemented."""
    child = Button
    multiple = 4


class Axis (Event):
    """:class:`Event` subclass representing an axis.

The magnitude of the axis position for a button is ``1`` if it is held, else
``0``.

Callbacks are called every frame with the current axis position (after summing
over each registered input and restricting to ``[-1, +1]``).

"""

    name = 'axis'
    components = 2
    input_types = (AxisInput, ButtonInput)

    def __init__ (self, *inputs):
        Event.__init__(self, *inputs)
        self._pos = 0

    def respond (self, changed):
        """:meth:`Event.respond`."""
        if changed:
            pos = 0
            for i, (evt_components, input_components) \
                in self.inputs.iteritems():
                if isinstance(i, AxisInput):
                    for ec, ic in zip(evt_components, input_components):
                        pos += (2 * ec - 1) * i.pos[ic]
                else: # i is ButtonInput
                    used_components = i.used_components
                    for ec, ic in zip(evt_components, input_components):
                        if ic in used_components and i._held[ic]:
                            pos += 2 * ec - 1
            self._pos = pos = min(1, max(-1, pos))
        else:
            pos = self._pos
        for cb in self.cbs:
            cb(pos)


class Axis2 (MultiEvent):
    """Not implemented."""
    child = Axis
    multiple = 2


class RelAxis (Event):
    """:class:`Event` subclass representing a relative axis.

Each input is scaled by a positive number (see :meth:`add` for details).

The magnitude of the relative position for an axis is its position, and for a
button is ``1`` if it is held, else ``0``.

Callbacks are called with the total, scaled relative change over all inputs
registered with this event.

"""
    name = 'relaxis'
    components = 2
    input_types = (RelAxisInput, AxisInput, ButtonInput)

    def __init__ (self, *inputs):
        #: ``{scale: input}`` (see :meth:`add`).
        self.input_scales = {}
        Event.__init__(self, *inputs)

    def add (self, *inputs):
        """:meth:`Event.add`.

Inputs are ``(scale, input[, evt_components][, input_components])``, where
``scale`` is a positive number to scale the relative axis's position by before
calling callbacks.

"""
        real_inputs = []
        scale = self.input_scales
        for i in inputs:
            if i[0] < 0:
                raise ValueError("input scaling must be non-negative.")
            scale[i[1]] = i[0]
            real_inputs.append(i[1:])
        Event.add(self, *real_inputs)

    def rm (self, *inputs):
        """:meth:`Event.rm`."""
        Event.rm(self, *inputs)
        scale = self.input_scales
        for i in inputs:
            del scale[i]

    def respond (self, changed):
        """:meth:`Event.respond`."""
        rel = 0
        scale = self.input_scales
        for i, (evt_components, input_components) \
            in self.inputs.iteritems():
            this_rel = 0
            if isinstance(i, RelAxisInput):
                for ec, ic in zip(evt_components, input_components):
                    this_rel += (2 * ec - 1) * i.rel[ic]
                i.reset()
            elif isinstance(i, AxisInput):
                for ec, ic in zip(evt_components, input_components):
                    this_rel += (2 * ec - 1) * i.pos[ic]
            else: # i is ButtonInput
                used_components = i.used_components
                for ec, ic in zip(evt_components, input_components):
                    if ic in used_components and i._held[ic]:
                        this_rel += 2 * ec - 1
            rel += this_rel * scale[i]
        if rel:
            for cb in self.cbs:
                cb(rel)


class RelAxis2 (MultiEvent):
    """Not implemented."""
    child = RelAxis
    multiple = 2


class EventHandler (dict):
    """Handles events.

EventHandler(scheduler)

:arg scheduler: :class:`sched.Scheduler <engine.sched.Scheduler>` instance to
                use for determining the current framerate.

Call :meth:`update` every frame to process and progagate Pygame events and call
callbacks.

Some notes:

 - Events are named or unnamed, and an :class:`EventHandler` is a ``dict`` of
   named events.
 - The ``'domain'`` name is reserved.
 - The ``__contains__`` method (``event in event_handler``) works for
   :class:`Event` instances. as well as names.

"""

    def __init__ (self, scheduler):
        #: As passed to the constructor.
        self.scheduler = scheduler
        self._named = set()
        #: A ``set`` of all registered unnamed events.
        self.evts = set()
        self._inputs = set()
        self._filtered_inputs = ('type', {UNFILTERABLE: set()})
        self._mods = {}

    def __str__ (self):
        return '<EventHandler object at {0}>'.format(hex(id(self)))

    def __contains__ (self, item):
        return dict.__contains__(self, item) or item in self._named or \
               item in self.evts

    def __setitem__ (self, item, val):
        self.add(**{item: val})

    def __delitem__ (self, item):
        self.rm(item)

    def add (self, *evts, **named_evts):
        """Register events.

:arg evts, named_evts: any number of :class:`Event` instances.  Keyword
                       arguments define named events with the key as the name.

"""
        # add(*evts, **named_evts, domain = None)
        # NOTE: can call with existing event to change domain
        created = []
        named = self._named
        unnamed = self.evts
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
        """Takes any number of registered events to remove them.

Raises ``KeyError`` if any arguments are missing.

"""
        named = self._named
        unnamed = self.evts
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
        vals = filters.pop(attr, (UNFILTERABLE,))
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
                        child = (attr, {UNFILTERABLE: child})
                    filtered[val] = child
                    self._prefilter(child, filters, i)
                else:
                    child.add(i)

    def _unprefilter (self, filtered, filters, i):
        attr, filtered = filtered
        # Input guarantees that this is non-empty
        vals = filters.pop(attr, (UNFILTERABLE,))
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
                if val is UNFILTERABLE:
                    # retain the UNFILTERABLE branch
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
                                        .setdefault(i._device_id, {})
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
        """Process Pygame events and call callbacks."""
        all_inputs = self._filtered_inputs
        changed = set()
        unchanged = set()
        mods = self._mods
        for pgevt in pg.event.get():
            inputs = all_inputs
            while isinstance(inputs, tuple):
                attr, inputs = inputs
                val = getattr(pgevt, attr) if hasattr(pgevt, attr) \
                                           else UNFILTERABLE
                inputs = inputs[val if val is UNFILTERABLE or val in inputs
                                    else UNFILTERABLE]
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
        for evts in (self._named, self.evts):
            for evt in evts:
                changed = evt._changed
                evt._changed = False
                evt.respond(changed)

    def load (self, filename, domain = None):
        """Not implemented."""
        # doesn't add events used in schemes - they _only_ go in the scheme
        pass

    def save (self, filename, domain):
        """Not implemented."""
        # save everything in the domain to file
        pass

    def unload(self, domain):
        """Not implemented."""
        pass

    def disable (self, domain):
        """Not implemented."""
        pass

    def enable (self, domain):
        """Not implemented."""
        pass

    def assign_devices (**devices):
        """Not implemented."""
        # takes {varname: device_ids}, device_ids False for none, True for all, id or list of ids
        pass

    def grab (self, cb, *types):
        """Not implemented."""
        # grabs next 'on'-type event from given devices/types and passes it to cb
        # types are device name or (device, type_name)
        pass

    def monitor_deadzones (self, *deadzones):
        """Not implemented."""
        # takes list of  (device, id, *args); do for all if none given
        pass

    def stop_monitor_deadzones (self):
        """Not implemented."""
        # returns {(device, id, *args): deadzone}, args is axis for pad
        # can register other deadzone events?
        pass

    def set_deadzones (self, deadzones):
        """Not implemented."""
        # takes stop_monitor_deadzones result
        pass

#: A value that an :class:`Input` cannot filter for.  If you want to filter for
#: ``None``, you may change this in the module, but make sure to do so before
#: creating any :class:`EventHandler` instances, and never after.
UNFILTERABLE = None

#: ``{device: allowed_mod_devices}`` for :class:`ButtonInput` instances.  An
#: input for :attr:`device <Input.device>` ``device`` may only have modifiers
#: with :attr:`device <Input.device>` in ``allowed_mod_devices``.
mod_devices = {
    'kbd': ('kbd',),
    'mouse': ('kbd', 'mouse'),
    'pad': ('pad',)
}

class mod:
    """Contains objects that act as specific keyboard modifiers."""
    CTRL = (_SneakyMultiKbdKey(pg.KMOD_CTRL, pg.K_LCTRL, pg.K_RCTRL))
    SHIFT = (_SneakyMultiKbdKey(pg.KMOD_SHIFT, pg.K_LSHIFT, pg.K_RSHIFT))
    ALT = (_SneakyMultiKbdKey(pg.KMOD_ALT, pg.K_LALT, pg.K_RALT))
    META = (_SneakyMultiKbdKey(pg.KMOD_META, pg.K_LMETA, pg.K_RMETA))

#: :class:`Button` mode: key down.
DOWN = 1
#: :class:`Button` mode: key up.
UP = 2
#: :class:`Button` mode: key held down.
HELD = 4
#: :class:`Button` mode: key repeat (virtual key down).
REPEAT = 8

##: A ``{cls.device: {cls.name: cls}}`` dict of usable named :class:`Input`
##: subclasses.
inputs_by_name = {}
for i in dict(vars()): # copy or it'll change size during iteration
    if isinstance(i, Input) and hasattr(i, name):
        inputs_by_name.setdefault(i.device, {})[i.name] = i
del i
##: A ``{cls.name: cls}`` dict of usable named :class:`Event` subclasses.
evts_by_name = dict((evt.name, name) for evt in vars()
                    if (isinstance(evt, Event) and hasattr(evt, 'name')) or
                       (isinstance(evt, MultiEvent) and
                        hasattr(evt.child, 'name')))

##: Needs doc.
evt_component_names = {
    0: (),
    1: ('button',),
    2: ('neg', 'pos'),
    4: ('left', 'right', 'up', 'down')
}
