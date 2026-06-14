import { useEffect, useRef, useState } from "react";
import { api, fmtTime, streamUrl } from "../api";
import { Modal, inputCls, Spinner } from "./ui";

/* Plays just a time range of one media — used to preview a search hit or cut. */
export function RangePreview({ item, onClose }) {
  const ref = useRef();
  useEffect(() => {
    const p = ref.current;
    if (!p) return;
    const onLoaded = () => { p.currentTime = item.start_s; p.play().catch(() => {}); };
    const onTime = () => { if (p.currentTime >= item.end_s) p.pause(); };
    p.addEventListener("loadedmetadata", onLoaded);
    p.addEventListener("timeupdate", onTime);
    return () => { p.removeEventListener("loadedmetadata", onLoaded); p.removeEventListener("timeupdate", onTime); };
  }, [item]);

  return (
    <Modal title={item.title || item.media_title} onClose={onClose} wide>
      {item.media_type === "video" ? (
        <video ref={ref} src={streamUrl(item.media_id)} controls className="w-full max-h-[55vh] bg-black" />
      ) : (
        <audio ref={ref} src={streamUrl(item.media_id)} controls className="w-full" />
      )}
      {item.text && <p className="text-sm text-zinc-400 mt-3">“{item.text}”</p>}
      <p className="text-xs text-zinc-500 mt-1">
        {item.media_title} · {fmtTime(item.start_s)} → {fmtTime(item.end_s)} · Esc to close
      </p>
    </Modal>
  );
}

/* Highlight exact query words inside a result line. */
function Highlight({ text, q }) {
  const words = q.toLowerCase().match(/\w+/g) || [];
  if (!words.length) return text;
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "ig");
  const parts = text.split(re);
  return parts.map((p, i) =>
    words.includes(p.toLowerCase())
      ? <mark key={i} className="bg-amber-400/30 text-amber-200 rounded px-0.5">{p}</mark> : p);
}

/**
 * The search panel. Modes:
 *  - media mode  (mediaId set): searches one transcript; clicking a result
 *    calls onPick(segment) — the parent scrolls/seeks.
 *  - global mode (no mediaId): searches EVERY transcript in the database;
 *    each result can be previewed in place or opened in its media.
 */
export default function SearchPanel({ mediaId = null, trackId = null, onPick = null,
                                      onOpenMedia = null, onResults = null,
                                      placeholder }) {
  const [q, setQ] = useState("");
  const [fuzzy, setFuzzy] = useState(true);
  const [smart, setSmart] = useState(() => localStorage.getItem("search_smart") === "1");
  const [smartAvail, setSmartAvail] = useState(false);
  const [results, setResults] = useState([]);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const debounce = useRef();
  const seq = useRef(0);

  useEffect(() => {
    api.get("/api/embed/status").then((s) => setSmartAvail(!!s.available)).catch(() => {});
  }, []);

  useEffect(() => {
    clearTimeout(debounce.current);
    if (!q.trim()) {
      setResults([]); setBusy(false); onResults?.([]);
      return;
    }
    setBusy(true);
    debounce.current = setTimeout(async () => {
      const mine = ++seq.current;
      try {
        const params = new URLSearchParams({
          q: q.trim(), fuzzy: fuzzy ? "1" : "0",
          smart: smart && smartAvail ? "1" : "0", limit: "80" });
        if (mediaId != null) params.set("media_id", mediaId);
        if (mediaId != null && trackId != null) params.set("track_id", trackId);
        const rs = await api.get(`/api/search/segments?${params}`);
        if (mine === seq.current) { setResults(rs); onResults?.(rs); }
      } catch { /* ignore */ }
      if (mine === seq.current) setBusy(false);
    }, 250);
    return () => clearTimeout(debounce.current);
  }, [q, fuzzy, smart, smartAvail, mediaId, trackId]);

  const toggleSmart = (v) => { setSmart(v); localStorage.setItem("search_smart", v ? "1" : "0"); };

  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="p-3 space-y-2 shrink-0 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <input className={inputCls} autoFocus
            placeholder={placeholder || (mediaId != null ? "Search this transcript…" : "Search all transcripts in the library…")}
            value={q} onChange={(e) => setQ(e.target.value)} />
          {busy && <Spinner />}
        </div>
        <div className="flex items-center gap-3 text-xs text-zinc-400 select-none">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input type="checkbox" className="accent-indigo-500" checked={fuzzy}
              onChange={(e) => setFuzzy(e.target.checked)} />
            Fuzzy
          </label>
          <label className={`flex items-center gap-1.5 ${smartAvail ? "cursor-pointer" : "opacity-40 cursor-not-allowed"}`}
            title={smartAvail ? "Semantic search — finds it by meaning, not just words"
              : "Install sentence-transformers and build the index to enable semantic search"}>
            <input type="checkbox" className="accent-indigo-500" checked={smart && smartAvail}
              disabled={!smartAvail} onChange={(e) => toggleSmart(e.target.checked)} />
            ✨ Smart (semantic)
          </label>
          {q.trim() && !busy && (
            <span className="ml-auto text-zinc-500">{results.length} hit{results.length === 1 ? "" : "s"}</span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {q.trim() && !busy && results.length === 0 && (
          <p className="text-sm text-zinc-500 text-center mt-8">Nothing found{fuzzy ? "" : " — try fuzzy match"}.</p>
        )}
        {!q.trim() && (
          <p className="text-sm text-zinc-600 text-center mt-8 px-4">
            {mediaId != null
              ? "Type to search this transcript. Click a hit to jump there."
              : "Type to search every subtitle segment of every media file."}
          </p>
        )}
        {results.map((r) => (
          <div key={r.id}
            onClick={() => onPick ? onPick(r) : setPreview(r)}
            className="rounded-lg border border-zinc-800 bg-zinc-900 hover:border-indigo-500/70 p-2.5 cursor-pointer group">
            <p className="text-sm leading-snug"><Highlight text={r.text} q={q} /></p>
            <div className="flex items-center gap-2 mt-1.5 text-xs text-zinc-500">
              {r.match === "fuzzy" && !r.methods && (
                <span className="px-1.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/30"
                  title="Fuzzy match — similarity score">
                  ~{Math.round(r.score * 100)}%
                </span>
              )}
              {r.match === "semantic" && (
                <span className="px-1.5 rounded-full bg-violet-500/15 text-violet-300 border border-violet-500/30"
                  title="Found by meaning (semantic)">✨ semantic</span>
              )}
              <span>{fmtTime(r.start_s)}</span>
              {mediaId == null && <span className="truncate">· {r.media_title}</span>}
              <span className="ml-auto flex gap-2 opacity-0 group-hover:opacity-100">
                <button className="hover:text-white"
                  onClick={(e) => { e.stopPropagation(); setPreview(r); }}>▶ preview</button>
                {onOpenMedia && (
                  <button className="hover:text-white"
                    onClick={(e) => { e.stopPropagation(); onOpenMedia(r); }}>open media ↗</button>
                )}
              </span>
            </div>
          </div>
        ))}
      </div>

      {preview && <RangePreview item={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}
