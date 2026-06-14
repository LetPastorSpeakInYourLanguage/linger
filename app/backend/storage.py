"""Where a media's bytes live. Today everything streams from media_store; this
indirection is the seam for relinkable / remote (Drive) sources later.
"""
from __future__ import annotations

from pathlib import Path

from . import media_ops
from .db import get_db


def local_file(media_id: int) -> Path | None:
    """The playable file in media_store, or None if this instance lacks it."""
    row = get_db().execute("SELECT filename FROM media WHERE id=?", (media_id,)).fetchone()
    if row and row["filename"]:
        p = media_ops.media_dir(media_id) / row["filename"]
        if p.exists():
            return p
    return None


def is_linked(media_id: int) -> bool:
    return local_file(media_id) is not None
