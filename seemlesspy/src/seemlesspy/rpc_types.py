import json
import types as types_module
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cache
from typing import (
    Annotated,
    Any,
    Literal,
    Self,
    Union,
    get_args,
    get_origin,
)

from pydantic import BeforeValidator, ConfigDict, PlainSerializer, TypeAdapter

_ANNOTATED: Any = Annotated

_Transform = Callable[[Any], Any]


@dataclass
class Transformer:
    to_json: _Transform | None = None
    from_json: _Transform | None = None


_transformers: dict[type, Transformer] = {}


def register_transformer(
    cls: type,
    to_json: _Transform | None = None,
    from_json: _Transform | None = None,
) -> None:
    _transformers[cls] = Transformer(to_json, from_json)
    _adapter.cache_clear()


def resolve_self(annotation: object, owner: type) -> object:
    if annotation is None or annotation is type(None):
        return annotation

    if annotation is Ellipsis:
        return annotation

    if annotation is Self:
        return owner

    origin = get_origin(annotation)

    if origin is None:
        return annotation

    if origin is types_module.UnionType or origin is Union:
        arguments = get_args(annotation)
        return _union([resolve_self(arg, owner) for arg in arguments])

    if origin is Literal:
        return annotation

    arguments = get_args(annotation)

    if not arguments:
        return annotation

    resolved = tuple(resolve_self(arg, owner) for arg in arguments)

    try:
        return origin[resolved if len(resolved) != 1 else resolved[0]]
    except TypeError:
        return annotation


def validate(annotation: object, owner: type, value: Any) -> Any:
    encoded = json.dumps(value)
    return _adapter(annotation, owner).validate_json(encoded, strict=True)


def to_json(annotation: object, owner: type, value: Any) -> Any:
    return _adapter(annotation, owner).dump_python(value, mode="json")


@cache
def _adapter(annotation: object, owner: type) -> TypeAdapter[Any]:
    resolved: Any = _adapter_annotation(annotation, owner)
    return TypeAdapter(
        resolved, config=ConfigDict(arbitrary_types_allowed=True)
    )


def _adapter_annotation(annotation: object, owner: type) -> object:
    if annotation is None or annotation is type(None):
        return annotation

    if annotation is Ellipsis:
        return annotation

    if annotation is Self:
        return _adapter_annotation(owner, owner)

    origin = get_origin(annotation)

    if origin is None:
        if isinstance(annotation, type):
            return _wrap_class(annotation)
        return annotation

    if origin is types_module.UnionType or origin is Union:
        arguments = get_args(annotation)
        return _union([_adapter_annotation(arg, owner) for arg in arguments])

    if origin is Literal:
        return annotation

    arguments = get_args(annotation)

    if not arguments:
        return annotation

    rewritten = tuple(_adapter_annotation(arg, owner) for arg in arguments)

    try:
        return origin[rewritten if len(rewritten) != 1 else rewritten[0]]
    except TypeError:
        return annotation


def _wrap_class(cls: type) -> object:
    target: Any = cls
    entry: Transformer | None = None

    for base in cls.__mro__:
        if base in _transformers:
            target = base
            entry = _transformers[base]
            break

    to_fn = entry.to_json if entry is not None else None
    from_fn = entry.from_json if entry is not None else None

    if to_fn is None and callable(getattr(target, "to_json", None)):
        to_fn = _instance_to_json

    if from_fn is None:
        method = getattr(target, "from_json", None)

        if callable(method):
            from_fn = method

    if to_fn is None and from_fn is None:
        return cls

    metadata: list[Any] = []

    if from_fn is not None:
        metadata.append(BeforeValidator(from_fn))

    if to_fn is not None:
        metadata.append(PlainSerializer(to_fn, return_type=Any))

    return _ANNOTATED[target, *metadata]


def _instance_to_json(value: Any) -> Any:
    return value.to_json()


def _union(arguments: Sequence[Any]) -> Any:
    result: Any = arguments[0]

    for argument in arguments[1:]:
        result |= argument

    return result
