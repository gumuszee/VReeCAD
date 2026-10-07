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

from freecad.BlocksCAD.cad import block, edit, picking, sketching, variables
from freecad.BlocksCAD.core.values import Field, ValueTarget, pretty_expression, single_variable

LABELS = {"LengthFwd": "Length", "Radius1": "Radius 1", "Radius2": "Radius 2", "Circumradius": "Radius", "Xmax": "X size", "Ymax": "Y size", "Zmax": "Z size",
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
            if sketching.is_sketch(obj):
                return (doc.Name, name), (lambda d=doc, o=obj: SketchValues(d, o))
            index = block.picked(obj) if block.is_block(obj) else None
            if index is not None and index < len(obj.Vertices):
                return (doc.Name, name, index), (lambda d=doc, o=obj, i=index: BlockValues(d, o, i))
            return (doc.Name, name), (lambda d=doc, o=obj: ObjectValues(d, o))
    return None


POINT_AXES = (("pt.x", "Point X"), ("pt.y", "Point Y"), ("pt.z", "Point Z"))


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


class BlockValues(ObjectValues):
    """The values of a block while one of its points is picked (by the Points tool): the three coordinates of the point, then the position
    of the block. The point is in the placement of the block; a coordinate can be bound to a variable like any value, which makes the
    property that carries the expression (`cad/block.py`)."""

    def __init__(self, doc, obj, index):
        super().__init__(doc, obj)
        self.index = index
        self.title = f"{obj.Label} point {index}"

    def _current(self, name):
        if name.startswith("pt."):
            return float(block.read(self.obj)[0][self.index]["xyz".index(name[3])])
        return super()._current(name)

    def _path(self, name):
        return f"Point{self.index}.{name[3]}" if name.startswith("pt.") else ObjectValues._path(name)

    def fields(self):
        bound = self._expressions()
        points = [Field(name, label, self._current(name), None, expression=bound.get(self._path(name))) for name, label in POINT_AXES]
        return points + super().fields()

    def _write(self, name, value):
        if not name.startswith("pt."):
            super()._write(name, value)
            return
        vertices, _ = block.read(self.obj)
        axis = "xyz".index(name[3])
        moved = tuple(value if i == axis else c for i, c in enumerate(vertices[self.index]))
        error = block.apply(self.doc, self.obj, [moved if i == self.index else v for i, v in enumerate(vertices)])
        if error is not None:
            raise ValueError(error)

    def bind(self, name, expression, value):
        if name.startswith("pt."):
            self._begin()
            block.ensure_point(self.obj, self.index)
        super().bind(name, expression, value)


class SketchValues(ObjectValues):
    """The values of a sketch: its named dimensions (`length`, `radius`, ...), then its position when it is not attached to a face. A dimension
    is a driving constraint, so a value set here moves the sketch to the nearest one that keeps the other constraints; a value the solver
    cannot take is refused. Dimensions can be bound to variables like any value (the path is `Constraints.<name>`)."""

    def _dimension(self, name):
        for index, label, _, value in sketching.dimensions(self.obj):
            if f"dim.{label}" == name:
                return index, value
        raise ValueError("That dimension is gone")

    def _current(self, name):
        return self._dimension(name)[1] if name.startswith("dim.") else super()._current(name)

    def _path(self, name):
        return "Constraints." + name[4:] if name.startswith("dim.") else ObjectValues._path(name)

    def fields(self):
        bound = self._expressions()
        fields = [Field(f"dim.{label}", label, value, edit.MIN_SIZE, expression=bound.get("Constraints." + label))
                  for _, label, _, value in sketching.dimensions(self.obj)]
        return fields + ([] if self.obj.AttachmentSupport else super().fields())

    def _write(self, name, value):
        if not name.startswith("dim."):
            super()._write(name, value)
            return
        error = sketching.set_dimension(self.obj, self._dimension(name)[0], value)
        if error is not None:
            raise ValueError(error)
