from __future__ import annotations

import appscript
from appscript import k
from twisted.internet.task import LoopingCall
from twisted.logger import Logger
from twisted.python.failure import Failure
from twisted.web.iweb import IRequest
from twisted.web.server import Request
from twisted.web.websocket import WebSocketResource, WebSocketTransport

omnifocus = appscript.app("omnifocus")
doc = omnifocus.documents[0].get()

from datetime import date, datetime, timedelta
from time import time

from appscript import its


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


log = Logger()

def query(enum_func):
    all_completed = 0.0
    all_pending = 0.0
    t0 = time()
    today = date.today()
    tomorrow = today + timedelta(days=1)
    yesterday = today - timedelta(days=1)
    e = doc.flattened_tasks[
        ((its.effective_due_date >= today).AND(its.effective_due_date < tomorrow)).OR(
            (its.completion_date >= today).OR(its.dropped_date >= today)
        )
    ]
    pending = []
    available_pending = 0.0
    for i, each in enumerate(enum_func(e)):
        log.info("enumerating omnifocus {i}", i=i)
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
    tn = time()
    return (avail_pct, complete_pct)


def eager_enum(appref):
    return appref.get()


class WebSocketDemo:
    loop: LoopingCall | None = None

    @classmethod
    def buildProtocol(cls, request: Request) -> WebSocketDemo:
        return cls()

    def negotiationStarted(self, transport: WebSocketTransport) -> None:
        self.transport = transport

    def negotiationFinished(self) -> None:
        def heartbeat() -> None:
            try:
                availpct, completepct = query(eager_enum)
                message = f"{availpct*100:0.1f}%"
                log.info("sending message: {message}", message=message)
                self.transport.sendTextMessage(message)
            except:
                Failure().printTraceback()

        self.loop = LoopingCall(heartbeat)
        self.loop.start(10.0, now=True)

    def textMessageReceived(self, data: str) -> None:
        self.transport.sendTextMessage(f"reply to {data}")

    def connectionLost(self, reason: Failure) -> None:
        if self.loop is not None:
            self.loop.stop()

    # Since WebSocketProtocol is a typing.Protocol and not a class, we must
    # provide implementations for all events, even those we don't care about.
    def bytesMessageReceived(self, data: bytes) -> None: ...
    def pongReceived(self, payload: bytes) -> None: ...


resource = WebSocketResource(WebSocketDemo)
