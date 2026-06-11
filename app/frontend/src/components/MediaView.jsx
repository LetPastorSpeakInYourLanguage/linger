import { useEffect, useMemo, useRef, useState } from "react";
import { api, fmtTime, streamUrl } from "../api";
import { Modal, inputCls, btnCls, btnGhost, Tag, modalOpen, useResizable, DragBar } from "./ui";
import SearchPanel from "./SearchPanel";
import { EditCutModal } from "./CutBrowser";

function SaveCutModal({ user, media, segments, onClose, onSaved }) {
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [note, setNote] = useState("");
  const [folderId, setFolderId] = useState("");
  const [folders, setFolders] = useState([]);
  const [newFolder, setNewFolder] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => { api.get("/api/folders").then(setFolders).catch(() => {}); }, []);

  const save = async () => {
    try {
      let fid = folderId ? Number(folderId) : null;
      if (newFolder.trim()) {
        const f = await api.post("/api/folders", { name: newFolder.trim() });
        fid = f.id;
      }
      await api.post("/api/cuts", {
        media_id: media.id,
        title: title || segments[0].text.slice(0, 60),
        note,
        folder_id: fid,
        segment_ids: segments.map((s) => s.id),
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
        user_id: user.id,
      });
      onSaved(); onClose();
    } catch (e) { setErr(e.message); }
  };

  return (
    <Modal title={`Save cut — ${segments.length} segment${segments.length > 1 ? "s" : ""}`} onClose={onClose}>
      <div className="space-y-3">
        <p className="text-sm text-zinc-400 bg-zinc-950 rounded-lg p-3 max-h-32 overflow-y-auto">
          “{segments.map((s) => s.text).join(" ")}”
        </p>
        <p className="text-xs text-zinc-500">
          {fmtTime(segments[0].start_s)} → {fmtTime(segments[segments.length - 1].end_s)}
        </p>
        <input className={inputCls} placeholder="Title (e.g. The confession scene)"
          value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
        <input className={inputCls} placeholder="Tags, comma separated (romance, confession)"
          value={tags} onChange={(e) => setTags(e.target.value)} />
        <div className="flex gap-2">
          <select className={inputCls} value={folderId} onChange={(e) => setFolderId(e.target.value)}>
            <option value="">No folder</option>
            {folders.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
          <input className={inputCls} placeholder="…or new folder"
            value={newFolder} onChange={(e) => setNewFolder(e.target.value)} />
        </div>
        <input className={inputCls} placeholder="Note (optional)"
          value={note} onChange={(e) => setNote(e.target.value)} />
        {err && <p className="text-sm text-red-400">{err}</p>}
        <div className="flex justify-end gap-2">
          <button className={btnGhost} onClick={onClose}>Cancel</button>
          <button className={btnCls} onClick={save}>Save cut</button>
        </div>
      </div>
    </Modal>
  );
}

/* The "Cuts" tab of the right panel: every cut made from this media. */
function MediaCuts({ cuts, folders, onPlay, onShow, onEdit, onDelete }) {
  const folderName = (id) => folders.find((f) => f.id === id)?.name;
  if (!cuts.length) {
    return (
      <p className="text-sm text-zinc-600 text-center mt-8 px-4">
        No cuts from this media yet. Select lines in the transcript and press <b>s</b>.
      </p>
    );
  }
  return (
    <div className="p-2 space-y-1.5 overflow-y-auto">
      {cuts.map((c) => (
        <div key={c.id} className="rounded-lg border border-zinc-800 bg-zinc-900 p-2.5 group">
          <div className="flex items-center gap-2">
            <button className="font-medium text-sm text-left truncate hover:text-indigo-300 flex-1"
              title="Play this cut in the player" onClick={() => onPlay(c)}>
              ▶ {c.title}
            </button>
            <span className="text-xs text-zinc-500 whitespace-nowrap">
              {fmtTime(c.start_s)}–{fmtTime(c.end_s)}
            </span>
          </div>
          <p className="text-xs text-zinc-500 mt-1 line-clamp-2">“{c.text}”</p>
          <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
            {folderName(c.folder_id) && (
              <span className="text-xs text-zinc-500">📁 {folderName(c.folder_id)}</span>
            )}
            {c.tags.map((t) => <Tag key={t} name={t} />)}
            <span className="ml-auto flex gap-2 text-xs opacity-0 group-hover:opacity-100">
              <button className="text-zinc-400 hover:text-white" onClick={() => onShow(c)}>show in transcript</button>
              <button className="text-zinc-400 hover:text-white" onClick={() => onEdit(c)}>edit</button>
              <button className="text-zinc-400 hover:text-red-400" onClick={() => onDelete(c)}>delete</button>
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function MediaView({ user, mediaId, back, initialSeg = null }) {
  const [media, setMedia] = useState(null);
  const [segments, setSegments] = useState([]);
  const [anchor, setAnchor] = useState(null);   // segment array index
  const [extent, setExtent] = useState(null);
  const [activeIdx, setActiveIdx] = useState(-1);
  const [showSave, setShowSave] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const [panelTab, setPanelTab] = useState("search"); // search | cuts
  const [cuts, setCuts] = useState([]);
  const [folders, setFolders] = useState([]);
  const [editing, setEditing] = useState(null);
  const [matched, setMatched] = useState(new Set());
  const playerRef = useRef();
  const stopAtRef = useRef(null);
  const segEls = useRef({});
  const [panelW, dragPanel] = useResizable("mediaview_panel_w", 360, 260, 640, true);

  const refreshCuts = () =>
    api.get(`/api/cuts?media_id=${mediaId}`).then(setCuts).catch(() => {});

  useEffect(() => {
    api.get(`/api/media/${mediaId}`).then(setMedia);
    api.get(`/api/media/${mediaId}/segments`).then(setSegments);
    api.get("/api/folders").then(setFolders).catch(() => {});
    refreshCuts();
  }, [mediaId]);

  // arriving from a global search hit: select + scroll + seek (paused)
  useEffect(() => {
    if (!initialSeg || !segments.length) return;
    const i = segments.findIndex((s) => s.id === initialSeg.id);
    if (i < 0) return;
    setAnchor(i); setExtent(null);
    const p = playerRef.current;
    if (p) p.currentTime = segments[i].start_s;
    setTimeout(() => scrollToIdx(i), 80);
  }, [initialSeg, segments]);

  const [selStart, selEnd] = useMemo(() => {
    if (anchor == null) return [null, null];
    const e = extent ?? anchor;
    return [Math.min(anchor, e), Math.max(anchor, e)];
  }, [anchor, extent]);

  const selectedSegments = useMemo(
    () => (selStart == null ? [] : segments.slice(selStart, selEnd + 1)),
    [segments, selStart, selEnd]);

  const onTime = () => {
    const t = playerRef.current?.currentTime ?? 0;
    if (stopAtRef.current != null && t >= stopAtRef.current) {
      playerRef.current.pause();
      stopAtRef.current = null;
    }
    let lo = 0, hi = segments.length - 1, found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (segments[mid].start_s <= t) { if (t <= segments[mid].end_s + 0.3) found = mid; lo = mid + 1; }
      else hi = mid - 1;
    }
    setActiveIdx(found);
  };

  const seekTo = (s, play = true) => {
    const p = playerRef.current;
    if (!p) return;
    p.currentTime = s.start_s;
    if (play) p.play().catch(() => {});
  };

  const scrollToIdx = (i) =>
    segEls.current[i]?.scrollIntoView({ block: "center", behavior: "smooth" });

  const clickSeg = (i, e) => {
    if (e.shiftKey && anchor != null) setExtent(i);
    else { setAnchor(i); setExtent(null); }
    stopAtRef.current = null;
    seekTo(segments[i]);
  };

  /* Grow/shrink the selection by whole lines — "also include the next two". */
  const extendSel = (dir) => {
    if (anchor == null) {
      if (activeIdx >= 0) setAnchor(activeIdx);
      return;
    }
    const cur = extent ?? anchor;
    const next = Math.max(0, Math.min(segments.length - 1, cur + dir));
    setExtent(next);
    scrollToIdx(next);
  };

  const playSelection = () => {
    if (!selectedSegments.length) return;
    stopAtRef.current = selectedSegments[selectedSegments.length - 1].end_s;
    seekTo(selectedSegments[0]);
  };

  /* a search hit was clicked: select that line, scroll, seek */
  const jumpToSearchHit = (seg) => {
    let i = segments.findIndex((s) => s.id === seg.id);
    if (i < 0) i = seg.idx;
    setAnchor(i); setExtent(null);
    stopAtRef.current = null;
    seekTo(segments[i] ?? seg, false);
    scrollToIdx(i);
  };

  const playCut = (c) => {
    if (!c.segments.length) return;
    stopAtRef.current = c.end_s;
    const p = playerRef.current;
    if (p) { p.currentTime = c.start_s; p.play().catch(() => {}); }
    const i = segments.findIndex((s) => s.id === c.segments[0].id);
    if (i >= 0) scrollToIdx(i);
  };

  const showCutInTranscript = (c) => {
    const first = segments.findIndex((s) => s.id === c.segments[0]?.id);
    const last = segments.findIndex((s) => s.id === c.segments[c.segments.length - 1]?.id);
    if (first < 0) return;
    setAnchor(first); setExtent(last >= 0 ? last : null);
    scrollToIdx(first);
  };

  const deleteCut = async (c) => {
    if (!confirm(`Delete cut "${c.title}"?`)) return;
    await api.del(`/api/cuts/${c.id}`);
    refreshCuts();
  };

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;
      if (modalOpen()) return;
      const p = playerRef.current;
      if (e.code === "Space") { e.preventDefault(); p && (p.paused ? p.play() : p.pause()); }
      else if (e.key === "ArrowRight" && !e.shiftKey) { e.preventDefault(); if (p) p.currentTime += 5; }
      else if (e.key === "ArrowLeft" && !e.shiftKey) { e.preventDefault(); if (p) p.currentTime -= 5; }
      else if (e.key === "ArrowDown" && e.shiftKey) { e.preventDefault(); extendSel(1); }
      else if (e.key === "ArrowUp" && e.shiftKey) { e.preventDefault(); extendSel(-1); }
      else if (e.key === "s" && selectedSegments.length) setShowSave(true);
      else if (e.key === "Escape") { setAnchor(null); setExtent(null); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedSegments, anchor, extent, activeIdx, segments]);

  if (!media) return null;

  const tabBtn = (id, label) => (
    <button onClick={() => setPanelTab(id)}
      className={`px-3 py-1.5 text-sm rounded-t-lg border-b-2 ${
        panelTab === id ? "border-indigo-500 text-white" : "border-transparent text-zinc-400 hover:text-white"}`}>
      {label}
    </button>
  );

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-800 shrink-0">
        <button onClick={back} className="text-zinc-400 hover:text-white text-sm">← Library</button>
        <h1 className="font-semibold truncate">{media.title}</h1>
        <span className="ml-auto text-xs text-zinc-600 hidden md:block">
          space play/pause · ←/→ seek · shift-click / shift-↑↓ extend · s save cut
        </span>
      </div>

      <div className="flex-1 flex min-h-0">
        {/* ---------------- left: player + transcript ---------------- */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="shrink-0 bg-black flex justify-center">
            {media.type === "video" ? (
              <video ref={playerRef} src={streamUrl(media.id)} controls
                className="max-h-[40vh] w-full object-contain" onTimeUpdate={onTime} />
            ) : (
              <audio ref={playerRef} src={streamUrl(media.id)} controls
                className="w-full px-6 py-4" onTimeUpdate={onTime} />
            )}
          </div>

          <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-800 bg-zinc-900/60 shrink-0 text-sm flex-wrap">
            {selectedSegments.length ? (
              <>
                <span className="text-zinc-300 whitespace-nowrap">
                  {selectedSegments.length} line{selectedSegments.length > 1 ? "s" : ""} ·{" "}
                  {fmtTime(selectedSegments[0].start_s)}–{fmtTime(selectedSegments[selectedSegments.length - 1].end_s)}
                </span>
                <button className={`${btnGhost} py-0.5 px-2`} title="Include previous line (shift-↑)"
                  onClick={() => extendSel(-1)}>⊕ prev</button>
                <button className={`${btnGhost} py-0.5 px-2`} title="Include next line (shift-↓)"
                  onClick={() => extendSel(1)}>⊕ next</button>
                <button className={btnGhost} onClick={playSelection}>▶ Play selection</button>
                <button className={btnCls} onClick={() => setShowSave(true)}>Save as Cut (s)</button>
                <button className="text-zinc-500 hover:text-white" onClick={() => { setAnchor(null); setExtent(null); }}>
                  clear (esc)
                </button>
              </>
            ) : (
              <span className="text-zinc-500">
                Click a line to play it · shift-click or shift-↓ to extend the selection across lines
              </span>
            )}
            {savedFlash && <span className="ml-auto text-emerald-400">Cut saved ✓</span>}
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-4 leading-8 text-[15px]">
            {segments.length === 0 && (
              <p className="text-zinc-500 text-center mt-12">No transcript segments.</p>
            )}
            {segments.map((s, i) => {
              const selected = selStart != null && i >= selStart && i <= selEnd;
              return (
                <span key={s.id}
                  ref={(el) => (segEls.current[i] = el)}
                  className={`seg ${i === activeIdx ? "active" : ""} ${selected ? "selected" : ""} ${
                    matched.has(s.id) ? "underline decoration-amber-400 decoration-2" : ""}`}
                  title={`#${s.idx} · ${fmtTime(s.start_s)} → ${fmtTime(s.end_s)}`}
                  onClick={(e) => clickSeg(i, e)}>
                  {s.text}{" "}
                </span>
              );
            })}
          </div>
        </div>

        <DragBar onMouseDown={dragPanel} />

        {/* ---------------- right: Search / Cuts panel ---------------- */}
        <div style={{ width: panelW }} className="shrink-0 flex flex-col min-h-0 border-l border-zinc-800 bg-zinc-950/60">
          <div className="flex gap-1 px-2 pt-1 border-b border-zinc-800 shrink-0">
            {tabBtn("search", "🔍 Search")}
            {tabBtn("cuts", `✂ Cuts (${cuts.length})`)}
          </div>
          {panelTab === "search" ? (
            <SearchPanel mediaId={media.id} onPick={jumpToSearchHit}
              onResults={(rs) => setMatched(new Set(rs.map((r) => r.id)))} />
          ) : (
            <MediaCuts cuts={cuts} folders={folders}
              onPlay={playCut} onShow={showCutInTranscript}
              onEdit={setEditing} onDelete={deleteCut} />
          )}
        </div>
      </div>

      {showSave && selectedSegments.length > 0 && (
        <SaveCutModal user={user} media={media} segments={selectedSegments}
          onClose={() => setShowSave(false)}
          onSaved={() => {
            setAnchor(null); setExtent(null);
            setSavedFlash(true); setTimeout(() => setSavedFlash(false), 2500);
            refreshCuts();
          }} />
      )}
      {editing && (
        <EditCutModal cut={editing} folders={folders}
          onClose={() => setEditing(null)} onSaved={refreshCuts} />
      )}
    </div>
  );
}
