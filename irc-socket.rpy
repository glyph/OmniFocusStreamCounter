from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, Self

from keyring import get_password
from twisted.internet.defer import Deferred
from twisted.internet.endpoints import HostnameEndpoint, wrapClientTLS
from twisted.internet.protocol import Factory
from twisted.internet.ssl import optionsForClientTLS
from twisted.internet.task import LoopingCall
from twisted.logger import Logger
from twisted.python.failure import Failure
from treq import get

from twisted.web.server import Request
from twisted.web.websocket import WebSocketResource, WebSocketTransport
from twisted.words.protocols.irc import IRCClient

log = Logger()


@dataclass
class TwitchyClient:
    client: IRCClient

    def handleSignedOn(self, superMethod: Callable[[], None]) -> None:
        log.info("signed on, sending Twitch commands")
        self.client.sendLine("CAP REQ :twitch.tv/membership")
        self.client.sendLine("CAP REQ :twitch.tv/tags")
        self.client.sendLine("CAP REQ :twitch.tv/commands")
        superMethod()
        log.info("done signing on")

    def debugHandling(
        self,
        superMethod: Callable[[bytes, bytes, list[bytes]], None],
        command: bytes,
        prefix: bytes,
        params: list[bytes],
    ) -> None:
        log.info(
            "handling command {command} {prefix} {params}",
            command=command,
            prefix=prefix,
            params=params,
        )
        superMethod(command, prefix, params)
        log.info("handled it")

    def lineDebug(
        self, superMethod: Callable[[bytes | str], None], line: bytes | str
    ) -> None:
        log.info("sending line {line}", line=line)
        superMethod(line)
        log.info("sent it", line=line)

    @classmethod
    async def connect(cls, reactor: Any, WebSocketDemo) -> Self:
        log.info("starting connection")
        pw = get_password("twitch.tv", "glyph_official_bot")
        response = await get(
            "https://id.twitch.tv/oauth2/validate",
            headers={"Authorization": f"OAuth {pw}"},
        )
        j = await response.json()
        print("valid?", j)
        endpoint = wrapClientTLS(
            optionsForClientTLS("irc.chat.twitch.tv"),
            HostnameEndpoint(reactor, "irc.chat.twitch.tv", 6697),
        )
        myClient = IRCClient()
        # myClient.username = "glyph_official"  # type:ignore[assignment]
        myClient.nickname = "glyph_official"
        if not pw:
            raise ValueError("empty password")
        myClient.password = f"oauth:{pw}"  # type:ignore[assignment]
        self = cls(myClient)
        setattr(
            self.client, "signedOn", partial(self.handleSignedOn, self.client.signedOn)
        )
        setattr(
            self.client,
            "handleCommand",
            partial(self.debugHandling, self.client.handleCommand),
        )
        def joinStuff(motd: list[bytes]) ->None:
            self.client.join("glyph_official")
        def joined(channel: bytes) -> None:
            log.info("joined {channel}", channel=channel)
            self.client.say("glyph_official", "hello world")
        setattr(self.client, "receivedMOTD", joinStuff)
        setattr(self.client, "joined", joined)
        # setattr(
        #     self.client,
        #     "sendLine",
        #     partial(self.lineDebug, self.client.sendLine),
        # )

        # def register(self, nickname, hostname="foo", servername="bar"):
        #     pass

        # setattr(self.client, "register", newRegister)
        await endpoint.connect(Factory.forProtocol(lambda: myClient))
        return self


class WebSocketDemo:
    loop: LoopingCall | None = None

    @classmethod
    def buildProtocol(cls, request: Request) -> WebSocketDemo:
        return cls()

    def negotiationStarted(self, transport: WebSocketTransport) -> None:
        self.transport = transport

    def negotiationFinished(self) -> None:
        from twisted.internet import reactor

        async def hello() -> None:
            try:
                connected = await TwitchyClient.connect(reactor, self)
                log.info("negotiated, connected: {connected}", connected=connected)
            except:
                log.failure("while connecting")

        Deferred.fromCoroutine(hello())

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
