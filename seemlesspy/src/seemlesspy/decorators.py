from collections.abc import Callable, Sequence
from functools import wraps
from typing import Any, ParamSpec, TypeVar, overload

from .connector import manager

_P = ParamSpec("_P")
_R = TypeVar("_R")

SEAMLESS_ATTR = "__seemless__"
SEAMLESS_CHANGES_ATTR = "__seemless_changes__"


class SeemlessProperty(property):
    __seemless__ = "property"


@overload
def seemlessmethod(
    func: Callable[_P, _R], *, changes: Sequence[str] = ...
) -> Callable[_P, _R]: ...


@overload
def seemlessmethod(
    func: None = ..., *, changes: Sequence[str] = ...
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]: ...


def seemlessmethod(
    func: Callable[_P, _R] | None = None,
    *,
    changes: Sequence[str] = (),
) -> Callable[_P, _R] | Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    if func is None:

        def decorate(inner: Callable[_P, _R]) -> Callable[_P, _R]:
            return _mark_method(inner, changes)

        return decorate

    return _mark_method(func, changes)


def _mark_method(
    func: Callable[_P, _R], changes: Sequence[str]
) -> Callable[_P, _R]:
    if not callable(func):
        raise TypeError(
            f"seemlessmethod expects a callable, got {type(func).__name__}"
        )
    setattr(func, SEAMLESS_ATTR, "method")
    setattr(func, SEAMLESS_CHANGES_ATTR, tuple(changes))
    return func


def seemlessproperty(prop: property) -> SeemlessProperty:
    if not isinstance(prop, property):
        raise TypeError(
            "seemlessproperty must be applied above @property, "
            f"got {type(prop).__name__}"
        )
    return SeemlessProperty(prop.fget, prop.fset, prop.fdel, prop.__doc__)


def seemlesschange(
    *,
    seemless_cls: type,
    changes: Sequence[str],
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    def decorate(func: Callable[_P, _R]) -> Callable[_P, _R]:
        @wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            result = func(*args, **kwargs)
            _notify(seemless_cls, changes, args, kwargs)
            return result

        return wrapper

    return decorate


def _notify(
    seemless_cls: type,
    changes: Sequence[str],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    for value in args:
        if isinstance(value, seemless_cls):
            manager.notify_nowait(value, changes)

    for value in kwargs.values():
        if isinstance(value, seemless_cls):
            manager.notify_nowait(value, changes)
