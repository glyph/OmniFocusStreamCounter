from json import loads

from pyscript import WebSocket, document, window

console = window.console

counter = document.getElementById("counter")
progress = document.getElementById("progress")
loading = document.getElementById("loading")

def onopen(event):
    progress.style.width = '1px'
    counter.removeChild(counter.childNodes[-1])
    counter.append("OPEN")


def onmessage(event):
    payload = loads(event.data)
    pct = payload['percent']
    if payload['type'] == 'update':
        element = progress
        counter.removeChild(counter.childNodes[-1])
        counter.append(f"{pct:0.1f}%")
    else:
        element = loading
    element.style.width = f"{pct}%"


def onclose(event):
    counter.removeChild(counter.childNodes[-1])
    counter.append("OOF!")



ws = WebSocket(
    url="wss://gale.host.glyph.im/omnifocus-socket.rpy",
    onopen=onopen,
    onmessage=onmessage,
    onclose=onclose,
)
