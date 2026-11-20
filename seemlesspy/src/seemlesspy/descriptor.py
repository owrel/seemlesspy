from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeAlias

if TYPE_CHECKING:
    from .base import SeemlessPy

AcceptedType: TypeAlias = str | int | float | dict | list | bool | None

AcceptedKind: TypeAlias = Literal["property", "method"]


def split_type(descriptor: str, separator: str) -> list[str]:
    parts: list[str] = []
    current = ""
    depth = 0

    for char in descriptor:
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1

        if char == separator and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += char

    parts.append(current.strip())
    return parts


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
