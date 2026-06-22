import { useEffect, useRef, useState } from "react";
import { api, fmtTime } from "../api";
import { Modal, inputCls, btnCls, btnGhost, Tag, Picker, useResizable, DragBar } from "./ui";
import SearchPanel, { RangePreview } from "./SearchPanel";
import TranslationPanel from "./TranslationPanel";

/* Turn a cut into a reusable background-audio bed — whole audio or music-only. */
function ToBedModal({ cut, user, onClose }) {
  const [mode, setMode] = useState("full");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const make = async () => {
    setBusy(true); setErr("");
    try {
      await api.post(`/api/cuts/${cut.id}/to-bg-audio`,
                     { mode, name: name.trim(), user_id: user.id });
      onClose(true);
    } catch (e) { setErr(e.message); setBusy(false); }
  };

  const opt = (val, title, desc) => (
    <label className={`block rounded-lg border p-3 cursor-pointer ${
      mode === val ? "border-indigo-500 bg-indigo-500/10" : "border-zinc-700 hover:border-zinc-500"}`}>
      <div className="flex items-center gap-2">
        <input type="radio" name="bedmode" className="accent-indigo-500"
          checked={mode === val} onChange={() => setMode(val)} />
        <span className="font-medium text-sm">{title}</span>
      </div>
      <p className="text-xs text-zinc-500 mt-1 ml-6">{desc}</p>
    </label>
  );

  return (
    <Modal title={`Make background bed — ${cut.title}`} onClose={() => onClose(false)}>
      <div className="space-y-3">
        {opt("full", "Full audio", "Use the whole cut's audio as the bed.")}
        {opt("accompaniment", "Music only (remove vocals)",
             "Separate with Demucs and keep just the music / ambience.")}
        <input className={inputCls} placeholder="Bed name (optional)"
          value={name} onChange={(e) => setName(e.target.value)} />
        {err && <p className="text-sm text-red-400">{err}</p>}
        <p className="text-xs text-zinc-500">
          It renders in the background and appears in the <b>Audio</b> tab when ready.
        </p>
        <div className="flex justify-end gap-2">
          <button className={btnGhost} onClick={() => onClose(false)}>Cancel</button>
          <button className={btnCls} disabled={busy} onClick={make}>
            {busy ? "Starting…" : "Create bed"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

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
export function FilterBar({ filters, setFilters, tags, folders, media, compact }) {
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
          items={folders.map((f) => ({
            key: f.id,
            label: f.name,                                   // full path so search matches ancestors
            icon: "📁",
            hint: f.cut_count != null ? `(${f.cut_count})` : undefined,
            value: f,
          }))}
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
          <button className="text-zinc-500 hover:text-zinc-50 ml-1"
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

/* Nested-folder manager with a desktop-file-manager feel: drag a folder onto
 * another to nest it, "＋" to make a sub-folder, double-click to rename inline.
 * Re-parenting is just a path change, so it rides on PATCH /api/folders (which
 * cascades to descendants). */
function FoldersModal({ folders, onClose, onChanged }) {
  const [newPath, setNewPath] = useState("");
  const [dragId, setDragId] = useState(null);
  const [overId, setOverId] = useState(null);   // -1 = the root drop zone
  const [editId, setEditId] = useState(null);
  const [editVal, setEditVal] = useState("");

  const create = async (path) => {
    const p = (path ?? newPath).trim();
    if (!p) return;
    await api.post("/api/folders", { name: p });
    setNewPath(""); onChanged();
  };
  const addSub = async (f) => {
    const leaf = prompt(`New sub-folder inside “${f.name}”:`);
    if (leaf && leaf.trim()) await create(`${f.name}/${leaf.trim()}`);
  };
  const beginRename = (f) => { setEditId(f.id); setEditVal(f.leaf); };
  const commitRename = async (f) => {
    const leaf = editVal.trim();
    setEditId(null);
    if (!leaf || leaf === f.leaf) return;
    const parent = f.name.includes("/") ? f.name.slice(0, f.name.lastIndexOf("/") + 1) : "";
    await api.patch(`/api/folders/${f.id}`, { name: parent + leaf }); onChanged();
  };
  const del = async (f) => {
    const kids = folders.some((x) => x.name.startsWith(f.name + "/"));
    if (!confirm(kids ? `Delete “${f.name}” and all its sub-folders? (Cuts are kept, just unfiled.)`
                      : `Delete folder “${f.name}”? (Cuts are kept, just unfiled.)`)) return;
    await api.del(`/api/folders/${f.id}?recursive=${kids ? 1 : 0}`); onChanged();
  };

  // a folder can't drop onto itself or its own descendant
  const canDrop = (drag, target) => drag && (!target
    || (drag.id !== target.id && target.name !== drag.name && !target.name.startsWith(drag.name + "/")
        && drag.name.slice(0, drag.name.lastIndexOf("/") + 1) !== (target.name ? target.name + "/" : "")));
  const drop = async (target) => {
    const drag = folders.find((x) => x.id === dragId);
    setOverId(null); setDragId(null);
    if (!canDrop(drag, target)) return;
    const newName = target ? `${target.name}/${drag.leaf}` : drag.leaf;   // null target = move to root
    if (newName === drag.name) return;
    await api.patch(`/api/folders/${drag.id}`, { name: newName }); onChanged();
  };

  return (
    <Modal title="Folders" onClose={onClose}>
      <div className="space-y-3">
        <div className="flex gap-2">
          <input className={inputCls} placeholder="New top-level folder, e.g. Movies"
            value={newPath} onChange={(e) => setNewPath(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()} />
          <button className={btnCls} onClick={() => create()}>Create</button>
        </div>
        <p className="text-xs text-zinc-500">
          Drag a folder onto another to nest it · ＋ adds a sub-folder · double-click to rename ·
          filtering a parent includes its sub-folders.
        </p>

        {/* root drop zone */}
        <div onDragOver={(e) => { if (dragId) { e.preventDefault(); setOverId(-1); } }}
          onDrop={() => drop(null)}
          className={`text-[11px] rounded-md border border-dashed px-2 py-1 ${
            overId === -1 ? "border-indigo-500 text-indigo-300 bg-indigo-500/10" : "border-zinc-800 text-zinc-600"}`}>
          ⌂ top level (drop here to un-nest)
        </div>

        <div className="max-h-[50vh] overflow-y-auto -mx-1">
          {folders.length === 0 && <p className="text-sm text-zinc-500 px-1">No folders yet.</p>}
          {folders.map((f) => {
            const drag = folders.find((x) => x.id === dragId);
            const isOver = overId === f.id && canDrop(drag, f);
            return (
              <div key={f.id} draggable={editId !== f.id}
                onDragStart={() => setDragId(f.id)} onDragEnd={() => { setDragId(null); setOverId(null); }}
                onDragOver={(e) => { if (dragId && canDrop(drag, f)) { e.preventDefault(); setOverId(f.id); } }}
                onDragLeave={() => setOverId((o) => (o === f.id ? null : o))}
                onDrop={() => drop(f)}
                className={`flex items-center gap-2 px-1 py-1 rounded group cursor-grab ${
                  isOver ? "bg-indigo-500/20 ring-1 ring-indigo-500" : "hover:bg-zinc-800/60"}`}
                style={{ marginLeft: f.depth * 16 }}>
                <span className="text-zinc-600 text-xs select-none">⠿</span>
                {editId === f.id ? (
                  <input autoFocus className={`${inputCls} !py-0.5 !w-40`} value={editVal}
                    onChange={(e) => setEditVal(e.target.value)} onBlur={() => commitRename(f)}
                    onKeyDown={(e) => { if (e.key === "Enter") commitRename(f); if (e.key === "Escape") setEditId(null); }} />
                ) : (
                  <span className="text-sm truncate" onDoubleClick={() => beginRename(f)}>📁 {f.leaf}</span>
                )}
                <span className="text-[11px] text-zinc-600">{f.cut_count}</span>
                <span className="ml-auto opacity-0 group-hover:opacity-100 flex gap-2.5 text-xs">
                  <button className="text-zinc-400 hover:text-zinc-50" title="New sub-folder" onClick={() => addSub(f)}>＋</button>
                  <button className="text-zinc-400 hover:text-zinc-50" onClick={() => beginRename(f)}>rename</button>
                  <button className="text-zinc-400 hover:text-red-400" onClick={() => del(f)}>delete</button>
                </span>
              </div>
            );
          })}
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
                                     onPreviewChange, onCutChanged, onCuts }) {
  const [intFilters, setIntFilters] = useState(EMPTY_FILTERS);
  const filters = extFilters ?? intFilters;
  const setFilters = setExtFilters ?? setIntFilters;

  const [cuts, setCuts] = useState([]);
  const [folders, setFolders] = useState([]);
  const [tags, setTags] = useState([]);
  const [media, setMedia] = useState([]);
  const [preview, setPreview] = useState(null);
  const [editing, setEditing] = useState(null);
  const [translating, setTranslating] = useState(null);
  const [bedFor, setBedFor] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [bulkTag, setBulkTag] = useState("");
  const [bulkLang, setBulkLang] = useState("");
  const [languages, setLanguages] = useState([]);
  const [showAddTo, setShowAddTo] = useState(false);
  const [showFolders, setShowFolders] = useState(false);
  const debounce = useRef();

  const refreshMeta = () => {
    api.get("/api/folders").then(setFolders).catch(() => {});
    api.get("/api/tags").then(setTags).catch(() => {});
    api.get("/api/media").then((m) => setMedia(m.filter((x) => x.status === "ready"))).catch(() => {});
    api.get("/api/languages").then(setLanguages).catch(() => {});
  };

  const refresh = () => {
    api.get(`/api/cuts?${filtersToParams(filters)}`)
      .then((cs) => { setCuts(cs); onCuts?.(cs); }).catch(() => {});
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

  const bulk = async (body, confirmMsg) => {
    if (confirmMsg && !confirm(confirmMsg)) return;
    try {
      const r = await api.post("/api/cuts/bulk", { cut_ids: [...selected], ...body });
      setSelected(new Set());
      refresh(); onCutChanged?.();
      return r;
    } catch (e) { alert(e.message); }
  };
  const selectAll = () => setSelected(new Set(cuts.map((c) => c.id)));

  return (
    <div className="h-full flex flex-col min-w-0">
      <div className="p-3 border-b border-zinc-800 shrink-0">
        <FilterBar filters={filters} setFilters={setFilters}
          tags={tags} folders={folders} media={media} compact={embedded} />
        {!embedded && (
          <div className="mt-2 flex items-center gap-3 text-xs text-zinc-400">
            {cuts.length > 0 && (
              <button className="hover:text-zinc-50 underline-offset-2 hover:underline"
                onClick={selectAll}>Select all {cuts.length}</button>
            )}
            {selected.size > 0 && (
              <button className="hover:text-zinc-50"
                onClick={() => setSelected(new Set())}>clear ({selected.size})</button>
            )}
            <button className="ml-auto hover:text-zinc-50" onClick={() => setShowFolders(true)}>📁 Folders</button>
          </div>
        )}
        {!embedded && selected.size > 0 && (
          <div className="mt-2 rounded-lg border border-indigo-500/40 bg-indigo-500/5 p-2 space-y-2">
            <p className="text-xs text-indigo-300">{selected.size} selected — bulk actions</p>
            <div className="flex flex-wrap items-center gap-2">
              <button className={`${btnCls} !py-1`} onClick={() => setShowAddTo(true)}>
                ＋ Recomposition
              </button>
              {/* add a tag to all */}
              <div className="flex items-center gap-1">
                <input className={`${inputCls} !py-1 w-28`} placeholder="tag…"
                  value={bulkTag} onChange={(e) => setBulkTag(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && bulkTag.trim()) {
                      bulk({ action: "add_tags", tags: [bulkTag.trim()] });
                      setBulkTag("");
                    }
                  }} />
                <button className={btnGhost} disabled={!bulkTag.trim()}
                  onClick={() => { bulk({ action: "add_tags", tags: [bulkTag.trim()] }); setBulkTag(""); }}>
                  tag
                </button>
              </div>
              {/* move to folder */}
              <select className={`${inputCls} !py-1 w-36`} defaultValue=""
                onChange={(e) => {
                  const v = e.target.value;
                  e.target.value = "";
                  if (v === "__new") {
                    const name = prompt("New folder name:");
                    if (name && name.trim()) bulk({ action: "set_folder", new_folder: name.trim() });
                  } else if (v === "__clear") {
                    bulk({ action: "clear_folder" });
                  } else if (v) {
                    bulk({ action: "set_folder", folder_id: Number(v) });
                  }
                }}>
                <option value="">Move to folder…</option>
                {folders.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
                <option value="__new">＋ New folder…</option>
                <option value="__clear">✕ Remove from folder</option>
              </select>
              {/* translate all to a language */}
              <select className={`${inputCls} !py-1 w-32`} value={bulkLang}
                onChange={(e) => setBulkLang(e.target.value)}>
                <option value="">Translate to…</option>
                {languages.filter((l) => l.code !== "en").map((l) => (
                  <option key={l.code} value={l.code}>{l.name}</option>
                ))}
              </select>
              {bulkLang && (
                <button className={btnGhost}
                  onClick={() => { bulk({ action: "translate", lang_code: bulkLang, user_id: user.id }); setBulkLang(""); }}>
                  translate
                </button>
              )}
              <button className="text-xs text-zinc-400 hover:text-red-400 ml-auto"
                onClick={() => bulk({ action: "delete" },
                  `Delete ${selected.size} cut(s)? This can't be undone.`)}>
                delete selected
              </button>
            </div>
          </div>
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
                  <button className="text-zinc-400 hover:text-zinc-50" onClick={() => setTranslating(c)}>translate/dub</button>
                  <button className="text-zinc-400 hover:text-zinc-50" onClick={() => setBedFor(c)}
                    title="Make a reusable background-audio bed from this cut">🎵 bed</button>
                  <button className="text-zinc-400 hover:text-zinc-50" onClick={() => setEditing(c)}>edit</button>
                  <button className="text-zinc-400 hover:text-red-400" onClick={() => removeCut(c)}>delete</button>
                </span>
              )}
              {embedded && (
                <button className="text-xs text-zinc-400 hover:text-zinc-50"
                  onClick={() => setTranslating(c)}>
                  dub
                </button>
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
      {translating && (
        <TranslationPanel cut={translating}
          onClose={() => setTranslating(null)}
          onChanged={() => { refresh(); onCutChanged?.(); }} />
      )}
      {showAddTo && (
        <AddToRecompModal cutIds={[...selected]} user={user}
          onClose={() => setShowAddTo(false)}
          onDone={() => setSelected(new Set())} />
      )}
      {showFolders && (
        <FoldersModal folders={folders}
          onClose={() => setShowFolders(false)}
          onChanged={() => { refreshMeta(); refresh(); }} />
      )}
      {bedFor && (
        <ToBedModal cut={bedFor} user={user}
          onClose={(made) => { setBedFor(null); if (made) alert("Bed queued — see the Audio tab."); }} />
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
