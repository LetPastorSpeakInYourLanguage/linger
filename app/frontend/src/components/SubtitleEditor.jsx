import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { inputCls, btnCls, btnGhost } from "./ui";

/* ---- time helpers: display "m:ss.cc", accept "h:mm:ss.s" | "m:ss" | "83.5" */
export function fmtT(s) {
  if (s == null) return "";
  s = Math.max(0, s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  const sec = (s % 60).toFixed(2).padStart(5, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

export function parseT(str) {
  const parts = String(str).trim().split(":");
  if (parts.some((p) => p === "" || isNaN(Number(p)))) return null;
  let s = 0;
  for (const p of parts) s = s * 60 + Number(p);
  return s >= 0 ? s : null;
}

/* One row being edited: times + text + set-from-player buttons. */
function EditRow({ seg, getTime, onDone, onCancel }) {
  const [start, setStart] = useState(fmtT(seg.start_s));
  const [end, setEnd] = useState(fmtT(seg.end_s));
  const [text, setText] = useState(seg.text);
  const [err, setErr] = useState("");

  const save = async () => {
    const s = parseT(start), e = parseT(end);
    if (s == null || e == null) return setErr("bad time format — use m:ss.cc or seconds");
    if (e <= s) return setErr("end must be after start");
    try {
      await api.patch(`/api/segments/${seg.id}`, { text, start_s: s, end_s: e });
      onDone();
    } catch (ex) { setErr(ex.message); }
  };

  const keys = (e) => {
    if (e.key === "Enter") { e.preventDefault(); save(); }
    if (e.key === "Escape") { e.stopPropagation(); onCancel(); }
  };

  return (
    <div className="rounded-lg border border-indigo-500 bg-zinc-900 p-2 space-y-2" onKeyDown={keys}>
      <div className="flex items-center gap-1.5 text-xs">
        <input className={`${inputCls} !w-24 !px-2 !py-1`} value={start}
          onChange={(e) => setStart(e.target.value)} title="Start time" />
        <button className={`${btnGhost} !px-1.5 !py-0.5 text-xs`} title="Set start = player position"
          onClick={() => setStart(fmtT(getTime()))}>⏱</button>
        <span className="text-zinc-600">→</span>
        <input className={`${inputCls} !w-24 !px-2 !py-1`} value={end}
          onChange={(e) => setEnd(e.target.value)} title="End time" />
        <button className={`${btnGhost} !px-1.5 !py-0.5 text-xs`} title="Set end = player position"
          onClick={() => setEnd(fmtT(getTime()))}>⏱</button>
        <span className="ml-auto flex gap-2">
          <button className={`${btnCls} !py-0.5`} onClick={save}>Save ⏎</button>
          <button className={`${btnGhost} !py-0.5`} onClick={onCancel}>Cancel</button>
        </span>
      </div>
      <textarea className={`${inputCls} resize-y`} rows={2} autoFocus value={text}
        onChange={(e) => setText(e.target.value)} />
      {err && <p className="text-xs text-red-400">{err}</p>}
    </div>
  );
}

/* Regex batch bar: preview → then replace or delete what matched. */
function BatchBar({ trackId, onChanged, onMatches }) {
  const [pattern, setPattern] = useState("");
  const [replacement, setReplacement] = useState("");
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async (action) => {
    if (!pattern.trim()) return;
    if (action === "delete" && !confirm("Delete EVERY line matching this regex?")) return;
    setBusy(true); setStatus(null);
    try {
      const r = await api.post(`/api/tracks/${trackId}/batch`, {
        pattern, action, replacement, case_sensitive: caseSensitive,
      });
      if (action === "preview") {
        setStatus(`${r.count} line(s) match` +
          (r.cuts_affected ? ` — careful: ${r.cuts_affected} cut(s) use them` : ""));
        onMatches(new Set(r.matches.map((m) => m.id)));
      } else {
        setStatus(`done: ${r.changed ?? 0} changed, ${r.deleted ?? 0} deleted` +
          (r.cuts_deleted ? `, ${r.cuts_deleted} now-empty cut(s) removed` : ""));
        onMatches(new Set());
        onChanged();
      }
    } catch (e) { setStatus(`error: ${e.message}`); }
    setBusy(false);
  };

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/70 p-2 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-zinc-500 whitespace-nowrap">Batch (regex):</span>
        <input className={`${inputCls} flex-1 min-w-[140px] !py-1 font-mono text-xs`}
          placeholder="pattern, e.g. \\[.*?\\] or ♪" value={pattern}
          onChange={(e) => { setPattern(e.target.value); setStatus(null); }} />
        <input className={`${inputCls} flex-1 min-w-[120px] !py-1 font-mono text-xs`}
          placeholder="replacement (for Replace)" value={replacement}
          onChange={(e) => setReplacement(e.target.value)} />
        <label className="flex items-center gap-1 text-xs text-zinc-400 whitespace-nowrap">
          <input type="checkbox" className="accent-indigo-500" checked={caseSensitive}
            onChange={(e) => setCaseSensitive(e.target.checked)} /> case
        </label>
        <button className={`${btnGhost} !py-1`} disabled={busy} onClick={() => run("preview")}>Preview</button>
        <button className={`${btnGhost} !py-1`} disabled={busy} onClick={() => run("replace")}>Replace</button>
        <button className={`${btnGhost} !py-1 hover:border-red-500 hover:text-red-400`} disabled={busy}
          onClick={() => run("delete")}>Delete matched</button>
      </div>
      {status && <p className="text-xs text-amber-300">{status}</p>}
    </div>
  );
}

/**
 * Subtitle editor: fix timings, edit text, insert and remove lines, and run
 * regex batch operations — all on the currently selected track.
 */
export default function SubtitleEditor({ trackId, segments, getTime, playRange, onChanged }) {
  const [editingId, setEditingId] = useState(null);
  const [matches, setMatches] = useState(new Set());
  const listRef = useRef();

  useEffect(() => { setEditingId(null); setMatches(new Set()); }, [trackId]);

  const EPS = 0.05;

  // Insert a line after `seg`. When there's a silent gap to the next line it fills
  // the WHOLE gap with a "[gap]" caption you then edit (e.g. [live music playing]) —
  // a real segment for a stretch of video that has no speech.
  const insertAfter = async (seg, text = "[gap]") => {
    const start = seg ? seg.end_s : 0;
    const next = segments.find((s) => s.start_s >= start && s.id !== seg?.id);
    const end = next ? Math.max(start + 0.3, next.start_s) : start + 2.5;
    const created = await api.post("/api/segments", { track_id: trackId, start_s: start, end_s: end, text });
    onChanged();
    setEditingId(created.id);
  };

  // Stretch a line's own boundary into the adjacent silence — no new line, just
  // more time on this cue (e.g. room for a longer dub in the target language).
  const extendStart = async (s, prev) => { await api.patch(`/api/segments/${s.id}`, { start_s: prev.end_s }); onChanged(); };
  const extendEnd = async (s, next) => { await api.patch(`/api/segments/${s.id}`, { end_s: next.start_s }); onChanged(); };

  const remove = async (seg) => {
    try {
      await api.del(`/api/segments/${seg.id}`);
    } catch (e) {
      if (!confirm(`${e.message}. Delete anyway? (Cuts left empty are removed.)`)) return;
      await api.del(`/api/segments/${seg.id}?force=1`);
    }
    onChanged();
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="p-2 shrink-0 space-y-2">
        <BatchBar trackId={trackId} onChanged={onChanged} onMatches={setMatches} />
        <p className="text-[11px] text-zinc-600 px-1">
          Click a line to edit · ▶ plays it · ＋ fills the gap after with a
          <span className="text-zinc-400"> [gap]</span> caption · <span className="font-mono text-zinc-400">[</span>/<span className="font-mono text-zinc-400">]</span> stretch
          this line into the surrounding silence (room for dubbing).
        </p>
      </div>

      <div ref={listRef} className="flex-1 overflow-y-auto px-2 pb-4 space-y-1">
        {segments.length === 0 && (
          <div className="text-center mt-10">
            <p className="text-zinc-500 text-sm mb-3">This track has no lines yet.</p>
            <button className={btnCls} onClick={() => insertAfter(null, "…")}>+ Add first line</button>
          </div>
        )}
        {segments.map((s, i) => {
          if (editingId === s.id) {
            return (
              <EditRow key={s.id} seg={s} getTime={getTime}
                onDone={() => { setEditingId(null); onChanged(); }}
                onCancel={() => setEditingId(null)} />
            );
          }
          const prev = segments[i - 1], next = segments[i + 1];
          const gapBefore = prev && prev.end_s < s.start_s - EPS;
          const gapAfter = next && s.end_s < next.start_s - EPS;
          return (
            <div key={s.id}
              className={`rounded-lg border px-2 py-1.5 flex items-center gap-2 group cursor-pointer ${
                matches.has(s.id) ? "border-amber-500/70 bg-amber-500/10" : "border-zinc-800/70 bg-zinc-900/40 hover:border-zinc-600"}`}
              onClick={() => setEditingId(s.id)}>
              <span className="text-[11px] text-zinc-600 w-8 text-right shrink-0">{s.idx}</span>
              <span className="text-[11px] text-zinc-500 font-mono whitespace-nowrap shrink-0">
                {fmtT(s.start_s)}–{fmtT(s.end_s)}
              </span>
              <span className="text-sm truncate flex-1">{s.text}</span>
              <span className="flex gap-1.5 shrink-0 opacity-0 group-hover:opacity-100 text-xs">
                {gapBefore && (
                  <button className="text-zinc-400 hover:text-indigo-300 font-mono" title="Extend start into the silence before (room for dubbing)"
                    onClick={(e) => { e.stopPropagation(); extendStart(s, prev); }}>[</button>
                )}
                {gapAfter && (
                  <button className="text-zinc-400 hover:text-indigo-300 font-mono" title="Extend end into the silence after"
                    onClick={(e) => { e.stopPropagation(); extendEnd(s, next); }}>]</button>
                )}
                <button className="text-indigo-400 hover:text-indigo-300" title="Play this line"
                  onClick={(e) => { e.stopPropagation(); playRange(s.start_s, s.end_s); }}>▶</button>
                <button className="text-zinc-400 hover:text-zinc-50" title={gapAfter ? "Fill the gap after with a [gap] caption line" : "Insert a line after this one"}
                  onClick={(e) => { e.stopPropagation(); insertAfter(s); }}>＋</button>
                <button className="text-zinc-400 hover:text-red-400" title="Delete this line"
                  onClick={(e) => { e.stopPropagation(); remove(s); }}>✕</button>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
