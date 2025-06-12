from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class SessionInfo:
    id: str
    status: str
    connected_at: datetime
    keepalive_timeout_seconds: float
    reconnect_url: str | None
    recovery_url: str | None


@dataclass
class Welcome:
    session: SessionInfo


@dataclass
class WelcomeEnvelope:
    message_type: Literal["session_welcome"]
    message_timestamp: datetime
    message_id: str
    payload: Welcome


@dataclass
class Notification: ...


@dataclass
class NotificationEnvelope:
    message_type: Literal["notification"]
    message_timestamp: datetime
    message_id: str
    payload: Notification


@dataclass
class Empty: ...


@dataclass
class KeepaliveEnvelope:
    message_type: Literal["notification"]
    message_timestamp: datetime
    message_id: str
    payload: Empty


SomePayload = WelcomeEnvelope
