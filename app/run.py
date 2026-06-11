"""Start Recomposer: python run.py  →  prints the URL to share over WiFi."""
import logging
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


class _IgnoreClientDisconnects(logging.Filter):
    """Browsers abort video range-requests constantly (seeking, switching cuts).
    On Windows that surfaces as a noisy-but-harmless ConnectionResetError
    (WinError 10054) from asyncio. Hide it; show everything else."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and record.exc_info[0] is not None:
            if issubclass(record.exc_info[0], (ConnectionResetError, ConnectionAbortedError)):
                return False
        msg = record.getMessage()
        return "ConnectionResetError" not in msg and "WinError 10054" not in msg


for _name in ("asyncio", "uvicorn.error"):
    logging.getLogger(_name).addFilter(_IgnoreClientDisconnects())


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


if __name__ == "__main__":
    import uvicorn

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print()
    print("  Recomposer is starting…")
    print(f"  You:          http://localhost:{port}")
    print(f"  Your brother: http://{lan_ip()}:{port}   (same WiFi)")
    print()
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, log_level="warning")
