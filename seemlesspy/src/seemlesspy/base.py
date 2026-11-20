import inspect
from collections.abc import Callable, Sequence
from functools import wraps
from types import FunctionType
from typing import Any

from .decorators import (
    SEAMLESS_ATTR,
    SEAMLESS_CHANGES_ATTR,
    SeemlessProperty,
    seemlessmethod,
    seemlessproperty,
)
from .descriptor import Class, Constructor, Member
from .errors import MissingAnnotationError
from .holder import add_class
from .rpc_types import resolve_self


class SeemlessPy:
    @classmethod
    def inspect_methods(cls) -> dict[str, Member]:
        members: dict[str, Member] = {}
        for name, func in inspect.getmembers(cls, predicate=inspect.isfunction):
            if getattr(func, SEAMLESS_ATTR, None) != "method":
                continue
            signature = inspect.signature(func, eval_str=True)
            params: list[tuple[str, object]] = []
            for index, param in enumerate(signature.parameters.values()):
                if index == 0:
                    continue
                annotation = _annotation_param(
                    param.annotation,
                    f"parameter {param.name!r}",
                    cls,
                    func,
                )
                params.append((param.name, annotation))
            members[name] = Member(
                kind="method",
                params=params,
                ret=_annotation_param(
                    signature.return_annotation,
                    f"return value of {name!r}",
                    cls,
                    func,
                ),
                ref=func,
                changes=getattr(func, SEAMLESS_CHANGES_ATTR, ()),
            )
        return members

    @classmethod
    def inspect_properties(cls) -> dict[str, Member]:
        properties: dict[str, Member] = {}
        for name, prop in inspect.getmembers(
            cls, predicate=_is_seemless_property
        ):
            getter = prop.fget
            if getter is None:
                raise NotImplementedError(
                    f"TODO: property {name!r} has no getter"
                )
            if prop.fset is not None:
                raise NotImplementedError(
                    f"TODO: descriptor shape for writable property {name!r}"
                )
            signature = inspect.signature(getter, eval_str=True)
            properties[name] = Member(
                kind="property",
                params=[],
                ret=_annotation_param(
                    signature.return_annotation,
                    f"return value of {name!r}",
                    cls,
                    getter,
                ),
                ref=None,
            )
        return properties

    @classmethod
    def inspect_class(cls) -> Class:
        members = cls.inspect_methods()
        members.update(cls.inspect_properties())
        return Class(
            name=cls.__name__,
            members=members,
            constructor=Constructor(
                params=_describe_constructor(cls),
                ref=cls.__init__,
            ),
            cls=cls,
        )

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        add_class(cls)

    def __new__(cls, *args, **kwargs):  # noqa
        return super().__new__(cls)


def _is_seemless_property(obj: object) -> bool:
    return getattr(obj, SEAMLESS_ATTR, None) == "property"


def _describe_constructor(
    cls: type,
) -> Sequence[tuple[str, object]]:
    init = cls.__init__
    if not isinstance(init, FunctionType):
        return []
    signature = inspect.signature(init, eval_str=True)
    constructor: list[tuple[str, object]] = []
    for index, param in enumerate(signature.parameters.values()):
        if index == 0:
            continue
        annotation = _annotation_param(
            param.annotation, f"parameter {param.name!r}", cls, init
        )
        constructor.append((param.name, annotation))
    return constructor


def _annotation_param(
    annotation: object, label: str, cls: type, func: FunctionType
) -> object:
    if annotation is inspect.Parameter.empty:
        raise MissingAnnotationError(cls, func, label)
    if annotation is None or annotation is type(None):
        return None
    return resolve_self(annotation, cls)


def seemlessify(
    cls: type,
    methods: Sequence[str],
    properties: Sequence[str],
) -> type[SeemlessPy]:
    namespace: dict[str, object] = {}

    for name in methods:
        namespace[name] = _forward_method(cls, name)

    for name in properties:
        namespace[name] = _forward_property(cls, name)

    return type(f"Seemless{cls.__name__}", (SeemlessPy, cls), namespace)


def _forward_method(cls: type, name: str) -> Callable[..., Any]:
    original = getattr(cls, name)

    @wraps(original)
    def forward(self: Any, *args: Any, **kwargs: Any) -> Any:
        return original(self, *args, **kwargs)

    return seemlessmethod(forward)


def _forward_property(cls: type, name: str) -> SeemlessProperty:
    original = getattr(cls, name)

    if not isinstance(original, property):
        raise TypeError(f"{cls.__name__}.{name} is not a property")

    getter = original.fget

    if getter is None:
        raise TypeError(f"{cls.__name__}.{name} has no getter")

    @wraps(getter)
    def forward(self: Any) -> Any:
        return getter(self)

    return seemlessproperty(property(forward))
