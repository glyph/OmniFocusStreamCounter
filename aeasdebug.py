import appscript.reference
import aem.aemsend
from twisted.logger import Logger

log = Logger()


originalCall = appscript.reference.Command.__call__
originalSend = aem.aemsend.Event.send


def debugCommandMethod(self, *args, **kargs):
    log.info(
        "calling a command method {ref}.{as_name}(*{args}, **{kargs})",
        ref=self._parentref,
        as_name=self.AS_name,
        args=args,
        kargs=kargs,
    )
    return originalCall(self, *args, **kargs)


def debugSend(self, *args, **kargs):
    log.info(
        "sending AE {params} {atts}",
        params=self._Event__params,
        atts=self._Event__atts,
    )
    return originalSend(self, *args, **kargs)


def install():
    appscript.reference.Command.__call__ = debugCommandMethod
    aem.aemsend.Event.send = debugSend
