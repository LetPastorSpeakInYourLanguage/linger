import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { ACCENTS, ACCENT_SWATCH, DENSITIES, getAppearance, setAppearance } from "./appearance";
import Library from "./components/Library";
import MediaView from "./components/MediaView";
import { CutsPage } from "./components/CutBrowser";
import Cutter from "./components/Cutter";
import Assembler from "./components/Assembler";
import Studio from "./components/Studio";
import AudioStudio from "./components/AudioStudio";
import JobsPanel from "./components/JobsPanel";
import JobsPage from "./components/JobsPage";
import Settings from "./components/Settings";

const COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#06b6d4"];

function Login({ onLogin }) {
  const [users, setUsers] = useState([]);
  const [name, setName] = useState("");
  useEffect(() => { api.get("/api/users").then(setUsers).catch(() => {}); }, []);

  const create = async () => {
    if (!name.trim()) return;
    const color = COLORS[users.length % COLORS.length];
    onLogin(await api.post("/api/users", { name: name.trim(), color }));
  };

  return (
    <div className="h-full flex items-center justify-center">
      <div className="w-80 space-y-6 text-center">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Recomposer</h1>
          <p className="text-zinc-400 text-sm mt-1">Who's working?</p>
        </div>
        {users.length > 0 && (
          <div className="flex flex-wrap justify-center gap-3">
            {users.map((u) => (
              <button key={u.id} onClick={() => onLogin(u)}
                className="px-4 py-3 rounded-xl bg-zinc-900 border border-zinc-800 hover:border-zinc-500 flex items-center gap-2">
                <span className="w-3 h-3 rounded-full" style={{ background: u.color }} />
                {u.name}
              </button>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <input value={name} onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
            placeholder="New name…"
            className="flex-1 bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 outline-none focus:border-indigo-500" />
          <button onClick={create}
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 font-medium">
            Join
          </button>
        </div>
      </div>
    </div>
  );
}

function Segmented({ value, options, onChange }) {
  return (
    <div className="flex rounded-md border border-zinc-700 overflow-hidden">
      {options.map((o) => (
        <button key={o.v} onClick={() => onChange(o.v)}
          className={`flex-1 px-2 py-1 text-xs capitalize ${value === o.v ? "bg-indigo-600 text-white" : "text-zinc-400 hover:text-zinc-50"}`}>
          {o.label ?? o.v}
        </button>
      ))}
    </div>
  );
}

/* Live theme / accent / density switcher (writes <html> data-* via appearance.js). */
function AppearanceMenu() {
  const [open, setOpen] = useState(false);
  const [a, setA] = useState(getAppearance);
  const ref = useRef();
  const update = (patch) => setA(setAppearance(patch));
  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const esc = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((v) => !v)} title="Appearance — theme, accent, density"
        className={`px-2 py-1 rounded-md ${open ? "bg-zinc-800 text-zinc-50" : "hover:text-zinc-50"}`}>🎨</button>
      {open && (
        <div className="absolute right-0 mt-2 w-60 z-50 bg-zinc-900 border border-zinc-800 rounded-lg shadow-2xl p-3 space-y-3">
          <div>
            <p className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1.5">Theme</p>
            <Segmented value={a.theme} onChange={(v) => update({ theme: v })}
              options={[{ v: "dark", label: "🌙 Dark" }, { v: "light", label: "☀ Light" }]} />
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1.5">Accent</p>
            <div className="flex gap-2">
              {ACCENTS.map((ac) => (
                <button key={ac} onClick={() => update({ accent: ac })} title={ac}
                  style={{ background: ACCENT_SWATCH[ac] }}
                  className={`w-7 h-7 rounded-full border-2 transition-transform hover:scale-110 ${a.accent === ac ? "border-zinc-100" : "border-transparent"}`} />
              ))}
            </div>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1.5">Density</p>
            <Segmented value={a.density} onChange={(v) => update({ density: v })}
              options={DENSITIES.map((dd) => ({ v: dd }))} />
          </div>
        </div>
      )}
    </div>
  );
}

const TABS = [
  { id: "library", label: "Library" },
  { id: "cutter", label: "⚡ Cutter" },
  { id: "cuts", label: "Cuts" },
  { id: "assembler", label: "🧩 Assembler" },
  { id: "studio", label: "Studio" },
  { id: "audio", label: "Audio" },
  { id: "jobs", label: "Jobs" },
  { id: "settings", label: "Settings" },
];

export default function App() {
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem("recomposer_user")); }
    catch { return null; }
  });
  const [view, setView] = useState({ tab: "library" }); // {tab, mediaId?, seg?}
  const [showJobs, setShowJobs] = useState(false);
  const [activeJobs, setActiveJobs] = useState(0);
  const openMedia = (id, seg = null) => setView({ tab: "media", mediaId: id, seg });
  const openCutter = (mediaId = null, trackId = null) => setView({ tab: "cutter", mediaId, trackId });
  const openStudio = (recompId = null) => setView({ tab: "studio", recompId });

  useEffect(() => {
    if (!user) return;
    const poll = () =>
      api.get("/api/jobs")
        .then((js) => setActiveJobs(
          js.filter((j) => j.status === "queued" || j.status === "running").length))
        .catch(() => {});
    poll();
    const t = setInterval(poll, 5000);
    return () => clearInterval(t);
  }, [user]);

  const login = (u) => {
    localStorage.setItem("recomposer_user", JSON.stringify(u));
    setUser(u);
  };
  const logout = () => {
    localStorage.removeItem("recomposer_user");
    setUser(null);
  };

  if (!user) return <Login onLogin={login} />;

  return (
    <div className="h-full flex flex-col">
      <header className="flex items-center gap-1 px-4 h-12 border-b border-zinc-800 bg-zinc-950/90 shrink-0">
        <span className="font-bold mr-4 text-indigo-400">Recomposer</span>
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setView({ tab: t.id })}
            className={`px-3 py-1.5 rounded-md text-sm ${
              view.tab === t.id || (t.id === "library" && view.tab === "media")
                ? "bg-zinc-800 text-zinc-50" : "text-zinc-400 hover:text-zinc-50"}`}>
            {t.label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2 text-sm text-zinc-400">
          <AppearanceMenu />
          <button onClick={() => setShowJobs((v) => !v)}
            className={`relative px-2 py-1 rounded-md text-sm ${
              showJobs ? "bg-zinc-800 text-zinc-50" : "hover:text-zinc-50"}`}
            title="Background jobs">
            ⚙ jobs
            {activeJobs > 0 && (
              <span className="absolute -top-1 -right-1.5 min-w-[16px] h-4 px-1 rounded-full bg-indigo-600 text-white text-[10px] leading-4 text-center">
                {activeJobs}
              </span>
            )}
          </button>
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: user.color }} />
          {user.name}
          <button onClick={logout} className="ml-2 text-xs hover:text-zinc-50">switch</button>
        </div>
      </header>
      {showJobs && <JobsPanel onClose={() => setShowJobs(false)} />}
      <main className="flex-1 min-h-0">
        {view.tab === "library" && (
          <Library user={user} openMedia={openMedia} />
        )}
        {view.tab === "media" && (
          <MediaView user={user} mediaId={view.mediaId} initialSeg={view.seg}
            back={() => setView({ tab: "library" })} openCutter={openCutter} />
        )}
        {view.tab === "cutter" && (
          <Cutter user={user} mediaId={view.mediaId} trackId={view.trackId} openMedia={openMedia} />
        )}
        {view.tab === "cuts" && <CutsPage user={user} openMedia={openMedia} />}
        {view.tab === "assembler" && <Assembler user={user} openStudio={openStudio} />}
        {view.tab === "studio" && <Studio user={user} initialRecompId={view.recompId} />}
        {view.tab === "audio" && <AudioStudio user={user} />}
        {view.tab === "jobs" && <JobsPage user={user} />}
        {view.tab === "settings" && <Settings user={user} onUser={login} />}
      </main>
    </div>
  );
}
