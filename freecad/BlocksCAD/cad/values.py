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
"""The values of a FreeCAD object that the value panels edit (docs/ux-design.md, Value panels): the size properties of a primitive
and the position of any object that has a placement. `ObjectValues` is the `core.values.ValueTarget` for one object: every `set`
changes the real property and recomputes, inside one transaction that is opened by the first change and kept (one undo step) by
`commit` or aborted by `cancel`; `source` finds the object to edit in the selection. A value the feature cannot take (a torus whose tube is wider than its ring) is taken back and refused.
A value may be bound to an expression of the variables of the document (`cad/variables.py`): a slider, the stick or the keypad then edit the
variable when the value is bound to one variable alone, and refuse when the expression is more than that.
`field_specs` is pure Python; FreeCAD is only used by the object."""

from freecad.BlocksCAD.cad import edit, picking, variables
from freecad.BlocksCAD.core.values import Field, ValueTarget, pretty_expression, single_variable

LABELS = {"Radius1": "Radius 1", "Radius2": "Radius 2", "Circumradius": "Radius", "Xmax": "X size", "Ymax": "Y size", "Zmax": "Z size",
          "X2max": "Top X size"}
ZERO_ALLOWED = {("Part::Cone", "Radius1"), ("Part::Cone", "Radius2"), ("Part::Wedge", "X2max")}   # a size that may be a point or an edge
POSITION = (("pos.x", "X"), ("pos.y", "Y"), ("pos.z", "Z"))


def field_specs(type_id):
    """(name, label, lowest value in millimetres or None) of what can be edited of a feature of this type: the sizes of a primitive,
    then the position."""
    specs = []
    for name in edit.SIZE_PROPERTIES.get(type_id, ()):
        specs.append((name, LABELS.get(name, name), 0.0 if (type_id, name) in ZERO_ALLOWED else edit.MIN_SIZE))
    specs += [(name, label, None) for name, label in POSITION]
    return specs


def editable(obj):
    """Whether the value panels can edit this object: it has a placement."""
    return obj is not None and hasattr(obj, "Placement")


def source(doc, get_selection=None):
    """(key, factory) for the first editable object that is selected in `doc`, or None when there is none: the key names the object, the
    factory makes its `ObjectValues`. The value panels follow the selection through this."""
    if doc is None:
        return None
    get_selection = get_selection or picking.get_selection
    for name, _ in get_selection(doc):
        obj = doc.getObject(name)
        if editable(obj):
            return (doc.Name, name), (lambda d=doc, o=obj: ObjectValues(d, o))
    return None


class ObjectValues(ValueTarget):
    def __init__(self, doc, obj):
        self.doc, self.obj = doc, obj
        self.title = obj.Label
        self._open = False

    def _current(self, name):
        if name.startswith("pos."):
            return float(getattr(self.obj.Placement.Base, name[4:]))
        value = getattr(self.obj, name)
        return float(getattr(value, "Value", value))

    @staticmethod
    def _path(name):
        return "Placement.Base." + name[4] if name.startswith("pos.") else name

    def _expressions(self):
        """Property path -> expression of every bound property of the object (FreeCAD writes a placement path with a leading dot)."""
        return {path.lstrip("."): expression for path, expression in getattr(self.obj, "ExpressionEngine", [])}

    def fields(self):
        bound = self._expressions()
        return [Field(name, label, self._current(name), low, expression=bound.get(self._path(name)))
                for name, label, low in field_specs(self.obj.TypeId)]

    def _begin(self):
        if not self._open:
            self.doc.openTransaction(f"Edit {self.obj.Label}")
            self._open = True

    def _write(self, name, value):
        if name.startswith("pos."):
            base, rotation = edit.placement(self.obj)
            index = "xyz".index(name[4])
            edit.set_placement(self.obj, tuple(value if i == index else c for i, c in enumerate(base)), rotation)
        else:
            setattr(self.obj, name, value)

    def set(self, name, value):
        expression = self._expressions().get(self._path(name))
        if expression is not None:
            self._set_variable(expression, value)
            return
        self._begin()
        before = self._current(name)
        self._write(name, value)
        self.doc.recompute()
        if not self.obj.isValid():                      # the feature cannot be built with this value: back to what it was
            self._write(name, before)
            self.doc.recompute()
            raise ValueError("The shape cannot take that value")

    def _set_variable(self, expression, value):
        """The value is bound: when it is bound to one variable alone, the variable takes the new value (and with it everything else that
        is bound to it); any other expression is refused."""
        variable = single_variable(expression)
        if variable is None:
            raise ValueError(f"Bound to {pretty_expression(expression)}: unbind it first")
        self._begin()
        before = dict(variables.list_variables(self.doc)).get(variable)
        variables.set_value(self.doc, variable, value)
        self.doc.recompute()
        if not self.obj.isValid():
            variables.set_value(self.doc, variable, before)
            self.doc.recompute()
            raise ValueError("The shape cannot take that value")

    # variables
    def variables(self):
        return variables.list_variables(self.doc)

    def bind(self, name, expression, value):
        self._begin()
        path = self._path(name)
        try:
            self.obj.setExpression(path, expression)
            self.doc.recompute()
        except Exception as error:
            self._unbind_quietly(path)
            raise ValueError("That expression cannot be used") from error
        if not self.obj.isValid():
            self._unbind_quietly(path)
            raise ValueError("The shape cannot take that value")

    def _unbind_quietly(self, path):
        try:
            self.obj.setExpression(path, None)
        finally:
            self.doc.recompute()

    def unbind(self, name):
        self._begin()
        self.obj.setExpression(self._path(name), None)
        self.doc.recompute()

    def make_variable(self, name, value):
        self._begin()
        variables.define(self.doc, name, value)

    def commit(self):
        if self._open:
            self._open = False
            self.doc.commitTransaction()

    def cancel(self):
        if self._open:
            self._open = False
            self.doc.abortTransaction()
            self.doc.recompute()
