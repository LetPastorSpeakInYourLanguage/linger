import { useEffect, useRef, useState } from "react";
import { api, fmtTime, streamUrl } from "../api";
import { inputCls, btnCls, btnGhost, modalOpen, useResizable, DragBar, ContextMenu } from "./ui";
import CutBrowser, { EMPTY_FILTERS } from "./CutBrowser";

/* Sequenced playback across multiple source media files, with per-cut loop.

   Double-buffered: two stacked <video> elements. While cut N plays, cut N+1's
   media is loaded, seeked AND frame-decoded in the hidden element; at the
   boundary we just swap which one is visible — no flash, no jump. The visible
   element never gets a .src assigned: new media always comes up on the
   standby and swaps in. Cut boundaries are watched with requestAnimationFrame
   (~16 ms) instead of the ~250 ms `timeupdate` event. */
function useSequencePlayer(cuts) {
  const refA = useRef();
  const refB = useRef();
  const [playingIdx, setPlayingIdx] = useState(-1);
  const [activeEl, setActiveEl] = useState(0); // 0 → refA visible, 1 → refB
  const [loop, setLoop] = useState(false);
  const stateRef = useRef({ idx: -1, cuts: [], loop: false, active: 0 });
  stateRef.current.cuts = cuts;
  stateRef.current.loop = loop;

  const els = () => [refA.current, refB.current];
  const getPlayer = () => els()[stateRef.current.active];
  const srcMatch = (el, src) => !!el && !!el.src && el.src.endsWith(src);

  /* Load src into el, seek to t and decode that frame: seeking right after
     `loadedmetadata` leaves a blank frame, so wait for `seeked`, then a muted
     play→pause warms the decoder. onReady fires once the frame is showable. */
  const primeEl = (el, src, t, onReady) => {
    const afterSeek = () => {
      const wasMuted = el.muted;
      el.muted = true;
      const p = el.play();
      (p && p.then ? p : Promise.resolve())
        .then(() => { el.pause(); el.muted = wasMuted; onReady?.(); })
        .catch(() => { el.muted = wasMuted; onReady?.(); });
    };
    const seek = () => {
      el.addEventListener("seeked", afterSeek, { once: true });
      try { el.currentTime = t; } catch { el.removeEventListener("seeked", afterSeek); }
    };
    if (!srcMatch(el, src)) {
      el.pause();
      el.src = src;
      el.preload = "auto";
      el.addEventListener("loadedmetadata", seek, { once: true });
    } else if (Math.abs(el.currentTime - t) > 0.4) {
      seek();
    } else {
      onReady?.();
    }
  };

  /* warm up the standby element with the NEXT cut's media, paused & decoded */
  const preloadNext = (idx) => {
    const st = stateRef.current;
    const next = st.cuts[idx + 1];
    if (!next) return;
    const nsrc = streamUrl(next.media_id);
    const cur = els()[st.active];
    const standby = els()[1 - st.active];
    if (!standby || srcMatch(cur, nsrc)) return; // same file: no swap needed
    primeEl(standby, nsrc, next.start_s);
  };

  const playFrom = (idx) => {
    const st = stateRef.current;
    const cut = st.cuts[idx];
    if (!cut) { setPlayingIdx(-1); return; }
    st.idx = idx;
    setPlayingIdx(idx);
    const src = streamUrl(cut.media_id);
    const cur = els()[st.active];
    const standby = els()[1 - st.active];
    if (!cur && !standby) return;

    const begin = (el) => {
      if (Math.abs(el.currentTime - cut.start_s) > 0.4) {
        try { el.currentTime = cut.start_s; } catch { /* not seekable yet */ }
      }
      el.play().catch(() => {});
      preloadNext(idx);
    };

    if (srcMatch(cur, src)) {
      begin(cur);
      return;
    }
    // different media: bring it up on the standby (already primed at the
    // boundary, instant) and swap — the visible element never loads in view
    const target = standby || cur;
    primeEl(target, src, cut.start_s, () => {
      if (stateRef.current.idx !== idx) return; // user moved on meanwhile
      cur?.pause();
      if (target === standby) {
        st.active = 1 - st.active;
        setActiveEl(st.active);
      }
      begin(target);
    });
  };

  // boundary watcher — rAF so we react within a frame of crossing end_s
  useEffect(() => {
    let raf;
    const tick = () => {
      const st = stateRef.current;
      const p = els()[st.active];
      const cut = st.cuts[st.idx];
      if (p && cut && st.idx >= 0 && !p.paused && p.currentTime >= cut.end_s) {
        if (st.loop) p.currentTime = cut.start_s;            // immerse mode
        else if (st.idx + 1 < st.cuts.length) playFrom(st.idx + 1);
        else { p.pause(); st.idx = -1; setPlayingIdx(-1); }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // playFrom only touches refs, so the first closure stays valid
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stop = () => {
    els().forEach((p) => p?.pause());
    stateRef.current.idx = -1;
    setPlayingIdx(-1);
  };

  return { refA, refB, activeEl, getPlayer, playingIdx, playFrom, stop, loop, setLoop };
}

function ExportModal({ recomp, exportJob, translationJob, onClose, onExport, onTranslate }) {
  const [languages, setLanguages] = useState([]);
  const [targetLang, setTargetLang] = useState("");
  const [audioMode, setAudioMode] = useState("original");
  const [quality, setQuality] = useState("720p");
  const [overwrite, setOverwrite] = useState(false);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    api.get("/api/languages").then((rows) => {
      setLanguages(rows);
      setTargetLang((cur) =>
        cur || rows.find((l) => l.dub_capable && l.code !== "en")?.code || rows[0]?.code || "");
    }).catch(() => {});
  }, []);

  const runTranslate = async () => {
    if (!targetLang.trim()) return;
    setBusy("translate"); setErr("");
    try {
      await onTranslate({ target_lang: targetLang.trim(), overwrite });
    } catch (e) { setErr(e.message); }
    setBusy("");
  };

  const runExport = async () => {
    setBusy("export"); setErr("");
    try {
      await onExport({
        audio_mode: audioMode,
        target_lang: targetLang.trim(),
        quality,
      });
      onClose();
    } catch (e) { setErr(e.message); }
    setBusy("");
  };
  const translationRunning = translationJob &&
    ["queued", "running"].includes(translationJob.status);

  return (
    <div data-modal className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl w-full max-w-lg max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="font-semibold">Export {recomp.title}</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-white text-xl leading-none">×</button>
        </div>
        <div className="p-4 space-y-4 overflow-y-auto">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-zinc-400">Target language</label>
              <select className={inputCls} value={targetLang}
                onChange={(e) => setTargetLang(e.target.value)}>
                {languages.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.name} ({l.code}){l.dub_capable ? "" : " · no voice"}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-zinc-400">Video quality</label>
              <select className={inputCls} value={quality}
                onChange={(e) => setQuality(e.target.value)}>
                <option value="480p">480p</option>
                <option value="720p">720p</option>
                <option value="1080p">1080p</option>
              </select>
            </div>
          </div>

          <div>
            <label className="text-xs text-zinc-400">Export audio</label>
            <select className={inputCls} value={audioMode}
              onChange={(e) => setAudioMode(e.target.value)}>
              <option value="original">Original audio</option>
              <option value="target_dub">Ready dub for target language</option>
              <option value="sequence">Saved sequence choices</option>
            </select>
          </div>

          <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium">Cut translations</p>
                <p className="text-xs text-zinc-500">
                  {recomp.cuts.length} cuts in this recomposition
                </p>
              </div>
              <button className={btnGhost} disabled={!targetLang || busy === "translate" || translationRunning}
                onClick={runTranslate}>
                {busy === "translate" ? "Starting…" : "Translate cuts"}
              </button>
            </div>
            <label className="flex items-center gap-2 text-xs text-zinc-400">
              <input type="checkbox" checked={overwrite}
                onChange={(e) => setOverwrite(e.target.checked)} />
              Replace existing translations in this language
            </label>
            {translationJob && (
              <p className={`text-xs ${
                translationJob.status === "failed" ? "text-red-400" : "text-amber-400"
              }`}>
                translation {translationJob.status}
                {translationJob.progress != null ? ` ${Math.round(translationJob.progress)}%` : ""} · {translationJob.detail || "queued"}
              </p>
            )}
          </div>

          {exportJob && (
            <p className="text-sm text-amber-400">
              export {exportJob.status}
              {exportJob.progress != null ? ` ${Math.round(exportJob.progress)}%` : ""} · {exportJob.detail || "queued"}
            </p>
          )}
          {err && <p className="text-sm text-red-400">{err}</p>}

          <div className="flex justify-end gap-2">
            <button className={btnGhost} onClick={onClose}>Cancel</button>
            <button className={btnCls} disabled={busy === "export" || !!exportJob || !recomp.cuts.length}
              onClick={runExport}>
              {busy === "export" ? "Starting…" : "Start export"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function RecompEditor({ user, recompId, back }) {
  const [recomp, setRecomp] = useState(null);
  const [dragIdx, setDragIdx] = useState(null);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [folders, setFolders] = useState([]);
  const [menu, setMenu] = useState(null); // {x, y, cut}
  const [showExport, setShowExport] = useState(false);
  const wasPlayingRef = useRef(false);
  const { refA, refB, activeEl, getPlayer, playingIdx, playFrom, stop, loop, setLoop } =
    useSequencePlayer(recomp?.cuts ?? []);

  const load = () => api.get(`/api/recompositions/${recompId}`).then(setRecomp);
  useEffect(() => { load(); api.get("/api/folders").then(setFolders).catch(() => {}); }, [recompId]);

  /* ---- export: start job, poll progress, list finished files */
  const [exports, setExports] = useState([]);
  const [exportJob, setExportJob] = useState(null);
  const [translationJob, setTranslationJob] = useState(null);

  const refreshExports = () => {
    api.get(`/api/recompositions/${recompId}/exports`).then(setExports).catch(() => {});
    api.get("/api/jobs").then((js) => {
      const j = js.find((x) =>
        x.kind === "export" && ["queued", "running"].includes(x.status) &&
        x.target_kind === "recomposition" && x.target_id === recompId);
      setExportJob(j || null);
      const runningTranslation = js.find((x) =>
        x.kind === "translate_recomposition" && ["queued", "running"].includes(x.status) &&
        x.target_kind === "recomposition" && x.target_id === recompId);
      if (runningTranslation) setTranslationJob(runningTranslation);
      else if (translationJob?.id) {
        const latest = js.find((x) => x.id === translationJob.id);
        setTranslationJob(["done", "failed", "cancelled"].includes(latest?.status)
          ? latest : null);
      }
    }).catch(() => {});
  };

  useEffect(() => { refreshExports(); }, [recompId]);
  useEffect(() => {
    const translationRunning = translationJob &&
      ["queued", "running"].includes(translationJob.status);
    if (!exportJob && !translationRunning) return;
    const t = setInterval(refreshExports, 2500);
    return () => clearInterval(t);
  }, [exportJob?.id, translationJob?.id]);

  const startExport = async (options) => {
    await api.post(`/api/recompositions/${recompId}/export`, options);
    refreshExports();
  };

  const saveOrder = async (cutIds) => {
    setRecomp(await api.put(`/api/recompositions/${recompId}/cuts`, { cut_ids: cutIds }));
  };

  const move = (from, to) => {
    if (to < 0 || to >= recomp.cuts.length) return;
    const ids = recomp.cuts.map((c) => c.id);
    const [x] = ids.splice(from, 1);
    ids.splice(to, 0, x);
    saveOrder(ids);
  };

  const removeAt = (idx) => {
    const ids = recomp.cuts.map((c) => c.id);
    ids.splice(idx, 1);
    saveOrder(ids);
  };

  const addCut = (cut) => saveOrder([...recomp.cuts.map((c) => c.id), cut.id]);

  const translateRecomp = async (options) => {
    const res = await api.post(`/api/recompositions/${recompId}/translations`, {
      lang_code: options.target_lang,
      user_id: user.id,
      overwrite: options.overwrite,
    });
    setTranslationJob({ id: res.job_id, status: "queued" });
    refreshExports();
  };

  /* Cut-preview popup opened from the browser: pause, then resume on close. */
  const onPreviewChange = (cut) => {
    const p = getPlayer();
    if (cut) {
      wasPlayingRef.current = !!p && !p.paused;
      p?.pause();
    } else if (wasPlayingRef.current) {
      p?.play().catch(() => {});
      wasPlayingRef.current = false;
    }
  };

  /* Right-click a sequence item → drive the cut browser's filters from it. */
  const menuItems = (cut) => {
    const folderName = folders.find((f) => f.id === cut.folder_id)?.name;
    const items = [
      { header: "Filter the cut browser by…" },
      {
        label: `🎬 Same media: ${cut.media_title}`,
        onClick: () => setFilters((f) => ({
          ...f,
          media: f.media.some((m) => m.id === cut.media_id) ? f.media
            : [...f.media, { id: cut.media_id, title: cut.media_title }],
        })),
      },
    ];
    if (folderName) {
      items.push({
        label: `📁 Folder: ${folderName}`,
        onClick: () => setFilters((f) => ({
          ...f,
          folders: f.folders.some((x) => x.id === cut.folder_id) ? f.folders
            : [...f.folders, { id: cut.folder_id, name: folderName }],
        })),
      });
    }
    for (const t of cut.tags) {
      items.push({
        label: `# Tag: ${t}`,
        onClick: () => setFilters((f) => ({
          ...f, tags: f.tags.includes(t) ? f.tags : [...f.tags, t],
        })),
      });
    }
    items.push({ divider: true });
    if (cut.tags.length || folderName) {
      items.push({
        label: "✚ Add all of this cut's filters",
        onClick: () => setFilters((f) => ({
          q: f.q,
          media: f.media.some((m) => m.id === cut.media_id) ? f.media
            : [...f.media, { id: cut.media_id, title: cut.media_title }],
          folders: folderName && !f.folders.some((x) => x.id === cut.folder_id)
            ? [...f.folders, { id: cut.folder_id, name: folderName }] : f.folders,
          tags: [...new Set([...f.tags, ...cut.tags])],
        })),
      });
    }
    items.push({ label: "✕ Clear all filters", onClick: () => setFilters({ ...EMPTY_FILTERS }) });
    return items;
  };

  /* Studio keyboard shortcuts — work no matter what has focus. */
  useEffect(() => {
    const onKey = (e) => {
      if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
      if (modalOpen()) return;
      const p = getPlayer();
      const n = recomp?.cuts?.length ?? 0;
      if (e.code === "Space") {
        e.preventDefault();
        if (!p) return;
        if (p.paused && playingIdx < 0 && n) playFrom(0);
        else p.paused ? p.play() : p.pause();
      } else if (e.key === "ArrowRight") { e.preventDefault(); if (p) p.currentTime += 5; }
      else if (e.key === "ArrowLeft") { e.preventDefault(); if (p) p.currentTime -= 5; }
      else if (e.key === "ArrowDown") {
        e.preventDefault();
        if (n) playFrom(Math.min(playingIdx < 0 ? 0 : playingIdx + 1, n - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (n) playFrom(Math.max(playingIdx < 0 ? 0 : playingIdx - 1, 0));
      } else if (e.key === "l" || e.key === "L") {
        setLoop((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [playingIdx, recomp, setLoop]);

  const [leftW, dragLeft] = useResizable("studio_left_w", 420, 300, 760);

  if (!recomp) return null;
  const total = recomp.cuts.reduce((acc, c) => acc + (c.end_s - c.start_s), 0);
  const hasVideo = recomp.cuts.some((c) => c.media_type === "video");

  return (
    <div className="h-full flex min-h-0">
      {/* left: cut search (resizable) */}
      <div style={{ width: leftW }} className="shrink-0 min-h-0 flex flex-col">
        <CutBrowser user={user} embedded onAdd={addCut}
          filters={filters} setFilters={setFilters}
          onPreviewChange={onPreviewChange}
          onCutChanged={load} />
      </div>
      <DragBar onMouseDown={dragLeft} />

      {/* right: sequence + player */}
      <div className="flex-1 flex flex-col min-w-0 border-l border-zinc-800">
        <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-800 shrink-0">
          <button onClick={back} className="text-zinc-400 hover:text-white text-sm">← Studio</button>
          <h1 className="font-semibold truncate">{recomp.title}</h1>
          <span className="text-xs text-zinc-500 whitespace-nowrap">{recomp.cuts.length} cuts · {fmtTime(total)}</span>
          <div className="ml-auto flex gap-2 items-center">
            <button title="Render this recomposition into one real video/audio file"
              className={btnGhost} disabled={!recomp.cuts.length || !!exportJob}
              onClick={() => setShowExport(true)}>
              ⬇ Export
            </button>
            <button title="Loop the playing cut (L)"
              className={`${btnGhost} ${loop ? "border-amber-500 text-amber-400" : ""}`}
              onClick={() => setLoop(!loop)}>
              🔁 Loop {loop ? "on" : "off"}
            </button>
            <button className={btnCls} disabled={!recomp.cuts.length}
              onClick={() => playFrom(0)}>▶ Play all</button>
            <button className={btnGhost} onClick={stop}>Stop</button>
          </div>
        </div>

        {(exportJob || exports.length > 0) && (
          <div className="px-4 py-1.5 border-b border-zinc-800/60 shrink-0 flex items-center gap-4 text-xs flex-wrap">
            {exportJob && (
              <span className="text-amber-400 animate-pulse">
                ⏳ exporting{exportJob.progress != null ? ` ${Math.round(exportJob.progress)}%` : ""} — {exportJob.detail || "queued"}
              </span>
            )}
            {exports.slice(0, 3).map((f) => (
              <span key={f.filename} className="inline-flex items-center gap-2">
                <a href={`/api/exports/${encodeURIComponent(f.filename)}`} download
                  className="text-indigo-400 hover:text-indigo-300">
                  ⬇ {f.filename} <span className="text-zinc-500">({(f.size / 1e6).toFixed(1)} MB)</span>
                </a>
                <button className="text-zinc-500 hover:text-red-400"
                  onClick={async () => {
                    if (!confirm(`Delete export "${f.filename}"?`)) return;
                    await api.del(`/api/exports/${encodeURIComponent(f.filename)}`);
                    refreshExports();
                  }}>
                  delete
                </button>
              </span>
            ))}
          </div>
        )}

        {/* double-buffered player: hidden element preloads the next cut's media */}
        <div className="shrink-0 bg-black relative" style={{ height: hasVideo ? "38vh" : "72px" }}>
          <video ref={refA} controls
            className={`absolute inset-0 w-full h-full object-contain transition-opacity duration-150 ${
              activeEl === 0 ? "opacity-100" : "opacity-0 pointer-events-none"}`} />
          <video ref={refB} controls
            className={`absolute inset-0 w-full h-full object-contain transition-opacity duration-150 ${
              activeEl === 1 ? "opacity-100" : "opacity-0 pointer-events-none"}`} />
        </div>

        <p className="px-4 py-1 text-[11px] text-zinc-600 border-b border-zinc-800/60 shrink-0">
          space play/pause · ←/→ seek 5s · ↑/↓ previous/next cut · L loop current cut · right-click a cut for filters
        </p>

        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {recomp.cuts.length === 0 && (
            <p className="text-zinc-500 text-sm text-center mt-10">
              Search your cuts on the left and add them to build the sequence.
            </p>
          )}
          {recomp.cuts.map((c, i) => (
            <div key={`${c.id}-${i}`} draggable
              onDragStart={() => setDragIdx(i)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={() => { if (dragIdx != null && dragIdx !== i) move(dragIdx, i); setDragIdx(null); }}
              onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY, cut: c }); }}
              className={`rounded-lg border p-3 flex items-center gap-3 cursor-grab ${
                playingIdx === i ? "border-amber-500 bg-amber-500/10" : "border-zinc-800 bg-zinc-900"}`}>
              <span className="text-zinc-600 text-sm w-6 text-right">{i + 1}.</span>
              <button onClick={() => playFrom(i)} title="Play from here"
                className="text-indigo-400 hover:text-indigo-300">▶</button>
              <button onClick={() => { playFrom(i); setLoop(true); }} title="Play this cut on loop"
                className={`text-sm ${loop && playingIdx === i ? "text-amber-400" : "text-zinc-500 hover:text-amber-400"}`}>
                🔁
              </button>
              <div className="min-w-0 flex-1">
                <p className="font-medium truncate">
                  {c.title}
                  {loop && playingIdx === i && <span className="text-amber-400 text-xs ml-2">looping</span>}
                </p>
                <p className="text-xs text-zinc-500 truncate">
                  {c.media_title} · {fmtTime(c.start_s)}–{fmtTime(c.end_s)} ({fmtTime(c.end_s - c.start_s)})
                  {c.tags.length > 0 && <> · {c.tags.map((t) => `#${t}`).join(" ")}</>}
                </p>
              </div>
              <div className="flex flex-col">
                <button className="text-zinc-500 hover:text-white text-xs" onClick={() => move(i, i - 1)}>▲</button>
                <button className="text-zinc-500 hover:text-white text-xs" onClick={() => move(i, i + 1)}>▼</button>
              </div>
              <button className="text-zinc-500 hover:text-red-400 text-sm" onClick={() => removeAt(i)}>✕</button>
            </div>
          ))}
        </div>
      </div>

      {menu && (
        <ContextMenu x={menu.x} y={menu.y} items={menuItems(menu.cut)}
          onClose={() => setMenu(null)} />
      )}
      {showExport && (
        <ExportModal recomp={recomp} exportJob={exportJob} translationJob={translationJob}
          onClose={() => setShowExport(false)}
          onExport={startExport}
          onTranslate={translateRecomp} />
      )}
    </div>
  );
}

export default function Studio({ user }) {
  const [recomps, setRecomps] = useState([]);
  const [openId, setOpenId] = useState(null);
  const [newTitle, setNewTitle] = useState("");

  const refresh = () => api.get("/api/recompositions").then(setRecomps);
  useEffect(() => { refresh(); }, []);

  const create = async () => {
    if (!newTitle.trim()) return;
    const r = await api.post("/api/recompositions", { title: newTitle.trim(), user_id: user.id });
    setNewTitle("");
    setOpenId(r.id);
  };

  const remove = async (r) => {
    if (!confirm(`Delete recomposition "${r.title}"? (Cuts are kept.)`)) return;
    await api.del(`/api/recompositions/${r.id}`);
    refresh();
  };

  if (openId != null) {
    return <RecompEditor user={user} recompId={openId}
      back={() => { setOpenId(null); refresh(); }} />;
  }

  return (
    <div className="h-full overflow-y-auto p-6 max-w-3xl mx-auto">
      <h1 className="text-xl font-semibold mb-5">Recompositions</h1>
      <div className="flex gap-2 mb-6">
        <input className={inputCls} placeholder="New recomposition title (e.g. Best confessions ever)…"
          value={newTitle} onChange={(e) => setNewTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && create()} />
        <button className={btnCls} onClick={create}>Create</button>
      </div>
      <div className="space-y-2">
        {recomps.length === 0 && (
          <p className="text-zinc-500 text-sm text-center mt-10">No recompositions yet.</p>
        )}
        {recomps.map((r) => (
          <div key={r.id}
            className="rounded-lg border border-zinc-800 bg-zinc-900 p-4 flex items-center gap-3 hover:border-zinc-600 cursor-pointer group"
            onClick={() => setOpenId(r.id)}>
            <span className="text-xl">🎞️</span>
            <div className="flex-1 min-w-0">
              <p className="font-medium truncate">{r.title}</p>
              <p className="text-xs text-zinc-500">
                {r.cut_count} cuts{r.created_by_name ? ` · by ${r.created_by_name}` : ""}
              </p>
            </div>
            <button className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 text-sm"
              onClick={(e) => { e.stopPropagation(); remove(r); }}>
              delete
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
