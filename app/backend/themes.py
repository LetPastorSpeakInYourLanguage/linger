"""Cross-reference theme clustering — group cuts that are about the same thing.

The "sequence of sequences" layer from the owner's notebook vision: after the
transcript is sliced into cuts (topic spans), some cuts are semantically related
even though they sit far apart in time — the speaker returns to a theme at the
start, middle and end. This finds those links.

Mechanism (no LLM): embed each cut as the mean of its member-segment vectors,
build a cosine kNN graph (an edge when two cuts are similar enough, capped per
node), and run **Louvain community detection**. Each community is a theme. Like
segmentation it's deterministic and cheap to re-run on cached vectors, so the
thresholds can be live-tuned, and re-running with different params surfaces
links a tighter pass missed.

`networkx` ships Louvain (`networkx.community.louvain_communities`), so this adds
no clustering dependency beyond networkx itself.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass

import numpy as np

from . import vectors


@dataclass(frozen=True)
class ThemeConfig:
    """Tunable knobs for one clustering pass."""
    name: str = "balanced"
    similarity_threshold: float = 0.55  # min cosine for two cuts to be linked
    max_edges_per_cut: int = 8          # keep only a cut's strongest links
    min_cluster_size: int = 2           # drop singleton "themes"
    resolution: float = 1.0             # Louvain: >1 → more, smaller communities
    seed: int = 13

    def to_dict(self) -> dict:
        return asdict(self)


PRESETS: dict[str, ThemeConfig] = {
    "loose": ThemeConfig(name="loose", similarity_threshold=0.42, max_edges_per_cut=12,
                         resolution=0.8),
    "balanced": ThemeConfig(),
    "tight": ThemeConfig(name="tight", similarity_threshold=0.68, max_edges_per_cut=6,
                        resolution=1.3),
}

PARAM_BOUNDS = {
    "similarity_threshold": (0.0, 0.95),
    "max_edges_per_cut": (1, 40),
    "min_cluster_size": (2, 20),
    "resolution": (0.1, 4.0),
}


def config_from(preset: str | None = None, overrides: dict | None = None) -> ThemeConfig:
    base = PRESETS.get((preset or "balanced"), PRESETS["balanced"])
    if not overrides:
        return base
    values = base.to_dict()
    values["name"] = "custom"
    for key, (lo, hi) in PARAM_BOUNDS.items():
        if key not in overrides or overrides[key] is None:
            continue
        caster = float if isinstance(lo, float) else int
        try:
            values[key] = min(hi, max(lo, caster(overrides[key])))
        except (TypeError, ValueError):
            continue
    return ThemeConfig(**values)


_STOP = set("the a an and or but of to in on at for with from by as is are was were be been "
            "this that it its they them we you i he she his her our your their not no so if "
            "do does did has have had will would can could about into over out up down".split())


def _label(titles_text: str) -> str:
    words = [w for w in re.findall(r"[a-z']+", titles_text.lower())
             if len(w) > 2 and w not in _STOP]
    top = [w for w, _ in Counter(words).most_common(3)]
    return " · ".join(top) if top else "Theme"


def cut_ids_for_scope(db, media_ids: list[int] | None, cut_ids: list[int] | None) -> list[int]:
    """Resolve which cuts to cluster: an explicit list, all cuts of some media,
    or (default) every cut in the library."""
    if cut_ids:
        return [int(c) for c in cut_ids]
    if media_ids:
        qm = ",".join("?" * len(media_ids))
        rows = db.execute(f"SELECT id FROM cuts WHERE media_id IN ({qm}) ORDER BY id",
                          list(media_ids)).fetchall()
    else:
        rows = db.execute("SELECT id FROM cuts ORDER BY id").fetchall()
    return [r["id"] for r in rows]


def _cut_vectors(db, cut_ids: list[int]) -> tuple[list[dict], np.ndarray]:
    """(cut metadata, normalized cut-embedding matrix) for cuts that have at
    least one embedded segment. Cuts with no vectors are silently skipped."""
    cuts, mats = [], []
    for cid in cut_ids:
        seg_ids = [r["segment_id"] for r in db.execute(
            "SELECT segment_id FROM cut_segments WHERE cut_id=?", (cid,))]
        vec = vectors.mean_vector(seg_ids)
        if vec is None:
            continue
        row = db.execute("SELECT id, title FROM cuts WHERE id=?", (cid,)).fetchone()
        if not row:
            continue
        text = " ".join(r["text"] for r in db.execute(
            "SELECT s.text FROM cut_segments cs JOIN segments s ON s.id=cs.segment_id "
            "WHERE cs.cut_id=? ORDER BY cs.position", (cid,)))
        cuts.append({"cut_id": int(row["id"]), "title": row["title"], "text": text})
        mats.append(np.asarray(vec, dtype="float32"))
    if not mats:
        return [], np.zeros((0, 0), dtype="float32")
    m = np.vstack(mats)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return cuts, m / norms


def cluster(db, scope_cut_ids: list[int], cfg: ThemeConfig) -> dict:
    """Run one clustering pass and return themes (no DB writes).

    Each theme lists its member cuts ordered most-representative-first (closest
    to the theme centroid). Raises if networkx isn't installed."""
    try:
        import networkx as nx
    except ImportError as e:
        raise RuntimeError("networkx is not installed — needed for theme clustering") from e

    cuts, matrix = _cut_vectors(db, scope_cut_ids)
    result = {"params": cfg.to_dict(), "param_bounds": PARAM_BOUNDS,
              "presets": list(PRESETS), "considered": len(cuts), "clusters": []}
    if len(cuts) < cfg.min_cluster_size:
        return result

    sims = matrix @ matrix.T
    graph = nx.Graph()
    graph.add_nodes_from(range(len(cuts)))
    for i in range(len(cuts)):
        cand = [(j, float(sims[i, j])) for j in range(len(cuts))
                if j != i and float(sims[i, j]) >= cfg.similarity_threshold]
        cand.sort(key=lambda it: it[1], reverse=True)
        for j, w in cand[:cfg.max_edges_per_cut]:
            graph.add_edge(i, j, weight=w)

    if graph.number_of_edges() == 0:
        return result

    communities = nx.community.louvain_communities(
        graph, weight="weight", resolution=cfg.resolution, seed=cfg.seed)

    clusters = []
    for comm in communities:
        idxs = sorted(comm)
        if len(idxs) < cfg.min_cluster_size:
            continue
        centroid = matrix[idxs].mean(axis=0)
        # most-representative-first within the theme
        idxs.sort(key=lambda k: -float(matrix[k] @ centroid))
        members = [cuts[k] for k in idxs]
        clusters.append({
            "name": _label(" ".join(m["title"] + " " + m["text"][:120] for m in members)),
            "size": len(members),
            "cut_ids": [m["cut_id"] for m in members],
            "members": [{"cut_id": m["cut_id"], "title": m["title"],
                         "preview": m["text"][:160]} for m in members],
        })
    clusters.sort(key=lambda c: -c["size"])
    result["clusters"] = clusters
    return result


def commit(db, clusters: list[dict], params: dict | None = None, replace: bool = False) -> dict:
    """Persist reviewed theme clusters into `cut_clusters` / `cluster_cuts`."""
    import json
    if replace:
        db.execute("DELETE FROM cut_clusters")
    created = []
    for spec in clusters or []:
        cut_ids = [int(c) for c in (spec.get("cut_ids") or []) if c is not None]
        if not cut_ids:
            continue
        name = (spec.get("name") or "Theme").strip()[:80] or "Theme"
        cid = db.execute(
            "INSERT INTO cut_clusters (name, params_json) VALUES (?,?)",
            (name, json.dumps(params or {}))).lastrowid
        for rank, cut_id in enumerate(cut_ids):
            db.execute(
                "INSERT OR IGNORE INTO cluster_cuts (cluster_id, cut_id, rank) VALUES (?,?,?)",
                (cid, cut_id, rank))
        created.append({"cluster_id": cid, "name": name, "size": len(cut_ids)})
    db.commit()
    return {"created": len(created), "clusters": created}


def list_clusters(db) -> list[dict]:
    out = []
    for c in db.execute("SELECT * FROM cut_clusters ORDER BY id DESC").fetchall():
        members = db.execute(
            "SELECT cc.cut_id, cu.title FROM cluster_cuts cc "
            "JOIN cuts cu ON cu.id=cc.cut_id WHERE cc.cluster_id=? ORDER BY cc.rank",
            (c["id"],)).fetchall()
        out.append({"id": c["id"], "name": c["name"], "created_at": c["created_at"],
                    "size": len(members),
                    "members": [{"cut_id": m["cut_id"], "title": m["title"]} for m in members]})
    return out
