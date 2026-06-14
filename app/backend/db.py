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


def _add_columns(conn, table: str, defs: list[str]):
    """ALTER TABLE ADD COLUMN for each definition whose column is missing."""
    have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    for d in defs:
        if d.split()[0] not in have:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {d}")


def _m1_jobs_queue(conn):
    """Job-queue hardening: progress, retries, cooperative cancel, claim leases,
    and a generic target reference (e.g. export → recomposition N)."""
    _add_columns(conn, "jobs", [
        "progress REAL",
        "priority INTEGER NOT NULL DEFAULT 0",
        "attempts INTEGER NOT NULL DEFAULT 0",
        "max_attempts INTEGER NOT NULL DEFAULT 2",
        "cancel_requested INTEGER NOT NULL DEFAULT 0",
        "worker_id TEXT",
        "lease_until TEXT",
        "started_at TEXT",
        "finished_at TEXT",
        "target_kind TEXT",
        "target_id INTEGER",
    ])
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_claim ON jobs(status, priority, id)")


LANGUAGE_DEFAULTS = [
    ("en", "English", "edge", "en-US-JennyNeural"),
    ("es", "Spanish", "edge", "es-ES-ElviraNeural"),
    ("fr", "French", "edge", "fr-FR-DeniseNeural"),
    ("de", "German", "edge", "de-DE-KatjaNeural"),
    ("pt", "Portuguese", "edge", "pt-BR-FranciscaNeural"),
    ("ar", "Arabic", "edge", "ar-SA-ZariyahNeural"),
    ("hi", "Hindi", "edge", "hi-IN-SwaraNeural"),
    ("ja", "Japanese", "edge", "ja-JP-NanamiNeural"),
    ("ko", "Korean", "edge", "ko-KR-SunHiNeural"),
    ("zh", "Chinese", "edge", "zh-CN-XiaoxiaoNeural"),
    ("am", "Amharic", "edge", "am-ET-MekdesNeural"),
]


def _m2_languages(conn):
    """Language registry. A language is dub-capable when a TTS voice is set."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS languages (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            tts_engine TEXT NOT NULL DEFAULT 'edge',
            tts_voice TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )""")
    for code, name, engine, voice in LANGUAGE_DEFAULTS:
        conn.execute(
            "INSERT OR IGNORE INTO languages (code, name, tts_engine, tts_voice) "
            "VALUES (?,?,?,?)",
            (code, name, engine, voice))


# Edge-TTS female/male voices for the seeded languages. Used to give translated
# speech a voice that matches each speaker's inferred gender.
GENDER_VOICE_DEFAULTS = {
    "en": ("en-US-JennyNeural", "en-US-GuyNeural"),
    "es": ("es-ES-ElviraNeural", "es-ES-AlvaroNeural"),
    "fr": ("fr-FR-DeniseNeural", "fr-FR-HenriNeural"),
    "de": ("de-DE-KatjaNeural", "de-DE-ConradNeural"),
    "pt": ("pt-BR-FranciscaNeural", "pt-BR-AntonioNeural"),
    "ar": ("ar-SA-ZariyahNeural", "ar-SA-HamedNeural"),
    "hi": ("hi-IN-SwaraNeural", "hi-IN-MadhurNeural"),
    "ja": ("ja-JP-NanamiNeural", "ja-JP-KeitaNeural"),
    "ko": ("ko-KR-SunHiNeural", "ko-KR-InJoonNeural"),
    "zh": ("zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural"),
    "am": ("am-ET-MekdesNeural", "am-ET-AmehaNeural"),
}


def _m3_translations_dubs(conn):
    """Cut translations, generated dub artifacts, and recomposition audio mode."""
    _add_columns(conn, "tracks", [
        "lang_code TEXT NOT NULL DEFAULT ''",
    ])
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cut_translations (
            id INTEGER PRIMARY KEY,
            cut_id INTEGER NOT NULL REFERENCES cuts(id) ON DELETE CASCADE,
            lang_code TEXT NOT NULL REFERENCES languages(code) ON DELETE RESTRICT,
            source TEXT NOT NULL DEFAULT 'manual',
            created_by INTEGER REFERENCES users(id),
            created_at TEXT DEFAULT (datetime('now'))
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS translation_segments (
            translation_id INTEGER NOT NULL REFERENCES cut_translations(id) ON DELETE CASCADE,
            segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
            text TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (translation_id, segment_id)
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dubs (
            id INTEGER PRIMARY KEY,
            translation_id INTEGER NOT NULL REFERENCES cut_translations(id) ON DELETE CASCADE,
            engine TEXT NOT NULL,
            voice TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            filename TEXT NOT NULL DEFAULT '',
            duration_s REAL,
            word_boundaries_json TEXT DEFAULT '[]',
            detail TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cut_translations_cut ON cut_translations(cut_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dubs_translation ON dubs(translation_id)")
    _add_columns(conn, "recomp_cuts", [
        "audio_mode TEXT NOT NULL DEFAULT 'original'",
        "dub_id INTEGER",
    ])


def _m5_dub_voice_gender(conn):
    """Per-dub gender override: 'auto' infers each line's speaker gender,
    'M'/'F' forces a single voice gender for the whole cut."""
    _add_columns(conn, "dubs", [
        "voice_gender TEXT NOT NULL DEFAULT 'auto'",
    ])


def _m6_background_audio(conn):
    """Background-audio assets + per-recomposition layers. A layer assigns one
    asset to a span of cuts [from_pos..to_pos] and fits it to that span's exact
    length (loop / stretch / trim). Several layers = several beds in sequence."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audio_assets (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            filename TEXT NOT NULL,
            duration_s REAL,
            added_by INTEGER REFERENCES users(id),
            created_at TEXT DEFAULT (datetime('now'))
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recomp_audio_layers (
            id INTEGER PRIMARY KEY,
            recomp_id INTEGER NOT NULL REFERENCES recompositions(id) ON DELETE CASCADE,
            asset_id INTEGER NOT NULL REFERENCES audio_assets(id) ON DELETE CASCADE,
            from_pos INTEGER NOT NULL DEFAULT 0,
            to_pos INTEGER NOT NULL DEFAULT 0,
            gain REAL NOT NULL DEFAULT 1.0,
            fit TEXT NOT NULL DEFAULT 'loop',
            ord INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audio_layers_recomp "
                 "ON recomp_audio_layers(recomp_id)")


def _m10_relinkable_media(conn):
    """Decouple media records from local files: a sha256 of the source so any
    copy can be verified, plus recorded source locations on this instance."""
    _add_columns(conn, "media", ["content_hash TEXT"])
    conn.execute("""
        CREATE TABLE IF NOT EXISTS media_sources (
            id INTEGER PRIMARY KEY,
            media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
            kind TEXT NOT NULL DEFAULT 'local',   -- local | url
            locator TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ok',
            priority INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_media_sources_media "
                 "ON media_sources(media_id)")


def _m9_segment_embeddings(conn):
    """Vector store for semantic search — one float32 BLOB per segment."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS segment_embeddings (
            segment_id INTEGER PRIMARY KEY REFERENCES segments(id) ON DELETE CASCADE,
            media_id INTEGER,
            text_hash TEXT,
            dim INTEGER,
            vec BLOB,
            model TEXT
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_seg_emb_media "
                 "ON segment_embeddings(media_id)")


def _m8_overlay_tracks(conn):
    """Styled text-overlay tracks burned onto a recomposition's export. Events
    are derived at render time from the cuts (source subtitle text or a
    translation), anchored to the shared timeline so reordering never desyncs."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS overlay_tracks (
            id INTEGER PRIMARY KEY,
            recomp_id INTEGER NOT NULL REFERENCES recompositions(id) ON DELETE CASCADE,
            name TEXT NOT NULL DEFAULT 'Captions',
            source TEXT NOT NULL DEFAULT 'subtitles',  -- subtitles | translation
            lang_code TEXT NOT NULL DEFAULT '',
            style_json TEXT NOT NULL DEFAULT '{}',
            enabled INTEGER NOT NULL DEFAULT 1,
            ord INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_overlay_tracks_recomp "
                 "ON overlay_tracks(recomp_id)")


def _m7_audio_asset_structure(conn):
    """Per-bed tweaking structure: trim the usable region, a clean loop region,
    fades, and default gain/fit — set once in the Audio studio, reused by every
    recomposition layer."""
    _add_columns(conn, "audio_assets", [
        "trim_start_s REAL NOT NULL DEFAULT 0",
        "trim_end_s REAL",
        "loop_start_s REAL",
        "loop_end_s REAL",
        "fade_in_s REAL NOT NULL DEFAULT 0",
        "fade_out_s REAL NOT NULL DEFAULT 0",
        "default_gain REAL NOT NULL DEFAULT 1.0",
        "default_fit TEXT NOT NULL DEFAULT 'loop'",
    ])


def _m4_gender_voices(conn):
    """Per-gender TTS voices + per-segment inferred speaker gender, so a dub
    can use a male or female voice that matches each line's speaker."""
    _add_columns(conn, "languages", [
        "tts_voice_female TEXT NOT NULL DEFAULT ''",
        "tts_voice_male TEXT NOT NULL DEFAULT ''",
    ])
    # gender: 'M' | 'F' | NULL (unknown). source: 'auto' | 'manual'.
    _add_columns(conn, "segments", [
        "gender TEXT",
        "gender_source TEXT",
    ])
    for code, (female, male) in GENDER_VOICE_DEFAULTS.items():
        conn.execute(
            "UPDATE languages SET tts_voice_female=? "
            "WHERE code=? AND tts_voice_female=''", (female, code))
        conn.execute(
            "UPDATE languages SET tts_voice_male=? "
            "WHERE code=? AND tts_voice_male=''", (male, code))


# Ordered, run-once migrations tracked via PRAGMA user_version. Append only —
# never reorder or edit a shipped migration.
MIGRATIONS = [
    _m1_jobs_queue,
    _m2_languages,
    _m3_translations_dubs,
    _m4_gender_voices,
    _m5_dub_voice_gender,
    _m6_background_audio,
    _m7_audio_asset_structure,
    _m8_overlay_tracks,
    _m9_segment_embeddings,
    _m10_relinkable_media,
]


def _migrate(conn):
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for i, migration in enumerate(MIGRATIONS, start=1):
        if version < i:
            migration(conn)
            conn.execute(f"PRAGMA user_version={i}")
            conn.commit()


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
    _migrate(conn)


def rows_to_dicts(rows):
    return [dict(r) for r in rows]
