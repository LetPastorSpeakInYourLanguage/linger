-- Story Understanding Layer (SUL) — the persistent "understanding" of a title that recaps, search,
-- Q&A and linger's recomposition features query. One row per fact, every fact time-anchored.
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS title   (id TEXT PRIMARY KEY, kind TEXT CHECK(kind IN ('film','series')), name TEXT, logline TEXT, genre_tone TEXT, bible_json TEXT);
CREATE TABLE IF NOT EXISTS media   (id TEXT PRIMARY KEY, title_id TEXT REFERENCES title(id), season INT, episode INT, path TEXT,
                                    duration REAL, audio_lang TEXT, sub_lang TEXT DEFAULT 'en', sub_source TEXT, hardsub_lang TEXT);
CREATE TABLE IF NOT EXISTS cue     (media_id TEXT REFERENCES media(id), idx INT, t0 REAL, t1 REAL, text TEXT, sdh TEXT, speaker TEXT,
                                    speaker_conf REAL, voice_cluster TEXT, PRIMARY KEY(media_id, idx));
CREATE TABLE IF NOT EXISTS character (id TEXT PRIMARY KEY, title_id TEXT REFERENCES title(id), name TEXT, aliases TEXT, role TEXT, arc TEXT,
                                    importance REAL, voice_cluster TEXT, face_ref TEXT);
CREATE TABLE IF NOT EXISTS scene   (id TEXT PRIMARY KEY, media_id TEXT REFERENCES media(id), cue0 INT, cue1 INT, t0 REAL, t1 REAL,
                                    setting TEXT, characters TEXT, summary TEXT, visual_notes TEXT, importance REAL);
CREATE TABLE IF NOT EXISTS thread  (id TEXT PRIMARY KEY, title_id TEXT REFERENCES title(id), name TEXT, summary TEXT, importance REAL);
CREATE TABLE IF NOT EXISTS beat    (id TEXT PRIMARY KEY, scene_id TEXT REFERENCES scene(id), media_id TEXT, cue0 INT, cue1 INT, t0 REAL, t1 REAL,
                                    text TEXT, short TEXT, kind TEXT, local_importance INT, global_importance REAL, tier TEXT,
                                    thread_id TEXT, emotion TEXT, emotion_intensity INT, spoiler_level INT, who TEXT);
CREATE TABLE IF NOT EXISTS beat_edge (src TEXT REFERENCES beat(id), dst TEXT REFERENCES beat(id), kind TEXT CHECK(kind IN ('requires','pays_off','callback')),
                                    PRIMARY KEY(src, dst, kind));
CREATE TABLE IF NOT EXISTS moment  (id INTEGER PRIMARY KEY, media_id TEXT, cue0 INT, cue1 INT, t0 REAL, t1 REAL, kind TEXT, what TEXT,
                                    emotion TEXT, intensity INT, av_expressive REAL, av_loudness REAL, still_t REAL);
CREATE TABLE IF NOT EXISTS turning_point (title_id TEXT, media_id TEXT, tp TEXT, beat_id TEXT REFERENCES beat(id));
CREATE TABLE IF NOT EXISTS embedding (owner_kind TEXT, owner_id TEXT, model TEXT, dim INT, vec BLOB, PRIMARY KEY(owner_kind, owner_id, model));
CREATE TABLE IF NOT EXISTS llm_call (task TEXT, media_id TEXT, prompt_sha TEXT, est_tokens INT, model TEXT, created TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(owner_kind, owner_id, text);
CREATE INDEX IF NOT EXISTS beat_tier ON beat(tier, global_importance);
CREATE INDEX IF NOT EXISTS cue_time ON cue(media_id, t0);
