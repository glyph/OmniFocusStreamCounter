from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Protocol

from appscript import app, its, k
from twisted.internet.defer import Deferred
from twisted.internet.interfaces import IReactorTime
from twisted.internet.task import deferLater
from twisted.logger import Logger, textFileLogObserver

omnifocus = app("omnifocus")
log = Logger()
doc = omnifocus.documents[0].get()


def available(task) -> bool:
    """
    determine if a task is available?
    """
    # todo: only first available if parent is sequential, parent has 'number of
    # available tasks' > 0?, effective defer date, status, effective status
    defer_date = task.effective_defer_date()
    parent = task.parent_task()
    unblocked = not (task.blocked() and task.number_of_available_tasks() == 0)
    # xxx this should be number of *remaining*, right?
    not_deferred = defer_date == k.missing_value or defer_date <= datetime.now()
    parent_available = parent == k.missing_value or available(parent)
    tags_available = all(tag.allows_next_action() for tag in task.tags())
    return unblocked and not_deferred and parent_available and tags_available


class ProgressStatus(Protocol):
    def updateProgress(
        self,
        availablePercent: float,
        completePercent: float,
    ) -> None: ...


def query(reactor: object, updatePercentages: ProgressStatus) -> Deferred[None]:
    clock = IReactorTime(reactor)

    async def rest() -> None:
        await deferLater(clock, 0.25)

    async def keepChecking() -> None:
        while True:
            await rest()
            all_completed = 0.0
            all_pending = 0.0
            # t0 = time()
            today = date.today()
            tomorrow = today + timedelta(days=1)
            # yesterday = today - timedelta(days=1)

            e = doc.flattened_tasks[
                (
                    (its.effective_due_date >= today).AND(
                        its.effective_due_date < tomorrow
                    )
                ).OR((its.completion_date >= today).OR(its.dropped_date >= today))
            ]
            pending = []
            available_pending = 0.0
            # wait for omnifocus to be in the background so we don't block its
            # UI and make it unpleasant to use.
            while omnifocus.frontmost():
                await rest()
            reflist = e.get()
            lastrep = 0.0
            for i, eachref in enumerate(reflist):
                pctdone = (i + 1) / len(reflist)
                if pctdone == 1.0 or (pctdone - lastrep >= 0.05):
                    lastrep = pctdone
                    log.info(
                        "querying omnifocus {pctdone:0.1f}% done",
                        pctdone=(pctdone * 100),
                    )
                await rest()
                each = eachref.get()
                if each.effectively_completed() or each.effectively_dropped():
                    all_completed += 1
                else:
                    pending.append(each)
                    all_pending += 1
                    if available(each):
                        available_pending += 1
            log.info("enumerated everything!")
            avail_pct = all_completed / (available_pending + all_completed)
            complete_pct = all_completed / (all_pending + all_completed)
            updatePercentages.updateProgress(avail_pct, complete_pct)
            # tn = time()

    return Deferred.fromCoroutine(keepChecking())


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

    from sys import stdout

    globalLogBeginner.beginLoggingTo([textFileLogObserver(stdout)])

    @react
    async def main(reactor: object) -> None:
        await query(reactor, PrintUpdater())
