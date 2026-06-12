import { useEffect, useMemo, useRef, useState } from "react";
import { api, fmtTime, streamUrl } from "../api";
import { Modal, inputCls, btnCls, btnGhost, Tag, modalOpen, useResizable, DragBar } from "./ui";
import SearchPanel from "./SearchPanel";
import { EditCutModal } from "./CutBrowser";
import SubtitleEditor from "./SubtitleEditor";

/* Attach another subtitle file (upload or host path) as a new track. */
function AddTrackModal({ mediaId, onClose, onDone }) {
  const [mode, setMode] = useState("upload");
  const [file, setFile] = useState(null);
  const [path, setPath] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const [opts, setOpts] = useState(null); // /api/transcribe/options
  const [model, setModel] = useState(() => localStorage.getItem("whisper_model") || "");
  const [language, setLanguage] = useState(() => localStorage.getItem("whisper_language") || "");

  useEffect(() => {
    api.get("/api/transcribe/options").then((o) => {
      setOpts(o);
      setModel((m) => m || o.default_model);
    }).catch(() => {});
  }, []);

  const submit = async () => {
    setErr("");
    try {
      if (mode === "whisper") {
        localStorage.setItem("whisper_model", model);
        localStorage.setItem("whisper_language", language);
        await api.post(`/api/media/${mediaId}/transcribe`, { model, language });
      } else {
        const fd = new FormData();
        if (mode === "upload") {
          if (!file) return;
          fd.append("file", file);
        } else {
          if (!path.trim()) return;
          fd.append("path", path);
        }
        fd.append("name", name);
        await api.upload(`/api/media/${mediaId}/subtitles`, fd);
      }
      onDone(); onClose();
    } catch (e) { setErr(e.message); }
  };

  const tab = (m, label) => (
    <button key={m} onClick={() => setMode(m)}
      className={`px-3 py-1.5 rounded-lg text-sm ${
        mode === m ? "bg-indigo-600 text-white" : "bg-zinc-950 text-zinc-400 hover:text-white"}`}>
      {label}
    </button>
  );

  return (
    <Modal title="Add subtitle track" onClose={onClose}>
      <div className="space-y-3">
        <div className="flex gap-2">
          {tab("upload", "Upload file")}{tab("path", "From this PC")}{tab("whisper", "🎙 Generate (Whisper)")}
        </div>
        {mode === "upload" && (
          <input type="file" accept=".srt,.vtt" className="block text-sm"
            onChange={(e) => setFile(e.target.files[0])} />
        )}
        {mode === "path" && (
          <input className={inputCls} placeholder={"D:\\movies\\notebook.en.srt"}
            value={path} onChange={(e) => setPath(e.target.value)} />
        )}
        {mode === "whisper" && (
          <>
            <div className="flex gap-2">
              <div className="flex-1">
                <label className="text-xs text-zinc-400">Model</label>
                <select className={inputCls} value={model}
                  onChange={(e) => setModel(e.target.value)}>
                  {(opts?.models || (model ? [model] : ["small"])).map((m) => (
                    <option key={m} value={m}>
                      {m}{opts && m === opts.default_model ? " (default)" : ""}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex-1">
                <label className="text-xs text-zinc-400">Language hint — optional</label>
                <input className={inputCls} placeholder="auto-detect (or en, es, am…)"
                  value={language} onChange={(e) => setLanguage(e.target.value)} />
              </div>
            </div>
            <p className="text-xs text-zinc-400 bg-zinc-950 rounded-lg p-3">
              Transcribes the audio in the background into its own track
              (named after the engine + model). Bigger models are more accurate
              but slower{opts?.device === "cpu" && " — on CPU, medium/large can take a long time"}.
              {opts?.engine
                ? <> Engine: <b>{opts.engine}</b> on <b>{opts?.device}</b>.</>
                : <> No engine detected — <code>pip install whisperx</code> on the server.</>}
              {" "}The track appears here when it's done; watch progress in the ⚙ jobs panel.
            </p>
          </>
        )}
        {mode !== "whisper" && (
          <input className={inputCls} placeholder="Track name (e.g. English, Director's notes) — optional"
            value={name} onChange={(e) => setName(e.target.value)} />
        )}
        <p className="text-xs text-zinc-500">
          Tracks are alternative subtitle sets for the same video — cuts always
          play from the source media, whichever track they were made from.
        </p>
        {err && <p className="text-sm text-red-400">{err}</p>}
        <div className="flex justify-end gap-2">
          <button className={btnGhost} onClick={onClose}>Cancel</button>
          <button className={btnCls} onClick={submit}>
            {mode === "whisper" ? "Start transcription" : "Add track"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

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
  const [tracks, setTracks] = useState([]);
  const [trackId, setTrackId] = useState(null);
  const [editMode, setEditMode] = useState(false);
  const [showAddTrack, setShowAddTrack] = useState(false);
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

  const refreshTracks = () =>
    api.get(`/api/media/${mediaId}/tracks`).then((ts) => {
      setTracks(ts);
      setTrackId((cur) =>
        ts.some((t) => t.id === cur) ? cur
          : (initialSeg?.track_id && ts.some((t) => t.id === initialSeg.track_id))
            ? initialSeg.track_id
            : ts[0]?.id ?? null);
    }).catch(() => {});

  const refreshSegments = () => {
    if (trackId == null) { setSegments([]); return; }
    api.get(`/api/media/${mediaId}/segments?track_id=${trackId}`).then(setSegments);
  };

  useEffect(() => {
    api.get(`/api/media/${mediaId}`).then(setMedia);
    api.get("/api/folders").then(setFolders).catch(() => {});
    refreshTracks();
    refreshCuts();
  }, [mediaId]);

  useEffect(() => {
    setAnchor(null); setExtent(null);
    refreshSegments();
  }, [trackId]);

  // while a transcription runs in the background, poll for the new track
  useEffect(() => {
    if (!media || media.status === "ready") return;
    const t = setInterval(() => {
      api.get(`/api/media/${mediaId}`).then(setMedia).catch(() => {});
      refreshTracks();
    }, 3000);
    return () => clearInterval(t);
  }, [media?.status, mediaId]);

  const removeTrack = async () => {
    const t = tracks.find((x) => x.id === trackId);
    if (!t || !confirm(`Delete subtitle track "${t.name}" (${t.segment_count} lines)?`)) return;
    try {
      await api.del(`/api/tracks/${t.id}`);
      setTrackId(null);
      refreshTracks(); refreshCuts();
    } catch (e) {
      alert(`Can't delete: ${e.message}`);
    }
  };

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

  /* Mouse selection: click = one line; drag across lines = a sequence;
     shift-click = extend from the anchor. Playback starts on release. */
  const draggingRef = useRef(false);
  const didDragRef = useRef(false);

  const segMouseDown = (i, e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    stopAtRef.current = null;
    if (e.shiftKey && anchor != null) { setExtent(i); return; }
    setAnchor(i); setExtent(null);
    draggingRef.current = true;
    didDragRef.current = false;
  };

  const segMouseEnter = (i) => {
    if (!draggingRef.current) return;
    didDragRef.current = true;
    setExtent(i);
  };

  const selRef = useRef({ anchor: null, extent: null });
  useEffect(() => { selRef.current = { anchor, extent }; }, [anchor, extent]);

  useEffect(() => {
    const up = () => {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      const { anchor: a, extent: ex } = selRef.current;
      if (a == null || !segments.length) return;
      if (didDragRef.current && ex != null && ex !== a) {
        const lo = Math.min(a, ex), hi = Math.max(a, ex);
        stopAtRef.current = segments[hi]?.end_s ?? null; // play the dragged range
        seekTo(segments[lo]);
      } else {
        seekTo(segments[a]); // simple click: play that line
      }
    };
    window.addEventListener("mouseup", up);
    return () => window.removeEventListener("mouseup", up);
  }, [segments]);

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
      else if (e.key === "s" && !editMode && selectedSegments.length) setShowSave(true);
      else if (e.key === "Escape") { setAnchor(null); setExtent(null); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedSegments, anchor, extent, activeIdx, segments, editMode]);

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
      <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-800 shrink-0 flex-wrap">
        <button onClick={back} className="text-zinc-400 hover:text-white text-sm">← Library</button>
        <h1 className="font-semibold truncate">{media.title}</h1>

        <div className="flex items-center gap-1.5 ml-2">
          {tracks.length > 0 && (
            <select value={trackId ?? ""} onChange={(e) => setTrackId(Number(e.target.value))}
              className="bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1 text-xs outline-none focus:border-indigo-500 max-w-[180px]"
              title="Subtitle track">
              {tracks.map((t) => (
                <option key={t.id} value={t.id}>{t.name} ({t.segment_count})</option>
              ))}
            </select>
          )}
          <button className={`${btnGhost} !px-2 !py-1 text-xs`} title="Add another subtitle track"
            onClick={() => setShowAddTrack(true)}>＋ subtitle</button>
          {trackId != null && (
            <>
              <button title={editMode ? "Back to the cut maker" : "Edit this track: timings, text, add/remove lines"}
                className={`!px-2 !py-1 text-xs rounded-lg border ${
                  editMode ? "border-amber-500 text-amber-400" : "border-zinc-700 hover:border-zinc-500"}`}
                onClick={() => setEditMode(!editMode)}>
                ✎ {editMode ? "editing" : "edit"}
              </button>
              <button className="text-zinc-600 hover:text-red-400 text-xs px-1" title="Delete this track"
                onClick={removeTrack}>🗑</button>
            </>
          )}
        </div>

        {media.status !== "ready" && (
          <span className="text-xs text-amber-400 animate-pulse">
            ⏳ {media.status_detail || media.status}
          </span>
        )}
        <span className="ml-auto text-xs text-zinc-600 hidden lg:block">
          space play/pause · ←/→ seek · drag / shift-↑↓ select lines · s save cut
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

          {!editMode && (
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
                Click a line to play it · <b className="text-zinc-300">drag across lines</b> to select a sequence · shift-click / shift-↓ also extends
              </span>
            )}
            {savedFlash && <span className="ml-auto text-emerald-400">Cut saved ✓</span>}
          </div>
          )}

          {editMode && trackId != null ? (
            <SubtitleEditor trackId={trackId} segments={segments}
              getTime={() => playerRef.current?.currentTime ?? 0}
              playRange={(s, e) => {
                const p = playerRef.current;
                if (!p) return;
                stopAtRef.current = e;
                p.currentTime = s;
                p.play().catch(() => {});
              }}
              onChanged={() => { refreshSegments(); refreshCuts(); refreshTracks(); }} />
          ) : (
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
                  onMouseDown={(e) => segMouseDown(i, e)}
                  onMouseEnter={() => segMouseEnter(i)}>
                  {s.text}{" "}
                </span>
              );
            })}
          </div>
          )}
        </div>

        <DragBar onMouseDown={dragPanel} />

        {/* ---------------- right: Search / Cuts panel ---------------- */}
        <div style={{ width: panelW }} className="shrink-0 flex flex-col min-h-0 border-l border-zinc-800 bg-zinc-950/60">
          <div className="flex gap-1 px-2 pt-1 border-b border-zinc-800 shrink-0">
            {tabBtn("search", "🔍 Search")}
            {tabBtn("cuts", `✂ Cuts (${cuts.length})`)}
          </div>
          {panelTab === "search" ? (
            <SearchPanel mediaId={media.id} trackId={trackId} onPick={jumpToSearchHit}
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
      {showAddTrack && (
        <AddTrackModal mediaId={mediaId} onClose={() => setShowAddTrack(false)}
          onDone={() => { refreshTracks(); }} />
      )}
    </div>
  );
}
