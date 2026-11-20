import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .contract import Contract
from .descriptor import AcceptedType, Descriptor

if TYPE_CHECKING:
    from .base import SeemlessPy


_descriptor = Descriptor(version="0.1", classes={})


@dataclass
class Session:
    instances: dict[str, dict[str, "SeemlessPy"]] = field(default_factory=dict)
    subscriptions: dict[str, dict[str, object]] = field(default_factory=dict)

    def add(self, instance: "SeemlessPy") -> str:
        cls_name = _class_name(instance.__class__)
        instance_id = secrets.token_urlsafe(16)
        instances = self.instances.setdefault(cls_name, {})
        instances[instance_id] = instance
        return instance_id

    def get(self, cls_name: str, instance_id: str) -> "SeemlessPy":
        instances = self.instances.get(cls_name)

        if instances is not None:
            instance = instances.get(instance_id)
            if instance is not None:
                return instance

        raise ValueError(f"unknown instance for {cls_name!r}")

    def release(self, cls_name: str, instance_id: str) -> None:
        instances = self.instances.get(cls_name)

        if instances is not None:
            instances.pop(instance_id, None)

        self.subscriptions.pop(instance_id, None)

    def subscribe(self, cls_name: str, instance_id: str, member: str) -> object:
        instance = self.get(cls_name, instance_id)
        value = getattr(instance, member)
        members = self.subscriptions.setdefault(instance_id, {})
        members[member] = value
        return value

    def unsubscribe(self, instance_id: str, member: str) -> None:
        members = self.subscriptions.get(instance_id)

        if members is not None:
            members.pop(member, None)

            if not members:
                self.subscriptions.pop(instance_id, None)

    def take_updates(
        self,
        instance: "SeemlessPy",
        members: Sequence[str] | None = None,
    ) -> list[tuple[str, str, object]]:
        instance_id = self._find_id(instance)

        if instance_id is None:
            return []

        subscribed = self.subscriptions.get(instance_id)

        if not subscribed:
            return []

        if members is None:
            candidates = list(subscribed)
        else:
            candidates = [member for member in members if member in subscribed]

        updates: list[tuple[str, str, object]] = []

        for member in candidates:
            value = getattr(instance, member)

            if value != subscribed[member]:
                subscribed[member] = value
                updates.append((instance_id, member, value))

        return updates

    def _find_id(self, instance: "SeemlessPy") -> str | None:
        instances = self.instances.get(_class_name(instance.__class__))

        if instances is None:
            return None

        for instance_id, candidate in instances.items():
            if candidate is instance:
                return instance_id

        return None


def add_class(cls: type["SeemlessPy"]) -> None:
    _register_class(cls)


def resolve_contract(contract: Contract, session: Session) -> Any:
    cls = _descriptor.classes.get(contract.cls_name)

    if cls is None:
        raise ValueError(f"unknown class {contract.cls_name!r}")

    if contract.kind == "constructor":
        _check_params(cls.constructor.params, contract.params)
        return session.add(cls.cls(**dict(contract.params)))

    if contract.instance_id is None:
        raise ValueError(f"{contract.kind} contract requires an instance id")

    if contract.kind == "release":
        session.release(contract.cls_name, contract.instance_id)
        return None

    member = cls.members.get(contract.member)

    if member is None:
        raise ValueError(
            f"unknown member {contract.member!r} on {contract.cls_name!r}"
        )

    expected_kind = "method" if contract.kind == "method" else "property"

    if member.kind != expected_kind:
        raise ValueError(
            f"{contract.member!r} is a {member.kind}, not a {expected_kind}"
        )

    _check_params(member.params, contract.params)
    instance = session.get(contract.cls_name, contract.instance_id)

    if contract.kind == "subscribe":
        return session.subscribe(
            contract.cls_name, contract.instance_id, contract.member
        )

    if contract.kind == "unsubscribe":
        session.unsubscribe(contract.instance_id, contract.member)
        return None

    if contract.kind == "property":
        return getattr(instance, contract.member)

    if member.ref is None:
        raise ValueError(f"{contract.member!r} is not callable")

    return member.ref(instance, **dict(contract.params))


def _class_name(cls: type["SeemlessPy"]) -> str:
    return f"{cls.__qualname__}"


def _register_class(cls: type["SeemlessPy"]) -> str:
    name = _class_name(cls)

    if name not in _descriptor.classes:
        _descriptor.classes[name] = cls.inspect_class()
    elif _descriptor.classes[name].cls is not cls:
        raise ValueError(f"class name collision for {name!r}")

    return name


def _check_params(
    expected: Sequence[tuple[str, AcceptedType]],
    provided: Sequence[tuple[str, AcceptedType]],
) -> None:
    values: dict[str, AcceptedType] = {}
    expected_names: list[str] = []

    for name, _ in expected:
        expected_names.append(name)

    for name, value in provided:
        if name in values:
            raise ValueError(f"duplicate parameter {name!r}")
        if name not in expected_names:
            raise ValueError(f"unknown parameter {name!r}")
        values[name] = value

    for name, type_name in expected:
        if name not in values:
            raise ValueError(f"missing parameter {name!r}")
        if not _matches_type(type_name, values[name]):
            raise ValueError(f"parameter {name!r} must be {type_name}")


def _matches_type(type_name: AcceptedType, value: object) -> bool:
    if not isinstance(type_name, str):
        return True
    if type_name == "str":
        return isinstance(value, str)
    if type_name == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "bool":
        return isinstance(value, bool)
    if type_name == "None":
        return value is None
    return True
