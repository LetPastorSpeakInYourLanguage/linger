import { useEffect, useRef, useState } from "react";
import { api, fmtTime } from "../api";
import { Modal, inputCls, btnCls, btnGhost, Spinner } from "./ui";

const STATUS_LABEL = {
  processing: ["Processing…", "text-amber-400"],
  uploaded: ["Uploaded", "text-zinc-400"],
  queued_transcription: ["Waiting for transcription", "text-amber-400"],
  extracting_audio: ["Extracting audio…", "text-amber-400"],
  transcribing: ["Transcribing…", "text-amber-400"],
  ready: ["Ready", "text-emerald-400"],
  error: ["Error", "text-red-400"],
};

function UploadModal({ user, onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [srt, setSrt] = useState(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    if (!file) return;
    setBusy(true); setErr("");
    const fd = new FormData();
    fd.append("file", file);
    if (srt) fd.append("subtitle", srt);
    fd.append("title", title);
    fd.append("user_id", user.id);
    try {
      await api.upload("/api/media", fd);
      onDone(); onClose();
    } catch (e) { setErr(e.message); setBusy(false); }
  };

  return (
    <Modal title="Add media" onClose={onClose}>
      <div className="space-y-4">
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
          <label className="text-sm text-zinc-400">
            Subtitles (.srt / .vtt) — optional. Without it, the file is auto-transcribed.
          </label>
          <input type="file" accept=".srt,.vtt" className="block mt-1 text-sm"
            onChange={(e) => setSrt(e.target.files[0])} />
        </div>
        <div>
          <label className="text-sm text-zinc-400">Title</label>
          <input className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        {err && <p className="text-sm text-red-400">{err}</p>}
        <div className="flex justify-end gap-2">
          <button className={btnGhost} onClick={onClose}>Cancel</button>
          <button className={btnCls} disabled={!file || busy} onClick={submit}>
            {busy ? "Uploading… (large files take a while)" : "Upload"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

export default function Library({ user, openMedia }) {
  const [media, setMedia] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [showUpload, setShowUpload] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const timer = useRef();

  const refresh = () => {
    api.get("/api/media").then((m) => { setMedia(m); setLoaded(true); }).catch(() => {});
    api.get("/api/jobs").then(setJobs).catch(() => {});
  };

  useEffect(() => {
    refresh();
    timer.current = setInterval(refresh, 3000);
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
        <button className={btnCls} onClick={() => setShowUpload(true)}>+ Add media</button>
      </div>

      {activeJobs.length > 0 && (
        <div className="mb-5 p-3 rounded-lg bg-zinc-900 border border-zinc-800 flex items-center gap-3">
          <Spinner />
          <div className="text-sm text-zinc-300">
            {activeJobs.map((j) => (
              <div key={j.id}>{j.media_title}: {j.detail || j.status}</div>
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
              <p className={`text-xs mt-1 ${color}`}>{label}</p>
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

      {showUpload && (
        <UploadModal user={user} onClose={() => setShowUpload(false)} onDone={refresh} />
      )}
    </div>
  );
}
