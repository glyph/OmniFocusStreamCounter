from __future__ import annotations

from dataclasses import dataclass
from datetime import time, timedelta
from typing import Any, Iterable, Protocol, Sequence

from appscript import CommandError, Reference, app, its, k
from datetype import DateTime, naive
from twisted.internet.defer import Deferred
from twisted.internet.interfaces import IReactorTime
from twisted.internet.task import deferLater
from twisted.logger import Logger, textFileLogObserver

omnifocus = app("omnifocus")
log = Logger()
doc = omnifocus.documents[0].get()

mail = app("mail")
inbox = mail.accounts["Fastmail"]().mailboxes["INBOX"]


class AppScriptReference[T](Protocol):
    def __call__(self) -> T: ...
    def __lt__(self, other: T) -> AppScriptReference[bool]: ...
    def __ge__(self, other: T) -> AppScriptReference[bool]: ...
    def OR(self, other: AppScriptReference[T] | T) -> AppScriptReference[bool]: ...
    def AND(self, other: AppScriptReference[T] | T) -> AppScriptReference[bool]: ...
    def get(self) -> T: ...


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


def available(task: SomeTask) -> bool:
    """
    determine if a task is available?
    """
    # todo: only first available if parent is sequential, parent has 'number of
    # available tasks' > 0?, effective defer date, status, effective status
    defer_date = task.effective_defer_date()
    parent = task.parent_task()
    unblocked = not (task.blocked() and task.number_of_available_tasks() == 0)
    # xxx this should be number of *remaining*, right?
    not_deferred = defer_date == k.missing_value or defer_date <= DateTime.now()
    parent_available = parent == k.missing_value or available(parent)
    tags_available = all(tag.allows_next_action() for tag in task.tags())
    # print(
    #     f"""
    # checking task: {task.name()}
    #     unblocked: {unblocked}
    #     not_deferred: {not_deferred}
    #     parent_available: {parent_available}
    #     tags_available: {tags_available}
    # """
    # )
    return unblocked and not_deferred and parent_available and tags_available


class ProgressStatus(Protocol):
    def updateLoading(self, loadedPercent: float) -> None:
        "the next refresh is C{loadedPercent} done loading"

    def updateProgress(
        self,
        availablePercent: float,
        completePercent: float,
    ) -> None:
        "we are availablePercent through the day"


def AND(
    a: AppScriptReference[Any] | bool, b: AppScriptReference[Any] | bool
) -> AppScriptReference[bool] | bool:
    operator = getattr(a, "AND", None)
    if operator is None:
        return bool(a and b)
    else:
        return operator(b)


def OR(
    a: AppScriptReference[Any] | bool, b: AppScriptReference[Any] | bool
) -> AppScriptReference[bool] | bool:
    operator = getattr(a, "OR", None)
    if operator is None:
        return bool(a or b)
    else:
        return operator(b)


class Nope:
    def __lt__(self, other: object) -> bool:
        return False

    def __ge__(self, other: object) -> bool:
        return False


def either[T](a: AppScriptReference[T]) -> AppScriptReference[T] | Nope:
    if isinstance(a, Reference):
        result = a.get()
        if result == k.missing_value:
            return Nope()
        return result
    else:
        return a


def expression(
    what: SomeTask, today: DateTime[None], tomorrow: DateTime[None]
) -> AppScriptReference[bool] | bool:
    return OR(
        (
            AND(
                AND(
                    OR(
                        (either(what.effective_due_date) < tomorrow),
                        (either(what.effective_planned_date) < tomorrow),
                    ),
                    (either(what.effectively_completed) == False),
                ),
                (either(what.effectively_dropped) == False),
            )
        ),
        OR(
            (either(what.completion_date) >= today),
            (either(what.dropped_date) >= today),
        ),
    )


@dataclass
class PropertyCache:
    _ref: Any
    _taskCache: dict[str, SomeTask]
    _tagCache: dict[str, SomeTag]
    _properties: dict[object, Any]
    _cachedTagRefs: list[Any] | None = None

    def __getattr__(self, name: str) -> Any:
        def get() -> Any:
            result = self._properties[getattr(k, name)]
            return result

        return get

    def parent_task(self) -> Any:
        # do the same thing with tags?
        ref = self._properties[k.parent_task]
        if ref == k.missing_value:
            return ref
        parentID = ref.id()
        if parentID not in self._taskCache:
            result: Any = PropertyCache(
                ref, self._taskCache, self._tagCache, ref.properties()
            )
            self._taskCache[parentID] = result
        return self._taskCache[parentID]

    def tags(self) -> Sequence[SomeTag]:
        if self._cachedTagRefs is None:
            self._cachedTagRefs = self._ref.tags()
        refs = self._cachedTagRefs
        result = []
        for ref in refs:
            tagID = ref.id()
            if tagID not in self._tagCache:
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


@dataclass
class Cacher:
    clock: IReactorTime
    taskCache: dict[str, SomeTask]  # map id to task
    lastUpdateTime: DateTime[None]
    updater: ProgressStatus
    tagCache: dict[str, SomeTag]  # map id to tag
    first: bool = True

    @classmethod
    async def new(cls, clock: IReactorTime, updater: ProgressStatus) -> Cacher:
        now = DateTime.now()
        today = now.date()
        todayStart = DateTime.combine(today, naive(time.min))
        tomorrowStart = todayStart + timedelta(days=1)
        e: AppScriptReference[Sequence[SomeTask]] = doc.flattened_tasks[
            expression(its, todayStart, tomorrowStart)
        ]
        log.info("Initial load...")
        refList = e.get()
        log.info("Loaded!")
        initialCache: dict[str, SomeTask] = {}
        tagCache: dict[str, SomeTag] = {}
        for i, eachRef in enumerate(refList):
            updater.updateLoading(100 * (i / len(refList)))
            await deferLater(clock, 0.01)
            cached = asPropertyCache(initialCache, tagCache, eachRef)
            initialCache[cached.id()] = cached

        return Cacher(clock, initialCache, now, updater, tagCache)

    async def checkForUpdates(self) -> bool:
        now = DateTime.now()
        # TODO: full refresh at midnight when date has changed
        today = now.date()
        todayStart = DateTime.combine(today, naive(time.min))
        tomorrowStart = todayStart + timedelta(days=1)
        then = self.lastUpdateTime
        newAndUpdated = doc.flattened_tasks[its.modification_date > then]()
        for i, task in enumerate(newAndUpdated):
            self.updater.updateLoading((i / len(newAndUpdated)) * 100)
            taskID = task.id()
            if expression(task, todayStart, tomorrowStart):
                self.taskCache[taskID] = asPropertyCache(
                    self.taskCache, self.tagCache, task
                )
            else:
                self.taskCache.pop(taskID, None)
        if newAndUpdated:
            self.updater.updateLoading(100.0)
        self.lastUpdateTime = now
        first = self.first
        self.first = False
        return first or bool(newAndUpdated)

    def values(self) -> Sequence[SomeTask]:
        return list(self.taskCache.values())


@dataclass
class OFReader:
    clock: IReactorTime
    updatePercentages: ProgressStatus
    cacher: Cacher

    async def rest(self, length: float = 0.1) -> None:
        await deferLater(self.clock, length)

    async def run(self) -> None:

        # print("Checking!")
        while True:
            # print("Resting!")
            await self.rest(1.0)
            # print("Computing!")
            result = await self.updateAndRetry()
            # print("Updating!")
            if result is not None:
                avail_pct, complete_pct = result
                self.updatePercentages.updateProgress(avail_pct, complete_pct)
            # print("Updated!")
            # tn = time()

    async def updateAndRetry(self) -> tuple[float, float] | None:
        while True:
            try:
                return await self.oneUpdate()
            except CommandError as ce:
                print(f"command error: {ce}")
                await self.rest()
                mail.launch()
                omnifocus.launch()

    async def oneUpdate(self) -> tuple[float, float] | None:
        # t0 = time()

        # print("constructing query")
        # print("constructed")
        pending = []
        available_pending = 0.0
        # wait for omnifocus to be in the background so we don't block its
        # UI and make it unpleasant to use.
        lastrep = 0.0

        all_completed = 0.0
        all_pending = 0.0
        log.info("checking for changes")
        anyChanges = await self.cacher.checkForUpdates()
        log.info("changes: {changes}", changes=anyChanges)
        if not anyChanges:
            return None
        reflist = self.cacher.values()
        for i, each in enumerate(reflist):
            pctdone = ((i + 1) / len(reflist)) * 100
            if pctdone == 100.0 or (pctdone - lastrep >= 1.0):
                lastrep = pctdone
                log.info(
                    "querying omnifocus {pctdone:0.1f}% done",
                    pctdone=pctdone,
                )
            # await self.rest()
            # print(f"revalidating {each.id()}: {expression(each, today, tomorrow)}")
            if each.effectively_completed() or each.effectively_dropped():
                all_completed += 1
                log.info(
                    "COMPLETED/DROPPED {name} {all_completed}",
                    name=each.name(),
                    all_completed=all_completed,
                )
            else:
                pending.append(each)
                log.info(
                    "PENDING {name} {pending}",
                    name=each.name(),
                    pending=len(pending),
                )
                all_pending += 1
                if available(each):
                    log.info(
                        "   available {available_pending}",
                        available_pending=available_pending,
                    )
                    available_pending += 1
                else:
                    log.info(
                        "   NOT available {available_pending}",
                        available_pending=available_pending,
                    )
        log.info("enumerated everything!")
        remaining_mail = len(inbox.messages())
        avail_pct = all_completed / (available_pending + all_completed + remaining_mail)
        complete_pct = all_completed / (all_pending + all_completed)
        return (avail_pct, complete_pct)


def query(reactor: object, progress: ProgressStatus) -> Deferred[None]:
    async def setUpAndGo() -> None:
        clock = IReactorTime(reactor)
        cacher = await Cacher.new(clock, progress)
        reader = OFReader(clock, progress, cacher)
        await reader.run()

    return Deferred.fromCoroutine(setUpAndGo()).addErrback(
        lambda f: log.failure("in omnifocus check loop", f)
    )


if __name__ == "__main__":
    from twisted.internet.task import react
    from twisted.logger import globalLogBeginner

    class PrintUpdater:
        def updateProgress(
            self, availablePercent: float, completePercent: float
        ) -> None:
            print(
                f"Updating completion percentage: {availablePercent} {completePercent}"
            )

        def updateLoading(self, loadedPercent: float) -> None:
            pass

    from sys import stdout

    globalLogBeginner.beginLoggingTo([textFileLogObserver(stdout)])

    @react
    async def main(reactor: object) -> None:
        await query(reactor, PrintUpdater())
