"""SQLite layer: schema, connection helpers, FTS5 search index."""
import os
import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(os.environ.get(
    "RECOMPOSER_DB",
    Path(__file__).resolve().parent.parent / "recomposer.db"))

_local = threading.local()

SCHEMA = """
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#6366f1'
);

CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('video','audio')),
    filename TEXT NOT NULL,
    duration REAL,
    status TEXT NOT NULL DEFAULT 'uploaded',
    status_detail TEXT,
    added_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY,
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'Subtitles',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tracks_media ON tracks(media_id);

CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY,
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    track_id INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    start_s REAL NOT NULL,
    end_s REAL NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_segments_media ON segments(media_id, idx);
-- idx_segments_track is created in init_db, after the track_id migration

CREATE TABLE IF NOT EXISTS folders (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES folders(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cuts (
    id INTEGER PRIMARY KEY,
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    note TEXT DEFAULT '',
    folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cut_segments (
    cut_id INTEGER NOT NULL REFERENCES cuts(id) ON DELETE CASCADE,
    segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (cut_id, position)
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS cut_tags (
    cut_id INTEGER NOT NULL REFERENCES cuts(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (cut_id, tag_id)
);

CREATE TABLE IF NOT EXISTS recompositions (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recomp_cuts (
    recomp_id INTEGER NOT NULL REFERENCES recompositions(id) ON DELETE CASCADE,
    cut_id INTEGER NOT NULL REFERENCES cuts(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (recomp_id, position)
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    media_id INTEGER REFERENCES media(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued',
    detail TEXT DEFAULT '',
    payload TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
    text, content='segments', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS segments_ai AFTER INSERT ON segments BEGIN
    INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS segments_ad AFTER DELETE ON segments BEGIN
    INSERT INTO segments_fts(segments_fts, rowid, text) VALUES('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS segments_au AFTER UPDATE ON segments BEGIN
    INSERT INTO segments_fts(segments_fts, rowid, text) VALUES('delete', old.id, old.text);
    INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
END;
"""

# Trigram index for fuzzy (typo-tolerant) search. Needs SQLite >= 3.34;
# created separately so older builds degrade gracefully to exact-only search.
TRI_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS segments_tri USING fts5(
    text, content='segments', content_rowid='id', tokenize='trigram'
);
CREATE TRIGGER IF NOT EXISTS segments_tri_ai AFTER INSERT ON segments BEGIN
    INSERT INTO segments_tri(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS segments_tri_ad AFTER DELETE ON segments BEGIN
    INSERT INTO segments_tri(segments_tri, rowid, text) VALUES('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS segments_tri_au AFTER UPDATE ON segments BEGIN
    INSERT INTO segments_tri(segments_tri, rowid, text) VALUES('delete', old.id, old.text);
    INSERT INTO segments_tri(rowid, text) VALUES (new.id, new.text);
END;
"""

HAS_TRIGRAM = False


def get_db() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:  # WAL is faster but unsupported on some mounted filesystems
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        _local.conn = conn
    return conn


def init_db():
    global HAS_TRIGRAM
    conn = get_db()
    tri_existed = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='segments_tri'").fetchone() is not None
    conn.executescript(SCHEMA)
    # migrations for databases created by older versions
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN payload TEXT DEFAULT '{}'")
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        conn.execute("ALTER TABLE segments ADD COLUMN track_id INTEGER "
                     "REFERENCES tracks(id) ON DELETE CASCADE")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.execute("CREATE INDEX IF NOT EXISTS idx_segments_track ON segments(track_id, idx)")
    # adopt pre-tracks segments into one 'Original' track per media
    for row in conn.execute(
            "SELECT DISTINCT media_id FROM segments WHERE track_id IS NULL").fetchall():
        cur = conn.execute("INSERT INTO tracks (media_id, name) VALUES (?, 'Original')",
                           (row[0],))
        conn.execute("UPDATE segments SET track_id=? WHERE media_id=? AND track_id IS NULL",
                     (cur.lastrowid, row[0]))
    try:
        conn.executescript(TRI_SCHEMA)
        if not tri_existed:  # index pre-existing segments once
            conn.execute("INSERT INTO segments_tri(segments_tri) VALUES('rebuild')")
        HAS_TRIGRAM = True
    except sqlite3.OperationalError:
        HAS_TRIGRAM = False  # old SQLite without trigram tokenizer: exact-only search
    conn.commit()


def rows_to_dicts(rows):
    return [dict(r) for r in rows]
