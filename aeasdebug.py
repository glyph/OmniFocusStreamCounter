import appscript.reference
import aem.aemsend
from twisted.logger import Logger

log = Logger()


originalCall = appscript.reference.Command.__call__
originalSend = aem.aemsend.Event.send
originalEventInit = aem.aemsend.Event.__init__


def debugCommandMethod(self, *args, **kargs):
    log.info(
        "calling a command method {ref}.{as_name}(*{args}, **{kargs})",
        ref=self._parentref,
        as_name=self.AS_name,
        args=args,
        kargs=kargs,
    )
    return originalCall(self, *args, **kargs)


def saveParamsAndAtts(self, address, event, params={}, atts={}, *args, **kwargs):
    self._Event__params = params
    self._Event__atts = atts
    return originalEventInit(self, address, event, params, atts, *args, **kwargs)


def debugSend(self, *args, **kargs):
    log.info(
        "sending AE {params} {atts}",
        params=self._Event__params,
        atts=self._Event__atts,
    )
    result = originalSend(self, *args, **kargs)
    log.info(
        "response received AE {params} {atts}",
        params=self._Event__params,
        atts=self._Event__atts,
    )
    return result


def install():
    # appscript.reference.Command.__call__ = debugCommandMethod
    aem.aemsend.Event.__init__ = saveParamsAndAtts
    aem.aemsend.Event.send = debugSend
