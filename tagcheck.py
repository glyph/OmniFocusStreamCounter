from dataclasses import dataclass
from typing import Literal
from cattrs.preconf.json import make_converter


jconv = make_converter()


@dataclass
class Tagged[T]:
    tag: T


@dataclass
class Envelope[T, V]:
    metadata: Tagged[T]
    value: V


@dataclass
class SomeTag1:
    value: Literal["A"]


@dataclass
class SomeTag2:
    value: Literal["B"]


@dataclass
class SomeValue1:
    a: str


@dataclass
class SomeValue2:
    b: int


value = jconv.loads(
    """
    [{"metadata": {"tag": {"value": "A"}}, "value": {"a": "hello"}},
     {"metadata": {"tag": {"value": "B"}}, "value": {"b": 7}}]
    """,
    list[Envelope[SomeTag2, SomeValue2] | Envelope[SomeTag1, SomeValue1]],
)
print(value)
