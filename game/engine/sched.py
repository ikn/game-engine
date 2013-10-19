"""Event scheduler and interpolation."""

from time import time
from bisect import bisect
from math import cos, atan, exp
from random import randrange, expovariate
from functools import partial

from pygame.time import wait

from .conf import conf
from .util import ir


def _match_in_nest (obj, x):
    """Check if every object in a data structure is equal to some given object.

_match_in_nest(obj, x)

obj: data structure to look in: an arbitrarily nested list of lists.
x: object to compare to  (not a list or tuple).

"""
    if isinstance(obj, (tuple, list)):
        return all(_match_in_nest(o, x) == x for o in obj)
    else:
        return obj == x


def call_in_nest (f, *args):
    """Collapse a number of similar data structures into one.

Used in ``interp_*`` functions.

call_in_nest(f, *args) -> result

:arg f: a function to call with elements of ``args``.
:arg args: each argument is a data structure of nested lists with a similar
           format.

:return: a new structure in the same format as the given arguments with each
         non-list object the result of calling ``f`` with the corresponding
         objects from each arg.

For example::

    >>> f = lambda n, c: str(n) + c
    >>> arg1 = [1, 2, 3, [4, 5], []]
    >>> arg2 = ['a', 'b', 'c', ['d', 'e'], []]
    >>> call_in_nest(f, arg1, arg2)
    ['1a', '2b', '3c', ['4d', '5e'], []]

One argument may have a list where others do not.  In this case, those that do
not have the object in that place passed to ``f`` for each object in the
(possibly further nested) list in the argument that does.  For example::

    >>> call_in_nest(f, [1, 2, [3, 4]], [1, 2, 3], 1)
    [f(1, 1, 1), f(2, 2, 1), [f(3, 3, 1),  f(4, 3, 1)]]

However, in arguments with lists, all lists must be the same length.

"""
    # Rect is a sequence but isn't recognised as collections.Sequence, so test
    # this way
    is_list = [(hasattr(arg, '__len__') and hasattr(arg, '__getitem__') and
                not isinstance(arg, basestring))
               for arg in args]
    if any(is_list):
        n = len(args[is_list.index(True)])
        # listify non-list args (assume all lists are the same length)
        args = (arg if this_is_list else [arg] * n
                for this_is_list, arg in zip(is_list, args))
        return [call_in_nest(f, *inner_args) for inner_args in zip(*args)]
    else:
        return f(*args)


def _cmp_structure (x, y):
    """Find whether the (nested list) structure of two objects is the same."""
    is_list = isinstance(x, (tuple, list))
    if is_list != isinstance(y, (tuple, list)):
        # one is a list, one isn't
        return False
    elif is_list:
        # both are lists: check length and contents
        return len(x) == len(y) and \
               all(_cmp_structure(xi, yi) for xi, yi in zip(x, y))
    else:
        # neither is a list
        return True


def interp_linear (*waypoints):
    """Linear interpolation for :meth:`Scheduler.interp`.

interp_linear(*waypoints) -> f

:arg waypoints: each is ``(v, t)`` to set the value to ``v`` at time ``t``.
                ``t`` can be omitted for any but the last waypoint: the first
                is ``0``, and other gaps are filled in with equal spacing.
                ``v`` is like the arguments taken by :func:`call_in_nest`, and
                we interpolate for each number in the nested list structure of
                ``v``.  Some objects in the ``v`` structures may be
                non-numbers, in which case they will not be varied (maybe your
                function takes another argument you don't want to vary);
                objects may be ``None`` to always use the initial value in that
                position.

:return: a function for which ``f(t) = v`` for every waypoint ``(t, v)``, with
         intermediate values linearly interpolated between waypoints.

"""
    # fill in missing times
    vs = []
    ts = []
    last = waypoints[-1]
    for w in waypoints:
        if w is last or _cmp_structure(w, last):
            vs.append(w[0])
            ts.append(w[1])
        else:
            vs.append(w)
            ts.append(None)
    ts[0] = 0
    # get groups with time = None
    groups = []
    group = None
    for i, (v, t) in enumerate(zip(vs, ts)):
        if t is None:
            if group is None:
                group = [i]
                groups.append(group)
        else:
            if group is not None:
                group.append(i)
            group = None
    # and assign times within those groups
    for i0, i1 in groups:
        t0 = ts[i0 - 1]
        dt = float(ts[i1] - t0) / (i1 - (i0 - 1))
        for i in xrange(i0, i1):
            ts[i] = t0 + dt * (i - (i0 - 1))
    interp_val = lambda r, v1, v2, v0: (r * (v2 - v1) + v1) \
                                       if isinstance(v2, (int, float)) else v0

    def val_gen ():
        t = yield
        while True:
            # get waypoints we're between
            i = bisect(ts, t)
            if i == 0:
                # before start
                t = yield vs[0]
            elif i == len(ts):
                # past end: use final value, then end
                last_val = lambda vl, v0: vl if isinstance(vl, (int, float)) \
                                             else v0
                t = yield call_in_nest(last_val, vs[-1], vs[0])
                yield None
            else:
                v1 = vs[i - 1]
                v2 = vs[i]
                t1 = ts[i - 1]
                t2 = ts[i]
                # get ratio of the way between waypoints
                r = 1 if t2 == t1 else (t - t1) / (t2 - t1) # t is always float
                t = yield call_in_nest(interp_val, r, v1, v2, vs[0])

    # start the generator; get_val is its send method
    g = val_gen()
    g.next()
    return g.send


def interp_target (v0, target, damp, freq = 0, speed = 0, threshold = 0):
    """Move towards a target.

interp_target(v0, target, damp, freq = 0, speed = 0, threshold = 0) -> f

:arg v0: the initial value (a structure of numbers like arguments to
         :func:`call_in_nest`).  Elements which are not numbers are ignored.
:arg target: the target value (has the same form as ``v0``).
:arg damp: rate we move towards the target (``> 0``).
:arg freq: if ``damp`` is small, oscillation around ``target`` can occur, and
           this controls the frequency.  If ``0``, there is no oscillation.
:arg speed: if ``freq`` is non-zero, this is the initial 'speed', in the same
            form as ``v0``.
:arg threshold: stop when within this distance of ``target``; in the same form
                as ``v0``.  If ``None``, never stop.  If varying more than one
                number, only stop when every number is within its threshold.

:return: a function that returns position given the current time.

"""
    if v0 == target: # nothing to do
        return lambda t: None

    def get_phase (v0, target, sped):
        if freq == 0 or not isinstance(v0, (int, float)) or v0 == target:
            return 0
        else:
            return atan(-(float(speed) / (v0 - target) + damp) / freq)

    phase = call_in_nest(get_phase, v0, target, speed)

    def get_amplitude (v0, target, phase):
        if isinstance(v0, (int, float)):
            return (v0 - target) / cos(phase) # cos(atan(x)) is never 0

    amplitude = call_in_nest(get_amplitude, v0, target, phase)

    def get_val (t):
        def interp_val (v0, target, amplitude, phase, threshold):
            if not isinstance(v0, (int, float)):
                return v0
            # amplitude is None if non-number
            if amplitude is None or v0 == target:
                if threshold is not None:
                    return None
                return v0
            else:
                dist = amplitude * exp(-damp * t)
                if threshold is not None and abs(dist) <= threshold:
                    return None
                return dist * cos(freq * t + phase) + target

        rtn = call_in_nest(interp_val, v0, target, amplitude, phase, threshold)
        if _match_in_nest(rtn, None):
            # all done
            rtn = None
        return rtn

    return get_val


def interp_shake (centre, amplitude = 1, threshold = 0, signed = True):
    """Shake randomly.

interp_shake(centre, amplitude = 1, threshold = 0, signed = True) -> f

:arg centre: the value to shake about; a nested list (a structure of numbers
             like arguments to :func:`call_in_nest`).  Elements which are not
             numbers are ignored.
:arg amplitude: a number to multiply the value by.  This can be a function that
                takes the elapsed time in seconds to vary in time.  Has the
                same form as ``centre`` (return value does, if a function).
:arg threshold: stop when ``amplitude`` is this small; in the same form as
                ``centre``.  If ``None``, never stop.  If varying more than one
                number, only stop when every number is within its threshold.
:arg signed: whether to shake around ``centre``.  If ``False``, values are
             always greater than ``centre`` (note that ``amplitude`` may be
             signed).

:return: a function that returns position given the current time.

"""
    def get_val (t):
        def interp_val (centre, amplitude, threshold):
            if not isinstance(centre, (int, float)):
                return centre
            if threshold is not None and abs(amplitude) <= threshold:
                return None
            val = amplitude * expovariate(1)
            if signed:
                val *= 2 * randrange(2) - 1
            return centre + val

        a = amplitude(t) if callable(amplitude) else amplitude
        rtn = call_in_nest(interp_val, centre, a, threshold)
        if _match_in_nest(rtn, None):
            # all done
            rtn = None
        return rtn

    return get_val


def interp_round (get_val, do_round = True):
    """Round the output of an existing interpolation function to integers.

interp_round(get_val, round_val = True) -> f

:arg get_val: the existing function.
:arg do_round: determines which values to round.  This is in the form of the
               values ``get_val`` returns, a structure of lists and booleans
               corresponding to each number (see :func:`call_in_nest`).

:return: the ``get_val`` wrapper that rounds the returned value.

"""
    def round_val (do, v):
        return ir(v) if isinstance(v, (int, float)) and do else v

    def round_get_val (t):
        return call_in_nest(round_val, do_round, get_val(t))

    return round_get_val


def interp_repeat (get_val, period = None, t_min = 0, t_start = None):
    """Repeat an existing interpolation function.

interp_repeat(get_val[, period], t_min = 0, t_start = t_min) -> f

:arg get_val: an existing interpolation function, as taken by
              :meth:`Scheduler.interp`.

Times passed to the returned function are looped around to fit in the range
[``t_min``, ``t_min + period``), starting at ``t_start``, and the result is
passed to ``get_val``.

If ``period`` is not given, repeats end at the end of ``get_val``.  Note that
this will not be entirely accurate, and you're probably better off specifying a
value if you can easily do so.

:return: the ``get_val`` wrapper that repeats ``get_val`` over the given
         period.

"""
    if t_start is None:
        t_start = t_min

    def val_gen ():
        pd = period
        val = None
        t = yield
        while True:
            # transform time and get the corresponding value
            t = t_min + (t_start - t_min + t)
            if pd is not None:
                t %= pd
            # else still in the first period (and want the whole thing)
            new_val = get_val(t)
            # if we got a value, yield it
            if new_val is not None:
                val = new_val
            elif pd is None:
                # else get_val has ended: we know the period size now
                pd = t - t_min
            # else yield the previous value (which may be None: if get_val
            #: returns None on the first call, we want to yield None)
            t = yield val

    # start the generator
    g = val_gen()
    g.next()
    return g.send


def interp_oscillate (get_val, t_max = None, t_min = 0, t_start = None):
    """Repeat a linear oscillation over an existing interpolation function.

interp_oscillate(get_val[, t_max], t_min = 0, t_start = t_min) -> f

:arg get_val: an existing interpolation function, as taken by
              :meth:`Scheduler.interp`.

Times passed to the returned function are looped and reversed to fit in the
range [``t_min``, ``t_max``), starting at ``t_start``.  If ``t_start`` is in
the range [``t_max``, ``2 * t_max - t_min``), it is mapped to the 'return
journey' of the oscillation.

If ``t_max`` is not given, it is taken to be the end of ``get_val``.  Note that
this will not be entirely accurate, and you're probably better off specifying a
value if you can easily do so.

:return: the ``get_val`` wrapper that oscillates ``get_val`` over the given
         range.

"""
    if t_start is None:
        t_start = t_min
    if t_max is not None:
        period = t_max - t_min
    else:
        period = None

    def val_gen ():
        pd = period
        val = None
        t = yield
        while True:
            # transform time and get the corresponding value
            t = t_start - t_min + t
            if pd is not None:
                t %= 2 * pd
                if t >= pd:
                    t = 2 * pd - t
            # else still in the first period (and want the whole thing)
            new_val = get_val(t)
            # if we got a value, yield it
            if new_val is not None:
                val = new_val
            elif pd is None:
                # else get_val has ended: we know the period size now
                pd = t - t_min
            # else yield the previous value (which may be None: if get_val
            #: returns None on the first call, we want to yield None)
            t = yield val

    # start the generator
    g = val_gen()
    g.next()
    return g.send


class Timer (object):
    """Frame-based timer.

Timer(fps=60)

:arg fps: frames per second to aim for.

"""

    def __init__ (self, fps=60):
        #: The current length of a frame in seconds.
        self.frame = None
        #: The current average frame time in seconds (like
        #: :attr:`current_fps`).
        self.current_frame_time = None
        self.fps = fps
        #: The amount of time in seconds that has elapsed since the start of
        #: the current call to :meth:`run`, if any.
        self.t = 0
        #: How many seconds the last frame took to run (including calling the
        #: ``cb`` argument to :meth:`run` and any sleeping to make up a full
        #: frame).
        self.elapsed = None

    @property
    def fps (self):
        """The target FPS.  Set this directly."""
        return self._fps

    @fps.setter
    def fps (self, fps):
        self._fps = int(round(fps))
        self.current_frame_time = self.frame = 1. / fps

    @property
    def current_fps (self):
        """The current framerate, an average based on
:data:`conf.FPS_AVERAGE_RATIO`.

If this is less than :attr:`fps`, then the timer isn't running at full speed
because of slow calls to the ``cb`` argument to :meth:`run`.

"""
        return 1 / self.current_frame_time

    def run (self, cb, *args, **kwargs):
        """Run indefinitely or for a specified amount of time.

run(cb, *args[, seconds][, frames]) -> remain

:arg cb: a function to call every frame.
:arg args: extra arguments to pass to cb.
:arg seconds: the number of seconds to run for; can be a float.  Accounts for
              changes to :attr:`fps`.
:arg frames: the number of frames to run for; can be a float.  Ignored if
             ``seconds`` is passed.

If neither ``seconds`` nor ``frames`` is given, run forever (until :meth:`stop`
is called).  Time passed is based on the number of frames that have passed, so
it does not necessarily reflect real time.

:return: the number of seconds/frames left until the timer has been running for
         the requested amount of time (or ``None``, if neither were given).
         This may be less than ``0`` if ``cb`` took a long time to run.

"""
        r = conf.FPS_AVERAGE_RATIO
        self.t = 0
        self._stopped = False
        seconds = kwargs.get('seconds')
        frames = kwargs.get('frames')
        if seconds is not None:
            seconds = max(seconds, 0)
        elif frames is not None:
            frames = max(frames, 0)
        # main loop
        t0 = time()
        while True:
            # call the callback
            frame = self.frame
            cb(*args)
            t_gone = time() - t0
            # return if necessary
            if self._stopped:
                if seconds is not None:
                    return seconds - t_gone
                elif frames is not None:
                    return frames - t_gone / frame
                else:
                    return None
            # check how long to wait until the end of the frame by aiming for a
            # rolling frame average equal to the target frame time
            frame_t = (1 - r) * self.current_frame_time + r * t_gone
            t_left = (frame - frame_t) / r
            # reduce wait if we would go over the requested running time
            if seconds is not None:
                t_left = min(seconds, t_left)
            elif frames is not None:
                t_left = min(frames * frame, t_left)
            # wait
            if t_left > 0:
                wait(int(1000 * t_left))
                t_gone += t_left
                frame_t += r * t_left
            # update some attributes
            t0 += t_gone
            self.elapsed = t_gone
            self.current_frame_time = frame_t
            self.t += t_gone
            # return if necessary
            if seconds is not None:
                seconds -= t_gone
                if seconds <= 0:
                    return seconds
            elif frames is not None:
                frames -= t_gone / frame
                if frames <= 0:
                    return frames

    def stop (self):
        """Stop the current call to :meth:`run`, if any."""
        self._stopped = True


class Scheduler (Timer):
    """Frame-based event scheduler.

Scheduler(fps = 60)

:arg fps: frames per second to aim for.

"""

    def __init__ (self, fps = 60):
        Timer.__init__(self, fps)
        self._cbs = {}
        self._max_id = 0

    def run (self, seconds = None, frames = None):
        """Start the scheduler.

run([seconds][, frames]) -> remain

Arguments and return value are as for :meth:`Timer.run`.

"""
        return Timer.run(self, self._update, seconds = seconds,
                         frames = frames)

    def add_timeout (self, cb, seconds=None, frames=None, repeat_seconds=None,
                     repeat_frames=None):
        """Call a function after a delay.

add_timeout(cb[, seconds][, frames][, repeat_seconds][, repeat_frames])
            -> ident

:arg cb: the function to call.
:arg seconds: how long to wait before calling, in seconds (respects changes to
              :attr:`Timer.fps`).  If passed, ``frames`` is ignored.
:arg frames: how long to wait before calling, in frames (same number of frames
             even if :attr:`Timer.fps` changes).
:arg repeat_seconds: how long to wait between calls, in seconds; time is
                     determined as for ``seconds``.  If passed,
                     ``repeat_frames`` is ignored; if neither is passed, the
                     initial time delay is used between calls.
:arg repeat_frames: how long to wait between calls, in frames (like
                    ``repeat_seconds``).

:return: a timeout identifier to pass to :meth:`rm_timeout`.  This is
         guaranteed to be unique over time.

Times can be floats, in which case part-frames are carried over, and time
between calls is actually an average over a large enough number of frames.

``cb`` can return a boolean true object to repeat the timeout; otherwise it
will not be called again.

"""
        if seconds is not None:
            frames = None
        elif frames is None:
            raise TypeError('expected \'seconds\' or \'frames\' argument')
        if repeat_seconds is not None:
            repeat_frames = None
        elif repeat_frames is None:
            repeat_seconds = seconds
            repeat_frames = frames
        self._cbs[self._max_id] = [seconds, frames, repeat_seconds,
                                   repeat_frames, True, cb]
        self._max_id += 1
        # ID is key in self._cbs
        return self._max_id - 1

    def rm_timeout (self, *ids):
        """Remove the timeouts with the given identifiers.

Missing IDs are ignored.

"""
        cbs = self._cbs
        for i in ids:
            if i in cbs:
                del cbs[i]

    def pause_timeout (self, *ids):
        """Pause the timeouts with the given identifiers."""
        cbs = self._cbs
        for i in ids:
            if i in cbs:
                cbs[i][4] = False

    def unpause_timeout (self, *ids):
        """Continue the paused timeouts with the given identifiers."""
        cbs = self._cbs
        for i in ids:
            if i in cbs:
                cbs[i][4] = True

    def _update (self):
        """Handle callbacks this frame."""
        cbs = self._cbs
        frame = self.frame
        # cbs might add/remove cbs, so use items instead of iteritems
        for i, data in cbs.items():
            if i not in cbs:
                # removed since we called .items()
                continue
            if data[0] is not None:
                remain = 0
                dt = frame
            else:
                remain = 1
                dt = 1
            if data[4]:
                data[remain] -= dt
                if data[remain] <= 0:
                    # call callback
                    if data[5]():
                        # add on delay
                        total = data[2] is None
                        data[total] += data[total + 2]
                    elif i in cbs: # else removed in above call
                        del cbs[i]
            # else paused

    def interp (self, get_val, set_val, t_max = None, bounds = None,
                end = None, round_val = False, multi_arg = False,
                resolution = None):
        """Vary a value over time.

interp(get_val, set_val[, t_max][, bounds][, end], round_val = False,
       multi_arg = False[, resolution]) -> timeout_id

:arg get_val: a function called with the elapsed time in seconds to obtain the
              current value.  If this function returns ``None``, the
              interpolation will be canceled.  The ``interp_*`` functions in
              this module can be used to construct such functions.
:arg set_val: a function called with the current value to set it.  This may
              also be an ``(obj, attr)`` tuple to do ``obj.attr = val``.
:arg t_max: if time becomes larger than this, cancel the interpolation.
:arg bounds: a function that takes the value returned from ``get_val`` and
             checks if it is outside of some boundaries, and returns the
             boundary value ``bdy`` if so (else None).  If the value falls out
             of bounds, ``set_val`` is called with ``bdy`` and the
             interpolation is canceled.
:arg end: used to do some cleanup when the interpolation is canceled (when
          ``get_val`` returns ``None`` or ``t_max``, ``val_min`` or ``val_max``
          comes into effect, but not when the ``rm_timeout`` method is called
          with ``timeout_id``).  This can be a final value to pass to
          ``set_val``, or a function to call without arguments.  If the
          function returns a (non-``None``) value, ``set_val`` is called with
          it.
:arg round_val: whether to round the value(s) (see :func:`interp_round` for
                details).
:arg multi_arg: whether values should be interpreted as lists of arguments to
                pass to ``set_val`` instead of a single argument.
:arg resolution: 'framerate' to update the value at.  If not given, the value
                 is set every frame it changes; if given, this sets an upper
                 limit on the number of times per second the value may updated.
                 The current value of :attr:`fps <Timer.fps>` (which may change
                 over the interpolation) also puts an upper limit on the rate.

:return: an identifier that can be passed to :meth:`rm_timeout` to remove the
        callback that continues the interpolation.  In this case ``end`` is not
        respected.

"""
        if round_val:
            get_val = interp_round(get_val, round_val)
        if not callable(set_val):
            obj, attr = set_val
            set_val = lambda val: setattr(obj, attr, val)

        def timeout_cb ():
            if resolution is not None:
                update_frame = 1. / resolution
            t = 0
            dt = 0
            last_v = None
            done = False
            while True:
                frame = self.frame
                t += frame
                dt += frame
                if resolution is None or dt >= update_frame:
                    if resolution is not None:
                        dt -= update_frame
                    # perform an update
                    v = get_val(t)
                    if v is None:
                        done = True
                    # check bounds
                    elif t_max is not None and t > t_max:
                        done = True
                    else:
                        if bounds is not None:
                            bdy = bounds(v)
                            if bdy is not None:
                                done = True
                                v = bdy
                        if v != last_v:
                            set_val(*v) if multi_arg else set_val(v)
                            last_v = v
                    if done:
                        # canceling for some reason
                        if callable(end):
                            v = end()
                        else:
                            v = end
                        # set final value if want to
                        if v is not None and v != last_v:
                            set_val(*v) if multi_arg else set_val(v)
                        yield False
                        # just in case we get called again (should never happen)
                        return
                    else:
                        yield True
                else:
                    yield True

        return self.add_timeout(timeout_cb().next, frames=1)

    def interp_simple (self, obj, attr, target, t, end_cb = None,
                       round_val = False):
        """A simple version of :meth:`interp`.

Varies an object's attribute linearly from its current value to a target value
in a set amount of time.

interp_simple(obj, attr, target, t[, end_cb], round_val = False) -> timeout_id

:arg obj: vary an attribute of this object.
:arg attr: the attribute name of ``obj`` to vary.
:arg target: a target value, in the same form as the current value in the given
             attribute (see :func:`call_in_nest`).
:arg t: the amount of time to take to reach the target value, in seconds.
:arg end_cb: a function to call when the target value has been reached.
:arg round_val: whether to round the value(s) (see :func:`interp_round` for
                details).

:return: an identifier that can be passed to :meth:`rm_timeout` to remove the
        callback that continues the interpolation.  In this case ``end_cb`` is
        not called.

"""
        get_val = interp_linear(getattr(obj, attr), (target, t))
        return self.interp(get_val, (obj, attr), end = end_cb,
                           round_val = round_val)

    def _interp_locked (self, interp_fn, *args, **kwargs):
        # HACK: Python 2 closures aren't great
        timeout_id = [None]

        def interp (*args, **kwargs):
            if timeout_id[0] is not None:
                self.rm_timeout(timeout_id[0])
            timeout_id[0] = interp_fn(*args, **kwargs)
            return timeout_id[0]

        return partial(interp, *args, **kwargs)

    def interp_locked (self, *args, **kwargs):
        """Generate a :meth:`interp` wrapper that allows only one running
interpolation.

With each successive call, the current interpolation is aborted and a new one
started.

The wrapper is partially applied using the positional and keyword arguments
passed to this function.  Typical usage is as follows::

    # create the wrapper that knows how to set values
    interp = scheduler.interp_locked(set_val=set_val)

    [...]

    # call it at some point with an interpolation function
    interp(get_val)

    [...]

    # call it again later with a different interpolation function
    interp(get_val2)
    # only one interpolation is running

"""
        return self._interp_locked(self.interp, *args, **kwargs)

    def interp_simple_locked (self, *args, **kwargs):
        """Like :meth:`interp_locked`, but wraps :meth:`interp_simple`."""
        return self._interp_locked(self.interp_simple, *args, **kwargs)

    def counter (self, t, autoreset=False):
        """Create and return a :class:`Counter` that uses this instance for
timing.

counter(t, autoreset=False) -> new_counter

Arguments are as taken by :class:`Counter`.

"""
        return Counter(self, t, autoreset)


class Counter (object):
    """A simple way of counting down to an event.

Counter(scheduler, t, autoreset=False)

:arg scheduler: :class:`Scheduler` instance to use for timing.
:arg t: how long a countdown lasts, in seconds.
:arg autoreset: whether to reset and count down from the beginning again when
                the countdown ends.  This is only useful with :attr:`cbs` (the
                finished state never becomes ``True``).

An instance is boolean ``True`` if the countdown has finished, else ``False``.
The initial state is finished---use :meth:`reset` to start the countdown.

An instance is boolean ``True`` if the countdown has finished, else ``False``.

See also :meth:`Scheduler.counter`.

"""

    def __init__ (self, scheduler, t, autoreset=False):
        self._scheduler = scheduler
        self._t = t
        #: As passed to the constructor.
        self.autoreset = autoreset
        #: ``set`` of functions to call when the countdown ends.
        self.cbs = set()
        self._timer_id = None
        self._finished = True

    @property
    def t (self):
        """How long a countdown lasts, in seconds.

Changing this resets the countdown (if running).

"""
        return self._t

    @t.setter
    def t (self, t):
        self._t = t
        if self._timer_id is not None:
            self.reset()

    def __nonzero__ (self):
        return self._finished

    def _end_cb (self):
        # called when the timeout ends
        if not self.autoreset:
            self._timer_id = None
            self._finished = True
        for cb in self.cbs:
            cb()
        return self.autoreset

    def reset (self):
        """Start counting down from the beginning again.

reset() -> self

Starts counting down even if the countdown wasn't already running.

"""
        if self._timer_id is not None:
            self._scheduler.rm_timeout(self._timer_id)
        self._finished = False
        self._timer_id = self._scheduler.add_timeout(self._end_cb, self.t)
        return self

    def cancel (self):
        """Stop counting down and set the finished state to ``False``.

cancel() -> self

"""
        if self._timer_id is not None:
            self._scheduler.rm_timeout(self._timer_id)
            self._timer_id = None
            self._finished = False
        return self

    def finish (self):
        """Stop counting down and set the finished state to ``True``.

finish() -> self

"""
        self.cancel()
        self._finished = True
        return self

    def cb (self, *cbs):
        """Add any number of callbacks to :attr:`cbs`.

cb(*cbs) -> self

Callbacks take no arguments.

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

    def pause (self):
        """Pause the counter, if running."""
        if self._timer_id is not None:
            self._scheduler.pause_timeout(self._timer_id)

    def unpause (self):
        """Unpause the counter, if paused."""
        if self._timer_id is not None:
            self._scheduler.unpause_timeout(self._timer_id)
