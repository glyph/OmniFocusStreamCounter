from __future__ import annotations

from datetime import timedelta
from typing import Awaitable, Callable, Iterable, Protocol

from appscript import CommandError, app, its, k
from datetype import Date, DateTime, Time
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


class SomeTag(Protocol):
    allows_next_action: AppScriptReference[bool]


class SomeTask(Protocol):
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


def expression(
    what: SomeTask, today: DateTime[None], tomorrow: DateTime[None]
) -> object:
    return (
        (
            (what.effective_due_date < tomorrow).OR(
                what.effective_planned_date < tomorrow
            )
        )
        .AND(what.effectively_completed == False)
        .AND(what.effectively_dropped == False)
    ).OR((what.completion_date >= today).OR(what.dropped_date >= today))


async def updateOnce(
    rest: Callable[[], Awaitable[None]], updatePercentages: ProgressStatus
) -> tuple[float, float]:
    all_completed = 0.0
    all_pending = 0.0
    # t0 = time()
    today = DateTime.combine(Date.today(), Time.min)
    tomorrow = today + timedelta(days=1)

    # print("constructing query")
    e = doc.flattened_tasks[expression(its, today, tomorrow)]
    # print("constructed")
    pending = []
    available_pending = 0.0
    # wait for omnifocus to be in the background so we don't block its
    # UI and make it unpleasant to use.
    while omnifocus.frontmost():
        await rest()
    # print("getting...")
    reflist = e.get()
    # print(f"gotted: {len(reflist)}")
    lastrep = 0.0
    for i, eachref in enumerate(reflist):
        pctdone = ((i + 1) / len(reflist)) * 100
        updatePercentages.updateLoading(pctdone)
        if pctdone == 100.0 or (pctdone - lastrep >= 1.0):
            lastrep = pctdone
            log.info(
                "querying omnifocus {pctdone:0.1f}% done",
                pctdone=pctdone,
            )
        await rest()
        each = eachref.get()
        if each.effectively_completed() or each.effectively_dropped():
            all_completed += 1
            log.info(
                "COMPLETED/DROPPED {name} {all_completed}",
                name=each.name(),
                all_completed=all_completed,
            )
        else:
            pending.append(each)
            log.info("PENDING {name} {pending}", name=each.name(), pending=len(pending))
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


async def updateOnceGuard(
    rest: Callable[[], Awaitable[None]], updatePercentages: ProgressStatus
) -> tuple[float, float]:
    while True:
        try:
            return await updateOnce(rest, updatePercentages)
        except CommandError as ce:
            print(f"command error: {ce}")
            await rest()
            mail.launch()
            omnifocus.launch()


def query(reactor: object, updatePercentages: ProgressStatus) -> Deferred[None]:
    clock = IReactorTime(reactor)

    async def rest() -> None:
        await deferLater(clock, 0.1)

    async def keepChecking() -> None:
        # print("Checking!")
        while True:
            # print("Resting!")
            await rest()
            # print("Computing!")
            avail_pct, complete_pct = await updateOnceGuard(rest, updatePercentages)
            # print("Updating!")
            updatePercentages.updateProgress(avail_pct, complete_pct)
            # print("Updated!")
            # tn = time()

    return Deferred.fromCoroutine(keepChecking()).addErrback(
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
