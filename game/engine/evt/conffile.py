import sys
import shlex

import pygame as pg

from . import inputs, evts

##: A ``{cls.device: {cls.name: cls}}`` dict of usable named :class:`Input`
##: subclasses.
inputs_by_name = {}
for i in vars(inputs).values(): # copy or it'll change size during iteration
    if (isinstance(i, type) and issubclass(i, inputs.Input) and
        hasattr(i, 'name')):
        inputs_by_name.setdefault(i.device, {})[i.name] = i
del i
##: A ``{cls.name: cls}`` dict of usable named :class:`Event` subclasses.
evts_by_name = dict(
    (evt.name, evt) for evt in vars(evts).values()
    if (isinstance(evt, type) and
        (issubclass(evt, evts.Event) and hasattr(evt, 'name')))
)

_input_identifiers = {
    inputs.KbdKey: lambda k: getattr(pg, 'K_' + k),
    inputs.MouseButton:
        {'LEFT': 1, 'RIGHT': 2, 'MIDDLE': 3, 'UP': 4, 'DOWN': 5}.__getitem__,
    inputs.PadButton: {}.__getitem__,
    inputs.PadAxis: {}.__getitem__,
    inputs.PadHat: {}.__getitem__
}


def _parse_input (lnum, n_components, words):
    # parse an input declaration line; words is non-empty; returns input
    # TODO: mods (remember _SneakyMultiKbdKey)
    # find the device
    device_i = None
    for i, w in enumerate(words):
        if w in inputs_by_name:
            device_i = i
            break
    if device_i is None:
        raise ValueError('line {0}: input declaration contains no '
                         'device'.format(lnum))
    device = words[device_i]
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
    # TODO: input components
    names = inputs_by_name[device]
    name_i = None
    for i, w in enumerate(words):
        if w in names:
            name_i = i
            break
    if name_i is None:
        if len(names) == 1:
            # no name, but there's only one choice
            name = names.keys()[0]
        else:
            raise ValueError('line {0}: input declaration contains no name'
                             .format(lnum))
    else:
        name = words[name_i]
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
        args.append(thresholds)
        if words:
            # let the input check values/numbers of components
            for w in words:
                try:
                    thresholds.append(float(w))
                except ValueError:
                    raise ValueError('line {0}: invalid \'threshold\' argument'
                                     .format(lnum))
    print cls, args, evt_components
    return (cls(*args), None if evt_components is None else [cnames.index(c) for c in evt_components])


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
    if evt_type in ('axis', 'relaxis'):
        if words:
            raise ValueError('line {0}: axis and relaxis events take no '
                             'arguments'.format(lnum))
    elif evt_type == 'button':
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


def parse (s):
    """Parse the given string as an event configuration.

parse(s) -> parsed

:return: ``{name: event}`` for each named :class:`Event` instance.

"""
    lines = s.splitlines()
    parsed = {} # events
    evt_cls = None
    for i, line in enumerate(lines):
        words = shlex.split(line, True)
        if not words:
            # blank line
            continue
        if words[0] in evts_by_name:
            # new event: create and add current event
            if evt_cls is not None:
                parsed[evt_name] = evt_cls(*args)
            evt_cls, evt_name, args = _parse_evthead(i + 1, words)
            if evt_name in parsed:
                raise ValueError('line {0}: duplicate event name'
                                 .format(i + 1))
        else:
            if evt_cls is None:
                raise ValueError('line {0}: expected event'.format(i + 1))
            # input line
            args.append(_parse_input(i + 1, evt_cls.components, words))
    if evt_cls is not None:
        parsed[evt_name] = evt_cls(*args)
    return parsed