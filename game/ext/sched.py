"""Event scheduler by Joseph Lansdowne.

Uses Pygame's wait function if available, else the less accurate time.sleep.
To use something else, do:

import sched
sched.wait = wait_function

This function should take the number of milliseconds to wait for.  This will
always be an integer.

Python version: 2.
Release: 8.

Licensed under the GNU General Public License, version 3; if this was not
included, you can find it here:
    http://www.gnu.org/licenses/gpl-3.0.txt

    CLASSES

Timer
Scheduler

"""

from time import time

try:
    from pygame.time import wait
except ImportError:
    from time import sleep

    def wait (t):
        sleep(int(t * 1000))


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

"""

    def __init__ (self, fps = 60):
        Timer.__init__(self, fps)
        self._cbs = {}
        self._max_id = 0

    def run (self, seconds = None, frames = None):
        """Start the scheduler.

run([seconds][, frames])

Arguments are as required by Timer.run.

"""
        Timer.run(self, self._update, seconds = seconds, frames = frames)

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
