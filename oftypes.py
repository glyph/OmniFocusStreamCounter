from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Protocol, TYPE_CHECKING

from datetype import DateTime


class AbstractExpression(Protocol):
    """
    Abstract description of an expression, (mostly) like the one described by
    appscript.
    """
    def __lt__(self, other: object) -> AbstractExpression: ...
    def __eq__(self, other: object) -> AbstractExpression: ...  # type:ignore[override]
    def __ge__(self, other: object) -> AbstractExpression: ...
    def OR(self, other: object) -> AbstractExpression: ...
    def AND(self, other: object) -> AbstractExpression: ...


class AbstractReference[T](Protocol):
    """
    Abstract description of a reference to a value, (mostly) like the one
    described by appscript.
    """
    def __call__(self) -> T: ...
    def get(self) -> T: ...
    def __lt__(self, other: object) -> AbstractExpression: ...
    def __ge__(self, other: object) -> AbstractExpression: ...
    def __eq__(self, other: object) -> AbstractExpression: ...  # type:ignore[override]


class ProgressStatus(Protocol):
    def updateLoading(self, loadedPercent: float) -> None:
        "the next refresh is C{loadedPercent} done loading"

    def updateProgress(
        self,
        availablePercent: float,
        completePercent: float,
    ) -> None:
        "we are availablePercent through the day"


class SomeTag(Protocol):
    allows_next_action: AbstractReference[bool]


class SomeTask(Protocol):
    name: AbstractReference[str]
    id: AbstractReference[str]
    effective_due_date: AbstractReference[DateTime[None]]
    effectively_completed: AbstractReference[bool]
    effectively_dropped: AbstractReference[bool]
    completion_date: AbstractReference[DateTime[None]]
    dropped_date: AbstractReference[DateTime[None]]
    effective_defer_date: AbstractReference[DateTime[None]]
    effective_planned_date: AbstractReference[DateTime[None]]
    parent_task: AbstractReference[SomeTask]
    blocked: AbstractReference[bool]
    number_of_available_tasks: AbstractReference[int]
    tags: AbstractReference[Iterable[SomeTag]]

    def properties(self) -> dict[Any, Any]: ...


@dataclass
class Expression:
    """
    concrete local/cached expression
    """

    _left: object
    _op: Callable[[Any, Any], bool]
    _right: object

    def get(self) -> object:
        return self._op(self._left, self._right)

    def __lt__(self, other: object) -> Expression:
        return Expression(self.get(), operator.lt, other)

    def __eq__(self, other: object) -> Expression:  # type:ignore[override]

        return Expression(self.get(), operator.eq, other)

    def __ge__(self, other: object) -> Expression:
        return Expression(self.get(), operator.ge, other)

    def OR(self, other: object) -> Expression:
        return Expression(
            self,
            operator.or_,
            other,
        )

    def AND(self, other: object) -> Expression:
        return Expression(
            self,
            operator.and_,
            other,
        )

    def __bool__(self) -> bool:
        return bool(self.get())


@dataclass
class CachedReference[T]:
    get: Callable[[], T]

    def __ge__(self, other: object) -> Expression:
        return Expression(self, operator.ge, other)

    def __lt__(self, other: object) -> Expression:
        return Expression(self, operator.lt, other)

    def __eq__(self, other: object) -> Expression:  # type:ignore[override]
        return Expression(self, operator.eq, other)

    def OR(self, other: object) -> CachedReference[object]:
        return CachedReference(lambda: self.get() or other)

    def AND(self, other: object) -> CachedReference[object]:
        return CachedReference(lambda: self.get() and other)

    def __call__(self) -> T:
        return self.get()

    def __bool__(self) -> bool:
        # this could be implemented but let's just make sure
        raise NotImplementedError("evaluations should be via Expression probably")


if TYPE_CHECKING:
    x: Any = object()
    a: Expression = x
    b: AbstractExpression
    b = a
    cached: CachedReference[Any] = x
    c: AbstractReference[Any] = cached
