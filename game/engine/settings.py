"""Settings handling.

Provides :class:`DummySettingsManager` and :class:`SettingsManager` (syncs to
disk).

"""

import sys
import os
from copy import deepcopy
import json
from collections import defaultdict

from .util import wrap_fn


class _JSONEncoder (json.JSONEncoder):
    """Extended json.JSONEncoder with support for sets and defaultdicts."""

    def default (self, o):
        if isinstance(o, set):
            return list(o)
        elif isinstance(o, defaultdict):
            return (o.default_factory(None), dict(o))
        else:
            return json.JSONEncoder.default(self, o)


class DummySettingsManager (object):
    """An object for handling settings.

:arg settings: a dict used to store the settings, or a (new-style) class with
               settings as attributes.
:arg types: the types of settings are preserved when changes are made by
            casting to their initial types.  For types for which this will not
            work, this argument can be passed as a ``{from_type: to_type}``
            dict to use ``to_type`` whenever ``from_type`` would otherwise be
            used.

To access and change settings, use attributes of this object.  To restore a
setting to its default (initial) value, delete it.  To add a new setting, just
set it to a value (or use :meth:`add`).

"""

    def __init__ (self, settings, types = {}):
        self._settings = {}
        self._defaults = {}
        self._types = {}
        self._tricky_types = types
        # {setting: {source: (set([before_cb]), set([after_cb]))}}
        self._cbs = {}
        self.add(settings)

    def add (self, settings):
        """Add more settings; takes ``settings`` like the constructor."""
        if isinstance(settings, type):
            settings = dict((k, v) for k, v in settings.__dict__.iteritems()
                                   if not k.startswith('_'))
        for k, v in settings.iteritems():
            setattr(self, k, v)

    def __getattr__ (self, k):
        return self._settings[k]

    def __setattr__ (self, k, v):
        # set if private
        if k[0] == '_':
            object.__setattr__(self, k, v)
            return (True, None)
        # ensure type
        t = self._types.get(k)
        if t is None:
            # new setting: use as new default
            self._defaults[k] = deepcopy(v)
            if v is not None:
                self._types[k] = type(v)
        elif not isinstance(v, t):
            try:
                v = self._tricky_types.get(t, t)(v)
            except (TypeError, ValueError):
                # invalid: fall back to default
                print >> sys.stderr, \
                      'warning: {0} has invalid type for \'{1}\'; falling ' \
                      'back to default'.format(repr(v), k)
                v = self._defaults[k]
        # check if different
        if k in self._settings and v == self._settings[k]:
            return (True, None)
        # store
        if self._call_before_cbs(k, v):
            self._settings[k] = v
            self._call_after_cbs(k, v)
            return (False, v)
        else:
            return (True, None)

    def __delattr__ (self, k):
        setattr(self, k, self._defaults[k])

    def _call_before_cbs (self, setting, value):
        if setting in self._cbs:
            for source, (before_cbs, after_cbs) \
                in self._cbs[setting].iteritems():
                for cb in before_cbs:
                    if not cb(value):
                        return False
        return True

    def _call_after_cbs (self, setting, value):
        if setting in self._cbs:
            for source, (before_cbs, after_cbs) \
                in self._cbs[setting].iteritems():
                for cb in after_cbs:
                    cb(value)
        return True

    def changed (self, *settings):
        """Mark some settings as having changed.

:arg settings: any number of names of settings that have been changed.

This is for settings that can be changed internally without setting them to new
values, such as appending to a list.  If you do this, you should call this
function to make sure that events are propagated and new values are handled
properly.

"""
        if settings:
            for k in settings:
                self._call_after_cbs(k, self._settings[v])
            self.dump()

    def on_change (self, setting, after_cb=None, before_cb=None, source=None):
        """Register callbacks for when the given setting is changed.

on_change(setting[, after_cb][, before_cb][, source])

:arg setting: the setting name, as used to change the setting (case-sensitive).
:arg after_cb: function to call after the setting has changed.
:arg before_cb: function to call before the setting is changed; its return
                value indicates whether to allow the setting to be changed.
                Note, however, that mutable settings may not always be
                prevented from changing, in which case ``before_cb`` will not
                be called and ``after_cb`` will.
:arg source: non-``None`` hashable object by which to group these callbacks for
             removal at a later time.  It is important to remove all callbacks
             added by a world when it is removed, since they may have
             references to the world, keeping all its objects in memory.

Both callbacks, when called, are passed the new value of the setting (or, if it
is determined that a callback takes no arguments, it is passed no arguments).

"""
        if before_cb is None and after_cb is None:
            return
        if setting not in self._settings:
            raise KeyError('no such setting: \'{0}\''.format(setting))
        cbs = self._cbs.setdefault(setting, {})
        before_cbs, after_cbs = cbs.setdefault(source, (set(), set()))
        if before_cb is not None:
            before_cb = wrap_fn(before_cb)
            before_cbs.add(before_cb)
        if after_cb is not None:
            after_cb = wrap_fn(after_cb)
            after_cbs.add(after_cb)

    def rm_cbs (self, source):
        """Remove callbacks registered for change events in the given group.

:arg source: the ``source`` argument passed to :meth:`on_change` previously.

Missing sources are ignored.

"""
        for setting, cbs in self._cbs.items():
            if source in cbs:
                del cbs[source]
                if not cbs:
                    del self._cbs[setting]

    def dump (self):
        """Force saving all settings.

This class's implementation does nothing.

"""
        pass


class SettingsManager (DummySettingsManager):
    """An object for handling settings; :class:`DummySettingsManager` subclass.

:arg fn: filename to save settings in.
:arg save: a list containing the names of the settings to save to ``fn``
          (others are stored in memory only).

All settings registered through :meth:`save` will be saved to the given file
whenever they are set.  If you change settings internally without setting them
(append to a list, for example), use :meth:`dump`.

"""

    def __init__ (self, settings, fn, save = (), types = {}):
        # load settings
        try:
            with open(fn) as f:
                new_settings = json.load(f)
        except IOError:
            new_settings = {}
        except ValueError:
            print >> sys.stderr, 'warning: invalid JSON: \'{0}\'' \
                                 .format(self._fn)
            new_settings = {}
        for k, v in new_settings.iteritems():
            if k in save:
                settings[k] = v
        # initialise
        self._fn = fn
        self._save = {}
        DummySettingsManager.__init__(self, settings, types)
        self.save(*save)

    def save (self, *save):
        """Register more settings for saving to disk.

Takes any number of strings corresponding to setting names.

"""
        if save:
            # create directory
            d = os.path.dirname(self._fn)
            try:
                os.makedirs(d)
            except OSError, e:
                if e.errno != 17: # 17 means already exists
                    print >> sys.stderr, 'warning: can\'t create directory: ' \
                                         '\'{0}\''.format(d)
            settings = self._settings
            self._save.update((k, settings.get(k)) for k in save)
            self.dump()

    def __setattr__ (self, k, v):
        done, v = DummySettingsManager.__setattr__(self, k, v)
        if done:
            return
        # save to file
        if k in self._save:
            print >> sys.stderr, 'info: saving setting: \'{0}\''.format(k)
            self._save[k] = v
            self.dump(False)

    def dump (self, public = True):
        """Force syncing to disk.

dump()

"""
        if not self._save:
            # nothing to save
            return
        if public:
            print >> sys.stderr, 'info: saving settings'
        try:
            if not os.path.exists:
                os.makedirs(os.path.dirname(self._fn))
            with open(self._fn, 'w') as f:
                json.dump(self._save, f, indent = 4, cls = _JSONEncoder)
        except IOError:
            print >> sys.stderr, 'warning: can\'t write to file: ' \
                                 '\'{0}\''.format(self._fn)
