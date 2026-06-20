/* The Cutter — a dedicated page for algorithmic, no-LLM topic cutting.
 *
 *   • LEFT   — hyperparameters; every change re-segments live (cached embeddings).
 *   • CENTRE — the WHOLE transcript, carved into bordered cut-groups so you watch
 *              the settings take shape. Click a line to select+seek; right-click a
 *              line for split-here / merge / rename; the playing line highlights.
 *   • RIGHT  — preview player, a control deck for the selected cut, and the
 *              clickable list of all cuts (kept in sync with the transcript).
 *   • FOOTER — folder + Create (always visible).
 *
 * Cuts are contiguous ranges over the ordered line positions, so every edit is a
 * boundary move, a merge, or a split — never a gap or overlap. A full keyboard
 * layer makes the whole thing mouse-optional (press ? for the cheat sheet).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, fmtTime, streamUrl } from "../api";
import { Slider, Spinner, ContextMenu, inputCls, btnCls } from "./ui";

const PRESETS = ["coarse", "balanced", "fine"];

const KNOBS = [
  { key: "min_split_score", label: "Boundary sensitivity", step: 0.01,
    hint: "lower = split more eagerly", fmt: (v) => v.toFixed(2) },
  { key: "min_duration_s", label: "Min cut length", step: 1, fmt: (v) => `${v}s` },
  { key: "min_segments", label: "Min lines / cut", step: 1, fmt: (v) => `${v}` },
  { key: "max_segments", label: "Max lines / cut", step: 1, fmt: (v) => `${v}` },
  { key: "window_size", label: "Compare window", step: 1,
    hint: "lines weighed each side", fmt: (v) => `${v}` },
  { key: "adaptive_std_weight", label: "Adaptiveness", step: 0.05,
    hint: "raise to demand sharper shifts", fmt: (v) => v.toFixed(2) },
  { key: "max_depth", label: "Max splits depth", step: 1, fmt: (v) => `${v}` },
];

const SHORTCUTS = [
  ["Space", "Play / pause selected cut"],
  ["Enter", "Replay selected from its start"],
  ["↑ / ↓  (K / J)", "Select previous / next cut"],
  ["Home / End", "Select first / last cut"],
  ["→ / ←", "Move END edge later / earlier"],
  ["⇧ ← / ⇧ →", "Move START edge earlier / later"],
  ["S", "Split selected cut in half"],
  ["M / ⇧ M", "Merge with next / previous"],
  ["R  (F2)", "Rename selected cut"],
  ["1 / 2 / 3", "Coarse / balanced / fine preset"],
  ["⌘/Ctrl + Enter", "Create the cuts"],
  ["?", "Toggle this help"],
];

/* ============================ the workspace ============================ */

function ScoreBar({ score }) {
  const pct = Math.max(0, Math.min(100, Math.round(score * 100)));
  return (
    <span className="inline-flex items-center gap-1.5" title={`Topic-shift strength ${pct}%`}>
      <span className="w-9 h-1.5 rounded-full bg-zinc-700 overflow-hidden">
        <span className="block h-full rounded-full bg-indigo-500" style={{ width: `${pct}%` }} />
      </span>
      <span className="text-[10px] text-zinc-500 tabular-nums">{pct}%</span>
    </span>
  );
}

function Stepper({ label, onMinus, onPlus, minusOk, plusOk, minusTip, plusTip }) {
  return (
    <div className="flex items-center gap-1">
      <span className="text-[10px] uppercase tracking-wide text-zinc-500 w-8">{label}</span>
      <button disabled={!minusOk} onClick={onMinus} title={minusTip}
        className="w-6 h-6 rounded-md border border-zinc-700 text-zinc-300 enabled:hover:border-zinc-500
                   enabled:hover:text-white disabled:opacity-30">−</button>
      <button disabled={!plusOk} onClick={onPlus} title={plusTip}
        className="w-6 h-6 rounded-md border border-zinc-700 text-zinc-300 enabled:hover:border-zinc-500
                   enabled:hover:text-white disabled:opacity-30">+</button>
    </div>
  );
}

function Workspace({ media, trackId, segments, user, onCommitted }) {
  const mediaId = media.id;

  const { order, byIdx } = useMemo(() => {
    const ord = segments.map((s) => s.idx);
    const map = {};
    segments.forEach((s) => { map[s.idx] = s; });
    return { order: ord, byIdx: map };
  }, [segments]);

  const autoTitle = useCallback((startPos) => {
    const txt = byIdx[order[startPos]]?.text || "";
    return txt.split(/\s+/).slice(0, 7).join(" ") || "Cut";
  }, [order, byIdx]);

  const [preset, setPreset] = useState("balanced");
  const [params, setParams] = useState(null);
  const [bounds, setBounds] = useState(null);
  const [rows, setRows] = useState([]);
  const [selK, setSelK] = useState(null);
  const [folder, setFolder] = useState("Topic cuts");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [committing, setCommitting] = useState(false);
  const [menu, setMenu] = useState(null);
  const [showHelp, setShowHelp] = useState(false);
  const runSeq = useRef(0);
  const groupRefs = useRef({});
  const listRefs = useRef({});
  const titleRef = useRef();

  /* ---- preview player (play / pause toggle, auto-stop at cut end) ---- */
  const previewRef = useRef();
  const stopAt = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [playingK, setPlayingK] = useState(null);
  const [curTime, setCurTime] = useState(0);
  const onTime = () => {
    const p = previewRef.current;
    if (!p) return;
    setCurTime(p.currentTime);
    if (stopAt.current != null && p.currentTime >= stopAt.current) { p.pause(); stopAt.current = null; }
  };

  /* ---- segmentation pass ---- */
  const run = useCallback(async (presetName, overrides) => {
    const seq = ++runSeq.current;
    setLoading(true); setError(null);
    try {
      const data = await api.post(`/api/media/${mediaId}/segment/preview`, {
        track_id: trackId, preset: presetName, params: overrides || null,
      });
      if (seq !== runSeq.current) return;
      setParams(data.params); setBounds(data.param_bounds);
      setRows(planToRows(data.plan, order));
    } catch (e) {
      if (seq !== runSeq.current) return;
      setError(e.message); setRows([]);
    } finally {
      if (seq === runSeq.current) setLoading(false);
    }
  }, [mediaId, trackId, order]);

  useEffect(() => { run("balanced", null); }, [run]);

  const choosePreset = (p) => { setPreset(p); run(p, null); };
  const debounce = useRef(null);
  const setKnob = (key, val) => {
    const next = { ...params, [key]: val, name: "custom" };
    setParams(next); setPreset("custom");
    clearTimeout(debounce.current);
    const overrides = {}; KNOBS.forEach((k) => { overrides[k.key] = next[k.key]; });
    debounce.current = setTimeout(() => run("balanced", overrides), 280);
  };

  /* ---- derived cuts + effective selection ---- */
  const deriveRow = useCallback((r) => {
    const from = byIdx[order[r.startPos]], to = byIdx[order[r.endPos]];
    return { ...r, fromIdx: order[r.startPos], toIdx: order[r.endPos],
             count: r.endPos - r.startPos + 1, start_s: from?.start_s, end_s: to?.end_s };
  }, [order, byIdx]);
  const derived = useMemo(() => rows.map(deriveRow), [rows, deriveRow]);
  const last = derived.length - 1;
  const sel = derived.length === 0 ? null : selK == null ? 0 : Math.min(selK, last);
  const selCut = sel != null ? derived[sel] : null;

  const activePos = useMemo(() => {
    if (!playing) return -1;
    for (let i = 0; i < order.length; i++) {
      const s = byIdx[order[i]];
      if (s && curTime >= s.start_s && curTime < s.end_s) return i;
    }
    return -1;
  }, [playing, curTime, order, byIdx]);

  /* ---- selection + reveal (two-way sync between transcript and list) ---- */
  const revealGroup = (k) => groupRefs.current[k]?.scrollIntoView({ block: "nearest" });
  const revealList = (k) => listRefs.current[k]?.scrollIntoView({ block: "nearest" });
  const selectFromTranscript = (k) => { setSelK(k); revealList(k); };
  const selectFromList = (k) => { setSelK(k); revealGroup(k); };
  const selectByKey = (k) => { setSelK(k); revealGroup(k); revealList(k); };

  /* ---- preview ---- */
  const playSpan = (k) => {
    const p = previewRef.current, d = derived[k];
    if (!p || !d) return;
    setPlayingK(k); stopAt.current = d.end_s;
    try { p.currentTime = d.start_s; p.play(); } catch { /* ignore */ }
  };
  const togglePlay = (k) => {
    const p = previewRef.current, d = derived[k];
    if (!p || !d) return;
    if (playingK === k && !p.paused) { p.pause(); return; }
    if (playingK === k && p.paused) {
      if (p.currentTime >= d.end_s - 0.05) p.currentTime = d.start_s;
      stopAt.current = d.end_s; p.play().catch(() => {}); return;
    }
    playSpan(k);
  };

  /* ---- boundary editing ---- */
  const nudge = (i, dir) => setRows((rs) => {
    const a = rs[i], b = rs[i + 1];
    if (!b) return rs;
    const split = a.endPos + dir;
    if (split < a.startPos || split >= b.endPos) return rs;
    const n = rs.slice();
    n[i] = { ...a, endPos: split, adjusted: true };
    n[i + 1] = { ...b, startPos: split + 1, adjusted: true,
                 title: b.userTitled ? b.title : autoTitle(split + 1) };
    return n;
  });
  const mergeAt = (i) => setRows((rs) => {
    const a = rs[i], b = rs[i + 1];
    if (!b) return rs;
    const n = rs.slice();
    n[i] = { ...a, endPos: b.endPos, adjusted: true };
    n.splice(i + 1, 1);
    return n;
  });
  const splitAt = (k, atPos) => setRows((rs) => {
    const r = rs[k];
    if (atPos <= r.startPos || atPos > r.endPos) return rs;
    const a = { ...r, endPos: atPos - 1, adjusted: true };
    const b = { startPos: atPos, endPos: r.endPos, score: r.score, adjusted: true,
                userTitled: false, title: autoTitle(atPos) };
    const n = rs.slice(); n.splice(k, 1, a, b); return n;
  });
  const setTitle = (k, title) => setRows((rs) => {
    const n = rs.slice(); n[k] = { ...n[k], title, userTitled: true }; return n;
  });

  const splitMid = (k = sel) => { const r = rows[k]; if (r) splitAt(k, Math.floor((r.startPos + r.endPos) / 2) + 1); };
  const mergePrev = () => { if (sel > 0) { mergeAt(sel - 1); setSelK(sel - 1); } };
  const mergeNext = () => { if (sel < last) mergeAt(sel); };

  const commit = async () => {
    setCommitting(true);
    try {
      const plan = derived.map((r) => ({ from_idx: r.fromIdx, to_idx: r.toIdx, title: r.title, tags: [], folder }));
      const res = await api.post(`/api/media/${mediaId}/segment/commit`, {
        track_id: trackId, plan, folder, user_id: user.id });
      onCommitted?.(res);
    } catch (e) { setError(e.message); setCommitting(false); }
  };

  /* ---- keyboard layer ---- */
  const kb = useRef({});
  // refresh the latest-values ref after every render (so the listener, bound once,
  // never reads stale state) — done in an effect to avoid writing a ref in render
  useEffect(() => {
    kb.current = { sel, last, derived, rows, playingK, choosePreset, togglePlay, playSpan,
                   nudge, mergePrev, mergeNext, splitMid, selectByKey, setShowHelp, commit, titleRef };
  });
  useEffect(() => {
    const onKey = (e) => {
      const t = (e.target.tagName || "").toLowerCase();
      const typing = t === "input" || t === "textarea" || t === "select";
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); kb.current.commit(); return; }
      if (typing) return;
      const k = kb.current.sel, L = kb.current.last;
      const set = (nk) => kb.current.selectByKey(Math.max(0, Math.min(L, nk)));
      const M = { ...kb.current };
      switch (e.key) {
        case " ": e.preventDefault(); if (k != null) M.togglePlay(k); break;
        case "Enter": if (k != null) M.playSpan(k); break;
        case "ArrowUp": case "k": e.preventDefault(); if (k != null) set(k - 1); break;
        case "ArrowDown": case "j": e.preventDefault(); if (k != null) set(k + 1); break;
        case "Home": e.preventDefault(); set(0); break;
        case "End": e.preventDefault(); set(L); break;
        case "ArrowRight": e.preventDefault(); if (k != null) (e.shiftKey ? M.nudge(k - 1, 1) : M.nudge(k, 1)); break;
        case "ArrowLeft": e.preventDefault(); if (k != null) (e.shiftKey ? M.nudge(k - 1, -1) : M.nudge(k, -1)); break;
        case "s": case "S": if (k != null) M.splitMid(k); break;
        case "m": e.preventDefault(); M.mergeNext(); break;
        case "M": e.preventDefault(); M.mergePrev(); break;
        case "r": case "R": case "F2": e.preventDefault(); M.titleRef.current?.select(); break;
        case "1": M.choosePreset("coarse"); break;
        case "2": M.choosePreset("balanced"); break;
        case "3": M.choosePreset("fine"); break;
        case "?": M.setShowHelp((v) => !v); break;
        default: break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const openMenu = (e, k, pos) => {
    e.preventDefault();
    selectFromTranscript(k);
    const r = rows[k]; if (!r) return;
    const items = [{ header: `Cut ${k + 1}` },
      { label: "▶ Play this cut", onClick: () => playSpan(k) }];
    if (pos > r.startPos) items.push({ label: "✂ Split before this line", onClick: () => splitAt(k, pos) });
    items.push({ label: "✂ Split in half", onClick: () => splitMid(k) });
    items.push({ label: "✎ Rename cut…",
      onClick: () => { const x = window.prompt("Cut title", r.title); if (x != null) setTitle(k, x); } });
    items.push({ divider: true });
    if (k > 0) items.push({ label: "⤺ Merge with previous", onClick: () => { mergeAt(k - 1); setSelK(k - 1); } });
    if (k < last) items.push({ label: "⤼ Merge with next", onClick: () => mergeAt(k) });
    setMenu({ x: e.clientX, y: e.clientY, items });
  };

  const noEngine = error && /embedding/i.test(error);
  const covered = derived.reduce((s, r) => s + ((r.end_s || 0) - (r.start_s || 0)), 0);
  const playIcon = (k) => (playingK === k && playing ? "❚❚" : "▶");

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <div className="flex-1 min-h-0 flex">
        {/* ===== left: hyperparameters ===== */}
        <div className="w-56 shrink-0 border-r border-zinc-800 overflow-y-auto p-4 flex flex-col gap-4">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] uppercase tracking-wide text-zinc-500">Preset</span>
              <span className="text-[10px] text-zinc-600">1 · 2 · 3</span>
            </div>
            <div className="grid grid-cols-3 gap-1">
              {PRESETS.map((p) => (
                <button key={p} onClick={() => choosePreset(p)}
                  className={`py-1 rounded-md text-xs capitalize border ${
                    preset === p ? "bg-indigo-600 border-indigo-500 text-white"
                                 : "border-zinc-700 text-zinc-400 hover:border-zinc-500"}`}>{p}</button>
              ))}
            </div>
            {preset === "custom" && <div className="mt-1.5 text-[10px] text-indigo-300">custom — tuned by hand</div>}
          </div>
          {params && bounds && (
            <div className="flex flex-col gap-3">
              {KNOBS.filter((k) => bounds[k.key]).map((k) => (
                <Slider key={k.key} label={k.label} hint={k.hint} fmt={k.fmt}
                  min={bounds[k.key][0]} max={bounds[k.key][1]} step={k.step}
                  value={params[k.key]} onChange={(v) => setKnob(k.key, v)} />
              ))}
            </div>
          )}
          <button onClick={() => setShowHelp(true)}
            className="mt-auto text-[11px] text-zinc-500 hover:text-indigo-300 text-left">⌨ Keyboard shortcuts (?)</button>
        </div>

        {/* ===== centre: live-segmented transcript ===== */}
        <div className="flex-1 min-w-0 flex flex-col">
          <div className="shrink-0 px-4 py-2.5 border-b border-zinc-800 flex items-center gap-2 text-sm">
            <span className="text-zinc-200 font-medium">
              {derived.length} cut{derived.length === 1 ? "" : "s"} across {order.length} lines
            </span>
            {loading && <span className="flex items-center gap-1.5 text-xs text-indigo-300"><Spinner /> tuning…</span>}
            <span className="ml-auto text-[11px] text-zinc-600">click a line to select · right-click for split / merge</span>
          </div>
          <div className="flex-1 overflow-y-auto px-4 py-3">
            {noEngine ? (
              <div className="text-center text-sm text-zinc-400 mt-16 px-6">
                Topic cutting needs the embedding model.
                <div className="text-xs text-zinc-600 mt-2">
                  Install <code className="text-zinc-400">transformers</code> (and build the search
                  index in Settings), then reopen this.</div>
              </div>
            ) : error ? (
              <div className="text-center text-sm text-red-400 mt-16">{error}</div>
            ) : derived.length === 0 && !loading ? (
              <div className="text-center text-sm text-zinc-500 mt-16">
                No cuts at these settings — lower the boundary sensitivity or min length.
              </div>
            ) : (
              derived.map((r, k) => {
                const on = k === sel;
                return (
                  <div key={r.startPos} ref={(el) => (groupRefs.current[k] = el)}
                    onClick={() => selectFromTranscript(k)}
                    className={`rounded-lg border mb-2 cursor-pointer transition-colors ${
                      on ? "border-indigo-500 bg-indigo-500/5" : "border-zinc-800 hover:border-zinc-700"}`}>
                    <div className="flex items-center gap-2 px-3 py-1.5 border-b border-zinc-800/70">
                      <span className="text-[11px] font-mono text-zinc-500">{String(k + 1).padStart(2, "0")}</span>
                      <span className={`text-sm font-medium truncate ${on ? "text-white" : "text-zinc-300"}`}>{r.title}</span>
                      <span className="text-[11px] text-zinc-600 font-mono shrink-0">{r.count}L · {fmtTime(r.end_s - r.start_s)}</span>
                      <span className="ml-auto shrink-0">
                        {r.adjusted ? <span className="text-[10px] text-amber-400">adjusted</span> : <ScoreBar score={r.score} />}
                      </span>
                      <button onClick={(e) => { e.stopPropagation(); togglePlay(k); }}
                        title="Play / pause" className="shrink-0 text-zinc-400 hover:text-indigo-300 px-1 text-xs">{playIcon(k)}</button>
                    </div>
                    <p className="px-3 py-2 text-[15px] leading-7 text-zinc-300">
                      {order.slice(r.startPos, r.endPos + 1).map((ix, j) => {
                        const pos = r.startPos + j;
                        const s = byIdx[ix];
                        return (
                          <span key={ix}
                            onClick={(e) => { e.stopPropagation(); selectFromTranscript(k); const p = previewRef.current; if (p) p.currentTime = s.start_s; }}
                            onContextMenu={(e) => openMenu(e, k, pos)}
                            className={`cursor-pointer rounded px-0.5 ${
                              pos === activePos ? "bg-indigo-500/30 text-white" : "hover:bg-zinc-800/70"}`}>
                            {s.text}{" "}
                          </span>
                        );
                      })}
                    </p>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* ===== right: player · deck · cut list ===== */}
        <div className="w-80 shrink-0 border-l border-zinc-800 flex flex-col min-h-0">
          <div className="p-3 border-b border-zinc-800 shrink-0">
            {media.type === "video" ? (
              <video ref={previewRef} src={streamUrl(mediaId)} onTimeUpdate={onTime} controls
                onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)}
                className="w-full rounded-lg bg-black aspect-video object-contain" />
            ) : (
              <audio ref={previewRef} src={streamUrl(mediaId)} onTimeUpdate={onTime} controls
                onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} className="w-full" />
            )}
          </div>

          {selCut && (
            <div className="p-3 border-b border-zinc-800 shrink-0 flex flex-col gap-2.5">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-mono text-zinc-500">{String(sel + 1).padStart(2, "0")}</span>
                <input ref={titleRef} value={selCut.title} onChange={(e) => setTitle(sel, e.target.value)}
                  className="flex-1 bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-sm outline-none
                             focus:border-indigo-500 min-w-0" />
              </div>
              <div className="flex items-center gap-2 text-[11px] text-zinc-500 font-mono">
                <span>{fmtTime(selCut.start_s)}–{fmtTime(selCut.end_s)}</span>
                <span>·</span><span>{selCut.count} lines</span>
                <button onClick={() => togglePlay(sel)}
                  className="ml-auto px-2 h-6 rounded-md border border-zinc-700 text-zinc-200 hover:border-indigo-500"
                  title="Play / pause (Space)">{playIcon(sel)}</button>
              </div>
              <div className="flex items-center justify-between gap-2">
                <Stepper label="Start" minusOk={sel > 0} plusOk={sel > 0}
                  onMinus={() => nudge(sel - 1, -1)} onPlus={() => nudge(sel - 1, 1)}
                  minusTip="Extend start ( ⇧← )" plusTip="Trim start ( ⇧→ )" />
                <Stepper label="End" minusOk={sel < last} plusOk={sel < last}
                  onMinus={() => nudge(sel, -1)} onPlus={() => nudge(sel, 1)}
                  minusTip="Trim end ( ← )" plusTip="Extend end ( → )" />
              </div>
              <div className="flex items-center gap-1.5">
                <button disabled={sel === 0} onClick={mergePrev}
                  className="flex-1 h-7 rounded-md border border-zinc-700 text-xs text-zinc-300 enabled:hover:border-zinc-500 disabled:opacity-30" title="Merge with previous (⇧M)">⤺ Merge prev</button>
                <button disabled={selCut.count < 2} onClick={() => splitMid()}
                  className="h-7 px-3 rounded-md border border-zinc-700 text-xs text-zinc-300 enabled:hover:border-zinc-500 disabled:opacity-30" title="Split in half (S)">✂ Split</button>
                <button disabled={sel === last} onClick={mergeNext}
                  className="flex-1 h-7 rounded-md border border-zinc-700 text-xs text-zinc-300 enabled:hover:border-zinc-500 disabled:opacity-30" title="Merge with next (M)">Merge next ⤼</button>
              </div>
            </div>
          )}

          <div className="flex-1 overflow-y-auto p-2 min-h-0">
            <div className="text-[10px] uppercase tracking-wide text-zinc-500 px-1 mb-1">All cuts</div>
            {derived.map((r, k) => (
              <div key={r.startPos} ref={(el) => (listRefs.current[k] = el)}
                onClick={() => selectFromList(k)}
                className={`flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer ${
                  k === sel ? "bg-indigo-500/10 text-white" : "hover:bg-zinc-800/60 text-zinc-300"}`}>
                <span className="text-[10px] font-mono text-zinc-500 w-5">{String(k + 1).padStart(2, "0")}</span>
                <span className="flex-1 truncate text-xs">{r.title}</span>
                <span className="text-[10px] font-mono text-zinc-600 shrink-0">{fmtTime(r.end_s - r.start_s)}</span>
                <button onClick={(e) => { e.stopPropagation(); togglePlay(k); }}
                  className="shrink-0 text-zinc-500 hover:text-indigo-300 text-xs" title="Play / pause">{playIcon(k)}</button>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ===== footer ===== */}
      <div className="shrink-0 flex items-center gap-3 px-4 py-3 border-t border-zinc-800 bg-zinc-900">
        <span className="text-xs text-zinc-500">
          {fmtTime(covered)} covered · avg {derived.length ? (covered / derived.length).toFixed(1) : "0"}s
        </span>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-zinc-500">Save into</span>
          <input value={folder} onChange={(e) => setFolder(e.target.value)}
            className={`${inputCls} !py-1 !w-44`} placeholder="Folder name" />
          <button className={btnCls} disabled={committing || !derived.length || !!noEngine} onClick={commit}
            title="Create cuts (⌘/Ctrl+Enter)">
            {committing ? "Saving…" : `Create ${derived.length} cut${derived.length === 1 ? "" : "s"}`}
          </button>
        </div>
      </div>

      {menu && <ContextMenu x={menu.x} y={menu.y} items={menu.items} onClose={() => setMenu(null)} />}
      {showHelp && <HelpOverlay onClose={() => setShowHelp(false)} />}
    </div>
  );
}

function HelpOverlay({ onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape" || e.key === "?") { e.preventDefault(); onClose(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl w-full max-w-md p-5"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold">Keyboard shortcuts</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-white text-xl leading-none">×</button>
        </div>
        <div className="grid grid-cols-1 gap-1.5">
          {SHORTCUTS.map(([keys, desc]) => (
            <div key={keys} className="flex items-center justify-between text-sm">
              <span className="text-zinc-400">{desc}</span>
              <kbd className="font-mono text-xs text-zinc-200 bg-zinc-950 border border-zinc-700 rounded px-2 py-0.5">{keys}</kbd>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ============================ the page (data + pickers) ============================ */

export default function Cutter({ user, mediaId: initialMediaId, trackId: initialTrackId, openMedia }) {
  const [mediaList, setMediaList] = useState([]);
  const [mediaId, setMediaId] = useState(initialMediaId ?? null);
  const [media, setMedia] = useState(null);
  const [tracks, setTracks] = useState([]);
  const [trackId, setTrackId] = useState(initialTrackId ?? null);
  const [segments, setSegments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [flash, setFlash] = useState(null);

  useEffect(() => {
    api.get("/api/media")
      .then((l) => setMediaList(l.filter((m) => m.segment_count > 0 && m.linked)))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (mediaId == null) { setMedia(null); setTracks([]); return; }
    api.get(`/api/media/${mediaId}`).then(setMedia).catch(() => {});
    api.get(`/api/media/${mediaId}/tracks`).then((ts) => {
      setTracks(ts);
      setTrackId((cur) => (ts.some((t) => t.id === cur) ? cur : ts[0]?.id ?? null));
    }).catch(() => {});
  }, [mediaId]);

  useEffect(() => {
    if (mediaId == null || trackId == null) { setSegments([]); return; }
    setLoading(true);
    api.get(`/api/media/${mediaId}/segments?track_id=${trackId}`)
      .then(setSegments).catch(() => setSegments([])).finally(() => setLoading(false));
  }, [mediaId, trackId]);

  const ready = media && trackId != null && segments.length > 0;

  return (
    <div className="h-full flex flex-col">
      {/* toolbar */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-800 shrink-0">
        <span className="font-semibold text-indigo-300 mr-1">⚡ Cutter</span>
        <select value={mediaId ?? ""} onChange={(e) => setMediaId(Number(e.target.value) || null)}
          className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1 text-sm outline-none focus:border-indigo-500 max-w-[260px]">
          <option value="">Choose media…</option>
          {mediaList.map((m) => (
            <option key={m.id} value={m.id}>{m.title} ({m.segment_count} lines)</option>
          ))}
        </select>
        {tracks.length > 0 && (
          <select value={trackId ?? ""} onChange={(e) => setTrackId(Number(e.target.value))}
            className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1 text-xs outline-none focus:border-indigo-500 max-w-[200px]">
            {tracks.map((t) => (
              <option key={t.id} value={t.id}>{t.name}{t.lang_code ? ` · ${t.lang_code}` : ""} ({t.segment_count})</option>
            ))}
          </select>
        )}
        {media && (
          <button className="text-xs text-zinc-500 hover:text-white" onClick={() => openMedia?.(media.id)}>
            open in Library →
          </button>
        )}
        {flash && <span className="ml-auto text-emerald-400 text-sm">{flash}</span>}
      </div>

      {/* body */}
      {!mediaId ? (
        <Picker mediaList={mediaList} onPick={setMediaId} />
      ) : loading ? (
        <div className="flex-1 flex items-center justify-center text-zinc-500"><Spinner /></div>
      ) : !ready ? (
        <div className="flex-1 flex items-center justify-center text-zinc-500 text-sm px-6 text-center">
          {tracks.length === 0
            ? "This media has no subtitle track yet — transcribe or add subtitles in the Library."
            : "No segments on this track."}
        </div>
      ) : (
        <Workspace key={`${mediaId}:${trackId}`} media={media} trackId={trackId} segments={segments} user={user}
          onCommitted={(res) => setFlash(`Created ${res.created} cut${res.created === 1 ? "" : "s"} ✓`)} />
      )}
    </div>
  );
}

function Picker({ mediaList, onPick }) {
  if (!mediaList.length) {
    return (
      <div className="flex-1 flex items-center justify-center text-zinc-500 text-sm px-6 text-center">
        No transcribed media yet. Add media and transcribe it in the Library, then come cut it here.
      </div>
    );
  }
  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto">
        <h2 className="text-zinc-300 font-medium mb-1">Pick something to cut</h2>
        <p className="text-zinc-500 text-sm mb-4">The engine carves the transcript into topic cuts you then sculpt.</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {mediaList.map((m) => (
            <button key={m.id} onClick={() => onPick(m.id)}
              className="text-left p-3 rounded-xl bg-zinc-900 border border-zinc-800 hover:border-indigo-500">
              <div className="text-sm font-medium truncate">{m.title}</div>
              <div className="text-xs text-zinc-500 mt-1">{m.type} · {m.segment_count} lines · {m.cut_count} cuts</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function planToRows(plan, order) {
  const pos = {};
  order.forEach((ix, i) => { pos[ix] = i; });
  return plan.map((c) => ({
    startPos: pos[c.from_idx] ?? 0,
    endPos: pos[c.to_idx] ?? order.length - 1,
    title: c.title, score: c.score, adjusted: false, userTitled: false,
  }));
}
