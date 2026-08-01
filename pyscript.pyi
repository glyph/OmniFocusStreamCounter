from dataclasses import dataclass
from typing import Callable

@dataclass
class WebSocket:
    url: str
    onopen: Callable
    onmessage: Callable
    onclose: Callable

class _Element: ...

class _Document:
    def getElementById(self, id: str) -> _Element: ...

class _Console: ...

class _Window:
    console: _Console

document: _Document
window: _Window
