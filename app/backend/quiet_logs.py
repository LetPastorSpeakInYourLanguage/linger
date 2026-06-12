"""Hide harmless client-disconnect noise from the logs.

Browsers abort video range-requests constantly (seeking, switching cuts).
On Windows that surfaces as ConnectionResetError (WinError 10054) from
asyncio's proactor transport — on Python 3.11+ sometimes wrapped inside a
BaseExceptionGroup by anyio, which a plain isinstance filter misses.
"""
import logging

_installed = False


def _is_disconnect(exc) -> bool:
    if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return all(_is_disconnect(e) for e in exc.exceptions)
    return False


class IgnoreClientDisconnects(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and record.exc_info[1] is not None:
            if _is_disconnect(record.exc_info[1]):
                return False
        msg = record.getMessage()
        return "ConnectionResetError" not in msg and "WinError 10054" not in msg


def install():
    global _installed
    if _installed:
        return
    _installed = True
    for name in ("asyncio", "uvicorn.error"):
        logging.getLogger(name).addFilter(IgnoreClientDisconnects())
