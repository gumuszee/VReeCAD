# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2026 Vojtech Tuma                                       *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 3 of     *
# *   the License, or (at your option) any later version.                   *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# ***************************************************************************
"""Registry of tool classes by name, in registration order (the order of the palette)."""

_TOOLS = {}


def register(cls):
    """Class decorator."""
    if not cls.name:
        raise ValueError(f"{cls.__name__} has no name")
    old = _TOOLS.get(cls.name)
    if old is not None and (old.__module__, old.__qualname__) != (cls.__module__, cls.__qualname__):
        raise ValueError(f"tool name '{cls.name}' is already registered by {old.__module__}.{old.__qualname__}")
    _TOOLS[cls.name] = cls
    return cls


def create(name, ctx):
    return _TOOLS[name](ctx)


def names():
    return list(_TOOLS)


def label_of(name):
    return _TOOLS[name].label


def unregister(name):
    _TOOLS.pop(name, None)
