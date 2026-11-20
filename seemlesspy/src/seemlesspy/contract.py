from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .descriptor import AcceptedType

_KINDS = (
    "method",
    "constructor",
    "property",
    "release",
    "subscribe",
    "unsubscribe",
)


@dataclass
class Contract:
    kind: Literal[
        "method",
        "constructor",
        "property",
        "release",
        "subscribe",
        "unsubscribe",
    ]
    cls_name: str
    instance_id: str | None
    member: str
    params: Sequence[tuple[str, AcceptedType]]

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError(f"unknown contract kind {self.kind!r}")

        if self.kind == "constructor":
            if self.instance_id is not None:
                raise ValueError(
                    "constructor contract must not have an instance id"
                )
            if self.member != "__init__":
                raise ValueError(
                    "constructor contract must use '__init__' as member"
                )
            return

        if self.instance_id is None:
            raise ValueError(f"{self.kind} contract requires an instance id")

        if (
            self.kind
            in {
                "property",
                "release",
                "subscribe",
                "unsubscribe",
            }
            and self.params
        ):
            raise ValueError(f"{self.kind} contract must not have params")


@dataclass
class ContractResolution:
    call: str = ""
    result: Any = None
    error: str | None = None
