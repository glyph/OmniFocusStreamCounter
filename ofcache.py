from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from appscript import k
from twisted.logger import Logger

from oftypes import AbstractReference, SomeTag, SomeTask, CachedReference

log = Logger()


@dataclass
class PropertyCache:
    _ref: Any
    _taskCache: dict[str, SomeTask]
    _tagCache: dict[str, SomeTag]
    _properties: dict[object, Any]
    _cachedTagRefs: list[Any] | None = None

    def __getattr__(self, name: str) -> AbstractReference[Any]:
        return CachedReference(lambda: self._properties[getattr(k, name)])

    def parent_task(self) -> SomeTask:
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
