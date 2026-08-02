from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    cache: Callable[[], None] = lambda: None
cache()  # type:ignore[name-defined]

from dataclasses import dataclass, field
from json import dumps

from twisted.internet import reactor
from twisted.logger import Logger
from twisted.python.failure import Failure
from twisted.web.server import Request
from twisted.web.websocket import (
    WebSocketProtocol,
    WebSocketResource,
    WebSocketTransport,
)

from ofprogress import ProgressStatus, query

log = Logger()


@dataclass
class MultiStatus:
    updaters: list[ProgressStatus] = field(default_factory=list)
    currentLoaded: float = 0.0
    currentAvailable: float = 0.0
    currentComplete: float = 0.0

    def addStatus(self, status: ProgressStatus) -> None:
        self.updaters.append(status)
        status.updateLoading(self.currentLoaded)
        status.updateProgress(self.currentAvailable, self.currentComplete)

    def removeStatus(self, status: ProgressStatus) -> None:
        self.updaters.remove(status)

    def updateLoading(self, loadedPercent: float) -> None:
        "the next refresh is C{loadedPercent} done loading"
        self.currentLoaded = loadedPercent
        for updater in self.updaters:
            updater.updateLoading(loadedPercent)

    def updateProgress(
        self,
        availablePercent: float,
        completePercent: float,
    ) -> None:
        "we are availablePercent through the day"
        self.currentAvailable = availablePercent
        self.currentComplete = completePercent
        for updater in self.updaters:
            updater.updateProgress(availablePercent, completePercent)


multi = MultiStatus()
query(reactor, multi)


class OmniFocusProgressSocket:

    @classmethod
    def buildProtocol(cls, request: Request) -> WebSocketProtocol:
        return cls()

    def negotiationStarted(self, transport: WebSocketTransport) -> None:
        self.transport = transport

    def updateProgress(self, availablePercent: float, completePercent: float) -> None:
        message = dumps({"type": "update", "percent": availablePercent * 100.0})
        self.transport.sendTextMessage(message)
        log.info("sending message: {message}", message=message)

    def updateLoading(self, loadedPercent: float) -> None:
        self.transport.sendTextMessage(
            dumps({"type": "loading", "percent": loadedPercent})
        )

    def negotiationFinished(self) -> None:
        multi.addStatus(self)

    def textMessageReceived(self, data: str) -> None:
        # self.transport.sendTextMessage(f"reply to {data}")
        "no-op"

    def connectionLost(self, reason: Failure) -> None:
        multi.removeStatus(self)

    # Since WebSocketProtocol is a typing.Protocol and not a class, we must
    # provide implementations for all events, even those we don't care about.
    def bytesMessageReceived(self, data: bytes | bytearray) -> None: ...
    def pongReceived(self, payload: bytes) -> None: ...


resource = WebSocketResource(OmniFocusProgressSocket)
