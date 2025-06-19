from pyscript import document, WebSocket


def onopen(event):
    counter.removeChild(counter.childNodes[0])
    counter.append("OPEN")


def onmessage(event):
    counter.removeChild(counter.childNodes[0])
    counter.append(event.data)


def onclose(event):
    counter.removeChild(counter.childNodes[0])
    counter.append("OOF!")


counter = document.getElementById("counter")

ws = WebSocket(
    url="wss://gale.host.glyph.im/omnifocus-socket.rpy",
    onopen=onopen,
    onmessage=onmessage,
    onclose=onclose,
)
