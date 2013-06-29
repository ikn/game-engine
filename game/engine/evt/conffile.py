"""Parse configuration strings to events and vice versa.

If an input or event class has a ``name`` attribute, it is 'named' and is
supported in configuration strings.

"""

# NOTE that using the same input axis on the same input for different events (or for a multievent) is not supported, and behaviour is undefined

import sys
import shlex
from StringIO import StringIO

import pygame as pg

from . import inputs, evts

#: A ``{cls.device: {cls.name: cls}}`` dict of usable named
#: :class:`Input <engine.evt.inputs.Input>` subclasses.
inputs_by_name = {}
for i in vars(inputs).values(): # copy or it'll change size during iteration
    if (isinstance(i, type) and issubclass(i, inputs.Input) and
        hasattr(i, 'name')):
        inputs_by_name.setdefault(i.device, {})[i.name] = i
del i
#: A ``{cls.name: cls}`` dict of usable named
#: :class:`BaseEvent <engine.evt.evts.BaseEvent>` subclasses.
evts_by_name = dict(
    (evt.name, evt) for evt in vars(evts).values()
    if (isinstance(evt, type) and
        (issubclass(evt, evts.BaseEvent) and hasattr(evt, 'name')))
)

_input_identifiers = {
    inputs.KbdKey: lambda k: getattr(pg, 'K_' + k),
    inputs.MouseButton: lambda k: getattr(inputs.mbtn, k),
    inputs.PadButton: {}.__getitem__,
    inputs.PadAxis: {}.__getitem__,
    inputs.PadHat: {}.__getitem__
}


def _parse_input (lnum, n_components, words, scalable):
    # parse an input declaration line; words is non-empty; returns input
    # TODO: mods (remember _SneakyMultiKbdKey)
    # find the device
    device_i = None
    for i, w in enumerate(words):
        if scalable and '*' in w:
            w = w[w.find('*') + 1:]
        if w in inputs_by_name:
            device_i = i
            break
    if device_i is None:
        raise ValueError('line {0}: input declaration contains no '
                         'device'.format(lnum))
    device = words[device_i]
    # parse relaxis scale
    scale = None
    if scalable and '*' in device:
        i = device.find('*')
        scale_s = device[:i]
        device = device[i + 1:]
        if i:
            try:
                scale = float(scale_s)
            except ValueError:
                raise ValueError('line {0}: invalid scaling value'
                                 .format(lnum))
    # everything before device is a component
    evt_components = words[:device_i]
    if evt_components:
        cnames = evts.evt_component_names[n_components]
        for c in evt_components:
            if c not in cnames:
                raise ValueError('line {0}: invalid event component: \'{1}\''
                                .format(lnum, c))
    else:
        # use all components: let the event check for mismatches
        evt_components = None
    words = words[device_i + 1:]
    # find the name
    names = inputs_by_name[device]
    name_i = None
    for i, w in enumerate(words):
        if ':' in w:
            w = w[:w.find(':')]
        if w in names:
            name_i = i
            break
    input_components = None
    if name_i is None:
        name = None
    else:
        name = words[name_i]
        # parse input components
        if ':' in name:
            i = name.find(':')
            ics_s = name[i + 1:]
            name = name[:i]
            if ics_s:
                # comma-separated ints
                try:
                    # int() handles whitespace fine
                    input_components = [int(ic) for ic in ics_s.split(',')]
                except ValueError:
                    raise ValueError('line {0}: invalid input components'
                                     .format(lnum))
    if not name:
        # name empty or entire argument omitted
        if len(names) == 1:
            # but there's only one choice
            name = names.keys()[0]
        else:
            raise ValueError('line {0}: input declaration contains no name'
                             .format(lnum))
    cls = names[name]
    # only device ID preceeds name
    if name_i is None or name_i == 0:
        device_id = True
    elif name_i == 1:
        # ^^
        print >> sys.stderr, 'warning: got device ID for input that ' \
                             'doesn\'t support it; ignoring'
        device_id = words[0]
        if device_id and device_id[0] == '<' and device_id[-1] == '>':
            device_id = device_id[1:-1]
        else:
            # ^^
            try:
                device_id = int(device_id)
            except ValueError:
                raise ValueError('line {0}: invalid device ID: \'{1}\''
                                 .format(lnum, device_id))
    else:
        raise ValueError('line {0}: too many arguments between device and name'
                         .format(lnum))
    if name_i is not None:
        words = words[name_i + 1:]
    # now just arguments remain
    if cls in (inputs.PadButton, inputs.PadAxis, inputs.PadHat):
        args = [device_id]
    else:
        args = []
    if cls in _input_identifiers: # [^^]
        # first is an identifier
        src = _input_identifiers[cls]
        if not words:
            raise ValueError('line {0}: too few arguments'.format(lnum))
        try:
            ident = src(words[0])
        except (AttributeError, KeyError):
            try:
                ident = int(words[0])
            except ValueError:
                raise ValueError('line {0}: invalid {1} code'
                                 .format(lnum, name))
        args.append(ident)
        words = words[1:]
    if cls in (inputs.KbdKey, inputs.MouseButton, inputs.PadButton):
        # no more args
        if words:
            raise ValueError('line {0}: too many arguments'.format(lnum))
    elif cls in (inputs.PadAxis, inputs.PadHat, inputs.MouseAxis):
        if cls is inputs.MouseAxis:
            # next arg is optional boundary
            if words:
                try:
                    args.append(float(words[0]))
                except ValueError:
                    raise ValueError('line {0}: invalid \'boundary\' argument'
                                     .format(lnum))
                words = words[1:]
        # next args are optional thresholds
        thresholds = []
        if words:
            # let the input check values/numbers of components
            for w in words:
                try:
                    thresholds.append(float(w))
                except ValueError:
                    raise ValueError('line {0}: invalid \'threshold\' argument'
                                     .format(lnum))
        if thresholds:
            args.append(thresholds)
    return ((() if scale is None else (scale,)) +
            (cls(*args), evt_components, input_components))


def _parse_evthead (lnum, words):
    # parse first line of an event declaration
    # words is non-empty and first is guaranteed to be a valid event type
    # returns (cls, name, args)
    evt_type = words[0]
    # get name
    if len(words) < 2:
        raise ValueError('line {0}: expected name for event'.format(lnum))
    name = words[1]
    if not name:
        raise ValueError('line {0}: invalid event name: \'{0}\''.format(lnum))
    words = words[2:]
    # parse args according to event type
    args = []
    if evt_type in ('axis', 'axis2', 'relaxis', 'relaxis2'):
        if words:
            raise ValueError('line {0}: axis and relaxis events take no '
                             'arguments'.format(lnum))
    elif evt_type in ('button', 'button2', 'button4'):
        # args are modes, last two may be repeat delays
        for i in xrange(len(words)):
            if hasattr(evts.bmode, words[i]):
                args.append(getattr(evts.bmode, words[i]))
            else:
                # check for float
                if i != len(words) - 2:
                    raise ValueError('line {0}: invalid event arguments'
                                     .format(lnum))
                for w in words[-2:]:
                    try:
                        args.append(float(w))
                    except ValueError:
                        raise ValueError('line {0}: invalid event arguments'
                                         .format(lnum))
                break
    else: # ^^
        raise ValueError('line {0}: unknown event type \'{1}\''
                         .format(lnum, evt_type))
    return (evts_by_name[evt_type], name, args)


def parse (config):
    """Parse an event configuration.

parse(config) -> parsed

:arg config: an open file-like object (with a ``readline`` method).

:return: ``{name: event}`` for each named
         :class:`BaseEvent <engine.evt.evts.BaseEvent>` instance.

"""
    parsed = {} # events
    evt_cls = None
    lnum = 1
    while True:
        line = config.readline()
        if not line:
            # end of file
            break
        words = shlex.split(line, True)
        if words:
            if words[0] in evts_by_name:
                # new event: create and add current event
                if evt_cls is not None:
                    parsed[evt_name] = evt_cls(*args)
                evt_cls, evt_name, args = _parse_evthead(lnum, words)
                if evt_name in parsed:
                    raise ValueError('line {0}: duplicate event name'
                                     .format(lnum))
                scalable = evt_cls.name in ('relaxis', 'relaxis2')
            else:
                if evt_cls is None:
                    raise ValueError('line {0}: expected event'.format(lnum))
                # input line
                if issubclass(evt_cls, evts.MultiEvent):
                    n_cs = evt_cls.multiple * evt_cls.child.components
                else:
                    n_cs = evt_cls.components
                args.append(_parse_input(lnum, n_cs, words, scalable))
        # else blank line
        lnum += 1
    if evt_cls is not None:
        parsed[evt_name] = evt_cls(*args)
    return parsed


def parse_s (config):
    """Parse an event configuration from a string.

parse(config) -> parsed

:arg config: the string to parse

:return: ``{name: event}`` for each named
         :class:`BaseEvent <engine.evt.evts.BaseEvent>` instance.

"""
    return parse(StringIO(config))
