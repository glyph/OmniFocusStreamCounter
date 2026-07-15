from __future__ import annotations
from typing import Protocol, Iterable, Any
from datetype import DateTime


class AppScriptExpression[T](Protocol):
    def __lt__(self, other: object) -> AppScriptExpression: ...
    def __eq__(self, other: object) -> AppScriptExpression: ...  # type:ignore[override]
    def __ge__(self, other: object) -> AppScriptExpression: ...
    def OR(self, other: AppScriptReference[T] | T) -> AppScriptExpression: ...
    def AND(self, other: AppScriptReference[T] | T) -> AppScriptExpression: ...


class AppScriptReference[T](Protocol):
    def __call__(self) -> T: ...
    def get(self) -> T: ...
    def __lt__(self, other: object) -> AppScriptExpression: ...
    def __ge__(self, other: object) -> AppScriptExpression: ...
    def __eq__(self, other: object) -> AppScriptExpression: ...  # type:ignore[override]


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
    allows_next_action: AppScriptReference[bool]


class SomeTask(Protocol):
    name: AppScriptReference[str]
    id: AppScriptReference[str]
    effective_due_date: AppScriptReference[DateTime[None]]
    effectively_completed: AppScriptReference[bool]
    effectively_dropped: AppScriptReference[bool]
    completion_date: AppScriptReference[DateTime[None]]
    dropped_date: AppScriptReference[DateTime[None]]
    effective_defer_date: AppScriptReference[DateTime[None]]
    effective_planned_date: AppScriptReference[DateTime[None]]
    parent_task: AppScriptReference[SomeTask]
    blocked: AppScriptReference[bool]
    number_of_available_tasks: AppScriptReference[int]

    tags: AppScriptReference[Iterable[SomeTag]]

    def properties(self) -> dict[Any, Any]: ...


