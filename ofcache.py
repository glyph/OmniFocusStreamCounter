from __future__ import annotations
from typing import Callable
from dataclasses import dataclass
import operator

@dataclass
class Expression[A, B]:
    _left: A
    _op: Callable[[A, B], bool]
    _right: B

    def OR[C](self, other: C) -> Expression[Expression[A, B], C]:
        return Expression(
            self,
            operator.and_,
            other,
        )

    def AND[C](self, other: C) -> Expression[Expression[A, B], C]:
        return Expression(
            self,
            operator.and_,
            other,
        )


@dataclass
class CachedReference[T]:
    get: Callable[[], T]

    def __call__(self) -> T:
        return self.get()

    def __lt___(self, other: T) -> Expression:
        return Expression(self, operator.lt, other)

    def __ge___(self, other: T) -> Expression:
        return Expression(self, operator.ge, other)

    def __eq__(self, other: T) -> Expression:  # type:ignore[override]
        return Expression(self, operator.eq, other)


