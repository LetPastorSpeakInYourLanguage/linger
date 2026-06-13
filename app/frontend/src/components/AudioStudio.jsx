import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { btnCls, btnGhost, inputCls, Spinner } from "./ui";

const FIT_HINT = {
  loop: "repeat the bed (its loop region if set) to fill any length",
  stretch: "time-stretch the bed to the exact length (tempo changes)",
  trim: "play once, padded with silence / cut to the length",
};

function NumberField({ label, value, onChange, step = 0.1, min = 0, hint, onGrab }) {
  return (
    <label className="text-xs text-zinc-400 block">
      <span className="flex items-center justify-between">
        {label}
        {onGrab && (
          <button type="button" className="text-[10px] text-indigo-400 hover:text-indigo-300"
            onClick={onGrab} title="Use the player's current time">⏱ grab</button>
        )}
      </span>
      <input type="number" step={step} min={min} className={inputCls}
        value={value ?? ""} onChange={(e) =>
          onChange(e.target.value === "" ? null : Number(e.target.value))} />
      {hint && <span className="text-[10px] text-zinc-600">{hint}</span>}
    </label>
  );
}

/* Edit one bed's structure and audition it at any length. */
function BedEditor({ asset, onSaved }) {
  const [d, setD] = useState(asset);
  const [previewLen, setPreviewLen] = useState(30);
  const [previewFit, setPreviewFit] = useState(asset.default_fit || "loop");
  const [previewUrl, setPreviewUrl] = useState(null);
  const [rendering, setRendering] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const srcRef = useRef();

  useEffect(() => { setD(asset); setPreviewFit(asset.default_fit || "loop"); }, [asset]);

  const grab = (field) => () => {
    const t = srcRef.current?.currentTime;
    if (t != null) setD((p) => ({ ...p, [field]: Math.round(t * 100) / 100 }));
  };

  const save = async () => {
    setSaving(true); setErr("");
    try {
      const body = {
        name: d.name,
        trim_start_s: d.trim_start_s ?? 0,
        fade_in_s: d.fade_in_s ?? 0,
        fade_out_s: d.fade_out_s ?? 0,
        default_gain: d.default_gain ?? 1,
        default_fit: d.default_fit || "loop",
      };
      if (d.trim_end_s == null) body.clear_trim_end = true;
      else body.trim_end_s = d.trim_end_s;
      if (d.loop_start_s == null || d.loop_end_s == null) body.clear_loop = true;
      else { body.loop_start_s = d.loop_start_s; body.loop_end_s = d.loop_end_s; }
      await api.patch(`/api/audio-assets/${asset.id}`, body);
      onSaved();
    } catch (e) { setErr(e.message); }
    setSaving(false);
  };

  const renderPreview = async () => {
    setRendering(true); setErr("");
    try {
      await save();  // preview reflects the saved structure
      const url = `/api/audio-assets/${asset.id}/preview?length=${previewLen}`
        + `&fit=${previewFit}&t=${Date.now()}`;
      setPreviewUrl(url);
    } catch (e) { setErr(e.message); }
    setRendering(false);
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="text-xs text-zinc-400">Name</label>
        <input className={inputCls} value={d.name || ""}
          onChange={(e) => setD({ ...d, name: e.target.value })} />
        <p className="text-xs text-zinc-500 mt-1">
          Original ({d.duration_s ? `${d.duration_s.toFixed(1)}s` : "?"}) — scrub to find trim / loop points:
        </p>
        <audio ref={srcRef} controls src={`/api/audio-assets/${asset.id}/audio`}
          className="w-full mt-1" />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <NumberField label="Trim start (s)" value={d.trim_start_s} onGrab={grab("trim_start_s")}
          onChange={(v) => setD({ ...d, trim_start_s: v ?? 0 })} />
        <NumberField label="Trim end (s)" value={d.trim_end_s} onGrab={grab("trim_end_s")}
          hint="blank = end of file" onChange={(v) => setD({ ...d, trim_end_s: v })} />
        <NumberField label="Fade in (s)" value={d.fade_in_s}
          onChange={(v) => setD({ ...d, fade_in_s: v ?? 0 })} />
        <NumberField label="Fade out (s)" value={d.fade_out_s}
          onChange={(v) => setD({ ...d, fade_out_s: v ?? 0 })} />
        <NumberField label="Loop region start (s)" value={d.loop_start_s} onGrab={grab("loop_start_s")}
          hint="optional — clean section to repeat" onChange={(v) => setD({ ...d, loop_start_s: v })} />
        <NumberField label="Loop region end (s)" value={d.loop_end_s} onGrab={grab("loop_end_s")}
          onChange={(v) => setD({ ...d, loop_end_s: v })} />
      </div>

      <div className="grid grid-cols-2 gap-3 items-end">
        <label className="text-xs text-zinc-400">Default fit
          <select className={inputCls} value={d.default_fit || "loop"}
            onChange={(e) => setD({ ...d, default_fit: e.target.value })}>
            <option value="loop">loop</option>
            <option value="stretch">stretch</option>
            <option value="trim">trim</option>
          </select>
        </label>
        <label className="text-xs text-zinc-400">Default volume {Math.round((d.default_gain ?? 1) * 100)}%
          <input type="range" min="0" max="1.5" step="0.05" className="w-full"
            value={d.default_gain ?? 1}
            onChange={(e) => setD({ ...d, default_gain: Number(e.target.value) })} />
        </label>
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3 space-y-2">
        <p className="text-xs text-zinc-300 font-medium">Audition at length</p>
        <div className="flex items-end gap-2">
          <label className="text-xs text-zinc-400">Seconds
            <input type="number" min="1" step="1" className={inputCls}
              value={previewLen} onChange={(e) => setPreviewLen(Number(e.target.value))} />
          </label>
          <label className="text-xs text-zinc-400">Fit
            <select className={inputCls} value={previewFit}
              onChange={(e) => setPreviewFit(e.target.value)}>
              <option value="loop">loop</option>
              <option value="stretch">stretch</option>
              <option value="trim">trim</option>
            </select>
          </label>
          <button className={btnGhost} disabled={rendering} onClick={renderPreview}>
            {rendering ? "Rendering…" : "Render & play"}
          </button>
        </div>
        <p className="text-[11px] text-zinc-600">{FIT_HINT[previewFit]}</p>
        {previewUrl && <audio key={previewUrl} controls autoPlay src={previewUrl} className="w-full" />}
      </div>

      {err && <p className="text-sm text-red-400">{err}</p>}
      <div className="flex justify-end">
        <button className={btnCls} disabled={saving} onClick={save}>
          {saving ? "Saving…" : "Save bed"}
        </button>
      </div>
    </div>
  );
}

export default function AudioStudio({ user }) {
  const [assets, setAssets] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [selId, setSelId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const refresh = () => api.get("/api/audio-assets").then((rows) => {
    setAssets(rows); setLoaded(true);
    setSelId((cur) => (rows.some((r) => r.id === cur) ? cur : rows[0]?.id ?? null));
  }).catch((e) => { setErr(e.message); setLoaded(true); });

  useEffect(() => { refresh(); }, []);

  const upload = async (file) => {
    if (!file) return;
    setBusy(true); setErr("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("name", file.name.replace(/\.[^.]+$/, ""));
      fd.append("user_id", user.id);
      const a = await api.upload("/api/audio-assets", fd);
      await refresh();
      setSelId(a.id);
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  const remove = async (id) => {
    if (!confirm("Delete this bed (and any layers using it)?")) return;
    await api.del(`/api/audio-assets/${id}`);
    refresh();
  };

  const selected = assets.find((a) => a.id === selId);

  return (
    <div className="h-full flex min-h-0">
      <div className="w-72 shrink-0 border-r border-zinc-800 flex flex-col">
        <div className="p-3 border-b border-zinc-800 flex items-center justify-between">
          <h1 className="font-semibold">Audio beds</h1>
          <label className={`${btnCls} cursor-pointer`}>
            {busy ? "…" : "+ Upload"}
            <input type="file" accept="audio/*" className="hidden"
              onChange={(e) => upload(e.target.files[0])} />
          </label>
        </div>
        <div className="flex-1 overflow-y-auto">
          {!loaded && <div className="p-4 text-zinc-400 flex gap-2 items-center"><Spinner /> Loading</div>}
          {loaded && assets.length === 0 && (
            <p className="p-4 text-sm text-zinc-500">
              No beds yet. Upload music or ambience to prepare reusable background tracks.
            </p>
          )}
          {assets.map((a) => (
            <button key={a.id} onClick={() => setSelId(a.id)}
              className={`w-full text-left px-3 py-2 border-b border-zinc-900 group flex items-center gap-2 ${
                a.id === selId ? "bg-zinc-800" : "hover:bg-zinc-900"}`}>
              <span className="text-lg">🎵</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">{a.name}</span>
                <span className="block text-[11px] text-zinc-500">
                  {a.duration_s ? `${a.duration_s.toFixed(1)}s` : ""} · {a.default_fit}
                </span>
              </span>
              <span onClick={(e) => { e.stopPropagation(); remove(a.id); }}
                className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 text-xs">
                delete
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 min-w-0 overflow-y-auto p-6">
        {err && <p className="text-sm text-red-400 mb-3">{err}</p>}
        {!selected && (
          <div className="text-center text-zinc-500 mt-24">
            <p className="text-lg">Prepare reusable background beds.</p>
            <p className="text-sm mt-1">
              Trim, set a clean loop region, add fades, then audition the bed at any length.
              Add it to any recomposition from the Studio's 🎵 Background panel.
            </p>
          </div>
        )}
        {selected && (
          <div className="max-w-2xl">
            <BedEditor asset={selected} onSaved={refresh} />
          </div>
        )}
      </div>
    </div>
  );
}
