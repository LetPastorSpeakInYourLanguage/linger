/* Jobs workspace — a controller column + a single locked-scroll job list.
 * Be an active participant in the queue: filter (status / kind / age), see rich
 * detail + progress, pause/resume, cancel, retry, reprioritise, and clear
 * finished history. The worker runs two lanes (heavy ingest + a light lane),
 * so a long transcription no longer freezes quick work. */
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";

const KIND_ICON = {
  download: "⬇", prepare: "⚙", transcribe: "🎙", export: "🎞", embed: "🧠",
  separate: "🎚", dub: "🗣", translate_recomposition: "🌐", translate_track: "🌐",
  cut_to_bg: "🎵", scan_folder: "📂",
};
const STATUS_BADGE = {
  queued: "text-amber-400 border-amber-400/40",
  running: "text-indigo-300 border-indigo-400/40",
  paused: "text-sky-300 border-sky-400/40",
  done: "text-emerald-400 border-emerald-500/40",
  failed: "text-red-400 border-red-500/40",
  cancelled: "text-zinc-400 border-zinc-600",
};
const STATUSES = ["running", "queued", "paused", "done", "failed", "cancelled"];
const AGES = [["all", "Any time"], ["1h", "Past hour"], ["24h", "Past day"], ["7d", "Past week"]];
const AGE_SECONDS = { "1h": 3600, "24h": 86400, "7d": 604800 };

function ago(iso) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso + "Z").getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
const secsAgo = (iso) => (iso ? (Date.now() - new Date(iso + "Z").getTime()) / 1000 : Infinity);

const label = (j) => j.media_title
  || (j.target_kind === "recomposition" ? `Recomposition #${j.target_id ?? ""}` : null)
  || j.kind;

export default function JobsPage() {
  const [jobs, setJobs] = useState([]);
  const [err, setErr] = useState("");
  const [auto, setAuto] = useState(true);
  const [statusSel, setStatusSel] = useState(new Set());   // empty = all
  const [kind, setKind] = useState("all");
  const [age, setAge] = useState("all");

  const refresh = () => api.get("/api/jobs?limit=300").then(setJobs).catch(() => {});
  useEffect(() => {
    refresh();
    if (!auto) return;
    const t = setInterval(refresh, 1500);
    return () => clearInterval(t);
  }, [auto]);

  const act = async (job, action) => {
    setErr("");
    try { await api.post(`/api/jobs/${job.id}/${action}`); refresh(); }
    catch (e) { setErr(e.message); }
  };
  const setPri = async (job, priority) => {
    setErr("");
    try { await api.patch(`/api/jobs/${job.id}`, { priority }); refresh(); }
    catch (e) { setErr(e.message); }
  };
  const clearHistory = async () => {
    if (!confirm("Clear all finished jobs (done, failed, cancelled) from history?")) return;
    setErr("");
    try { await api.post("/api/jobs/clear"); refresh(); }
    catch (e) { setErr(e.message); }
  };

  const kinds = useMemo(() => [...new Set(jobs.map((j) => j.kind))].sort(), [jobs]);
  const counts = useMemo(() => {
    const c = {}; jobs.forEach((j) => { c[j.status] = (c[j.status] || 0) + 1; }); return c;
  }, [jobs]);

  const toggleStatus = (s) => setStatusSel((cur) => {
    const n = new Set(cur); n.has(s) ? n.delete(s) : n.add(s); return n;
  });

  const visible = useMemo(() => jobs.filter((j) =>
    (statusSel.size === 0 || statusSel.has(j.status))
    && (kind === "all" || j.kind === kind)
    && (age === "all" || secsAgo(j.updated_at || j.created_at) <= AGE_SECONDS[age])
  ), [jobs, statusSel, kind, age]);

  const running = visible.filter((j) => j.status === "running");
  const queued = visible.filter((j) => j.status === "queued")
    .sort((a, b) => (b.priority - a.priority) || (a.id - b.id));
  const paused = visible.filter((j) => j.status === "paused");
  const history = visible.filter((j) => ["done", "failed", "cancelled"].includes(j.status)).slice(0, 120);
  const prios = queued.map((j) => j.priority);
  const hi = Math.max(0, ...prios), lo = Math.min(0, ...prios);
  const move = (job, dir) => setPri(job,
    dir === "top" ? hi + 1 : dir === "bottom" ? lo - 1 : dir === "up" ? job.priority + 1 : job.priority - 1);

  const row = (j, pos) => {
    const active = j.status === "queued" || j.status === "running";
    return (
      <div key={j.id} className="flex items-center gap-3 px-3 py-2.5 border border-zinc-800 rounded-lg bg-zinc-900/50">
        {pos != null && <span className="text-xs font-mono text-zinc-600 w-5 text-right shrink-0">{pos}</span>}
        <span title={j.kind} className="text-lg shrink-0">{KIND_ICON[j.kind] || "·"}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium truncate">{label(j)}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full border shrink-0 ${STATUS_BADGE[j.status] || "text-zinc-400 border-zinc-700"}`}>{j.status}</span>
            {j.attempts > 1 && <span className="text-[10px] text-zinc-600 shrink-0">try {j.attempts}/{j.max_attempts}</span>}
          </div>
          <p className="text-xs text-zinc-500 truncate" title={j.detail}>
            {j.kind} · {j.detail || "—"}
          </p>
          <p className="text-[10px] text-zinc-600 mt-0.5 flex gap-2 flex-wrap">
            <span>updated {ago(j.updated_at || j.created_at)}</span>
            {j.started_at && <span>· started {ago(j.started_at)}</span>}
            {j.finished_at && <span>· finished {ago(j.finished_at)}</span>}
            {j.progress != null && j.status !== "running" && <span>· {Math.round(j.progress)}%</span>}
          </p>
          {(j.status === "running" || j.status === "paused") && j.progress != null && (
            <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden mt-1.5">
              <div className={`h-full transition-all ${j.status === "paused" ? "bg-sky-500/60" : "bg-indigo-500"}`}
                style={{ width: `${j.progress}%` }} />
            </div>
          )}
        </div>
        {j.status === "queued" && (
          <div className="flex items-center gap-1 text-xs text-zinc-400 shrink-0">
            <button title="To top" className="hover:text-white px-1" onClick={() => move(j, "top")}>⤒</button>
            <button title="Up" className="hover:text-white px-1" onClick={() => move(j, "up")}>▲</button>
            <button title="Down" className="hover:text-white px-1" onClick={() => move(j, "down")}>▼</button>
            <button title="To bottom" className="hover:text-white px-1" onClick={() => move(j, "bottom")}>⤓</button>
            <span className="text-[10px] text-zinc-600 w-8 text-center" title="priority">p{j.priority}</span>
          </div>
        )}
        <div className="flex items-center gap-2 shrink-0 text-xs">
          {active && (
            <button onClick={() => act(j, "pause")} className="text-zinc-400 hover:text-sky-300"
              title="Pause (resumable)">{j.pause_requested ? "pausing…" : "⏸"}</button>
          )}
          {j.status === "paused" && (
            <button onClick={() => act(j, "resume")} className="text-zinc-400 hover:text-emerald-300" title="Resume">▶ resume</button>
          )}
          {active && (
            <button onClick={() => act(j, "cancel")} className="text-zinc-400 hover:text-red-400">
              {j.cancel_requested ? "cancelling…" : "cancel"}
            </button>
          )}
          {(j.status === "failed" || j.status === "cancelled" || j.status === "paused") && (
            <button onClick={() => act(j, "retry")} className="text-zinc-400 hover:text-indigo-300" title="Restart from scratch">retry</button>
          )}
        </div>
      </div>
    );
  };

  const section = (title, count, body) => (
    <div>
      <div className="sticky top-0 z-10 bg-zinc-950/95 backdrop-blur text-[11px] uppercase tracking-wide text-zinc-500 py-1.5">
        {title} {count != null && <span className="text-zinc-600">({count})</span>}
      </div>
      <div className="space-y-1.5">{body}</div>
    </div>
  );

  const chip = (active, onClick, children, extra = "") => (
    <button onClick={onClick}
      className={`px-2 py-1 rounded-md text-xs border ${active
        ? "bg-indigo-600 border-indigo-500 text-white"
        : "border-zinc-700 text-zinc-400 hover:border-zinc-500"} ${extra}`}>
      {children}
    </button>
  );

  return (
    <div className="h-full flex min-h-0">
      {/* ---- controller column (does not scroll with the list) ---- */}
      <div className="w-60 shrink-0 border-r border-zinc-800 flex flex-col">
        <div className="p-3 border-b border-zinc-800">
          <h1 className="font-semibold">Jobs</h1>
          <p className="text-xs text-zinc-500 mt-0.5">
            {counts.running || 0} running · {counts.queued || 0} queued
            {counts.paused ? ` · ${counts.paused} paused` : ""}
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-4 text-sm">
          <div>
            <p className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1.5">Status</p>
            <div className="flex flex-wrap gap-1.5">
              {STATUSES.map((s) => chip(statusSel.has(s), () => toggleStatus(s),
                <>{s}{counts[s] ? <span className="opacity-60 ml-1">{counts[s]}</span> : null}</>))}
            </div>
            {statusSel.size > 0 && (
              <button className="text-[11px] text-zinc-500 hover:text-white mt-1.5" onClick={() => setStatusSel(new Set())}>
                clear status filter
              </button>
            )}
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1.5">Kind</p>
            <select value={kind} onChange={(e) => setKind(e.target.value)}
              className="w-full bg-zinc-900 border border-zinc-700 rounded-md px-2 py-1 text-xs outline-none">
              <option value="all">All kinds</option>
              {kinds.map((k) => <option key={k} value={k}>{KIND_ICON[k] || "·"} {k}</option>)}
            </select>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1.5">Age</p>
            <div className="flex flex-wrap gap-1.5">
              {AGES.map(([v, lbl]) => chip(age === v, () => setAge(v), lbl))}
            </div>
          </div>
          <div className="space-y-1.5 pt-1 border-t border-zinc-800">
            <label className="flex items-center gap-2 text-xs text-zinc-400">
              <input type="checkbox" className="accent-indigo-500" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
              auto-refresh
            </label>
            <button className="text-xs text-zinc-400 hover:text-white block" onClick={refresh}>↻ refresh now</button>
            <button className="text-xs text-zinc-400 hover:text-red-400 block" onClick={clearHistory}>🗑 clear finished history</button>
          </div>
        </div>
      </div>

      {/* ---- the only scrolling region: the job list ---- */}
      <div className="flex-1 min-w-0 overflow-y-auto p-4 space-y-5">
        {err && <p className="text-sm text-red-400">{err}</p>}
        {visible.length === 0 && (
          <p className="text-sm text-zinc-600 text-center mt-10">No jobs match these filters.</p>
        )}
        {running.length > 0 && section("Running", running.length, running.map((j) => row(j)))}
        {queued.length > 0 && section("Queue — reprioritise with the arrows", queued.length, queued.map((j, i) => row(j, i + 1)))}
        {paused.length > 0 && section("Paused — resume to continue", paused.length, paused.map((j) => row(j)))}
        {history.length > 0 && section("History", history.length, history.map((j) => row(j)))}
      </div>
    </div>
  );
}
