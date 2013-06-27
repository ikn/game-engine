import pygame as pg

from .inputs import *

class bmode:
    """Contains :class:`Button` modes."""
    DOWN = 1
    UP = 2
    HELD = 4
    REPEAT = 8

#: ``{n_components: component_names}`` for event components, giving a sequence
#: of component names corresponding to their indices for an event's number of
#: components.
evt_component_names = {
    0: (),
    1: ('button',),
    2: ('neg', 'pos'),
    4: ('left', 'right', 'up', 'down')
}


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
``(input, evt_components = None, input_components = None)`` tuples.

 - ``evt_components`` is a sequence of the component indices (or a single
   component index) of this event that this input provides data for.  Defaults
   to every component, in order.  Instead of indices, components can also be
   names from :data:``evt_component_names``.
 - ``input_components`` is a sequence of the component indices of (or a single
   component index) of the input to match up to ``evt_components``.  Defaults
   to every component of the input, in order.

If there is a mismatch in numbers of components, ``ValueError`` is raised.

"""
        types = self.input_types
        components = self.components
        c_by_name = dict((v, i) for i, v in
                         enumerate(evt_component_names[components]))
        self_add = self.inputs.__setitem__
        eh_add = None if self.eh is None else self.eh._add_inputs
        new_inputs = []
        for i in inputs:
            # work out components and perform checks
            if isinstance(i, Input):
                if i.components != components:
                    raise ValueError(
                        '{0} got a non-{1}-component input but no component '
                        'data'.format(type(self).__name__, components)
                    )
                i = (i,)
            if len(i) == 1:
                i = (i[0], None)
            if len(i) == 2:
                i = (i[0], i[1], None)
            if i[1] is None:
                i = (i[0], range(components), i[2])
            if i[2] is None:
                i = (i[0], i[1], range(i[0].components))
            i, orig_evt_components, input_components = i
            if not isinstance(i, types):
                raise TypeError('{0} events only accept inputs of type {1}'
                                .format(type(self).__name__,
                                        tuple(t.__name__ for t in types)))
            if isinstance(orig_evt_components, (int, basestring)):
                orig_evt_components = (orig_evt_components,)
            if isinstance(input_components, int):
                input_components = (input_components,)
            evt_components = []
            for ec in orig_evt_components:
                # translate from name
                if isinstance(ec, basestring):
                    try:
                        ec = c_by_name[ec]
                    except KeyError:
                        raise ValueError('unknown component name: \'{0}\''
                                         .format(ec))
                # check validity
                if ec < 0 or ec >= components:
                    raise ValueError('{0} has no component {1}'
                                     .format(self, ec))
                evt_components.append(ec)
            for ic in input_components:
                if ic < 0 or ic >= i.components:
                    raise ValueError('{0} has no component {1}'.format(i, ic))
            if len(evt_components) != len(input_components):
                raise ValueError('component mismatch: {0}'
                                 .format(i, evt_components, input_components))
            # add if not already added
            if i.evt is not self:
                if i.evt is not None:
                    # remove from current event
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
                # not necessary since we may raise KeyError, but a good sanity
                # check
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
                # call once for each Pygame event stored
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
            button mode (one of :data:`bmode.DOWN`, :data:`bmode.UP`,
            :data:`bmode.HELD` and :data:`bmode.REPEAT`) or a bitwise-OR of
            button modes.
:arg initial_delay: keyword-only argument.  If the :data:`bmode.REPEAT` mode is
                    given, this is the initial delay in seconds before a button
                    starts repeating while held.
:arg repeat_delay: like initial_delay, the time between repeats in seconds.

Callbacks are called with ``{mode: count}`` for each ``mode`` given, where
``count`` is the number of occurrences of events corresponding to that mode
that have happened within the last frame.  The ``count`` for :data:`bmode.HELD`
is only ever ``0`` or ``1``, and indicates whether the button was held at the
end of the frame.  The ``count`` for :data:`bmode.REPEAT` may only be ``> 1``
if either repeat rate is greater than the current framerate.

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
        if modes & bmode.REPEAT and (self.initial_delay is None or
                                     self.repeat_delay is None):
            raise TypeError('initial_delay and repeat_delay arguments are ' \
                            'required if given the REPEAT mode')
        # whether currently repeating
        self._repeating = False

    def down (self, i, component):
        """:meth:`Event.down`."""
        if component in self.inputs[i][1]:
            self._downevts += 1

    def up (self, i, component):
        """:meth:`Event.up`."""
        if component in self.inputs[i][1]:
            self._upevts += 1
            # stop repeating if let go of all buttons at any point
            if (self.modes & bmode.REPEAT and
                not any(i.held[0] for i in self.inputs)):
                self._repeating = False

    def respond (self, changed):
        """:meth:`Event.respond`."""
        modes = self.modes
        if modes & (bmode.HELD | bmode.REPEAT):
            held = any(i.held[0] for i in self.inputs)
        else:
            held = False
        if not changed and not held:
            # nothing to do
            return
        # construct callback argument
        evts = {}
        if modes & bmode.DOWN:
            evts[bmode.DOWN] = self._downevts
        if modes & bmode.UP:
            evts[bmode.UP] = self._upevts
        self._downevts = self._upevts = 0
        if modes & bmode.HELD:
            evts[bmode.HELD] = held
        if modes & bmode.REPEAT:
            n_repeats = 0
            if self._repeating:
                if held:
                    # continue repeating
                    if self.eh is None:
                        raise RuntimeError('cannot respond properly if not ' \
                                           'attached to an EventHandler')
                    t = self._repeat_remain
                    # use target framerate for determinism
                    t -= self.eh.scheduler.frame
                    if t < 0:
                        # repeat rate may be greater than the framerate
                        n_repeats, t = divmod(t, self.repeat_delay)
                        n_repeats = -int(n_repeats)
                    self._repeat_remain = t
                else:
                    # stop repeating
                    self._repeating = False
            elif held:
                # start repeating
                self._repeating = True
                self._repeat_remain = self.initial_delay
            evts[bmode.REPEAT] = n_repeats
        if any(evts.itervalues()):
            for cb in self.cbs:
                cb(evts)


class Button2 (MultiEvent):
    """Not implemented."""
    # calls once for each component, with axis (0, 1), {evts}
    child = Button
    multiple = 2


class Button4 (MultiEvent):
    """Not implemented."""
    # calls once for each component, with axis, direction (-1, 1), {evts}
    child = Button
    multiple = 4


class Axis (Event):
    """:class:`Event` subclass representing an axis.

The magnitude of the axis position for a button is ``1`` if it is held, else
``0``.

Callbacks are called every frame with the current axis position (after summing
over each registered input and restricting to ``-1 <= x <= 1``).

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
            # compute position: sum over every input
            pos = 0
            for i, (evt_components, input_components) \
                in self.inputs.iteritems():
                if isinstance(i, AxisInput):
                    # add current axis position for each component
                    for ec, ic in zip(evt_components, input_components):
                        pos += (2 * ec - 1) * i.pos[ic]
                else: # i is ButtonInput
                    used_components = i.used_components
                    # add 1 for each held component
                    for ec, ic in zip(evt_components, input_components):
                        if ic in used_components and i._held[ic]:
                            pos += 2 * ec - 1
            # clamp to [-1, 1]
            self._pos = pos = min(1, max(-1, pos))
        else:
            # use previous position
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
        # extract and store scales before passing to Event.add
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
        # remove stored scales (no KeyError means all inputs exist)
        scale = self.input_scales
        for i in inputs:
            del scale[i]

    def respond (self, changed):
        """:meth:`Event.respond`."""
        rel = 0
        scale = self.input_scales
        # sum all relative positions
        for i, (evt_components, input_components) \
            in self.inputs.iteritems():
            this_rel = 0
            if isinstance(i, RelAxisInput):
                for ec, ic in zip(evt_components, input_components):
                    this_rel += (2 * ec - 1) * i.rel[ic]
                i.reset()
            elif isinstance(i, AxisInput):
                # use axis position
                for ec, ic in zip(evt_components, input_components):
                    this_rel += (2 * ec - 1) * i.pos[ic]
            else: # i is ButtonInput
                used_components = i.used_components
                for ec, ic in zip(evt_components, input_components):
                    # use 1 for each held component
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
