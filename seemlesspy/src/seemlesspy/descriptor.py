from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeAlias

if TYPE_CHECKING:
    from .base import SeemlessPy

AcceptedType: TypeAlias = str | int | dict | list | bool | None

AcceptedKind: TypeAlias = Literal["property", "method"]


@dataclass
class Member:
    kind: AcceptedKind
    params: Sequence[tuple[str, AcceptedType]]
    ret: AcceptedType
    ref: Callable | None
    changes: Sequence[str] = ()


@dataclass
class Constructor:
    params: Sequence[tuple[str, AcceptedType]]
    ref: Callable


@dataclass
class Class:
    name: str
    members: dict[str, Member]
    constructor: Constructor
    cls: type["SeemlessPy"]


@dataclass
class Descriptor:
    version: str
    classes: dict[str, Class]
