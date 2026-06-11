"""Segment search engine.

Two layers, designed to stay fast at millions of segments:

1. EXACT  — FTS5 (bm25-ranked): phrase-prefix match, then AND-of-word-prefixes.
   Pure index lookups, no table scans.
2. FUZZY  — typo tolerance. The query is split into character trigrams and OR-ed
   against a trigram FTS5 index (same trick as Postgres pg_trgm): segments that
   share many trigrams with the query bubble up via bm25. Only that small
   candidate set (a few hundred rows) is then re-ranked in Python with
   word-level similarity (difflib), so "amaizng" finds "amazing".

Both run on indexes; the expensive scoring only ever touches candidates.
"""
import re
from difflib import SequenceMatcher

from . import db as dbmod
from .db import get_db, rows_to_dicts

WORD_RE = re.compile(r"\w+", re.UNICODE)

FUZZY_CANDIDATES = 400   # rows pulled from the trigram index for re-ranking
FUZZY_THRESHOLD = 0.6    # min avg word-similarity to count as a match
MAX_TRIGRAMS = 48        # cap the OR-query size for long queries


def _words(s: str) -> list[str]:
    return WORD_RE.findall(s.lower())


def _phrase_prefix(q: str) -> str:
    return '"' + q.replace('"', '""') + '"*'


def _and_words(words: list[str]) -> str:
    return " AND ".join('"' + w.replace('"', '""') + '"*' for w in words)


def _trigram_query(q: str) -> str | None:
    s = " ".join(_words(q))  # normalized: lowercase, single spaces
    tris = {s[i:i + 3] for i in range(len(s) - 2)}
    tris = {t for t in tris if t.strip() == t or " " not in t}
    if not tris:
        return None
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in list(tris)[:MAX_TRIGRAMS])


def _word_similarity(qw: str, w: str) -> float:
    if qw == w:
        return 1.0
    if abs(len(qw) - len(w)) > max(2, len(qw) // 2):
        return 0.0
    return SequenceMatcher(None, qw, w).ratio()


def _score(query_words: list[str], text: str) -> float:
    """Average best-match similarity of each query word against the text's words."""
    words = _words(text)
    if not words or not query_words:
        return 0.0
    total = 0.0
    for qw in query_words:
        best = 0.0
        for w in words:
            r = _word_similarity(qw, w)
            if r > best:
                best = r
                if best > 0.99:
                    break
        total += best
    return total / len(query_words)


BASE_SQL = """SELECT s.*, m.title AS media_title, m.type AS media_type
              FROM {fts} f JOIN segments s ON s.id = f.rowid
              JOIN media m ON m.id = s.media_id
              WHERE {fts} MATCH ?"""


def _fts(db, fts_table: str, match: str, media_id, limit: int):
    sql = BASE_SQL.format(fts=fts_table)
    params: list = [match]
    if media_id is not None:
        sql += " AND s.media_id = ?"
        params.append(media_id)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    try:
        return rows_to_dicts(db.execute(sql, params))
    except Exception:
        return []  # malformed FTS query etc. — never break the endpoint


def search_segments(q: str, media_id: int | None = None,
                    limit: int = 60, fuzzy: bool = True) -> list[dict]:
    db = get_db()
    q = q.strip()
    if not q:
        return []
    limit = min(max(limit, 1), 200)
    qwords = _words(q)

    out, seen = [], set()

    def take(rows, match_kind, score=None):
        for r in rows:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            r["match"] = match_kind
            r["score"] = round(score if score is not None else 1.0, 3)
            out.append(r)

    # 1) exact phrase (with prefix on the last word)
    take(_fts(db, "segments_fts", _phrase_prefix(q), media_id, limit), "exact")

    # 2) all words present (any order)
    if len(out) < limit and len(qwords) > 1:
        take(_fts(db, "segments_fts", _and_words(qwords), media_id, limit), "exact")

    # 3) fuzzy via trigram candidates + word-level re-rank
    if fuzzy and len(out) < limit and getattr(dbmod, "HAS_TRIGRAM", False):
        tq = _trigram_query(q)
        if tq:
            cands = _fts(db, "segments_tri", tq, media_id, FUZZY_CANDIDATES)
            scored = []
            for r in cands:
                if r["id"] in seen:
                    continue
                s = _score(qwords, r["text"])
                if s >= FUZZY_THRESHOLD:
                    scored.append((s, r))
            scored.sort(key=lambda x: -x[0])
            for s, r in scored[: limit - len(out)]:
                take([r], "fuzzy", s)

    return out[:limit]
