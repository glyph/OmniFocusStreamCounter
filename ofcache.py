from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from appscript import k
from twisted.logger import Logger

from oftypes import AppScriptReference, SomeTag, SomeTask

log = Logger()

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


@dataclass
class PropertyCache:
    _ref: Any
    _taskCache: dict[str, SomeTask]
    _tagCache: dict[str, SomeTag]
    _properties: dict[object, Any]
    _cachedTagRefs: list[Any] | None = None

    def __getattr__(self, name: str) -> AppScriptReference[Any]:
        return CachedReference(lambda: self._properties[getattr(k, name)])

    def parent_task(self) -> Any:
        # do the same thing with tags?
        ref = self._properties[k.parent_task]
        if ref == k.missing_value:
            return ref
        # TODO: we already _got_ the .id() but appscript keeps it as private
        # data, so we have to fish it out like this
        parentID = ref.AS_aemreference._key
        if parentID not in self._taskCache:
            log.info("cache miss for parent ID {tagID}", tagID=parentID)
            result: Any = PropertyCache(
                ref, self._taskCache, self._tagCache, ref.properties()
            )
            # TODO: if the parent task doesn't match the expression, we store
            # it in the cache anyway, and that's bad, because it results in a
            # too-large denominator
            self._taskCache[parentID] = result
        return self._taskCache[parentID]

    def tags(self) -> Sequence[SomeTag]:
        if self._cachedTagRefs is None:
            # .id() is safe here because it's actually a cached string
            log.info("cache miss for tags on {id}", id=self.id())
            self._cachedTagRefs = self._ref.tags()
        refs = self._cachedTagRefs
        result = []
        for ref in refs:
            # see TODO in parent_task
            tagID = ref.AS_aemreference._key
            if tagID not in self._tagCache:
                log.info("cache miss for tag ID {tagID}", tagID=tagID)
                # ehhh close enough, parent_task is wrong but attr access
                # should line up close enough.
                newCachedTag: Any = PropertyCache(
                    ref, self._taskCache, self._tagCache, ref.properties()
                )
                self._tagCache[tagID] = newCachedTag
            result.append(self._tagCache[tagID])

        return result

    def properties(self) -> dict[object, Any]:
        return self._properties


def asPropertyCache(
    taskCache: dict[str, SomeTask], tagCache: dict[str, SomeTag], task: SomeTask
) -> SomeTask:
    result: Any = PropertyCache(task, taskCache, tagCache, task.properties())
    return result


