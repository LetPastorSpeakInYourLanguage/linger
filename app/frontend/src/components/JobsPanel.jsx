import { useEffect, useState } from "react";
import { api } from "../api";

const KIND_ICON = { download: "⬇", prepare: "⚙", transcribe: "🎙", export: "🎞" };

const STATUS_BADGE = {
  queued: "text-amber-400 border-amber-400/40",
  running: "text-indigo-300 border-indigo-400/40",
  done: "text-emerald-400 border-emerald-500/40",
  failed: "text-red-400 border-red-500/40",
  cancelled: "text-zinc-400 border-zinc-600",
};

function ago(iso) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso + "Z").getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

/* Right-side drawer listing every background job with progress + controls. */
export default function JobsPanel({ onClose }) {
  const [jobs, setJobs] = useState([]);
  const [err, setErr] = useState("");

  const refresh = () => api.get("/api/jobs").then(setJobs).catch(() => {});
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2000);
    const esc = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => { clearInterval(t); window.removeEventListener("keydown", esc); };
  }, [onClose]);

  const act = async (job, action) => {
    setErr("");
    try { await api.post(`/api/jobs/${job.id}/${action}`); refresh(); }
    catch (e) { setErr(e.message); }
  };

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-96 max-w-[90vw] bg-zinc-950 border-l border-zinc-800 shadow-2xl flex flex-col">
      <div className="flex items-center justify-between px-4 h-12 border-b border-zinc-800 shrink-0">
        <h2 className="font-semibold text-sm">Background jobs</h2>
        <button onClick={onClose} title="Close (Esc)"
          className="text-zinc-400 hover:text-white text-xl leading-none">×</button>
      </div>
      {err && <p className="text-xs text-red-400 px-4 py-2">{err}</p>}
      <div className="flex-1 overflow-y-auto divide-y divide-zinc-900">
        {jobs.length === 0 && (
          <p className="text-sm text-zinc-500 p-4">No jobs yet.</p>
        )}
        {jobs.map((j) => {
          const active = j.status === "queued" || j.status === "running";
          return (
            <div key={j.id} className="px-4 py-3">
              <div className="flex items-center gap-2">
                <span title={j.kind}>{KIND_ICON[j.kind] || "·"}</span>
                <span className="text-sm font-medium truncate flex-1"
                  title={j.media_title || j.kind}>
                  {j.media_title || (j.kind === "export" ? `Export #${j.target_id ?? ""}` : j.kind)}
                </span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${
                  STATUS_BADGE[j.status] || "text-zinc-400 border-zinc-700"}`}>
                  {j.status}
                </span>
              </div>
              <p className="text-xs text-zinc-500 mt-1 truncate" title={j.detail}>
                {j.kind} · {j.detail || "—"}
              </p>
              {active && j.progress != null && (
                <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden mt-2">
                  <div className="h-full bg-indigo-500 transition-all"
                    style={{ width: `${j.progress}%` }} />
                </div>
              )}
              <div className="flex items-center gap-3 mt-1.5 text-xs">
                <span className="text-zinc-600">{ago(j.updated_at || j.created_at)}</span>
                {active && (
                  <button onClick={() => act(j, "cancel")}
                    className="text-zinc-400 hover:text-red-400">
                    {j.cancel_requested ? "cancelling…" : "cancel"}
                  </button>
                )}
                {(j.status === "failed" || j.status === "cancelled") && (
                  <button onClick={() => act(j, "retry")}
                    className="text-zinc-400 hover:text-indigo-300">retry</button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
