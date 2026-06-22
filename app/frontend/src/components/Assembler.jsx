/* The Assembler — the recomposition powerhouse. Build many recompositions at
 * once by meaning & theme over a filtered cut library.
 *
 *   • LEFT  — Scope dashboard (filter + folder/tag/media breakdowns + utilisation
 *             + sample previews) and a Created-recompositions tab.
 *   • CENTRE— theme-first: clusters auto-load; a rank-by-meaning search bar sits
 *             on top and expands a scroll-locked result list. Click a theme to
 *             open it as a draft.
 *   • RIGHT — multiple persisted drafts (switchable tabs), inplace title, per-draft
 *             undo/redo, save, finalize (no reroute), PiP player, and a resizable
 *             ✨ recommendations strip in the bottom third.
 */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, fmtTime, streamUrl } from "../api";
import { Modal, Slider, Spinner, inputCls, btnCls, btnGhost, DragBar, modalOpen } from "./ui";
import { EMPTY_FILTERS, filtersToParams, FilterBar } from "./CutBrowser";
import ForgeCutModal from "./ForgeCutModal";

const TKNOBS = [
  { key: "similarity_threshold", label: "Link threshold", step: 0.01, hint: "higher = tighter", fmt: (v) => v.toFixed(2) },
  { key: "resolution", label: "Granularity", step: 0.05, hint: "higher = more themes", fmt: (v) => v.toFixed(2) },
  { key: "max_edges_per_cut", label: "Links / cut", step: 1, fmt: (v) => `${v}` },
  { key: "min_cluster_size", label: "Min size", step: 1, fmt: (v) => `${v}` },
];
// Default ceiling for the O(n²) theme graph / rank pass. The user can raise or
// lower it (trading thoroughness for speed) from the header.
const DEFAULT_CAP = 2000;
const CAP_CHOICES = [200, 500, 1000, 2000, 4000, 8000];

function Bar({ score }) {
  const pct = Math.max(0, Math.min(100, Math.round((score || 0) * 100)));
  return (
    <span className="w-8 h-1.5 rounded-full bg-zinc-700 overflow-hidden shrink-0" title={`${pct}% similar`}>
      <span className="block h-full rounded-full bg-indigo-500" style={{ width: `${pct}%` }} />
    </span>
  );
}

export default function Assembler({ user, openStudio }) {
  const [cache, setCache] = useState({});
  const mergeCache = useCallback((list) => setCache((c) => {
    const n = { ...c }; list.forEach((x) => { const id = x.cut_id ?? x.id; n[id] = { ...n[id], ...x, id }; }); return n;
  }), []);
  const cut = (id) => cache[id];

  /* ============================ LEFT: scope ============================ */
  const [leftTab, setLeftTab] = useState("scope");
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [tags, setTags] = useState([]);
  const [folders, setFolders] = useState([]);
  const [media, setMedia] = useState([]);
  const [scope, setScope] = useState(null);
  const [samples, setSamples] = useState([]);
  const [sampleN, setSampleN] = useState(6);
  const [previewCut, setPreviewCut] = useState(null);
  const [created, setCreated] = useState([]);
  const scopeDeb = useRef();

  useEffect(() => {
    api.get("/api/tags").then(setTags).catch(() => {});
    api.get("/api/folders").then(setFolders).catch(() => {});
    api.get("/api/media").then((m) => setMedia(m.filter((x) => x.status === "ready"))).catch(() => {});
  }, []);

  const scopeBody = useMemo(() => {
    const p = filtersToParams(filters);
    return { q: p.get("q") || "", folder_ids: p.get("folder_ids") || "",
             media_ids: p.get("media_ids") || "", tags: p.get("tags") || "" };
  }, [filters]);

  const loadScope = useCallback(() => {
    api.post("/api/assembler/scope", scopeBody).then(setScope).catch(() => {});
    api.post(`/api/assembler/sample?n=${sampleN}`, scopeBody)
      .then((s) => { setSamples(s); mergeCache(s); }).catch(() => {});
  }, [scopeBody, sampleN, mergeCache]);
  useEffect(() => {
    clearTimeout(scopeDeb.current);
    scopeDeb.current = setTimeout(loadScope, 250);
    return () => clearTimeout(scopeDeb.current);
  }, [loadScope]);

  const loadCreated = useCallback(() => {
    api.get("/api/recompositions?status=final").then(setCreated).catch(() => {});
  }, []);
  useEffect(loadCreated, [loadCreated]);

  const scopeIds = scope?.cut_ids || [];

  /* ============================ CENTRE: discovery ============================ */
  // rank-by-meaning search bar
  const [query, setQuery] = useState("");
  const [ranked, setRanked] = useState(null);
  const [rankOpen, setRankOpen] = useState(true);
  const [rankBusy, setRankBusy] = useState(false);
  const runRank = async () => {
    if (!query.trim() || !scopeIds.length) return;
    setRankBusy(true); setRankOpen(true);
    try {
      const r = await api.post("/api/cuts/rank", { prompt: query.trim(), cut_ids: scopeIds.slice(0, cap), limit: cap });
      setRanked(r.ranked); mergeCache(r.ranked);
    } catch (e) { alert(e.message); }
    setRankBusy(false);
  };

  // theme clustering (auto-loads)
  const [tparams, setTparams] = useState(null);
  const [tbounds, setTbounds] = useState(null);
  const [tpreset, setTpreset] = useState("balanced");
  const [clusters, setClusters] = useState(null);
  const [clusterBusy, setClusterBusy] = useState(false);
  const [openClusters, setOpenClusters] = useState(new Set());
  const cSeq = useRef(0);
  const [cap, setCap] = useState(() => Number(localStorage.getItem("asm_cap")) || DEFAULT_CAP);
  const setCapPersist = (n) => { setCap(n); localStorage.setItem("asm_cap", String(n)); };
  const clusterCap = useMemo(() => scopeIds.slice(0, cap), [scopeIds, cap]);
  const runCluster = useCallback(async (preset, overrides) => {
    if (!clusterCap.length) { setClusters([]); return; }
    const seq = ++cSeq.current; setClusterBusy(true);
    try {
      const r = await api.post("/api/clusters/preview",
        { cut_ids: clusterCap, preset, params: overrides || null });
      if (seq !== cSeq.current) return;
      setTparams(r.params); setTbounds(r.param_bounds); setClusters(r.clusters);
      r.clusters.forEach((cl) => mergeCache(cl.members));
    } catch (e) { if (seq === cSeq.current) alert(e.message); }
    finally { if (seq === cSeq.current) setClusterBusy(false); }
  }, [clusterCap, mergeCache]);

  // auto-cluster whenever the scope changes (theme-first: invite into work)
  const lastClustered = useRef("");
  useEffect(() => {
    const key = clusterCap.join(",");
    if (clusterCap.length && key !== lastClustered.current) {
      lastClustered.current = key;
      runCluster(tpreset === "custom" ? "balanced" : tpreset, null);
    }
  }, [clusterCap, runCluster, tpreset]);

  const tDeb = useRef();
  const setTKnob = (key, val) => {
    const next = { ...tparams, [key]: val, name: "custom" };
    setTparams(next); setTpreset("custom");
    clearTimeout(tDeb.current);
    const ov = {}; TKNOBS.forEach((k) => { ov[k.key] = next[k.key]; });
    tDeb.current = setTimeout(() => runCluster("balanced", ov), 300);
  };

  /* ============================ RIGHT: multi-draft ============================ */
  const [drafts, setDrafts] = useState([]);
  const [d, setD] = useState(null);   // active: {id, title, status, cutIds, dirty, hist, future}
  const loadDrafts = useCallback(() => {
    api.get("/api/recompositions?status=draft").then(setDrafts).catch(() => {});
  }, []);
  useEffect(loadDrafts, [loadDrafts]);

  const openRecomp = async (id) => {
    const r = await api.get(`/api/recompositions/${id}`);
    mergeCache(r.cuts);
    setD({ id, title: r.title, status: r.status, cutIds: r.cuts.map((c) => c.id),
           dirty: false, hist: [], future: [] });
  };
  const newDraft = async (title = "Untitled draft", cutIds = []) => {
    const r = await api.post("/api/recompositions",
      { title, user_id: user.id, status: "draft", cut_ids: cutIds });
    loadDrafts(); await openRecomp(r.id);
  };
  const editIds = (fn) => setD((s) => s && ({
    ...s, hist: [...s.hist, s.cutIds], future: [], cutIds: fn(s.cutIds), dirty: true }));
  const addToDraft = (ids) => editIds((cur) => [...cur, ...ids.filter((x) => !cur.includes(x))]);
  const removeFromDraft = (id) => editIds((cur) => cur.filter((x) => x !== id));
  const moveDraft = (from, to) => { if (to < 0 || !d || to >= d.cutIds.length) return;
    editIds((cur) => { const n = cur.slice(); const [x] = n.splice(from, 1); n.splice(to, 0, x); return n; }); };
  const undo = () => setD((s) => (!s || !s.hist.length) ? s : ({
    ...s, future: [s.cutIds, ...s.future], cutIds: s.hist[s.hist.length - 1], hist: s.hist.slice(0, -1), dirty: true }));
  const redo = () => setD((s) => (!s || !s.future.length) ? s : ({
    ...s, hist: [...s.hist, s.cutIds], cutIds: s.future[0], future: s.future.slice(1), dirty: true }));
  const renameDraft = (title) => setD((s) => s && ({ ...s, title, dirty: true }));

  const saveDraft = async () => {
    if (!d) return;
    await api.put(`/api/recompositions/${d.id}/cuts`, { cut_ids: d.cutIds });
    await api.patch(`/api/recompositions/${d.id}`, { title: d.title });
    setD((s) => s && ({ ...s, dirty: false }));
    loadDrafts(); loadCreated();
  };
  const finalize = async () => {
    if (!d) return;
    await saveDraft();
    await api.patch(`/api/recompositions/${d.id}`, { status: "final" });
    setD(null); loadDrafts(); loadCreated();
  };
  const deleteDraft = async (id) => {
    if (!confirm("Delete this draft?")) return;
    await api.del(`/api/recompositions/${id}`);
    if (d?.id === id) setD(null);
    loadDrafts();
  };
  const switchTo = async (id) => { if (d?.dirty) await saveDraft(); openRecomp(id); };

  /* recommendations (seed = active draft) — its own panel, count-adjustable */
  const [recs, setRecs] = useState([]);
  const [recsN, setRecsN] = useState(() => Number(localStorage.getItem("asm_recsN")) || 15);
  const setRecsNPersist = (n) => { setRecsN(n); localStorage.setItem("asm_recsN", String(n)); };
  const [recsBusy, setRecsBusy] = useState(false);
  const recDeb = useRef();
  const loadRecs = useCallback(() => {
    const seeds = d?.cutIds || [];
    if (!seeds.length || !scopeIds.length) { setRecs([]); return; }
    setRecsBusy(true);
    api.post("/api/cuts/similar", { seed_cut_ids: seeds, cut_ids: scopeIds, exclude: seeds, limit: recsN })
      .then((r) => { setRecs(r.ranked); mergeCache(r.ranked); })
      .catch(() => setRecs([])).finally(() => setRecsBusy(false));
  }, [d?.cutIds, scopeIds, recsN, mergeCache]);
  useEffect(() => {
    clearTimeout(recDeb.current);
    recDeb.current = setTimeout(loadRecs, 400);
    return () => clearTimeout(recDeb.current);
  }, [loadRecs]);

  /* ===================== preview player (detachable) ===================== */
  const playerRef = useRef();
  const stopAt = useRef(null);
  const queue = useRef([]);
  const pendingResume = useRef(null);   // carry playback across dock/detach remounts
  const [nowId, setNowId] = useState(null);
  const [playing, setPlaying] = useState(false);
  const playOne = (c) => {
    const p = playerRef.current; if (!p || !c || c.media_id == null) return;
    setNowId(c.id ?? c.cut_id); stopAt.current = c.end_s;
    const go = () => { try { p.currentTime = c.start_s; p.play().catch(() => {}); } catch { /* ignore */ } };
    if (String(c.media_id) !== p.dataset.media) { p.dataset.media = String(c.media_id); p.src = streamUrl(c.media_id); p.onloadedmetadata = go; }
    else go();
  };
  const onTime = () => {
    const p = playerRef.current; if (!p || stopAt.current == null) return;
    if (p.currentTime >= stopAt.current) { if (queue.current.length) playOne(queue.current.shift());
      else { p.pause(); stopAt.current = null; setNowId(null); } }
  };
  const playCut = (c) => { queue.current = []; playOne(c); };
  const playSeq = (ids) => { const cs = ids.map(cut).filter(Boolean); if (!cs.length) return; queue.current = cs.slice(1); playOne(cs[0]); };
  const stopPlay = () => { const p = playerRef.current; if (p) p.pause(); stopAt.current = null; queue.current = []; setNowId(null); };

  /* retitle a cut everywhere (cache-driven) */
  const setCutTitle = (id, title) => setCache((c) => ({ ...c, [id]: { ...c[id], title } }));
  const saveCutTitle = (id) => { const c = cache[id]; if (c) api.patch(`/api/cuts/${id}`, { title: c.title }).catch(() => {}); };

  /* lazy segment expansion */
  const [openCuts, setOpenCuts] = useState(new Set());
  const toggleSegs = async (id) => {
    setOpenCuts((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
    if (!cache[id]?.segments) { try { const full = await api.get(`/api/cuts/${id}`); mergeCache([full]); } catch { /* ignore */ } }
  };

  /* ===== fully dynamic 2-D layout: five independent panels (scope · themes ·
     player · drafts · recommendations) arranged in COLUMNS (horizontal), each a
     vertical STACK. Every panel can be shown/hidden, reordered (◀ ▶ across
     columns, ▲ ▼ within a column — that's the vertical split), and resized; the
     player can detach into a floating window (our own picture-in-picture). ===== */
  const PANELS = ["scope", "discovery", "player", "drafts", "recs"];
  const PANEL_TITLE = { scope: "Scope", discovery: "Themes & search", player: "Player", drafts: "Drafts", recs: "Recommendations" };
  const PANEL_DEFW = { scope: 280, discovery: 460, player: 340, drafts: 340, recs: 320 };
  const DEF_COLUMNS = [["scope"], ["discovery"], ["player"], ["drafts", "recs"]];
  const PANEL_DEFH = 260;

  const [widths, setWidths] = useState(() => { try { return { ...PANEL_DEFW, ...JSON.parse(localStorage.getItem("asm_widths") || "{}") }; } catch { return { ...PANEL_DEFW }; } });
  const setWidth = (id, w) => setWidths((p) => { const n = { ...p, [id]: w }; localStorage.setItem("asm_widths", JSON.stringify(n)); return n; });
  const [heights, setHeights] = useState(() => { try { return JSON.parse(localStorage.getItem("asm_heights") || "{}"); } catch { return {}; } });
  const setHeight = (id, h) => setHeights((p) => { const n = { ...p, [id]: h }; localStorage.setItem("asm_heights", JSON.stringify(n)); return n; });
  const dragWidth = (id, invert) => (e) => {
    e.preventDefault();
    const startX = e.clientX, start = widths[id] || PANEL_DEFW[id] || 320;
    const mv = (ev) => { const delta = invert ? startX - ev.clientX : ev.clientX - startX;
      setWidth(id, Math.max(220, Math.min(760, start + delta))); };
    const up = () => { window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up);
      document.body.style.cursor = ""; document.body.style.userSelect = ""; };
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
    document.body.style.cursor = "col-resize"; document.body.style.userSelect = "none";
  };
  const dragHeight = (id) => (e) => {
    e.preventDefault();
    const startY = e.clientY, start = heights[id] || PANEL_DEFH;
    const mv = (ev) => setHeight(id, Math.max(110, Math.min(760, start + (ev.clientY - startY))));
    const up = () => { window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up);
      document.body.style.cursor = ""; document.body.style.userSelect = ""; };
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
    document.body.style.cursor = "row-resize"; document.body.style.userSelect = "none";
  };

  const [layout, setLayout] = useState(() => {
    const base = { columns: DEF_COLUMNS.map((c) => [...c]), hidden: {}, detached: false };
    try {
      const s = { ...base, ...JSON.parse(localStorage.getItem("asm_layout3") || "{}") };
      const seen = new Set();   // self-heal: each panel exactly once; drop unknowns
      s.columns = (s.columns || []).map((col) => col.filter((id) => PANELS.includes(id) && !seen.has(id) && seen.add(id))).filter((col) => col.length);
      PANELS.forEach((id) => { if (!seen.has(id)) s.columns.push([id]); });
      if (!s.columns.length) s.columns = DEF_COLUMNS.map((c) => [...c]);
      return s;
    } catch { return base; }
  });
  const persistLayout = (n) => { localStorage.setItem("asm_layout3", JSON.stringify(n)); return n; };
  const setLay = (patch) => setLayout((l) => persistLayout({ ...l, ...patch }));
  const toggleHide = (id) => setLayout((l) => persistLayout({ ...l, hidden: { ...l.hidden, [id]: !l.hidden[id] } }));
  const resetLayout = () => setLayout(persistLayout({ columns: DEF_COLUMNS.map((c) => [...c]), hidden: {}, detached: false }));
  const movePanel = (id, dir) => setLayout((l) => {
    const cols = l.columns.map((c) => [...c]);
    let ci = -1, ri = -1;
    cols.forEach((c, i) => { const j = c.indexOf(id); if (j >= 0) { ci = i; ri = j; } });
    if (ci < 0) return l;
    if (dir === "up" || dir === "down") {
      const nj = ri + (dir === "up" ? -1 : 1);
      if (nj < 0 || nj >= cols[ci].length) return l;
      [cols[ci][ri], cols[ci][nj]] = [cols[ci][nj], cols[ci][ri]];
    } else {
      cols[ci].splice(ri, 1);
      if (dir === "left") { if (ci === 0) cols.unshift([id]); else cols[ci - 1].push(id); }
      else { if (ci === cols.length - 1) cols.push([id]); else cols[ci + 1].push(id); }
    }
    return persistLayout({ ...l, columns: cols.filter((c) => c.length) });
  });

  /* detachable player: a floating, draggable window (our own PiP) */
  const [floatPos, setFloatPos] = useState(() => { try { return JSON.parse(localStorage.getItem("asm_float") || "null"); } catch { return null; } });
  const detachToggle = () => {
    const p = playerRef.current;
    if (p && p.dataset.media) pendingResume.current = { media: p.dataset.media, src: p.src, t: p.currentTime, paused: p.paused };
    setLay({ detached: !layout.detached });
  };
  useEffect(() => {   // restore playback onto the freshly-mounted <video>
    const p = playerRef.current, r = pendingResume.current; pendingResume.current = null;
    if (p && r && r.src) {
      p.dataset.media = r.media; p.src = r.src;
      p.onloadedmetadata = () => { try { p.currentTime = r.t; } catch { /* ignore */ } if (!r.paused) p.play().catch(() => {}); };
    }
  }, [layout.detached]);
  const startFloatDrag = (e) => {
    e.preventDefault();
    const rect = e.currentTarget.parentElement.getBoundingClientRect();
    const offX = e.clientX - rect.left, offY = e.clientY - rect.top;
    const mv = (ev) => {
      const pos = { x: Math.max(0, Math.min(window.innerWidth - 80, ev.clientX - offX)),
                    y: Math.max(0, Math.min(window.innerHeight - 40, ev.clientY - offY)) };
      setFloatPos(pos); localStorage.setItem("asm_float", JSON.stringify(pos));
    };
    const up = () => { window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up); document.body.style.userSelect = ""; };
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up); document.body.style.userSelect = "none";
  };

  /* ---------- saved sessions (named workspace snapshots) ---------- */
  const [sessions, setSessions] = useState(() => { try { return JSON.parse(localStorage.getItem("asm_sessions") || "{}"); } catch { return {}; } });
  const [sessOpen, setSessOpen] = useState(false);
  const persistSessions = (s) => { setSessions(s); localStorage.setItem("asm_sessions", JSON.stringify(s)); };
  const saveSession = () => {
    const name = prompt("Save this workspace (filters + layout + panels) as:");
    if (!name || !name.trim()) return;
    persistSessions({ ...sessions, [name.trim()]: {
      filters, columns: layout.columns, hidden: layout.hidden, detached: layout.detached,
      widths, heights, cap, leftTab, recsN } });
    setSessOpen(false);
  };
  const loadSession = (name) => {
    const s = sessions[name]; if (!s) return;
    setFilters(s.filters || EMPTY_FILTERS);
    setLayout(persistLayout({ columns: s.columns || DEF_COLUMNS.map((c) => [...c]), hidden: s.hidden || {}, detached: !!s.detached }));
    if (s.widths) { setWidths(s.widths); localStorage.setItem("asm_widths", JSON.stringify(s.widths)); }
    if (s.heights) { setHeights(s.heights); localStorage.setItem("asm_heights", JSON.stringify(s.heights)); }
    if (s.cap) setCapPersist(s.cap);
    if (s.leftTab) setLeftTab(s.leftTab);
    if (s.recsN) setRecsNPersist(s.recsN);
    setSessOpen(false);
  };
  const deleteSession = (name) => { const n = { ...sessions }; delete n[name]; persistSessions(n); };

  /* ---------- keyboard layer (Assembler-wide shortcuts) ---------- */
  const [showHelp, setShowHelp] = useState(false);
  useEffect(() => {
    const onKey = (e) => {
      if (modalOpen()) return;
      const t = e.target;
      const block = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.tagName === "BUTTON" || t.isContentEditable);
      if (e.key === "?" && !block) { e.preventDefault(); setShowHelp((v) => !v); return; }
      if (e.key === "Escape" && showHelp) { setShowHelp(false); return; }
      if (block || e.ctrlKey || e.metaKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (e.key === " ") { e.preventDefault(); const p = playerRef.current; if (p) (p.paused ? p.play().catch(() => {}) : p.pause()); return; }
      if (k === "s" && d) { e.preventDefault(); saveDraft(); return; }
      if (k === "n") { e.preventDefault(); newDraft(); return; }
      if (k === "f" && d) { e.preventDefault(); finalize(); return; }
      if (k === "d") { e.preventDefault(); detachToggle(); return; }
      if ((e.key === "[" || e.key === "]") && drafts.length) {
        e.preventDefault();
        const i = drafts.findIndex((x) => x.id === d?.id);
        const j = (i < 0 ? 0 : i + (e.key === "]" ? 1 : -1) + drafts.length) % drafts.length;
        switchTo(drafts[j].id); return;
      }
      if (["1", "2", "3", "4", "5"].includes(e.key)) { e.preventDefault(); toggleHide(PANELS[Number(e.key) - 1]); return; }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [d, showHelp, drafts, layout.detached]);   // eslint-disable-line

  const inDraft = useMemo(() => new Set(d?.cutIds || []), [d]);
  const [forgeCut, setForgeCut] = useState(null);
  const onForged = async (newId) => {
    try { const full = await api.get(`/api/cuts/${newId}`); mergeCache([full]); addToDraft([newId]); } catch { /* ignore */ }
  };

  /* ---------- a reusable cut card ---------- */
  const Card = ({ id, score, draftRow, idx }) => {
    const c = cut(id); if (!c) return null;
    const open = openCuts.has(id);
    const isOn = nowId === id && playing;
    return (
      <div className={`rounded-lg border ${isOn ? "border-indigo-500 bg-indigo-500/5" : "border-zinc-800 bg-zinc-900/50"}`}>
        <div className="flex items-center gap-2 px-2 py-1.5">
          {draftRow && <span className="text-[11px] font-mono text-zinc-500 w-5 text-right">{idx + 1}</span>}
          {score != null && <Bar score={score} />}
          <button onClick={() => (isOn ? stopPlay() : playCut(c))} className="shrink-0 text-zinc-400 hover:text-indigo-300 text-xs" title="Preview">{isOn ? "❚❚" : "▶"}</button>
          <input value={c.title || ""} onChange={(e) => setCutTitle(id, e.target.value)} onBlur={() => saveCutTitle(id)}
            onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
            className="flex-1 bg-transparent text-sm font-medium outline-none focus:bg-zinc-950 rounded px-1 py-0.5 min-w-0" />
          <button onClick={() => toggleSegs(id)} className="shrink-0 text-zinc-500 hover:text-zinc-50 text-xs" title="Segments">{open ? "▾" : "▸"}</button>
          {draftRow ? (
            <>
              <div className="flex flex-col">
                <button className="text-zinc-500 hover:text-zinc-50 text-[10px] leading-3" onClick={() => moveDraft(idx, idx - 1)}>▲</button>
                <button className="text-zinc-500 hover:text-zinc-50 text-[10px] leading-3" onClick={() => moveDraft(idx, idx + 1)}>▼</button>
              </div>
              <button className="shrink-0 text-zinc-500 hover:text-indigo-300 text-xs" title="Forge a modified cut"
                onClick={async () => { const full = c.segments ? c : await api.get(`/api/cuts/${id}`); mergeCache([full]); setForgeCut(full); }}>✂</button>
              <button className="shrink-0 text-zinc-500 hover:text-red-400 text-xs" onClick={() => removeFromDraft(id)}>✕</button>
            </>
          ) : (
            <button onClick={() => addToDraft([id])} disabled={!d || inDraft.has(id)}
              className={`shrink-0 text-xs px-2 py-0.5 rounded-md border ${
                !d ? "border-zinc-800 text-zinc-700" : inDraft.has(id) ? "border-zinc-800 text-zinc-600"
                  : "border-indigo-600/60 text-indigo-300 hover:border-indigo-500"}`}>
              {inDraft.has(id) ? "added" : "＋"}
            </button>
          )}
        </div>
        <div className="px-2 pb-1 text-[11px] text-zinc-500 font-mono flex items-center gap-2">
          <span className="truncate">{c.media_title}</span>
          {c.start_s != null && <span>· {fmtTime(c.end_s - c.start_s)}</span>}
        </div>
        {open && (
          <div className="px-2 pb-2 space-y-0.5">
            {(c.segments || []).map((s) => (
              <button key={s.id} onClick={() => { const p = playerRef.current; if (!p) return; queue.current = []; setNowId(id); stopAt.current = c.end_s;
                  const go = () => { p.currentTime = s.start_s; p.play().catch(() => {}); };
                  if (String(c.media_id) !== p.dataset.media) { p.dataset.media = String(c.media_id); p.src = streamUrl(c.media_id); p.onloadedmetadata = go; } else go(); }}
                className="block w-full text-left text-xs text-zinc-400 hover:text-zinc-50 hover:bg-zinc-800/60 rounded px-1.5 py-0.5">
                <span className="font-mono text-[10px] text-zinc-600 mr-1.5">{fmtTime(s.start_s)}</span>{s.text}
              </button>
            ))}
            {!c.segments && <p className="text-[11px] text-zinc-600 px-1.5">loading…</p>}
          </div>
        )}
      </div>
    );
  };

  /* ---------- panel bodies (placed into the dynamic panel row by the layout) ---------- */
  const renderScopePanel = () => (
    <>
      <div className="flex gap-1 px-2 pt-2 border-b border-zinc-800 shrink-0">
        {[["scope", "Scope"], ["created", `Created${created.length ? ` (${created.length})` : ""}`]].map(([id, lbl]) => (
          <button key={id} onClick={() => setLeftTab(id)}
            className={`px-3 py-1.5 text-sm border-b-2 -mb-px ${leftTab === id ? "border-indigo-500 text-zinc-50" : "border-transparent text-zinc-400 hover:text-zinc-50"}`}>{lbl}</button>
        ))}
      </div>
      {leftTab === "scope" ? (
        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          <FilterBar filters={filters} setFilters={setFilters} tags={tags} folders={folders} media={media} compact />
          {scope && (
            <>
              <div className="grid grid-cols-3 gap-2 text-center">
                {[["In scope", scope.total], ["Used", scope.used], ["Unused", scope.unused]].map(([k, v]) => (
                  <div key={k} className="rounded-lg border border-zinc-800 bg-zinc-900/50 py-1.5">
                    <div className="text-lg font-semibold">{v}</div>
                    <div className="text-[10px] uppercase tracking-wide text-zinc-500">{k}</div>
                  </div>
                ))}
              </div>
              <Breakdown title="By media" rows={scope.by_media} labelKey="media_title"
                onPick={(r) => setFilters((f) => f.media.some((m) => m.id === r.media_id) ? f : ({ ...f, media: [...f.media, { id: r.media_id, title: r.media_title }] }))} />
              <Breakdown title="By folder" rows={scope.by_folder} labelKey="name"
                onPick={(r) => r.folder_id && setFilters((f) => f.folders.some((x) => x.id === r.folder_id) ? f : ({ ...f, folders: [...f.folders, { id: r.folder_id, name: r.name }] }))} />
              <Breakdown title="Top tags" rows={scope.by_tag} labelKey="name"
                onPick={(r) => setFilters((f) => f.tags.includes(r.name) ? f : ({ ...f, tags: [...f.tags, r.name] }))} />
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] uppercase tracking-wide text-zinc-500">Samples</span>
                  <select value={sampleN} onChange={(e) => setSampleN(Number(e.target.value))}
                    className="bg-zinc-900 border border-zinc-700 rounded px-1 py-0.5 text-[11px] outline-none">
                    {[6, 10, 16, 24].map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </div>
                <div className="space-y-1">
                  {samples.map((s) => (
                    <button key={s.id} onClick={() => setPreviewCut(s)}
                      className="block w-full text-left text-xs rounded-md border border-zinc-800 bg-zinc-900/40 px-2 py-1 hover:border-zinc-600 truncate">
                      ▶ {s.title} <span className="text-zinc-600">· {fmtTime(s.end_s - s.start_s)}</span>
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
          {created.length === 0 && <p className="text-xs text-zinc-600 text-center mt-6">No created recompositions yet.</p>}
          {created.map((r) => (
            <div key={r.id} className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-2.5 py-2 flex items-center gap-2 group">
              <span>🎞️</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium truncate">{r.title}</p>
                <p className="text-[11px] text-zinc-500">{r.cut_count} cuts</p>
              </div>
              <button className="text-xs text-zinc-400 hover:text-indigo-300" onClick={() => openRecomp(r.id)} title="Edit here">edit</button>
              <button className="text-xs text-zinc-400 hover:text-indigo-300" onClick={() => openStudio?.(r.id)} title="Open in Studio">↗</button>
            </div>
          ))}
        </div>
      )}
    </>
  );

  const draftsBody = () => (
    <>
      {/* draft tabs */}
      <div className="shrink-0 flex items-center gap-1 px-2 py-1.5 border-b border-zinc-800 overflow-x-auto">
        {drafts.map((dr) => (
          <button key={dr.id} onClick={() => switchTo(dr.id)}
            className={`shrink-0 px-2 py-1 rounded-md text-xs border ${d?.id === dr.id ? "bg-indigo-600 border-indigo-500 text-white" : "border-zinc-700 text-zinc-400 hover:border-zinc-500"}`}>
            {dr.title} <span className="opacity-60">{dr.cut_count}</span>
          </button>
        ))}
        <button className="shrink-0 px-2 py-1 rounded-md text-xs border border-zinc-700 text-zinc-400 hover:border-zinc-500" onClick={() => newDraft()}>＋ draft</button>
      </div>

      {!d ? (
        <div className="flex-1 flex items-center justify-center text-center text-sm text-zinc-600 px-6">
          Pick a theme → “draft”, or ＋ draft, to start a recomposition.
        </div>
      ) : (
        <>
          {/* draft header */}
          <div className="shrink-0 px-2 py-1.5 border-b border-zinc-800 flex items-center gap-1.5">
            <input value={d.title} onChange={(e) => renameDraft(e.target.value)} onBlur={saveDraft}
              className="flex-1 bg-transparent text-sm font-semibold outline-none focus:bg-zinc-950 rounded px-1 py-0.5 min-w-0" />
            <button className="text-zinc-400 hover:text-zinc-50 disabled:opacity-30" disabled={!d.hist.length} onClick={undo} title="Undo">↶</button>
            <button className="text-zinc-400 hover:text-zinc-50 disabled:opacity-30" disabled={!d.future.length} onClick={redo} title="Redo">↷</button>
            <button className="text-zinc-400 hover:text-indigo-300" disabled={!d.cutIds.length} onClick={() => playSeq(d.cutIds)} title="Play draft">▶</button>
            <button className={`text-xs ${d.dirty ? "text-amber-400" : "text-emerald-400"}`} onClick={saveDraft} title="Save">{d.dirty ? "● save" : "✓"}</button>
            {d.status === "draft"
              ? <button className="text-xs text-indigo-300 hover:text-indigo-200" onClick={finalize} title="Create recomposition (finalize)">🎬</button>
              : <button className="text-xs text-indigo-300" onClick={() => openStudio?.(d.id)} title="Open in Studio">↗</button>}
            <button className="text-zinc-500 hover:text-red-400 text-xs" onClick={() => deleteDraft(d.id)} title="Delete draft">🗑</button>
          </div>

          {/* draft cuts */}
          <div className="flex-1 overflow-y-auto p-2 space-y-1.5 min-h-0">
            {d.cutIds.length === 0 && <p className="text-xs text-zinc-600 text-center mt-4">Empty — add cuts from themes, search, or recommendations.</p>}
            {d.cutIds.map((id, i) => <Card key={`${id}-${i}`} id={id} draftRow idx={i} />)}
          </div>
        </>
      )}
    </>
  );

  const recsBody = () => (
    <div className="flex-1 min-h-0 flex flex-col">
      <div className="shrink-0 flex items-center gap-2 px-2 py-1.5 border-b border-zinc-800 text-xs">
        <span className="text-zinc-400 truncate">✨ for “{d?.title || "—"}”</span>
        <select value={recsN} onChange={(e) => setRecsNPersist(Number(e.target.value))}
          className="ml-auto bg-zinc-900 border border-zinc-700 rounded px-1 py-0.5 outline-none" title="How many to suggest">
          {[10, 15, 25, 40].map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
        <button className="text-zinc-400 hover:text-zinc-50" onClick={loadRecs} title="Refresh">{recsBusy ? "…" : "↻"}</button>
        <button className="text-indigo-300 hover:text-indigo-200 disabled:opacity-30" disabled={!d || !recs.length}
          onClick={() => addToDraft(recs.map((r) => r.cut_id))} title="Add all to the active draft">＋ all</button>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {!d ? <p className="text-[11px] text-zinc-600 text-center mt-4">Open a draft to get recommendations.</p>
          : recs.length === 0 ? <p className="text-[11px] text-zinc-600 text-center mt-4">Add a few cuts and suggestions appear here.</p>
            : recs.map((r) => <Card key={r.cut_id} id={r.cut_id} score={r.score} />)}
      </div>
    </div>
  );

  // single <video> instance — rendered either in the docked Player panel or in
  // the floating window (never both), so playback survives dock/detach.
  const videoEl = () => (
    <video ref={playerRef} controls onTimeUpdate={onTime}
      onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)}
      className="w-full bg-black aspect-video object-contain" />
  );
  const playerControls = () => (
    <div className="flex items-center gap-2 text-xs">
      <button className="text-zinc-400 hover:text-indigo-300 disabled:opacity-30" disabled={!d?.cutIds?.length}
        onClick={() => d && playSeq(d.cutIds)} title="Play the active draft">▶ draft</button>
      <button className="text-zinc-400 hover:text-red-400 disabled:opacity-30" disabled={nowId == null}
        onClick={stopPlay} title="Stop">■ stop</button>
      {nowId != null && cut(nowId) && (
        <span className="ml-auto text-zinc-500 truncate">{cut(nowId).title}</span>
      )}
    </div>
  );
  const playerBody = () => (
    <div className="flex-1 min-h-0 overflow-y-auto p-2 space-y-2">
      <div className="rounded-lg overflow-hidden border border-zinc-800">{videoEl()}</div>
      {playerControls()}
      <p className="text-[11px] text-zinc-600">Tip: ⧉ in this panel's header detaches the player into a floating window, freeing this slot.</p>
    </div>
  );

  const discoveryBody = () => (
    <>
      {/* rank search bar */}
      <div className="shrink-0 p-2 border-b border-zinc-800 flex gap-2">
        <input className={inputCls} value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && runRank()}
          placeholder="🔎 Rank these cuts by meaning — e.g. moments of quiet defiance…" />
        <button className={btnCls} disabled={rankBusy || !query.trim() || !scopeIds.length} onClick={runRank}>
          {rankBusy ? "…" : "Rank"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {/* ranked results — first, collapsible, scroll-locked */}
        {ranked && (
          <div className="rounded-lg border border-indigo-500/40 bg-indigo-500/5">
            <button className="w-full flex items-center gap-2 px-2.5 py-2 text-sm" onClick={() => setRankOpen((v) => !v)}>
              <span>{rankOpen ? "▾" : "▸"}</span>
              <span className="font-medium">🔎 “{query}”</span>
              <span className="text-[11px] text-zinc-500">{ranked.length} ranked</span>
              <span className="ml-auto text-[11px] text-zinc-500" onClick={(e) => { e.stopPropagation(); setRanked(null); }}>✕ clear</span>
            </button>
            {rankOpen && (
              <div className="max-h-72 overflow-y-auto px-2 pb-2 space-y-1.5">
                {ranked.length === 0 ? <p className="text-xs text-zinc-500 px-1 py-2">No embeddable cuts in scope.</p>
                  : ranked.map((r) => <Card key={r.cut_id} id={r.cut_id} score={r.score} />)}
              </div>
            )}
          </div>
        )}

        {/* theme controls */}
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-2 space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-500">Themes</span>
            {["loose", "balanced", "tight"].map((p) => (
              <button key={p} onClick={() => { setTpreset(p); runCluster(p, null); }}
                className={`px-2 py-0.5 rounded-md text-xs capitalize border ${tpreset === p ? "bg-indigo-600 border-indigo-500 text-white" : "border-zinc-700 text-zinc-400 hover:border-zinc-500"}`}>{p}</button>
            ))}
            {clusterBusy && <span className="flex items-center gap-1 text-xs text-indigo-300"><Spinner /> clustering…</span>}
            {scopeIds.length > cap && <span className="text-[11px] text-amber-400">top {cap} of {scopeIds.length}</span>}
          </div>
          {tparams && tbounds && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
              {TKNOBS.filter((k) => tbounds[k.key]).map((k) => (
                <Slider key={k.key} label={k.label} hint={k.hint} fmt={k.fmt}
                  min={tbounds[k.key][0]} max={tbounds[k.key][1]} step={k.step}
                  value={tparams[k.key]} onChange={(v) => setTKnob(k.key, v)} />
              ))}
            </div>
          )}
        </div>

        {/* clusters */}
        {clusters == null ? <p className="text-zinc-600 text-sm text-center mt-8">Finding themes…</p>
          : clusters.length === 0 ? <p className="text-zinc-500 text-sm text-center mt-8">No themes — loosen the threshold or widen the scope.</p>
          : clusters.map((cl, ci) => {
            const open = openClusters.has(ci);
            return (
              <div key={ci} className="rounded-lg border border-zinc-800 bg-zinc-900/40">
                <div className="flex items-center gap-2 px-2.5 py-2">
                  <button className="text-zinc-500 hover:text-zinc-50 text-xs w-4"
                    onClick={() => setOpenClusters((s) => { const n = new Set(s); n.has(ci) ? n.delete(ci) : n.add(ci); return n; })}>{open ? "▾" : "▸"}</button>
                  <span className="text-sm font-medium truncate flex-1">🧩 {cl.name}</span>
                  <span className="text-[11px] text-zinc-500 shrink-0">{cl.size}</span>
                  <button className="text-xs text-zinc-400 hover:text-indigo-300" title="Preview as sequence" onClick={() => playSeq(cl.cut_ids)}>▶ seq</button>
                  <button className={`${btnGhost} !py-0.5`} disabled={!d} onClick={() => addToDraft(cl.cut_ids)} title="Add to active draft">＋ add</button>
                  <button className={`${btnCls} !py-0.5`} onClick={() => newDraft(cl.name, cl.cut_ids)} title="Open as a new draft">draft →</button>
                </div>
                {open && <div className="px-2.5 pb-2 space-y-1.5">{cl.cut_ids.map((id) => <Card key={id} id={id} />)}</div>}
              </div>
            );
          })}
      </div>
    </>
  );

  /* ----- 2-D layout helpers (columns × stacks) ----- */
  const isVisible = (id) => !layout.hidden[id] && !(id === "player" && layout.detached);
  const visCols = layout.columns.map((col) => col.filter(isVisible)).filter((col) => col.length);
  const mainColIdx = Math.max(0, visCols.findIndex((col) => col.includes("discovery")));
  const colWidth = (col) => widths[col[0]] || PANEL_DEFW[col[0]] || 320;
  const colBoundaryDrag = (li, ri) =>
    li >= 0 && li !== mainColIdx ? dragWidth(visCols[li][0], false)
      : ri >= 0 && ri !== mainColIdx ? dragWidth(visCols[ri][0], true)
        : null;

  const panelBody = (id) =>
    id === "scope" ? renderScopePanel()
      : id === "discovery" ? discoveryBody()
        : id === "player" ? playerBody()
          : id === "recs" ? recsBody()
            : draftsBody();

  const panelChrome = (id, ri, colLen) => (
    <div className="shrink-0 flex items-center gap-1 px-2 py-1 border-b border-zinc-800 bg-zinc-950/50 text-[11px]">
      <span className="font-medium text-zinc-400 truncate">{PANEL_TITLE[id]}</span>
      <div className="ml-auto flex items-center gap-0.5 text-zinc-500">
        <button title="Move to the column on the left" onClick={() => movePanel(id, "left")} className="hover:text-zinc-50 px-1">◀</button>
        <button title="Move up in this column" disabled={ri <= 0} onClick={() => movePanel(id, "up")} className="hover:text-zinc-50 disabled:opacity-20 px-1">▲</button>
        <button title="Move down in this column" disabled={ri >= colLen - 1} onClick={() => movePanel(id, "down")} className="hover:text-zinc-50 disabled:opacity-20 px-1">▼</button>
        <button title="Move to the column on the right" onClick={() => movePanel(id, "right")} className="hover:text-zinc-50 px-1">▶</button>
        {id === "player" && <button title="Detach into a floating window" onClick={detachToggle} className="hover:text-indigo-300 px-1">⧉</button>}
        <button title="Hide panel" onClick={() => toggleHide(id)} className="hover:text-red-400 px-1">✕</button>
      </div>
    </div>
  );

  const renderColumn = (col, ci) => {
    const isMainCol = ci === mainColIdx;
    return (
      <div style={isMainCol ? undefined : { width: colWidth(col) }}
        className={`${isMainCol ? "flex-1 min-w-0" : "shrink-0"} flex flex-col min-h-0 ${ci < visCols.length - 1 ? "border-r border-zinc-800" : ""}`}>
        {col.map((id, ri) => {
          const isLast = ri === col.length - 1;   // bottom panel of each column flexes
          return (
            <Fragment key={id}>
              <div style={isLast ? undefined : { height: heights[id] || PANEL_DEFH }}
                className={`${isLast ? "flex-1" : "shrink-0"} min-h-0 flex flex-col overflow-hidden`}>
                {panelChrome(id, ri, col.length)}
                <div className="flex-1 min-h-0 flex flex-col overflow-hidden">{panelBody(id)}</div>
              </div>
              {!isLast && <div onMouseDown={dragHeight(id)}
                className="h-1.5 shrink-0 cursor-row-resize bg-zinc-800/60 hover:bg-indigo-500 transition-colors" title="Drag to resize" />}
            </Fragment>
          );
        })}
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-800 shrink-0">
        <span className="font-semibold text-indigo-300">🧩 Assembler</span>
        <span className="text-xs text-zinc-500 hidden xl:inline">discover by meaning &amp; theme · build many recompositions at once</span>
        <div className="ml-auto flex items-center gap-3 text-xs text-zinc-500">
          <label className="flex items-center gap-1"
            title="Max cuts the theme + rank engines work on. Lower = faster; higher = more thorough.">
            <span>speed cap</span>
            <select value={cap} onChange={(e) => setCapPersist(Number(e.target.value))}
              className="bg-zinc-900 border border-zinc-700 rounded px-1 py-0.5 outline-none">
              {CAP_CHOICES.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <div className="flex items-center gap-1" title="Show / hide panels (◀ ▶ ▲ ▼ in each panel header reorder & vertically split; ⧉ detaches the player)">
            {PANELS.map((id) => {
              const shown = !layout.hidden[id];
              return (
                <button key={id} onClick={() => toggleHide(id)}
                  className={`px-1.5 py-0.5 rounded border capitalize ${shown ? "border-indigo-500 text-indigo-300" : "border-zinc-700 hover:border-zinc-500"}`}>
                  {id === "discovery" ? "themes" : id === "recs" ? "recs" : id}{id === "player" && layout.detached ? " ⧉" : ""}
                </button>
              );
            })}
            <button onClick={resetLayout} title="Reset layout to default"
              className="px-1.5 py-0.5 rounded border border-zinc-700 hover:border-zinc-500">⤺</button>
          </div>
          {/* saved sessions */}
          <div className="relative">
            <button onClick={() => setSessOpen((v) => !v)} title="Saved sessions (filters + layout)"
              className={`px-1.5 py-0.5 rounded border ${sessOpen ? "border-indigo-500 text-indigo-300" : "border-zinc-700 hover:border-zinc-500"}`}>💾 sessions ▾</button>
            {sessOpen && (
              <div className="absolute right-0 mt-1 w-56 z-40 bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl py-1">
                <button onClick={saveSession} className="block w-full text-left px-3 py-1.5 text-xs hover:bg-zinc-800 text-indigo-300">＋ Save current as…</button>
                {Object.keys(sessions).length === 0 && <p className="px-3 py-1.5 text-[11px] text-zinc-600">No saved sessions yet.</p>}
                {Object.keys(sessions).map((name) => (
                  <div key={name} className="flex items-center group hover:bg-zinc-800">
                    <button onClick={() => loadSession(name)} className="flex-1 text-left px-3 py-1.5 text-xs truncate">{name}</button>
                    <button onClick={() => deleteSession(name)} title="Delete" className="px-2 text-zinc-600 hover:text-red-400 opacity-0 group-hover:opacity-100">✕</button>
                  </div>
                ))}
              </div>
            )}
          </div>
          <button onClick={() => setShowHelp(true)} title="Keyboard shortcuts (?)" className="px-1.5 py-0.5 rounded border border-zinc-700 hover:border-zinc-500">?</button>
          <span>{scope ? `${scope.total} in scope` : "…"}</span>
        </div>
      </div>

      <div className="flex-1 min-h-0 flex">
        {visCols.length === 0 && (
          <div className="flex-1 flex items-center justify-center text-sm text-zinc-600">All panels hidden — re-enable one above.</div>
        )}
        {visCols.map((col, ci) => (
          <Fragment key={`col-${ci}-${col.join("-")}`}>
            {ci > 0 && (() => { const bar = colBoundaryDrag(ci - 1, ci); return bar ? <DragBar onMouseDown={bar} /> : null; })()}
            {renderColumn(col, ci)}
          </Fragment>
        ))}
      </div>

      {/* detached floating player — our own picture-in-picture */}
      {layout.detached && !layout.hidden.player && createPortal((() => {
        const w = 380;
        const x = floatPos?.x ?? (window.innerWidth - w - 24);
        const y = floatPos?.y ?? (window.innerHeight - w * 0.62 - 90);
        return (
          <div style={{ position: "fixed", left: x, top: y, width: w, zIndex: 50 }}
            className="bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl overflow-hidden">
            <div onMouseDown={startFloatDrag}
              className="cursor-move flex items-center gap-2 px-2 py-1 bg-zinc-950 border-b border-zinc-800 text-[11px] text-zinc-400 select-none">
              <span>▣ Player</span>
              {nowId != null && cut(nowId) && <span className="truncate text-zinc-500">{cut(nowId).title}</span>}
              <button className="ml-auto hover:text-indigo-300" onClick={detachToggle} title="Dock back into the workspace">⤓ dock</button>
            </div>
            {videoEl()}
            <div className="px-2 py-1 bg-zinc-950 border-t border-zinc-800">{playerControls()}</div>
          </div>
        );
      })(), document.body)}

      {forgeCut && (
        <ForgeCutModal cut={forgeCut} user={user}
          onClose={() => setForgeCut(null)} onCreated={onForged} />
      )}
      {previewCut && (
        <Modal title={previewCut.title} onClose={() => setPreviewCut(null)} wide>
          <video src={streamUrl(previewCut.media_id)} controls autoPlay
            onLoadedMetadata={(e) => { e.target.currentTime = previewCut.start_s; }}
            className="w-full rounded-lg bg-black aspect-video object-contain" />
          <p className="text-sm text-zinc-400 mt-2">“{previewCut.text}”</p>
          <p className="text-xs text-zinc-600 mt-1">{previewCut.media_title} · {fmtTime(previewCut.start_s)}–{fmtTime(previewCut.end_s)}</p>
        </Modal>
      )}
      {showHelp && (
        <Modal title="Assembler shortcuts" onClose={() => setShowHelp(false)}>
          <div className="space-y-1.5 text-sm">
            {[["Space", "play / pause the player"], ["S", "save the active draft"], ["N", "new draft"],
              ["F", "finalize (create) the active draft"], ["D", "detach / dock the player"],
              ["[  /  ]", "previous / next draft"], ["1–5", "show/hide scope · themes · player · drafts · recs"],
              ["?", "toggle this help"]].map(([key, what]) => (
              <div key={key} className="flex items-center gap-3">
                <kbd className="font-mono text-xs px-2 py-0.5 rounded bg-zinc-800 border border-zinc-700 min-w-[64px] text-center">{key}</kbd>
                <span className="text-zinc-300">{what}</span>
              </div>
            ))}
            <p className="text-xs text-zinc-500 pt-2">Shortcuts pause while you're typing in a field. Reorder panels with ◀ ▶ ▲ ▼ in each panel's header (▲▼ stacks them — that's the vertical split).</p>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Breakdown({ title, rows, labelKey, onPick }) {
  if (!rows || rows.length === 0) return null;
  const max = Math.max(...rows.map((r) => r.count), 1);
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">{title}</div>
      <div className="space-y-0.5">
        {rows.slice(0, 8).map((r, i) => (
          <button key={i} onClick={() => onPick(r)}
            className="block w-full text-left relative rounded px-2 py-0.5 hover:bg-zinc-800/60 group">
            <span className="absolute inset-y-0 left-0 rounded bg-indigo-500/10 group-hover:bg-indigo-500/20"
              style={{ width: `${(r.count / max) * 100}%` }} />
            <span className="relative flex justify-between text-xs">
              <span className="truncate text-zinc-300">{r[labelKey]}</span>
              <span className="text-zinc-500 ml-2">{r.count}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
