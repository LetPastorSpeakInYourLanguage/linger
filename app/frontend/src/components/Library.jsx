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
  const [path, setPath] = useState("");
  const [srtPath, setSrtPath] = useState("");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [pct, setPct] = useState(null);
  const [err, setErr] = useState("");

  const submit = async () => {
    setBusy(true); setErr(""); setPct(null);
    try {
      if (mode === "upload") {
        if (!file) return setBusy(false);
        const fd = new FormData();
        fd.append("file", file);
        if (srt) fd.append("subtitle", srt);
        fd.append("title", title);
        fd.append("user_id", user.id);
        await xhrUpload("/api/media", fd, setPct);
      } else if (mode === "path") {
        if (!path.trim()) return setBusy(false);
        await api.post("/api/media/import-path", {
          path, subtitle_path: srtPath.trim() || null, title, user_id: user.id,
        });
      } else {
        if (!url.trim()) return setBusy(false);
        await api.post("/api/media/from-url", { url, title, user_id: user.id });
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

export default function Library({ user, openMedia }) {
  const [media, setMedia] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
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

  const activeJobs = jobs.filter((j) => j.status === "queued" || j.status === "running");

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-xl font-semibold">Library</h1>
        <button className={btnCls} onClick={() => setShowAdd(true)}>+ Add media</button>
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
    </div>
  );
}
