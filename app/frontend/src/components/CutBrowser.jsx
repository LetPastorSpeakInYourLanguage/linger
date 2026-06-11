import { useEffect, useRef, useState } from "react";
import { api, fmtTime } from "../api";
import { Modal, inputCls, btnCls, btnGhost, Tag, Picker, useResizable, DragBar } from "./ui";
import SearchPanel, { RangePreview } from "./SearchPanel";

/* ------------------------------------------------------------ filters */

export const EMPTY_FILTERS = { q: "", tags: [], folders: [], media: [] };

export function filtersToParams(filters) {
  const params = new URLSearchParams();
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.tags.length) params.set("tags", filters.tags.join(","));
  if (filters.folders.length) params.set("folder_ids", filters.folders.map((f) => f.id).join(","));
  if (filters.media.length) params.set("media_ids", filters.media.map((m) => m.id).join(","));
  return params;
}

const hasFilters = (f) => f.q.trim() || f.tags.length || f.folders.length || f.media.length;

/* Chips + searchable add-pickers. Scales: nothing is ever listed in full. */
function FilterBar({ filters, setFilters, tags, folders, media, compact }) {
  const addTag = (name) =>
    !filters.tags.includes(name) &&
    setFilters({ ...filters, tags: [...filters.tags, name] });
  const addFolder = (f) =>
    !filters.folders.some((x) => x.id === f.id) &&
    setFilters({ ...filters, folders: [...filters.folders, f] });
  const addMedia = (m) =>
    !filters.media.some((x) => x.id === m.id) &&
    setFilters({ ...filters, media: [...filters.media, m] });

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <input className={`${inputCls} flex-1 min-w-[160px]`}
          placeholder="Search cuts by title or spoken text…"
          value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} />
        <Picker label="Tag" icon="#" align={compact ? "right" : "left"}
          items={tags.map((t) => ({ key: t.id, label: t.name, icon: "#", hint: `(${t.usage})`, value: t }))}
          onPick={(i) => addTag(i.label)} />
        <Picker label="Folder" icon="📁" align={compact ? "right" : "left"}
          items={folders.map((f) => ({ key: f.id, label: f.name, icon: "📁", value: f }))}
          onPick={(i) => addFolder(i.value)} />
        <Picker label="Media" icon="🎬" align="right"
          items={media.map((m) => ({ key: m.id, label: m.title, icon: m.type === "video" ? "🎬" : "🎙️", value: m }))}
          onPick={(i) => addMedia(i.value)} />
      </div>

      {(filters.tags.length > 0 || filters.folders.length > 0 || filters.media.length > 0) && (
        <div className="flex items-center gap-1.5 flex-wrap text-xs">
          {filters.media.map((m) => (
            <button key={`m${m.id}`} title="Remove filter"
              onClick={() => setFilters({ ...filters, media: filters.media.filter((x) => x.id !== m.id) })}
              className="px-2 py-0.5 rounded-full bg-sky-500/15 border border-sky-500/40 text-sky-300 hover:border-sky-300 max-w-[180px] truncate">
              🎬 {m.title} ×
            </button>
          ))}
          {filters.folders.map((f) => (
            <button key={`f${f.id}`} title="Remove filter"
              onClick={() => setFilters({ ...filters, folders: filters.folders.filter((x) => x.id !== f.id) })}
              className="px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 hover:border-emerald-300">
              📁 {f.name} ×
            </button>
          ))}
          {filters.tags.map((t) => (
            <button key={`t${t}`} title="Remove filter"
              onClick={() => setFilters({ ...filters, tags: filters.tags.filter((x) => x !== t) })}
              className="px-2 py-0.5 rounded-full bg-indigo-500/15 border border-indigo-500/40 text-indigo-300 hover:border-indigo-300">
              #{t} ×
            </button>
          ))}
          <button className="text-zinc-500 hover:text-white ml-1"
            onClick={() => setFilters({ ...EMPTY_FILTERS, q: filters.q })}>
            clear all
          </button>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- modals */

export function EditCutModal({ cut, folders, onClose, onSaved }) {
  const [title, setTitle] = useState(cut.title);
  const [tags, setTags] = useState(cut.tags.join(", "));
  const [folderId, setFolderId] = useState(cut.folder_id ?? "");
  const [note, setNote] = useState(cut.note ?? "");

  const save = async () => {
    await api.patch(`/api/cuts/${cut.id}`, {
      title,
      note,
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
        <input className={inputCls} value={note} onChange={(e) => setNote(e.target.value)}
          placeholder="Note (optional)" />
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

/* ----------------------------------------------------------- browser */

/**
 * The cut browser. Pass `filters`/`setFilters` to control filtering from
 * outside (the Studio does, for right-click "filter by…" actions).
 */
export default function CutBrowser({ user, embedded = false, onAdd,
                                     filters: extFilters, setFilters: setExtFilters,
                                     onPreviewChange }) {
  const [intFilters, setIntFilters] = useState(EMPTY_FILTERS);
  const filters = extFilters ?? intFilters;
  const setFilters = setExtFilters ?? setIntFilters;

  const [cuts, setCuts] = useState([]);
  const [folders, setFolders] = useState([]);
  const [tags, setTags] = useState([]);
  const [media, setMedia] = useState([]);
  const [preview, setPreview] = useState(null);
  const [editing, setEditing] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [showAddTo, setShowAddTo] = useState(false);
  const debounce = useRef();

  const refreshMeta = () => {
    api.get("/api/folders").then(setFolders).catch(() => {});
    api.get("/api/tags").then(setTags).catch(() => {});
    api.get("/api/media").then((m) => setMedia(m.filter((x) => x.status === "ready"))).catch(() => {});
  };

  const refresh = () => {
    api.get(`/api/cuts?${filtersToParams(filters)}`).then(setCuts).catch(() => {});
  };

  useEffect(refreshMeta, []);
  useEffect(() => {
    clearTimeout(debounce.current);
    debounce.current = setTimeout(refresh, 250);
    return () => clearTimeout(debounce.current);
  }, [JSON.stringify(filters)]);

  const folderName = (id) => folders.find((f) => f.id === id)?.name;

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

  const openPreview = (c) => { setPreview(c); onPreviewChange?.(c); };
  const closePreview = () => { setPreview(null); onPreviewChange?.(null); };

  const addTagFilter = (t) =>
    !filters.tags.includes(t) && setFilters({ ...filters, tags: [...filters.tags, t] });
  const addFolderFilter = (id) => {
    const f = folders.find((x) => x.id === id);
    if (f && !filters.folders.some((x) => x.id === id))
      setFilters({ ...filters, folders: [...filters.folders, f] });
  };
  const addMediaFilter = (c) =>
    !filters.media.some((x) => x.id === c.media_id) &&
    setFilters({ ...filters, media: [...filters.media, { id: c.media_id, title: c.media_title }] });

  return (
    <div className="h-full flex flex-col min-w-0">
      <div className="p-3 border-b border-zinc-800 shrink-0">
        <FilterBar filters={filters} setFilters={setFilters}
          tags={tags} folders={folders} media={media} compact={embedded} />
        {!embedded && selected.size > 0 && (
          <button className={`${btnCls} mt-2`} onClick={() => setShowAddTo(true)}>
            Add {selected.size} selected to recomposition
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {cuts.length === 0 && (
          <p className="text-zinc-500 text-sm text-center mt-10">
            No cuts {hasFilters(filters) ? "match these filters" : "yet — open a media file in the Library and select some lines"}.
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
                onClick={() => openPreview(c)} title="Preview">
                ▶ {c.title}
              </button>
              <span className="text-xs text-zinc-500 whitespace-nowrap ml-auto">
                {fmtTime(c.end_s - c.start_s)}
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
            <div className="flex items-center gap-1.5 mt-2 flex-wrap">
              <button onClick={() => addMediaFilter(c)} title="Filter by this media"
                className="text-xs text-sky-400/80 hover:text-sky-300 max-w-[160px] truncate">
                🎬 {c.media_title}
              </button>
              {c.folder_id != null && folderName(c.folder_id) && (
                <button onClick={() => addFolderFilter(c.folder_id)} title="Filter by this folder"
                  className="text-xs text-emerald-400/80 hover:text-emerald-300">
                  📁 {folderName(c.folder_id)}
                </button>
              )}
              {c.tags.map((t) => <Tag key={t} name={t} onClick={() => addTagFilter(t)} />)}
              {c.created_by_name && (
                <span className="text-xs text-zinc-600 ml-auto">by {c.created_by_name}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {preview && <RangePreview item={preview} onClose={closePreview} />}
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

/* ------------------------------------------------------------ page */

/** The Cuts tab: cut browser on the left + the global transcript search
 *  ("the monster" — every subtitle of every media) on a resizable right panel. */
export function CutsPage({ user, openMedia }) {
  const [w, drag] = useResizable("cuts_search_w", 400, 280, 720, true);
  return (
    <div className="h-full flex min-h-0">
      <div className="flex-1 min-w-0">
        <CutBrowser user={user} />
      </div>
      <DragBar onMouseDown={drag} />
      <div style={{ width: w }} className="shrink-0 flex flex-col min-h-0 border-l border-zinc-800 bg-zinc-950/60">
        <div className="px-3 py-2 border-b border-zinc-800 shrink-0 text-sm font-medium">
          🔍 Transcript search <span className="text-zinc-500 font-normal text-xs">across all media</span>
        </div>
        <SearchPanel onOpenMedia={(seg) => openMedia(seg.media_id, seg)} />
      </div>
    </div>
  );
}
