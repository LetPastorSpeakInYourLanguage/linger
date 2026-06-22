import { useEffect, useRef, useState } from "react";
import { api, fmtTime } from "../api";
import { Modal, inputCls, btnCls, btnGhost, Spinner } from "./ui";

const STATUS_LABEL = {
  preparing: ["Preparing…", "text-amber-400"],
  downloading: ["Downloading…", "text-amber-400"],
  uploaded: ["Uploaded", "text-zinc-400"],
  queued_transcription: ["Waiting for transcription", "text-amber-400"],
  extracting_audio: ["Extracting audio…", "text-amber-400"],
  transcribing: ["Transcribing…", "text-amber-400"],
  ready: ["Ready", "text-emerald-400"],
  error: ["Error", "text-red-400"],
};

const BUSY = new Set(["preparing", "downloading", "queued_transcription",
  "extracting_audio", "transcribing"]);

/* Upload with progress needs XHR — fetch can't report upload progress. */
function xhrUpload(url, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.upload.onprogress = (e) =>
      e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
      else {
        let msg = xhr.statusText;
        try { msg = JSON.parse(xhr.responseText).detail || msg; } catch { /* ignore */ }
        reject(new Error(msg));
      }
    };
    xhr.onerror = () => reject(new Error("network error during upload"));
    xhr.send(formData);
  });
}

function AddMediaModal({ user, onClose, onDone }) {
  const [mode, setMode] = useState("upload"); // upload | path | link
  const [file, setFile] = useState(null);
  const [srt, setSrt] = useState(null);
  const [subtitleLanguage, setSubtitleLanguage] = useState("");
  const [path, setPath] = useState("");
  const [srtPath, setSrtPath] = useState("");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [pct, setPct] = useState(null);
  const [err, setErr] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [models, setModels] = useState(null);
  const [whisperModel, setWhisperModel] = useState(
    () => localStorage.getItem("whisper_model") || "");

  useEffect(() => {
    api.get("/api/transcribe/options").then((o) => {
      setModels(o);
      setWhisperModel((m) => m || o.default_model);
    }).catch(() => {});
  }, []);

  const submit = async () => {
    setBusy(true); setErr(""); setPct(null);
    localStorage.setItem("whisper_model", whisperModel);
    try {
      if (mode === "upload") {
        if (!file) return setBusy(false);
        const fd = new FormData();
        fd.append("file", file);
        if (srt) fd.append("subtitle", srt);
        fd.append("title", title);
        fd.append("user_id", user.id);
        fd.append("whisper_model", whisperModel);
        fd.append("subtitle_language", subtitleLanguage);
        await xhrUpload("/api/media", fd, setPct);
      } else if (mode === "path") {
        if (!path.trim()) return setBusy(false);
        await api.post("/api/media/import-path", {
          path, subtitle_path: srtPath.trim() || null, title, user_id: user.id,
          whisper_model: whisperModel,
          subtitle_language: subtitleLanguage,
        });
      } else {
        if (!url.trim()) return setBusy(false);
        await api.post("/api/media/from-url", {
          url, title, user_id: user.id, whisper_model: whisperModel,
        });
      }
      onDone(); onClose();
    } catch (e) { setErr(e.message); setBusy(false); }
  };

  const tab = (id, label) => (
    <button onClick={() => setMode(id)}
      className={`px-3 py-1.5 rounded-lg text-sm ${
        mode === id ? "bg-indigo-600 text-white" : "bg-zinc-950 text-zinc-400 hover:text-white"}`}>
      {label}
    </button>
  );

  return (
    <Modal title="Add media" onClose={onClose}>
      <div className="space-y-4">
        <div className="flex gap-2">{tab("upload", "Upload file")}{tab("path", "From this PC")}{tab("link", "From link")}</div>

        {mode === "upload" && (
          <>
            <div>
              <label className="text-sm text-zinc-400">Video or audio file</label>
              <input type="file" accept="video/*,audio/*,.mkv" className="block mt-1 text-sm"
                onChange={(e) => {
                  setFile(e.target.files[0]);
                  if (!title && e.target.files[0])
                    setTitle(e.target.files[0].name.replace(/\.[^.]+$/, ""));
                }} />
            </div>
            <div>
              <label className="text-sm text-zinc-400">Subtitles (.srt / .vtt) — optional</label>
              <input type="file" accept=".srt,.vtt" className="block mt-1 text-sm"
                onChange={(e) => setSrt(e.target.files[0])} />
            </div>
            <div>
              <label className="text-sm text-zinc-400">Subtitle language code — optional</label>
              <input className={inputCls} placeholder="en, es, am…"
                value={subtitleLanguage} onChange={(e) => setSubtitleLanguage(e.target.value)} />
            </div>
            <p className="text-xs text-zinc-500">
              Tip: if the file is already on the computer running the server,
              “From this PC” is much faster (no upload copy).
            </p>
          </>
        )}

        {mode === "path" && (
          <>
            <div>
              <label className="text-sm text-zinc-400">
                Full path of the file on the server computer
              </label>
              <input className={inputCls} placeholder={"D:\\movies\\notebook.mp4"}
                value={path} onChange={(e) => setPath(e.target.value)} />
            </div>
            <div>
              <label className="text-sm text-zinc-400">Path of the .srt — optional</label>
              <input className={inputCls} placeholder={"D:\\movies\\notebook.srt"}
                value={srtPath} onChange={(e) => setSrtPath(e.target.value)} />
            </div>
            <div>
              <label className="text-sm text-zinc-400">Subtitle language code — optional</label>
              <input className={inputCls} placeholder="en, es, am…"
                value={subtitleLanguage} onChange={(e) => setSubtitleLanguage(e.target.value)} />
            </div>
            <p className="text-xs text-zinc-500">
              The original file is read in place and never modified or deleted.
            </p>
          </>
        )}

        {mode === "link" && (
          <>
            <div>
              <label className="text-sm text-zinc-400">YouTube / public video link</label>
              <input className={inputCls} placeholder="https://www.youtube.com/watch?v=…"
                value={url} onChange={(e) => setUrl(e.target.value)} />
            </div>
            <p className="text-xs text-zinc-500">
              Needs <code>pip install yt-dlp</code> on the server. Download runs in the
              background — watch progress on the media card. Title is taken from the
              video if left blank.
            </p>
          </>
        )}

        <div>
          <label className="text-sm text-zinc-400">Title {mode === "link" && "(optional)"}</label>
          <input className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>

        <div>
          <button className="text-xs text-zinc-500 hover:text-zinc-300"
            onClick={() => setAdvanced((v) => !v)}>
            {advanced ? "▾" : "▸"} advanced
          </button>
          {advanced && (
            <div className="mt-2 p-3 rounded-lg bg-zinc-950 border border-zinc-800">
              <label className="text-xs text-zinc-400">
                Whisper model — used only if no subtitles are attached
              </label>
              <select className={`${inputCls} mt-1`} value={whisperModel}
                onChange={(e) => setWhisperModel(e.target.value)}>
                {(models?.models || (whisperModel ? [whisperModel] : ["small"])).map((m) => (
                  <option key={m} value={m}>
                    {m}{models && m === models.default_model ? " (default)" : ""}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {pct != null && (
          <div>
            <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
              <div className="h-full bg-indigo-500 transition-all" style={{ width: `${pct}%` }} />
            </div>
            <p className="text-xs text-zinc-500 mt-1">
              {pct < 100 ? `Uploading ${pct}%` : "Upload done — processing continues in background"}
            </p>
          </div>
        )}
        {err && <p className="text-sm text-red-400">{err}</p>}

        <div className="flex justify-end gap-2">
          <button className={btnGhost} onClick={onClose}>Cancel</button>
          <button className={btnCls} disabled={busy} onClick={submit}>
            {busy ? "Working…" : "Add"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

/* Watch local folders and bulk-ingest from them. Movies pair with sibling
 * subtitle files (auto-transcribe when missing); audio folders fill the bed
 * library, mirroring sub-directories as bed folders. */
function ScanFoldersModal({ onClose, onScanned }) {
  const [list, setList] = useState([]);
  const [path, setPath] = useState("");
  const [kind, setKind] = useState("media");
  const [err, setErr] = useState("");
  const [scanned, setScanned] = useState(null);

  const load = () => api.get("/api/scan-folders").then(setList).catch(() => {});
  useEffect(() => { load(); }, []);

  const add = async () => {
    if (!path.trim()) return;
    setErr("");
    try { await api.post("/api/scan-folders", { path: path.trim(), kind }); setPath(""); load(); }
    catch (e) { setErr(e.message); }
  };
  const scan = async (f) => {
    try { await api.post(`/api/scan-folders/${f.id}/scan`); setScanned(f.id); onScanned?.(); }
    catch (e) { setErr(e.message); }
  };
  const del = async (f) => { await api.del(`/api/scan-folders/${f.id}`); load(); };

  return (
    <Modal title="Scan folders" onClose={onClose} wide>
      <div className="space-y-3">
        <p className="text-xs text-zinc-500">
          Point at a folder on this machine. <b>Media</b> folders ingest movies and attach
          sibling subtitles (<span className="font-mono">movie.srt</span> / <span className="font-mono">movie.en.srt</span>),
          transcribing only when a movie has none. <b>Audio</b> folders fill the bed library,
          mirroring sub-folders. Scanning runs in the background — watch the <b>Jobs</b> page.
        </p>
        <div className="flex gap-2">
          <input className={inputCls} placeholder="C:\Movies  or  /home/me/movies"
            value={path} onChange={(e) => setPath(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()} />
          <select className={`${inputCls} !w-28`} value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="media">Media</option>
            <option value="audio">Audio</option>
          </select>
          <button className={btnCls} onClick={add}>Add</button>
        </div>
        {err && <p className="text-sm text-red-400">{err}</p>}
        {scanned && <p className="text-xs text-emerald-400">Scan queued — see the Jobs page for progress.</p>}
        <div className="space-y-1.5 max-h-[50vh] overflow-y-auto">
          {list.length === 0 && <p className="text-sm text-zinc-500">No watched folders yet.</p>}
          {list.map((f) => (
            <div key={f.id} className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
              <span>{f.kind === "audio" ? "🎵" : "🎬"}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-mono truncate">{f.path}</p>
                <p className="text-[11px] text-zinc-500">
                  {f.kind} · {f.ingested} ingested {f.exists ? "" : "· ⚠ not found on this PC"}
                </p>
              </div>
              <button className={`${btnGhost} !py-1`} disabled={!f.exists} onClick={() => scan(f)}>Scan now</button>
              <button className="text-zinc-500 hover:text-red-400 text-xs" onClick={() => del(f)}>remove</button>
            </div>
          ))}
        </div>
      </div>
    </Modal>
  );
}

export default function Library({ user, openMedia }) {
  const [media, setMedia] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [showScan, setShowScan] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const timer = useRef();

  const refresh = () => {
    api.get("/api/media").then((m) => { setMedia(m); setLoaded(true); }).catch(() => {});
    api.get("/api/jobs").then(setJobs).catch(() => {});
  };

  useEffect(() => {
    refresh();
    timer.current = setInterval(refresh, 2000);
    return () => clearInterval(timer.current);
  }, []);

  const remove = async (m) => {
    if (!confirm(`Delete "${m.title}" and all its cuts?`)) return;
    try { await api.del(`/api/media/${m.id}?user_id=${user.id}`); refresh(); }
    catch (e) { alert(e.message); }
  };

  const relink = async (m) => {
    const ans = prompt(
      `"${m.title}" is unlinked on this computer.\n\n`
      + "Paste a LOCAL path to your copy (sha256-verified), or a URL to re-download:");
    if (!ans || !ans.trim()) return;
    const v = ans.trim();
    const body = /^https?:\/\//i.test(v) ? { url: v, user_id: user.id }
                                         : { path: v, user_id: user.id };
    try {
      await api.post(`/api/media/${m.id}/relink`, body);
      refresh();
    } catch (e) { alert(e.message); }
  };

  const buildIndex = async () => {
    try {
      const r = await api.post("/api/embed/all");
      alert(`Building semantic search index for ${r.queued.length} media in the background.`);
    } catch (e) { alert(e.message); }
  };

  const activeJobs = jobs.filter((j) => j.status === "queued" || j.status === "running");

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-semibold">Library</h1>
        <div className="flex gap-2">
          <button className={btnGhost} onClick={buildIndex}
            title="Embed transcripts for semantic ('Smart') search">✨ Build search index</button>
          <button className={btnGhost} onClick={() => setShowScan(true)}
            title="Watch local folders and bulk-ingest movies + subtitles / bg-audio">📂 Scan folders</button>
          <button className={btnCls} onClick={() => setShowAdd(true)}>+ Add media</button>
        </div>
      </div>

      {activeJobs.length > 0 && (
        <div className="mb-5 p-3 rounded-lg bg-zinc-900 border border-zinc-800 flex items-center gap-3">
          <Spinner />
          <div className="text-sm text-zinc-300">
            {activeJobs.map((j) => (
              <div key={j.id}>
                {j.media_title || (j.kind === "export" ? "Export" : j.kind)}: {j.detail || j.status}
              </div>
            ))}
          </div>
        </div>
      )}

      {loaded && media.length === 0 && (
        <div className="text-center text-zinc-500 mt-24">
          <p className="text-lg">No media yet.</p>
          <p className="text-sm mt-1">Add a movie, podcast or lecture — with subtitles if you have them.</p>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {media.map((m) => {
          const [label, color] = STATUS_LABEL[m.status] || [m.status, "text-zinc-400"];
          const busy = BUSY.has(m.status);
          return (
            <div key={m.id}
              className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 hover:border-zinc-600 cursor-pointer group"
              onClick={() => m.status === "ready" && openMedia(m.id)}>
              <div className="flex items-start justify-between">
                <span className="text-2xl">{m.type === "video" ? "🎬" : "🎙️"}</span>
                <button onClick={(e) => { e.stopPropagation(); remove(m); }}
                  className="opacity-0 group-hover:opacity-100 text-zinc-500 hover:text-red-400 text-sm">
                  delete
                </button>
              </div>
              <h3 className="font-medium mt-2 truncate" title={m.title}>{m.title}</h3>
              <p className={`text-xs mt-1 ${color}`}>
                {label}{busy && m.status_detail ? ` — ${m.status_detail}` : ""}
              </p>
              {m.linked === false && !busy && (
                <div className="mt-1">
                  <span className="text-xs text-amber-400">⚠ unlinked on this PC</span>
                  <button className={`${btnGhost} ml-2 text-xs`}
                    onClick={(e) => { e.stopPropagation(); relink(m); }}>relink…</button>
                </div>
              )}
              {m.status === "error" && (
                <p className="text-xs text-red-400/80 mt-1 line-clamp-2">{m.status_detail}</p>
              )}
              <p className="text-xs text-zinc-500 mt-2">
                {fmtTime(m.duration)} · {m.segment_count} segments · {m.cut_count} cuts
                {m.added_by_name && <> · by {m.added_by_name}</>}
              </p>
              {m.status === "error" && (
                <button className={`${btnGhost} mt-2 text-xs`}
                  onClick={(e) => { e.stopPropagation(); api.post(`/api/media/${m.id}/transcribe`).then(refresh); }}>
                  Retry transcription
                </button>
              )}
            </div>
          );
        })}
      </div>

      {showAdd && (
        <AddMediaModal user={user} onClose={() => setShowAdd(false)} onDone={refresh} />
      )}
      {showScan && (
        <ScanFoldersModal onClose={() => setShowScan(false)} onScanned={refresh} />
      )}
    </div>
  );
}
