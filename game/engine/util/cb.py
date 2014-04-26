"""Callback management utilities."""

import inspect


def takes_args (func):
    """Determine whether the given function takes any arguments.

:return: ``True`` if the function can take arguments, or if the result could
         not be determined (the argument is not a function, or not a
         pure-Python function), else ``False``.

"""
    try:
        args, varargs, kwargs, defaults = inspect.getargspec(func)
    except TypeError:
        return True
    want = 2 if inspect.ismethod(func) else 1
    return varargs is not None or len(args) >= want


def wrap_fn (func):
    """Return a function that calls ``func``, possibly omitting arguments.

wrap_fn(func) -> wrapper

When ``wrapper`` is called, it calls ``func`` (and returns its return value),
but only passes any arguments on to ``func`` if it is determined that ``func``
takes any arguments (using :func:`takes_args`).

"""
    pass_args = takes_args(func)

    def wrapper (*args, **kwargs):
        if pass_args:
            return func(*args, **kwargs)
        else:
            return func()

    return wrapper


class CbManager (object):
    """Simple callback manager."""

    def __init__ (self):
        # {given cb: cb to call}
        self._cbs = {}

    @property
    def cbs (self):
        """List of registered callback functions."""
        return self._cbs.keys()

    def cb (self, *cbs):
        """Register callbacks.

cb(*cbs) -> self

If a callback is determined not to be able to take arguments, it is not passed
any.

"""
        self._cbs.update((cb, wrap_fn(cb)) for cb in cbs)
        return self

    def rm_cbs (self, *cbs):
        """Remove any number of callbacks from :attr:`cbs`.

rm_cbs(*cbs) -> self

Missing items are ignored.

"""
        all_cbs = self._cbs
        for cb in cbs:
            if cb in all_cbs:
                del all_cbs[cb]
        return self

    def call (self, *args, **kwargs):
        """Call all registered callbacks with the given arguments.

call(*args, **kwargs) -> results

:return: value returned by each callback, as ``{cb: result}``.

"""
        return dict((cb, real_cb(*args, **kwargs))
                    for cb, real_cb in self._cbs.iteritems())


class GroupedCbManager (object):
    """Manage callbacks grouped by type.

GroupedCbManager([groups])

:arg groups: allowed groups; overrides the class's default :attr:`groups`.

A group identifier may be hashable object.  Groups are equivalent if they
produce the same hash value.

"""

    #: Groups available to place callbacks in.  If methods are given any other
    #: group identifier not in here, ``ValueError`` is raised.
    groups = ()

    def __init__ (self, groups=None):
        if groups is not None:
            self.groups = groups
        # {group: manager}
        try:
            self._cbs = dict((groups, CbManager()) for group in self.groups)
        except TypeError:
            raise TypeError('invalid callback groups specified: {}'
                .format(self.groups))

    @property
    def cbs (self):
        """Registered callback functions, as ``{group: callbacks}``."""
        return dict((group, mgr.cbs) for group, mgr in self._cbs.iteritems())

    def _group (self, group):
        # get callback manager for the given group, else throw
        if group in self.groups:
            return self._cbs[group]
        else:
            raise ValueError('unknown callback group: {}'.format(group))

    def cb (self, group, *cbs):
        """Register callbacks for a group.

cb(group, *cbs) -> self

If a callback is determined not to be able to take arguments, it is not passed
any.

"""
        return self._group(group).cb(*cbs)

    def rm_cbs (self, group, *cbs):
        """Remove any number of callbacks in a group from :attr:`cbs`.

rm_cbs(group, *cbs) -> self

Missing items are ignored.

"""
        return self._group(group).rm_cbs(*cbs)

    def call (self, group, *args, **kwargs):
        """Call all registered callbacks in a group with the given arguments.

call(group, *args, **kwargs) -> results

:return: value returned by each callback, as ``{cb: result}``.

"""
        return self._group(group).call(*args, **kwargs)
