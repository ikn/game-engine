"""Event scheduler by Joseph Lansdowne.

Uses Pygame's wait function if available, else the less accurate time.sleep.
To use something else, do:

import sched
sched.wait = wait_function

This function should take the number of milliseconds to wait for.  This will
always be an integer.

Python version: 2.
Release: 11.

Licensed under the GNU General Public License, version 3; if this was not
included, you can find it here:
    http://www.gnu.org/licenses/gpl-3.0.txt

    CLASSES

Timer
Scheduler

    FUNCTIONS

interp_linear
interp_target
interp_round
interp_repeat
interp_oscillate

"""

from time import time
from bisect import bisect
from math import cos, atan, exp
from random import randrange, expovariate

try:
    from pygame.time import wait
except ImportError:
    from time import sleep

    def wait (t):
        sleep(int(t * 1000))


def ir (x):
    """Returns the argument rounded to the nearest integer."""
    # this is about twice as fast as int(round(x))
    y = int(x)
    return (y + (x - y >= .5)) if x > 0 else (y - (y - x >= .5))


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

Used in interp_* functions.

call_in_nest(f, *args) -> result

Each arg in args is a data structure of nested lists with a similar format (eg.
[1, 2, 3, [4, 5], []] and ['a', 'b', 'c', ['d', 'e'], []]).  result is a new
structure in the same format with each non-list object the result of calling f
with the corresponding objects from each arg (eg. f = lambda n, c: str(n) + c
produces the result ['1a', '2b', '3c', ['4d', '5e'], []]).

One argument may have a list where others do not.  In this case, those that do
not have the object in that place passed to f for each object in the (possibly
further nested) list in the argument that does.  For example, given
[1, 2, [3, 4]], [1, 2, 3] and 1, result is
[f(1, 1, 1), f(2, 2, 1), [f(3, 3, 1),  f(4, 3, 1)]].  However, in args with
lists, all lists must be the same length.

"""
    is_list = [isinstance(arg, (tuple, list)) for arg in args]
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
    """Linear interpolation for Scheduler.interp.

interp_linear(*waypoints) -> f

waypoints: each is (v, t) to set the value to v at time t.  t can be omitted
           for any but the last waypoint; the first is 0, and other gaps are
           filled in with equal spacing.  v is like the arguments taken by the
           call_in_nest function in this module, and we interpolate for each number in the nested list structure of v.  Some objects in the v
           structures may be non-numbers, in which case they will not be varied
           (maybe your function takes another argument you don't want to vary).

f: a function for which f(t) = v for every waypoint, with intermediate values
   linearly interpolated between waypoints.

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
    interp_val = lambda r, v1, v2: (r * (v2 - v1) + v1) \
                                   if isinstance(v1, (int, float)) else v1

    def val_gen ():
        t = yield
        while 1:
            # get waypoints we're between
            i = bisect(ts, t)
            if i == 0:
                # before start
                t = yield vs[0]
            elif i == len(ts):
                # past end: use final value, then end
                t = yield vs[-1]
                yield None # to avoid StopIteration issues
                return
            else:
                v0 = vs[i - 1]
                v1 = vs[i]
                t0 = ts[i - 1]
                t1 = ts[i]
                # get ratio of the way between waypoints
                r = 1 if t1 == t0 else (t - t0) / (t1 - t0) # t is always float
                t = yield call_in_nest(interp_val, r, v0, v1)

    # start the generator; get_val is its send method
    g = val_gen()
    g.next()
    return g.send


def interp_target (v0, target, damp, freq = 0, speed = 0, threshold = 0):
    """Move towards a target.

interp_target(v0, target, damp, freq = 0, speed = 0, threshold = 0) -> f

v0: the initial value (a structure of numbers like arguments to this module's
    call_in_nest function).  Elements which are not numbers are ignored.
target: the target value (has the same form as v0).
damp: rate we move towards the target (> 0).
freq: if damping is low, oscillation around the target can occur, and this
      controls the frequency.  If 0, there is no oscillation.
speed: if frequency is non-zero, this is the initial 'speed', in the same form
       as v0.
threshold: stop when within this distance of the target, in the same form as
           v0.  If None, never stop.  If varying more than one number, only
           stop when every number is within its threshold.

f: function that returns position given the current time.

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

interp(centre, amplitude = 1, threshold = 0, signed = True) -> f

centre: the value to shake about; a nested list (a structure of numbers like
        arguments to this module's call_in_nest function).  Elements which are
        not numbers are ignored.
amplitude: a number to multiply the value by.  This can be a function that
           takes the elapsed time in seconds to vary in time.  Has the same
           form as centre (return value if a function).
threshold: stop when amplitude is this small.  If None, never stop.  If varying
           more than one number, only stop when every number is within its
           threshold.
signed: whether to shake around the centre.  If False, values are greater than
        centre (not that amplitude may be signed).

f: function that returns position given the current time.

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

get_val: the existing function.  The values it returns are as the arguments
         taken by the call_in_nest function in this module.
do_round: determines which values to round.  This is in the form of the values
          get_val returns, a structure of lists and booleans corresponding to
          each number in get_val.  Any list in this structure can be replaced
          by a single boolean to apply to the entire (nested) list.  Non-number
          objects in the value's structure are ignored.

f: the get_val wrapper that rounds the returned value.

"""
    def round_val (do, v):
        return ir(v) if isinstance(v, (int, float)) and do else v

    def round_get_val (t):
        return call_in_nest(round_val, do_round, get_val(t))

    return round_get_val


def interp_repeat (get_val, period, t_min = 0, t_start = None):
    """Repeat an existing interpolation function.

interp_repeat(get_val, period, t_min = 0, t_start = t_min) -> f

get_val: an existing interpolation function, as taken by Scheduler.interp.

Times passed to the returned function are looped around to fit in the range
[t_min, t_min + period), starting at t_start, and the result is passed to
get_val.

f: the get_val wrapper that repeats get_val over the given period.

"""
    if t_start is None:
        t_start = t_min
    return lambda t: get_val(t_min + (t_start - t_min + t) % period)


def interp_oscillate (get_val, t_max, t_min = 0, t_start = None):
    """Repeat a linear oscillation over an existing interpolation function.

interp_oscillate(get_val, t_max, t_min = 0, t_start = t_min) -> f

get_val: an existing interpolation function, as taken by Scheduler.interp.

Times passed to the returned function are looped and reversed to fit in the
range [t_min, t_max), starting at t_start.  If t_start is in the range
[t_max, 2 * t_max + - t_min), it is mapped to the 'return journey' of the
oscillation.

f: the generated get_val wrapper.

"""
    if t_start is None:
        t_start = t_min
    period = t_max - t_min

    def osc_get_val (t):
        t = (t_start - t_min + t) % (2 * period)
        if t >= period:
            t = 2 * period - t
        return get_val(t_min + t)

    return osc_get_val


class Timer (object):
    """Simple timer.

Either call run once and stop if you need to, or step every time you've done
what you need to.

    CONSTRUCTOR

Timer(fps = 60)

fps: frames per second to aim for.

    METHODS

run
step
stop

    ATTRIBUTES

fps: the current target FPS.  Set this directly.
frame: the current length of a frame in seconds.
t: the time at the last step, if using individual steps.

"""

    def __init__ (self, fps = 60):
        self.fps = fps
        self.t = time()

    def run (self, cb, *args, **kwargs):
        """Run indefinitely or for a specified amount of time.

run(cb, *args[, seconds][, frames]) -> remain

cb: a function to call every frame.
args: extra arguments to pass to cb.
seconds, frames: keyword-only arguments that determine how long to run for.  If
                 seconds is passed, frames is ignored; if neither is given, run
                 forever (until Timer.stop is called).  Either can be a float.
                 Time passed is based on the number of frames that have passed,
                 so it does not necessarily reflect real time.

remain: the number of frames/seconds left until the timer has been running for
        the requested amount of time (or None, if neither were given).  This
        may be less than 0 if cb took a long time to run.

"""
        self.stopped = False
        seconds = kwargs.get('seconds')
        frames = kwargs.get('frames')
        if seconds is not None:
            seconds = max(seconds, 0)
        elif frames is not None:
            frames = max(frames, 0)
        # main loop
        t0 = time()
        while 1:
            frame = self.frame
            cb(*args)
            t = time()
            t_gone = min(t - t0, frame)
            if self.stopped:
                if seconds is not None:
                    return seconds - t_gone
                elif frames is not None:
                    return frames - t_gone / frame
                else:
                    return None
            t_left = frame - t_gone # until next frame
            if seconds is not None:
                t_left = min(seconds, t_left)
            elif frames is not None:
                t_left = min(frames, t_left / frame)
            if t_left > 0:
                wait(int(1000 * t_left))
                t0 = t + t_left
            else:
                t0 = t
            if seconds is not None:
                seconds -= t_gone + t_left
                if seconds <= 0:
                    return seconds
            elif frames is not None:
                frames -= (t_gone + t_left) / frame
                if frames <= 0:
                    return frames

    def step (self):
        """Step forwards one frame."""
        t = time()
        t_left = self.t + self.frame - t
        if t_left > 0:
            wait(int(1000 * t_left))
            self.t = t + t_left
        else:
            self.t = t

    def stop (self):
        """Stop any current call to Timer.run."""
        self.stopped = True

    @property
    def fps (self):
        return self._fps

    @fps.setter
    def fps (self, fps):
        self._fps = int(round(fps))
        self.frame = 1. / fps


class Scheduler (Timer):
    """Simple event scheduler (Timer subclass).

Takes the same arguments as Timer.

    METHODS

add_timeout
rm_timeout
interp
interp_simple

"""

    def __init__ (self, fps = 60):
        Timer.__init__(self, fps)
        self._cbs = {}
        self._max_id = 0

    def run (self, seconds = None, frames = None):
        """Start the scheduler.

run([seconds][, frames]) -> remain

Arguments and return value are as for Timer.run.

"""
        return Timer.run(self, self._update, seconds = seconds,
                         frames = frames)

    def step (self):
        self._update()
        Timer.step(self)

    def add_timeout (self, cb, *args, **kwargs):
        """Call a function after a delay.

add_timeout(cb, *args[, seconds][, frames][, repeat_seconds][, repeat_frames])
            -> ID

cb: the function to call.
args: list of arguments to pass to cb.
seconds: how long to wait before calling, in seconds (respects changes to FPS).
         If passed, frames is ignored.
frames: how long to wait before calling, in frames (same number of frames even
        if FPS changes).
repeat_seconds, repeat_frames:
    how long to wait between calls; time is determined as for the seconds and
    frames arguments.  If repeat_seconds is passed, repeat_frames is ignored;
    if neither is passed, the initial time delay is used between calls.

ID: an ID to pass to rm_timeout.  This is guaranteed to be unique over time.

Times can be floats, in which case part-frames are carried over, and time
between calls is actually an average over a large enough number of frames.

The called function can return a boolean True object to repeat the timeout;
otherwise it will not be called again.

"""
        seconds = kwargs.get('seconds')
        frames = kwargs.get('frames')
        repeat_seconds = kwargs.get('repeat_seconds')
        repeat_frames = kwargs.get('repeat_frames')
        if seconds is not None:
            frames = None
        if repeat_seconds is not None:
            repeat_frames = None
        elif repeat_frames is None:
            repeat_seconds = seconds
            repeat_frames = frames
        self._cbs[self._max_id] = [seconds, frames, repeat_seconds,
                                   repeat_frames, cb, args]
        self._max_id += 1
        # ID is key in self._cbs
        return self._max_id - 1

    def rm_timeout (self, *ids):
        """Remove the timeouts with the given IDs."""
        for i in ids:
            try:
                del self._cbs[i]
            except KeyError:
                pass

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
            data[remain] -= dt
            if data[remain] <= 0:
                # call callback
                if data[4](*data[5]):
                    # add on delay
                    total = 0 if data[2] is not None else 1
                    data[not total] = None
                    data[total] += data[total + 2]
                elif i in cbs: # else removed in above call
                    del cbs[i]

    def interp (self, get_val, set_val, t_max = None, val_min = None,
                val_max = None, end = None, round_val = False, multi_arg = False):
        """Vary a value over time.

interp(get_val, set_val[, t_max][, val_min][, val_max][, end],
       round_val = False, multi_arg = False) -> timeout_id

get_val: a function called with the elapsed time in seconds to obtain the
         current value.  If this function returns None, the interpolation will
         be canceled.  The interp_* functions in this module can be used to
         construct such functions.  The value must actually be a list of
         arguments to pass to set_val (unless set_val is (obj, attr)).
set_val: a function called with the current value to set it.  This may also be
         an (obj, attr) tuple to do obj.attr = val.
t_max: if time becomes larger than this, cancel the interpolation.
val_min, val_max: minimum and maximum values of the interpolated value.  If
                  given, get_val must only return values that can be compared
                  with these.  If the value ever falls outside of this range,
                  set_val is called with the value at the boundary it is beyond
                  (val_min or val_max) and the interpolation is canceled.
end: used to do some cleanup when the interpolation is canceled (when get_val
     returns None or t_max, val_min or val_max comes into effect, but not when
     the rm_timeout method is called with the returned id).  This can be a
     final value to pass to set_val, or a function to call without arguments.
     If the function returns a (non-None) value, set_val is called with it.
round_val: whether to round the value(s) (see the interp_round function in this
           module for other possible values).
multi_arg: whether values should be interpreted as lists of arguments to pass
           to set_val instead of a single list argument.

timeout_id: an identifier that can be passed to the rm_timeout method to remove
            the callback that continues the interpolation.  In this case the
            end argument is not respected.

"""
        if round_val:
            get_val = interp_round(get_val, round_val)
        if not callable(set_val):
            obj, attr = set_val
            set_val = lambda val: setattr(obj, attr, val)

        def timeout_cb ():
            t = 0
            last_v = None
            done = False
            while 1:
                t += self.frame
                v = get_val(t)
                if v is None:
                    done = True
                # check bounds
                elif t_max is not None and t > t_max:
                    done = True
                else:
                    if val_min is not None and v < val_min:
                        done = True
                        v = val_min
                    elif val_max is not None and v > val_max:
                        done = True
                        v = val_max
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

        return self.add_timeout(timeout_cb().next, frames = 1)

    def interp_simple (self, obj, attr, target, t, end_cb = None,
                       round_val = False):
        """A simple version of the interp method.

Varies an object's attribute linearly from its current value to a target value
in a set amount of time.

interp_simple(obj, attr, target, t[, end], round_val = False) -> timeout_id

obj, attr: this function varies the attribute attr of the object obj.
target: a target value, in the same form as the current value in the given
        attribute.
t: the amount of time to take to reach the target value.
end_cb: a function to call when the target value has been reached.
round_val: whether to round the value(s) (see the interp_round function in this
           module for other possible values).

timeout_id: an identifier that can be passed to the rm_timeout method to remove
            the callback that continues the interpolation.  In this case end_cb
            is not called.

"""
        get_val = interp_linear(getattr(obj, attr), (target, t))
        self.interp(get_val, (obj, attr), end = end_cb, round_val = round_val)
