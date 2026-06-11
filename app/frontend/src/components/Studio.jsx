import { useEffect, useRef, useState } from "react";
import { api, fmtTime, streamUrl } from "../api";
import { inputCls, btnCls, btnGhost } from "./ui";
import CutBrowser from "./CutBrowser";

/* Sequenced playback across multiple source media files. */
function useSequencePlayer(cuts) {
  const playerRef = useRef();
  const [playingIdx, setPlayingIdx] = useState(-1);
  const stateRef = useRef({ idx: -1, cuts: [] });
  stateRef.current.cuts = cuts;

  const playFrom = (idx) => {
    const cut = stateRef.current.cuts[idx];
    const p = playerRef.current;
    if (!cut || !p) { setPlayingIdx(-1); return; }
    stateRef.current.idx = idx;
    setPlayingIdx(idx);
    const src = streamUrl(cut.media_id);
    const seekAndPlay = () => {
      p.currentTime = cut.start_s;
      p.play().catch(() => {});
    };
    if (!p.src.endsWith(src)) {
      p.src = src;
      p.addEventListener("loadedmetadata", seekAndPlay, { once: true });
    } else {
      seekAndPlay();
    }
  };

  const onTime = () => {
    const { idx, cuts } = stateRef.current;
    const p = playerRef.current;
    if (idx < 0 || !p || !cuts[idx]) return;
    if (p.currentTime >= cuts[idx].end_s) {
      if (idx + 1 < cuts.length) playFrom(idx + 1);
      else { p.pause(); stateRef.current.idx = -1; setPlayingIdx(-1); }
    }
  };

  const stop = () => {
    playerRef.current?.pause();
    stateRef.current.idx = -1;
    setPlayingIdx(-1);
  };

  return { playerRef, playingIdx, playFrom, onTime, stop };
}

function RecompEditor({ user, recompId, back }) {
  const [recomp, setRecomp] = useState(null);
  const [dragIdx, setDragIdx] = useState(null);
  const { playerRef, playingIdx, playFrom, onTime, stop } = useSequencePlayer(recomp?.cuts ?? []);

  const load = () => api.get(`/api/recompositions/${recompId}`).then(setRecomp);
  useEffect(() => { load(); }, [recompId]);

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

  if (!recomp) return null;
  const total = recomp.cuts.reduce((acc, c) => acc + (c.end_s - c.start_s), 0);
  const hasVideo = recomp.cuts.some((c) => c.media_type === "video");

  return (
    <div className="h-full flex min-h-0">
      {/* left: cut search */}
      <div className="w-[420px] shrink-0 border-r border-zinc-800 min-h-0">
        <CutBrowser user={user} embedded onAdd={addCut} />
      </div>

      {/* right: sequence + player */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center gap-3 px-4 py-2 border-b border-zinc-800 shrink-0">
          <button onClick={back} className="text-zinc-400 hover:text-white text-sm">← Studio</button>
          <h1 className="font-semibold truncate">{recomp.title}</h1>
          <span className="text-xs text-zinc-500">{recomp.cuts.length} cuts · {fmtTime(total)}</span>
          <div className="ml-auto flex gap-2">
            <button className={btnCls} disabled={!recomp.cuts.length}
              onClick={() => playFrom(0)}>▶ Play all</button>
            <button className={btnGhost} onClick={stop}>Stop</button>
          </div>
        </div>

        <div className="shrink-0 bg-black flex justify-center">
          {hasVideo ? (
            <video ref={playerRef} controls className="max-h-[38vh] w-full object-contain"
              onTimeUpdate={onTime} />
          ) : (
            <audio ref={playerRef} controls className="w-full px-6 py-3" onTimeUpdate={onTime} />
          )}
        </div>

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
              className={`rounded-lg border p-3 flex items-center gap-3 cursor-grab ${
                playingIdx === i ? "border-amber-500 bg-amber-500/10" : "border-zinc-800 bg-zinc-900"}`}>
              <span className="text-zinc-600 text-sm w-6 text-right">{i + 1}.</span>
              <button onClick={() => playFrom(i)} title="Play from here"
                className="text-indigo-400 hover:text-indigo-300">▶</button>
              <div className="min-w-0 flex-1">
                <p className="font-medium truncate">{c.title}</p>
                <p className="text-xs text-zinc-500 truncate">
                  {c.media_title} · {fmtTime(c.start_s)}–{fmtTime(c.end_s)} ({fmtTime(c.end_s - c.start_s)})
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
