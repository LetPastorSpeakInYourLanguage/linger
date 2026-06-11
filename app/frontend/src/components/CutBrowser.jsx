import { useEffect, useRef, useState } from "react";
import { api, fmtTime, streamUrl } from "../api";
import { Modal, inputCls, btnCls, btnGhost, Tag } from "./ui";

export function CutPreview({ cut, onClose }) {
  const ref = useRef();
  useEffect(() => {
    const p = ref.current;
    if (!p) return;
    const onLoaded = () => { p.currentTime = cut.start_s; p.play().catch(() => {}); };
    const onTime = () => { if (p.currentTime >= cut.end_s) p.pause(); };
    p.addEventListener("loadedmetadata", onLoaded);
    p.addEventListener("timeupdate", onTime);
    return () => { p.removeEventListener("loadedmetadata", onLoaded); p.removeEventListener("timeupdate", onTime); };
  }, [cut]);

  return (
    <Modal title={cut.title} onClose={onClose} wide>
      {cut.media_type === "video" ? (
        <video ref={ref} src={streamUrl(cut.media_id)} controls className="w-full max-h-[55vh] bg-black" />
      ) : (
        <audio ref={ref} src={streamUrl(cut.media_id)} controls className="w-full" />
      )}
      <p className="text-sm text-zinc-400 mt-3">“{cut.text}”</p>
      <p className="text-xs text-zinc-500 mt-1">
        {cut.media_title} · {fmtTime(cut.start_s)} → {fmtTime(cut.end_s)}
      </p>
    </Modal>
  );
}

function EditCutModal({ cut, folders, onClose, onSaved }) {
  const [title, setTitle] = useState(cut.title);
  const [tags, setTags] = useState(cut.tags.join(", "));
  const [folderId, setFolderId] = useState(cut.folder_id ?? "");

  const save = async () => {
    await api.patch(`/api/cuts/${cut.id}`, {
      title,
      tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
      folder_id: folderId ? Number(folderId) : null,
      clear_folder: !folderId,
    });
    onSaved(); onClose();
  };

  return (
    <Modal title="Edit cut" onClose={onClose}>
      <div className="space-y-3">
        <input className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} />
        <input className={inputCls} value={tags} onChange={(e) => setTags(e.target.value)}
          placeholder="tags, comma separated" />
        <select className={inputCls} value={folderId} onChange={(e) => setFolderId(e.target.value)}>
          <option value="">No folder</option>
          {folders.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
        </select>
        <div className="flex justify-end gap-2">
          <button className={btnGhost} onClick={onClose}>Cancel</button>
          <button className={btnCls} onClick={save}>Save</button>
        </div>
      </div>
    </Modal>
  );
}

function AddToRecompModal({ cutIds, onClose, onDone, user }) {
  const [recomps, setRecomps] = useState([]);
  const [newTitle, setNewTitle] = useState("");
  useEffect(() => { api.get("/api/recompositions").then(setRecomps); }, []);

  const add = async (recompId) => {
    const r = await api.get(`/api/recompositions/${recompId}`);
    const existing = r.cuts.map((c) => c.id);
    await api.put(`/api/recompositions/${recompId}/cuts`, { cut_ids: [...existing, ...cutIds] });
    onDone(); onClose();
  };

  const createAndAdd = async () => {
    if (!newTitle.trim()) return;
    const r = await api.post("/api/recompositions", { title: newTitle.trim(), user_id: user.id });
    await api.put(`/api/recompositions/${r.id}/cuts`, { cut_ids: cutIds });
    onDone(); onClose();
  };

  return (
    <Modal title={`Add ${cutIds.length} cut${cutIds.length > 1 ? "s" : ""} to…`} onClose={onClose}>
      <div className="space-y-2">
        {recomps.map((r) => (
          <button key={r.id} onClick={() => add(r.id)}
            className="w-full text-left px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 hover:border-indigo-500">
            {r.title} <span className="text-zinc-500 text-xs">({r.cut_count} cuts)</span>
          </button>
        ))}
        <div className="flex gap-2 pt-2">
          <input className={inputCls} placeholder="New recomposition title…"
            value={newTitle} onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && createAndAdd()} />
          <button className={btnCls} onClick={createAndAdd}>Create</button>
        </div>
      </div>
    </Modal>
  );
}

export default function CutBrowser({ user, embedded = false, onAdd }) {
  const [cuts, setCuts] = useState([]);
  const [folders, setFolders] = useState([]);
  const [tags, setTags] = useState([]);
  const [q, setQ] = useState("");
  const [folderId, setFolderId] = useState(null);
  const [tag, setTag] = useState("");
  const [preview, setPreview] = useState(null);
  const [editing, setEditing] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [showAddTo, setShowAddTo] = useState(false);
  const debounce = useRef();

  const refresh = () => {
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (folderId != null) params.set("folder_id", folderId);
    if (tag) params.set("tag", tag);
    api.get(`/api/cuts?${params}`).then(setCuts).catch(() => {});
    api.get("/api/folders").then(setFolders).catch(() => {});
    api.get("/api/tags").then(setTags).catch(() => {});
  };

  useEffect(() => {
    clearTimeout(debounce.current);
    debounce.current = setTimeout(refresh, 250);
    return () => clearTimeout(debounce.current);
  }, [q, folderId, tag]);

  const toggleSel = (id) => {
    const next = new Set(selected);
    next.has(id) ? next.delete(id) : next.add(id);
    setSelected(next);
  };

  const removeCut = async (cut) => {
    if (!confirm(`Delete cut "${cut.title}"?`)) return;
    await api.del(`/api/cuts/${cut.id}`);
    refresh();
  };

  return (
    <div className={`h-full flex ${embedded ? "" : "p-0"}`}>
      {!embedded && (
        <aside className="w-52 shrink-0 border-r border-zinc-800 p-4 space-y-4 overflow-y-auto">
          <div>
            <h3 className="text-xs uppercase text-zinc-500 mb-2">Folders</h3>
            <button onClick={() => setFolderId(null)}
              className={`block w-full text-left text-sm px-2 py-1 rounded ${folderId == null ? "bg-zinc-800" : "hover:bg-zinc-900"}`}>
              All cuts
            </button>
            {folders.map((f) => (
              <button key={f.id} onClick={() => setFolderId(f.id === folderId ? null : f.id)}
                className={`block w-full text-left text-sm px-2 py-1 rounded ${folderId === f.id ? "bg-zinc-800" : "hover:bg-zinc-900"}`}>
                📁 {f.name}
              </button>
            ))}
          </div>
          {tags.length > 0 && (
            <div>
              <h3 className="text-xs uppercase text-zinc-500 mb-2">Tags</h3>
              <div className="flex flex-wrap gap-1.5">
                {tags.map((t) => (
                  <Tag key={t.id} name={t.name} active={tag === t.name}
                    onClick={() => setTag(tag === t.name ? "" : t.name)} />
                ))}
              </div>
            </div>
          )}
        </aside>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center gap-2 p-3 border-b border-zinc-800 shrink-0">
          <input className={inputCls} placeholder="Search cuts by title or spoken text…"
            value={q} onChange={(e) => setQ(e.target.value)} />
          {embedded && tags.length > 0 && (
            <select className={`${inputCls} w-36`} value={tag} onChange={(e) => setTag(e.target.value)}>
              <option value="">all tags</option>
              {tags.map((t) => <option key={t.id} value={t.name}>#{t.name}</option>)}
            </select>
          )}
          {!embedded && selected.size > 0 && (
            <button className={`${btnCls} whitespace-nowrap`} onClick={() => setShowAddTo(true)}>
              Add {selected.size} to recomposition
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {cuts.length === 0 && (
            <p className="text-zinc-500 text-sm text-center mt-10">
              No cuts {q || tag || folderId != null ? "match" : "yet — open a media file in the Library and select some lines"}.
            </p>
          )}
          {cuts.map((c) => (
            <div key={c.id}
              className={`rounded-lg border p-3 group ${
                selected.has(c.id) ? "border-indigo-500 bg-indigo-500/10" : "border-zinc-800 bg-zinc-900"}`}>
              <div className="flex items-center gap-2">
                {!embedded && (
                  <input type="checkbox" checked={selected.has(c.id)} onChange={() => toggleSel(c.id)}
                    className="accent-indigo-500" />
                )}
                <button className="font-medium text-left truncate hover:text-indigo-300"
                  onClick={() => setPreview(c)} title="Preview">
                  ▶ {c.title}
                </button>
                <span className="text-xs text-zinc-500 whitespace-nowrap ml-auto">
                  {fmtTime(c.end_s - c.start_s)} · {c.media_title}
                </span>
                {embedded ? (
                  <button className={`${btnCls} py-0.5`} onClick={() => onAdd(c)}>+ Add</button>
                ) : (
                  <span className="opacity-0 group-hover:opacity-100 flex gap-2 text-xs">
                    <button className="text-zinc-400 hover:text-white" onClick={() => setEditing(c)}>edit</button>
                    <button className="text-zinc-400 hover:text-red-400" onClick={() => removeCut(c)}>delete</button>
                  </span>
                )}
              </div>
              <p className="text-sm text-zinc-400 mt-1 line-clamp-2">“{c.text}”</p>
              {(c.tags.length > 0 || c.created_by_name) && (
                <div className="flex items-center gap-1.5 mt-2">
                  {c.tags.map((t) => <Tag key={t} name={t} onClick={() => setTag(t)} />)}
                  {c.created_by_name && (
                    <span className="text-xs text-zinc-600 ml-auto">by {c.created_by_name}</span>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {preview && <CutPreview cut={preview} onClose={() => setPreview(null)} />}
      {editing && (
        <EditCutModal cut={editing} folders={folders}
          onClose={() => setEditing(null)} onSaved={refresh} />
      )}
      {showAddTo && (
        <AddToRecompModal cutIds={[...selected]} user={user}
          onClose={() => setShowAddTo(false)}
          onDone={() => setSelected(new Set())} />
      )}
    </div>
  );
}
