from __future__ import annotations

from twisted.internet.task import LoopingCall
from twisted.python.failure import Failure

# from twisted.web.iweb import IRequest
from twisted.web.server import Request
from twisted.web.websocket import WebSocketResource, WebSocketTransport
from twisted.internet import reactor
from twisted.logger import Logger

from ofprogress import query

log = Logger()


class OmniFocusProgressSocket:
    loop: LoopingCall | None = None

    @classmethod
    def buildProtocol(cls, request: Request) -> OmniFocusProgressSocket:
        return cls()

    def negotiationStarted(self, transport: WebSocketTransport) -> None:
        self.transport = transport

    def updateProgress(self, availablePercent: float, completePercent: float) -> None:
        message = f"{availablePercent*100:0.1f}%"
        self.transport.sendTextMessage(message)
        log.info("sending message: {message}", message=message)

    def negotiationFinished(self) -> None:
        query(reactor, self)

    def textMessageReceived(self, data: str) -> None:
        self.transport.sendTextMessage(f"reply to {data}")

    def connectionLost(self, reason: Failure) -> None:
        if self.loop is not None:
            self.loop.stop()

    # Since WebSocketProtocol is a typing.Protocol and not a class, we must
    # provide implementations for all events, even those we don't care about.
    def bytesMessageReceived(self, data: bytes) -> None: ...
    def pongReceived(self, payload: bytes) -> None: ...


resource = WebSocketResource(OmniFocusProgressSocket)
