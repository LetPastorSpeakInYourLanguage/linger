/* Audio studio — a three-panel background-bed library that mirrors the Cuts /
 * Assembler workspaces:
 *   • LEFT   — folder tree (drag a bed onto a folder to file it).
 *   • CENTRE — search + tag filters (the same filtering language as cuts) over
 *              the bed list.
 *   • RIGHT  — the selected bed's editor, grouped into cards instead of one
 *              long form.
 */
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { btnCls, btnGhost, inputCls, Picker, Spinner, useResizable, DragBar } from "./ui";

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

function Card({ title, children }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3 space-y-3">
      <p className="text-xs font-medium text-zinc-300">{title}</p>
      {children}
    </div>
  );
}

/* Chip-based tag editor (no more comma-separated raw string). */
function TagInput({ tags, onChange }) {
  const [val, setVal] = useState("");
  const add = (t) => {
    const n = t.trim().replace(/^#/, "").toLowerCase();
    if (n && !tags.includes(n)) onChange([...tags, n]);
    setVal("");
  };
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {tags.map((t) => (
        <span key={t} className="text-xs px-2 py-0.5 rounded-full bg-indigo-500/15 border border-indigo-500/40 text-indigo-300">
          #{t}
          <button className="ml-1 hover:text-white" onClick={() => onChange(tags.filter((x) => x !== t))}>×</button>
        </span>
      ))}
      <input className="bg-zinc-950 border border-zinc-700 rounded-md px-2 py-0.5 text-xs outline-none focus:border-indigo-500 w-24"
        placeholder="add tag…" value={val} onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(val); } }}
        onBlur={() => val.trim() && add(val)} />
    </div>
  );
}

/* Edit one bed's structure and audition it at any length. */
function BedEditor({ asset, folders, onSaved }) {
  const [d, setD] = useState(asset);
  const [previewLen, setPreviewLen] = useState(30);
  const [previewFit, setPreviewFit] = useState(asset.default_fit || "loop");
  const [previewUrl, setPreviewUrl] = useState(null);
  const [rendering, setRendering] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const srcRef = useRef();

  useEffect(() => { setD(asset); setPreviewFit(asset.default_fit || "loop"); setPreviewUrl(null); }, [asset]);

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
        folder: d.folder || "",
        tags: (d.tags || []).map((t) => t.trim()).filter(Boolean),
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
      setPreviewUrl(`/api/audio-assets/${asset.id}/preview?length=${previewLen}&fit=${previewFit}&t=${Date.now()}`);
    } catch (e) { setErr(e.message); }
    setRendering(false);
  };

  return (
    <div className="space-y-4 max-w-2xl">
      <Card title="Bed & source">
        <label className="text-xs text-zinc-400 block">Name
          <input className={inputCls} value={d.name || ""} onChange={(e) => setD({ ...d, name: e.target.value })} />
        </label>
        <p className="text-[11px] text-zinc-500">
          Original ({d.duration_s ? `${d.duration_s.toFixed(1)}s` : "?"}) — scrub to find trim / loop points, then ⏱ grab:
        </p>
        <audio ref={srcRef} controls src={`/api/audio-assets/${asset.id}/audio`} className="w-full" />
      </Card>

      <Card title="Filing">
        <label className="text-xs text-zinc-400 block">Folder <span className="text-zinc-600">(use “/” to nest)</span>
          <input className={inputCls} list="bed-folder-list" value={d.folder || ""} placeholder="e.g. Action/Tension"
            onChange={(e) => setD({ ...d, folder: e.target.value })} />
          <datalist id="bed-folder-list">
            {folders.map((f) => <option key={f.name} value={f.name} />)}
          </datalist>
        </label>
        <div>
          <p className="text-xs text-zinc-400 mb-1">Tags</p>
          <TagInput tags={d.tags || []} onChange={(tags) => setD({ ...d, tags })} />
        </div>
      </Card>

      <Card title="Trim & loop">
        <div className="grid grid-cols-2 gap-3">
          <NumberField label="Trim start (s)" value={d.trim_start_s} onGrab={grab("trim_start_s")}
            onChange={(v) => setD({ ...d, trim_start_s: v ?? 0 })} />
          <NumberField label="Trim end (s)" value={d.trim_end_s} onGrab={grab("trim_end_s")}
            hint="blank = end of file" onChange={(v) => setD({ ...d, trim_end_s: v })} />
          <NumberField label="Loop region start (s)" value={d.loop_start_s} onGrab={grab("loop_start_s")}
            hint="optional — clean section to repeat" onChange={(v) => setD({ ...d, loop_start_s: v })} />
          <NumberField label="Loop region end (s)" value={d.loop_end_s} onGrab={grab("loop_end_s")}
            onChange={(v) => setD({ ...d, loop_end_s: v })} />
        </div>
      </Card>

      <Card title="Fades & defaults">
        <div className="grid grid-cols-2 gap-3 items-end">
          <NumberField label="Fade in (s)" value={d.fade_in_s} onChange={(v) => setD({ ...d, fade_in_s: v ?? 0 })} />
          <NumberField label="Fade out (s)" value={d.fade_out_s} onChange={(v) => setD({ ...d, fade_out_s: v ?? 0 })} />
          <label className="text-xs text-zinc-400">Default fit
            <select className={inputCls} value={d.default_fit || "loop"}
              onChange={(e) => setD({ ...d, default_fit: e.target.value })}>
              <option value="loop">loop</option>
              <option value="stretch">stretch</option>
              <option value="trim">trim</option>
            </select>
          </label>
          <label className="text-xs text-zinc-400">Default volume {Math.round((d.default_gain ?? 1) * 100)}%
            <input type="range" min="0" max="1.5" step="0.05" className="w-full accent-indigo-500"
              value={d.default_gain ?? 1} onChange={(e) => setD({ ...d, default_gain: Number(e.target.value) })} />
          </label>
        </div>
      </Card>

      <Card title="Audition at length">
        <div className="flex items-end gap-2">
          <label className="text-xs text-zinc-400">Seconds
            <input type="number" min="1" step="1" className={inputCls}
              value={previewLen} onChange={(e) => setPreviewLen(Number(e.target.value))} />
          </label>
          <label className="text-xs text-zinc-400">Fit
            <select className={inputCls} value={previewFit} onChange={(e) => setPreviewFit(e.target.value)}>
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
      </Card>

      {err && <p className="text-sm text-red-400">{err}</p>}
      <div className="flex justify-end">
        <button className={btnCls} disabled={saving} onClick={save}>{saving ? "Saving…" : "Save bed"}</button>
      </div>
    </div>
  );
}

export default function AudioStudio({ user }) {
  const [assets, setAssets] = useState([]);
  const [folders, setFolders] = useState([]);
  const [audioTags, setAudioTags] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [selId, setSelId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [folder, setFolder] = useState("");      // selected folder filter ("" = all)
  const [q, setQ] = useState("");
  const [tagFilter, setTagFilter] = useState([]);
  const [dragId, setDragId] = useState(null);
  const [overFolder, setOverFolder] = useState(null);
  const [listW, dragList] = useResizable("audio_list_w", 340, 260, 520);

  const refresh = () => {
    const p = new URLSearchParams();
    if (folder) p.set("folder", folder);
    if (q.trim()) p.set("q", q.trim());
    if (tagFilter.length) p.set("tags", tagFilter.join(","));
    api.get(`/api/audio-assets?${p}`).then((rows) => {
      setAssets(rows); setLoaded(true);
      setSelId((cur) => (rows.some((r) => r.id === cur && r.filename) ? cur
        : rows.find((r) => r.filename)?.id ?? null));
    }).catch((e) => { setErr(e.message); setLoaded(true); });
    api.get("/api/audio-folders").then(setFolders).catch(() => {});
    api.get("/api/audio-tags").then(setAudioTags).catch(() => {});
  };

  useEffect(() => { refresh(); }, [folder, q, tagFilter]);   // eslint-disable-line
  useEffect(() => {
    if (!assets.some((a) => !a.filename)) return;
    const t = setInterval(refresh, 2500);
    return () => clearInterval(t);
  }, [assets]);   // eslint-disable-line

  const upload = async (file) => {
    if (!file) return;
    setBusy(true); setErr("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("name", file.name.replace(/\.[^.]+$/, ""));
      fd.append("folder", folder);              // upload into the selected folder
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
  const moveTo = async (id, dest) => { await api.patch(`/api/audio-assets/${id}`, { folder: dest }); refresh(); };
  const addTagFilter = (t) => !tagFilter.includes(t) && setTagFilter([...tagFilter, t]);

  const selected = assets.find((a) => a.id === selId);
  const folderRow = (name, lbl, depth, count) => {
    const on = folder === name;
    const isOver = overFolder === name;
    return (
      <button key={name || "__all"} onClick={() => setFolder(name)}
        onDragOver={(e) => { if (dragId != null) { e.preventDefault(); setOverFolder(name); } }}
        onDragLeave={() => setOverFolder((o) => (o === name ? null : o))}
        onDrop={() => { if (dragId != null) moveTo(dragId, name); setOverFolder(null); setDragId(null); }}
        style={{ paddingLeft: 10 + depth * 14 }}
        className={`w-full text-left pr-2 py-1 text-sm flex items-center gap-1.5 ${
          isOver ? "bg-indigo-500/20 ring-1 ring-indigo-500" : on ? "bg-zinc-800 text-white" : "hover:bg-zinc-900 text-zinc-300"}`}>
        <span>{name === "" ? "🗂" : "📁"}</span>
        <span className="truncate flex-1">{lbl}</span>
        {count != null && <span className="text-[10px] text-zinc-600">{count}</span>}
      </button>
    );
  };

  return (
    <div className="h-full flex min-h-0">
      {/* ===== LEFT: folder tree ===== */}
      <div className="w-56 shrink-0 border-r border-zinc-800 flex flex-col min-h-0">
        <div className="p-3 border-b border-zinc-800 flex items-center justify-between">
          <h1 className="font-semibold">Audio beds</h1>
          <label className={`${btnCls} cursor-pointer`}>
            {busy ? "…" : "+ Upload"}
            <input type="file" accept="audio/*" className="hidden" onChange={(e) => upload(e.target.files[0])} />
          </label>
        </div>
        <div className="px-3 py-2 border-b border-zinc-800 text-[10px] uppercase tracking-wide text-zinc-500">Folders</div>
        <div className="flex-1 overflow-y-auto py-1">
          {folderRow("", "All beds", 0, null)}
          {folders.map((f) => folderRow(f.name, f.leaf, f.depth + 1, f.count))}
          {folders.length === 0 && <p className="px-3 py-2 text-[11px] text-zinc-600">Set a bed's Folder to organise beds here.</p>}
        </div>
      </div>

      {/* ===== CENTRE: filters + bed list ===== */}
      <div style={{ width: listW }} className="shrink-0 flex flex-col min-h-0 border-r border-zinc-800">
        <div className="p-2 border-b border-zinc-800 space-y-2 shrink-0">
          <div className="flex items-center gap-2">
            <input className={`${inputCls} flex-1 !py-1.5`} placeholder="Search beds by name…"
              value={q} onChange={(e) => setQ(e.target.value)} />
            <Picker label="Tag" icon="#" align="right"
              items={audioTags.map((t) => ({ key: t.id, label: t.name, icon: "#", hint: `(${t.usage})` }))}
              onPick={(i) => addTagFilter(i.label)} />
          </div>
          {(folder || tagFilter.length > 0) && (
            <div className="flex items-center gap-1.5 flex-wrap text-xs">
              {folder && (
                <button onClick={() => setFolder("")} title="Clear folder filter"
                  className="px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 hover:border-emerald-300">
                  📁 {folder} ×
                </button>
              )}
              {tagFilter.map((t) => (
                <button key={t} onClick={() => setTagFilter(tagFilter.filter((x) => x !== t))} title="Remove tag filter"
                  className="px-2 py-0.5 rounded-full bg-indigo-500/15 border border-indigo-500/40 text-indigo-300 hover:border-indigo-300">
                  #{t} ×
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="flex-1 overflow-y-auto">
          {!loaded && <div className="p-4 text-zinc-400 flex gap-2 items-center"><Spinner /> Loading</div>}
          {loaded && assets.length === 0 && (
            <p className="p-4 text-sm text-zinc-500">No beds match. Upload music/ambience, or clear the filters.</p>
          )}
          {assets.map((a) => (
            <button key={a.id} onClick={() => a.filename && setSelId(a.id)}
              draggable={!!a.filename} onDragStart={() => setDragId(a.id)} onDragEnd={() => setDragId(null)}
              className={`w-full text-left px-3 py-2 border-b border-zinc-900 group flex items-center gap-2 cursor-grab ${
                a.id === selId ? "bg-zinc-800" : "hover:bg-zinc-900"} ${!a.filename ? "opacity-60" : ""}`}>
              <span className="text-lg">🎵</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">{a.name}</span>
                <span className="block text-[11px] text-zinc-500 truncate">
                  {!a.filename ? "processing…"
                    : `${a.duration_s ? a.duration_s.toFixed(1) + "s" : ""} · ${a.default_fit}`}
                  {a.folder ? ` · 📁 ${a.folder}` : ""}
                </span>
                {a.tags?.length > 0 && (
                  <span className="flex flex-wrap gap-1 mt-0.5">
                    {a.tags.map((t) => <span key={t} className="text-[10px] text-indigo-300/80">#{t}</span>)}
                  </span>
                )}
              </span>
              <span onClick={(e) => { e.stopPropagation(); remove(a.id); }}
                className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 text-xs">delete</span>
            </button>
          ))}
        </div>
      </div>
      <DragBar onMouseDown={dragList} />

      {/* ===== RIGHT: editor ===== */}
      <div className="flex-1 min-w-0 overflow-y-auto p-6">
        {err && <p className="text-sm text-red-400 mb-3">{err}</p>}
        {!selected ? (
          <div className="text-center text-zinc-500 mt-24">
            <p className="text-lg">Prepare reusable background beds.</p>
            <p className="text-sm mt-1">
              Pick a bed to trim, set a clean loop region, add fades, file it in a folder + tags,
              then audition it at any length. Add beds to a recomposition from the Studio's 🎵 Background panel.
            </p>
          </div>
        ) : (
          <BedEditor asset={selected} folders={folders} onSaved={refresh} />
        )}
      </div>
    </div>
  );
}
