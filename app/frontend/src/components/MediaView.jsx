import { useEffect, useMemo, useRef, useState } from "react";
import { api, fmtTime, streamUrl } from "../api";
import { Modal, inputCls, btnCls, btnGhost } from "./ui";

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

export default function MediaView({ user, mediaId, back }) {
  const [media, setMedia] = useState(null);
  const [segments, setSegments] = useState([]);
  const [anchor, setAnchor] = useState(null);   // segment idx
  const [extent, setExtent] = useState(null);   // segment idx
  const [activeIdx, setActiveIdx] = useState(-1);
  const [showSave, setShowSave] = useState(false);
  const [filter, setFilter] = useState("");
  const [savedFlash, setSavedFlash] = useState(false);
  const playerRef = useRef();
  const stopAtRef = useRef(null);

  useEffect(() => {
    api.get(`/api/media/${mediaId}`).then(setMedia);
    api.get(`/api/media/${mediaId}/segments`).then(setSegments);
  }, [mediaId]);

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
    // binary search for active segment
    let lo = 0, hi = segments.length - 1, found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (segments[mid].start_s <= t) { if (t <= segments[mid].end_s + 0.3) found = mid; lo = mid + 1; }
      else hi = mid - 1;
    }
    setActiveIdx(found);
  };

  const seekTo = (s) => {
    const p = playerRef.current;
    if (!p) return;
    p.currentTime = s.start_s;
    p.play().catch(() => {});
  };

  const clickSeg = (i, e) => {
    if (e.shiftKey && anchor != null) setExtent(i);
    else { setAnchor(i); setExtent(null); }
    stopAtRef.current = null;
    seekTo(segments[i]);
  };

  const playSelection = () => {
    if (!selectedSegments.length) return;
    stopAtRef.current = selectedSegments[selectedSegments.length - 1].end_s;
    seekTo(selectedSegments[0]);
  };

  const matches = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return new Set();
    return new Set(segments.filter((s) => s.text.toLowerCase().includes(q)).map((s) => s.idx));
  }, [filter, segments]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if (e.code === "Space") { e.preventDefault();
        const p = playerRef.current;
        p && (p.paused ? p.play() : p.pause());
      }
      if (e.key === "s" && selectedSegments.length) setShowSave(true);
      if (e.key === "Escape") { setAnchor(null); setExtent(null); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedSegments]);

  if (!media) return null;

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-800 shrink-0">
        <button onClick={back} className="text-zinc-400 hover:text-white text-sm">← Library</button>
        <h1 className="font-semibold truncate">{media.title}</h1>
        <input className="ml-auto bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1 text-sm outline-none focus:border-indigo-500 w-64"
          placeholder="Find in transcript…" value={filter} onChange={(e) => setFilter(e.target.value)} />
      </div>

      <div className="shrink-0 bg-black flex justify-center">
        {media.type === "video" ? (
          <video ref={playerRef} src={streamUrl(media.id)} controls
            className="max-h-[42vh] w-full object-contain" onTimeUpdate={onTime} />
        ) : (
          <audio ref={playerRef} src={streamUrl(media.id)} controls
            className="w-full px-6 py-4" onTimeUpdate={onTime} />
        )}
      </div>

      <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-800 bg-zinc-900/60 shrink-0 text-sm">
        {selectedSegments.length ? (
          <>
            <span className="text-zinc-300">
              {selectedSegments.length} selected · {fmtTime(selectedSegments[0].start_s)}–{fmtTime(selectedSegments[selectedSegments.length - 1].end_s)}
            </span>
            <button className={btnGhost} onClick={playSelection}>▶ Play selection</button>
            <button className={btnCls} onClick={() => setShowSave(true)}>Save as Cut (s)</button>
            <button className="text-zinc-500 hover:text-white" onClick={() => { setAnchor(null); setExtent(null); }}>
              clear (esc)
            </button>
          </>
        ) : (
          <span className="text-zinc-500">
            Click a line to play it · shift-click to extend the selection · space pauses
          </span>
        )}
        {savedFlash && <span className="ml-auto text-emerald-400">Cut saved ✓</span>}
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 leading-8 text-[15px] max-w-4xl mx-auto w-full">
        {segments.length === 0 && (
          <p className="text-zinc-500 text-center mt-12">No transcript segments.</p>
        )}
        {segments.map((s, i) => {
          const selected = selStart != null && i >= selStart && i <= selEnd;
          const matched = matches.has(s.idx);
          return (
            <span key={s.id}
              className={`seg ${i === activeIdx ? "active" : ""} ${selected ? "selected" : ""} ${
                matched ? "underline decoration-amber-400 decoration-2" : ""}`}
              title={`#${s.idx} · ${fmtTime(s.start_s)} → ${fmtTime(s.end_s)}`}
              onClick={(e) => clickSeg(i, e)}>
              {s.text}{" "}
            </span>
          );
        })}
      </div>

      {showSave && selectedSegments.length > 0 && (
        <SaveCutModal user={user} media={media} segments={selectedSegments}
          onClose={() => setShowSave(false)}
          onSaved={() => {
            setAnchor(null); setExtent(null);
            setSavedFlash(true); setTimeout(() => setSavedFlash(false), 2500);
          }} />
      )}
    </div>
  );
}
