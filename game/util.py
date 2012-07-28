from collections import defaultdict

def dd (default, items = {}):
    """Create a collections.defaultdict with a static default.

dd(default[, items]) -> default_dict

default: the default value.
items: dict or dict-like to initialise with.

default_dict: the created defaultdict.

"""
    return defaultdict(lambda: default, items)

def ir (x):
    """Returns the argument rounded to the nearest integer."""
    return int(round(x))