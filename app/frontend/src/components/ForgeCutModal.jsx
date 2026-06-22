/* Forge a modified cut — a mini-Cutter over one cut's track. Slide the start/end
 * boundaries across the surrounding transcript and create a NEW cut (the original
 * is never touched), ready to drop into your draft. */
import { useEffect, useRef, useState } from "react";
import { api, fmtTime, streamUrl } from "./../api";
import { Modal, inputCls, btnCls, btnGhost } from "./ui";

export default function ForgeCutModal({ cut, user, onClose, onCreated }) {
  const trackId = cut.segments?.[0]?.track_id;
  const mediaId = cut.media_id;
  const [segs, setSegs] = useState(null);   // full ordered track segments
  const [a, setA] = useState(0);            // start index into segs
  const [b, setB] = useState(0);            // end index (inclusive)
  const [title, setTitle] = useState(`${cut.title} (edit)`);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const playerRef = useRef();
  const stopAt = useRef(null);
  const lineRefs = useRef({});   // index → element, for scroll-to-active

  useEffect(() => {
    if (trackId == null) { setErr("this cut has no track"); return; }
    api.get(`/api/media/${mediaId}/segments?track_id=${trackId}`).then((rows) => {
      setSegs(rows);
      const ids = new Set((cut.segments || []).map((s) => s.id));
      const idxs = rows.map((r, i) => (ids.has(r.id) ? i : -1)).filter((i) => i >= 0);
      setA(idxs.length ? idxs[0] : 0);
      setB(idxs.length ? idxs[idxs.length - 1] : 0);
    }).catch((e) => setErr(e.message));
  }, [mediaId, trackId, cut]);

  // keep the boundary being adjusted in view as it moves through the transcript
  useEffect(() => { lineRefs.current[a]?.scrollIntoView({ block: "nearest" }); }, [a]);
  useEffect(() => { lineRefs.current[b]?.scrollIntoView({ block: "nearest" }); }, [b]);

  const last = (segs?.length || 1) - 1;
  const onTime = () => { const p = playerRef.current; if (p && stopAt.current != null && p.currentTime >= stopAt.current) { p.pause(); stopAt.current = null; } };
  const seekPlay = (start, end) => {
    const p = playerRef.current; if (!p) return;
    stopAt.current = end;
    const go = () => { p.currentTime = start; p.play().catch(() => {}); };
    if (p.dataset.media !== String(mediaId)) { p.dataset.media = String(mediaId); p.src = streamUrl(mediaId); p.onloadedmetadata = go; } else go();
  };
  const play = () => { if (segs) seekPlay(segs[a].start_s, segs[b].end_s); };   // whole selection

  const create = async () => {
    if (!segs) return;
    setBusy(true); setErr("");
    try {
      const segment_ids = segs.slice(a, b + 1).map((s) => s.id);
      const r = await api.post("/api/cuts", {
        media_id: mediaId, title: title.trim() || "Edited cut",
        segment_ids, tags: [], user_id: user.id });
      onCreated?.(r.id);
      onClose();
    } catch (e) { setErr(e.message); setBusy(false); }
  };

  const step = (label, minus, plus, mOk, pOk, mTip, pTip) => (
    <div className="flex items-center gap-1">
      <span className="text-[10px] uppercase tracking-wide text-zinc-500 w-9">{label}</span>
      <button disabled={!mOk} onClick={minus} title={mTip}
        className="w-7 h-7 rounded-md border border-zinc-700 text-zinc-300 enabled:hover:border-indigo-500 disabled:opacity-30">−</button>
      <button disabled={!pOk} onClick={plus} title={pTip}
        className="w-7 h-7 rounded-md border border-zinc-700 text-zinc-300 enabled:hover:border-indigo-500 disabled:opacity-30">+</button>
    </div>
  );

  return (
    <Modal title="Forge a modified cut" onClose={onClose} wide>
      <div className="space-y-3">
        <input className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} />
        {err && <p className="text-sm text-red-400">{err}</p>}
        {!segs ? <p className="text-sm text-zinc-500">Loading transcript…</p> : (
          <>
            <video ref={playerRef} controls onTimeUpdate={onTime}
              className="w-full rounded-lg bg-black aspect-video object-contain" />
            <div className="flex items-center gap-4">
              {step("Start", () => setA((x) => Math.max(0, x - 1)), () => setA((x) => Math.min(b, x + 1)),
                a > 0, a < b, "Include the previous line", "Drop the first line")}
              {step("End", () => setB((x) => Math.max(a, x - 1)), () => setB((x) => Math.min(last, x + 1)),
                b > a, b < last, "Drop the last line", "Include the next line")}
              <span className="text-xs text-zinc-500 font-mono">
                {fmtTime(segs[a].start_s)}–{fmtTime(segs[b].end_s)} · {b - a + 1} lines
              </span>
              <button className={`${btnGhost} ml-auto`} onClick={play}>▶ preview</button>
            </div>
            <p className="text-[11px] text-zinc-600 -mb-1">Lines in the selection are clickable — tap one to play it.</p>
            <div className="max-h-64 overflow-y-auto rounded-lg border border-zinc-800 p-2 text-[15px] leading-7">
              {segs.map((s, i) => {
                const inRange = i >= a && i <= b;
                return (
                  <span key={s.id} ref={(el) => { lineRefs.current[i] = el; }}
                    onClick={() => inRange && seekPlay(s.start_s, s.end_s)}
                    title={inRange ? "Play this line" : undefined}
                    className={`rounded px-0.5 ${inRange
                      ? "text-zinc-100 bg-indigo-500/10 cursor-pointer hover:bg-indigo-500/30"
                      : "text-zinc-600"}`}>
                    {s.text}{" "}
                  </span>
                );
              })}
            </div>
          </>
        )}
        <div className="flex justify-end gap-2">
          <button className={btnGhost} onClick={onClose}>Cancel</button>
          <button className={btnCls} disabled={busy || !segs} onClick={create}>
            {busy ? "Creating…" : "Create cut"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
