from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Self, TypeAlias

from cattrs import ClassValidationError
from cattrs.preconf.json import make_converter
from keyring import get_password
from twisted.internet.defer import Deferred
from twisted.logger import Logger
from twisted.python.failure import Failure
from twisted.web.websocket import WebSocketClientEndpoint, WebSocketTransport

converter = make_converter()
log = Logger()


@dataclass
class OAuthStorage:
    path: Path
    cred: OAuthCredential
    client_id: str = "8v16ofu37kwgde0d6phskwqw1yhxya"
    _cachedValidation: AppValidation | Validation | None = None

    def name(self) -> str:
        return self.path.name

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.cred.access_token}",
            "Client-Id": self.client_id,
            "Content-Type": "application/json",
        }

    async def validate(self) -> Validation | AppValidation | None:
        if self._cachedValidation is not None:
            return self._cachedValidation
        from treq import get

        response = await get(
            "https://id.twitch.tv/oauth2/validate",
            headers=self.headers(),
        )
        json = await response.json()

        if response.code == 200:
            print("validstructure", json)
            myAlias: TypeAlias = AppValidation | Validation
            self._cachedValidation = converter.structure(json, myAlias)  # type:ignore[arg-type]
            return self._cachedValidation
        else:
            return None

    async def refresh(self) -> Validation | AppValidation | None:
        print("checking", self.name())
        if it := await self.validate():
            print("already valid")
            return it

        if self.cred.refresh_token is None:
            print("cannot refresh no refresh token :-(")
            return None

        from treq import post

        response = await post(
            "https://id.twitch.tv/oauth2/token",
            headers=self.headers(),
            data=dict(
                client_id=self.client_id,
                client_secret=get_password("dev.twitch.tv", "GlyphOfficialBot"),
                grant_type="refresh_token",
                refresh_token=self.cred.refresh_token,
            ),
        )
        body = await response.json()
        if response.code == 200:
            try:
                refreshed = converter.structure(body, RefreshedCredential)
            except ClassValidationError as cve:
                print("sub-exceptions:", cve.group_exceptions())
            else:
                self.cred = refreshed.to_storable(self.cred)
                new = self.path.parent / (self.path.name + ".new")
                with (new).open("w") as w:
                    w.write(converter.dumps(self.cred))

                new.rename(self.path)
            return await self.validate()
        else:
            print("got code", response.code, body)
            return None


@dataclass
class Validation:
    client_id: str
    login: str
    scopes: list[str]
    user_id: str
    expires_in: float


@dataclass
class AppValidation:
    client_id: str
    scopes: list[str] | None
    expires_in: float


@dataclass
class OAuthCredential:
    access_token: str = field(repr=False)
    expires_at: str
    scopes: str | list[str]
    refresh_token: str | None = field(repr=False, default=None)


@dataclass
class RefreshedCredential:
    access_token: str = field(repr=False)
    expires_in: float
    scope: str | list[str]
    token_type: str

    def to_storable(self, previous: OAuthCredential) -> OAuthCredential:
        print(f"scope: {previous.scopes!r} {self.scope!r}")
        return OAuthCredential(
            access_token=self.access_token,
            refresh_token=previous.refresh_token,
            expires_at=(
                datetime.now(timezone.utc) + timedelta(seconds=self.expires_in)
            ).isoformat(),
            scopes=self.scope,
        )


creds = []
for cred_path in Path("~").expanduser().glob("Secrets/TwitchBot/*.json"):
    print(cred_path)
    with cred_path.open() as f:
        creds.append(
            OAuthStorage(
                path=cred_path,
                cred=converter.loads(f.read(), OAuthCredential),
            )
        )
from pprint import pprint

pprint(creds)


from twisted.internet.task import react


@dataclass
class IncomingChatWebsocket:
    botCredentials: OAuthStorage
    broadcasterUserID: str
    botUserID: str

    def buildProtocol(self, uri: str) -> Self:
        return self

    async def registerEventSubListeners(self, sessionID: str) -> None:
        from treq import post

        print("subscribing")
        response = await post(
            "https://api.twitch.tv/helix/eventsub/subscriptions",
            headers=self.botCredentials.headers(),
            json={
                "type": "channel.chat.message",
                "version": "1",
                "condition": {
                    "broadcaster_user_id": self.broadcasterUserID,
                    "user_id": self.botUserID,
                },
                "transport": {
                    "method": "websocket",
                    "session_id": sessionID,
                },
            },
        )

        print("done subscribing")
        if response.code != 202:
            data = await response.json()
            print(
                f"Failed to subscribe to channel.chat.message. API call returned status code {response.code} ({data})"
            )
        else:
            data = await response.json()
            print(f"subscribed to {data}")
        print("response done")

    def sendChatMessage(self, chatMessage: str) -> None:
        pass

    def textMessageReceived(self, data: str) -> None:
        from json import loads

        jdata = loads(data)
        print("--message--")
        pprint(jdata)
        match jdata["metadata"]["message_type"]:
            case "session_welcome":
                # Register the Session ID it gives us
                Deferred.fromCoroutine(
                    self.registerEventSubListeners(jdata["payload"]["session"]["id"])
                ).addErrback(lambda f: log.failure("failed", f))
            case "notification":
                match jdata["metadata"]["subscription_type"]:
                    case "channel.chat.message":
                        # First, print the message to the program's console.
                        print(
                            f'{jdata["payload"]["event"]["broadcaster_user_login"]} '
                            f'<${jdata["payload"]["event"]["chatter_user_login"]}> '
                            f'{jdata["payload"]["event"]["message"]["text"]}'
                        )

                        if (
                            jdata["payload"]["event"]["message"]["text"].strip()
                            == "HeyGuys"
                        ):
                            # If so, send back "VoHiYo" to the chatroom
                            self.sendChatMessage("VoHiYo")

    def negotiationStarted(self, transport: WebSocketTransport) -> None:
        self.transport = transport

    def negotiationFinished(self) -> None: ...

    def bytesMessageReceived(self, data: bytes) -> None: ...

    def connectionLost(self, reason: Failure) -> None: ...

    def pongReceived(self, payload: bytes) -> None: ...


@react
async def main(reactor: Any) -> None:
    for storage in creds:
        await storage.refresh()

    bot_creds = next(each for each in creds if each.name() == "bot-uat.json")
    broadcaster_creds = next(each for each in creds if each.name() == "broadcaster-uat.json")
    app_creds = next(each for each in creds if each.name() == "chat-app-token.json")

    print("bot", bot_creds)
    print("broadcast", broadcaster_creds)
    print("app", app_creds)

    wsce = WebSocketClientEndpoint.new(reactor, "wss://eventsub.wss.twitch.tv/ws")
    botValidation = await bot_creds.validate()
    broadcasterValidation = await broadcaster_creds.validate()
    assert isinstance(botValidation, Validation), "really should be valid at this point"
    assert isinstance(broadcasterValidation, Validation), "both should have validated"
    await wsce.connect(
        IncomingChatWebsocket(
            bot_creds,
            broadcasterUserID=broadcasterValidation.user_id,
            botUserID=botValidation.user_id,
        )
    )
    await Deferred()
