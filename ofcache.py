from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from appscript import k
from twisted.logger import Logger

from oftypes import AbstractReference, SomeTag, SomeTask, CachedReference

log = Logger()


@dataclass
class PropertyCache:
    """
    A L{PropertyCache} is a cached version of the data in an appscript
    reference, derived from its C{properties()}, to avoid doing (slow)
    AppleEvent round trips to retrieve each property as a method call.
    """

    _ref: Any
    _taskCache: dict[str, SomeTask]
    _tagCache: dict[str, SomeTag]
    _properties: dict[object, Any]
    _cachedTagRefs: list[Any] | None = None

    def __getattr__(self, name: str) -> AbstractReference[Any]:
        return CachedReference(lambda: self._properties[getattr(k, name)])

    def parent_task(self) -> SomeTask:
        ref = self._properties[k.parent_task]
        if ref == k.missing_value:
            return ref
        # TODO: we already _got_ the .id() but appscript keeps it as private
        # data, so we have to fish it out like this
        return fromRef(
            ref, "parent ID", self._taskCache, self._taskCache, self._tagCache
        )

    def tags(self) -> Sequence[SomeTag]:
        if self._cachedTagRefs is None:
            # .id() is safe here because it's actually a cached string
            log.info("cache miss for tags on {id}", id=self.id())
            self._cachedTagRefs = self._ref.tags()
        refs = self._cachedTagRefs
        result = []
        for ref in refs:
            result.append(
                fromRef(ref, "tag ID", self._tagCache, self._taskCache, self._tagCache)
            )

        return result

    def properties(self) -> dict[object, Any]:
        return self._properties


def fromRef[T: SomeTask | SomeTag](
    ref: Any,
    someType: str,
    someCache: dict[str, T],
    taskCache: dict[str, SomeTask],
    tagCache: dict[str, SomeTag],
    overwrite: bool = False,
) -> T:
    someID = ref.AS_aemreference._key
    if overwrite or someID not in someCache:
        log.info("cache miss for {someType} {someID}", someType=someType, someID=someID)
        newCache: T = PropertyCache(  # type:ignore[assignment]
            ref,
            taskCache,
            tagCache,
            ref.properties(),
        )
        someCache[someID] = newCache
    return someCache[someID]


def asPropertyCache(
    taskCache: dict[str, SomeTask], tagCache: dict[str, SomeTag], task: SomeTask
) -> SomeTask:
    result: Any = PropertyCache(task, taskCache, tagCache, task.properties())
    return result
