import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { btnCls, btnGhost, inputCls, Spinner } from "./ui";

const VOICE_HINTS = [
  "en-US-JennyNeural", "es-ES-ElviraNeural", "fr-FR-DeniseNeural", "de-DE-KatjaNeural",
  "pt-BR-FranciscaNeural", "ar-SA-ZariyahNeural", "hi-IN-SwaraNeural", "ja-JP-NanamiNeural",
  "ko-KR-SunHiNeural", "zh-CN-XiaoxiaoNeural", "am-ET-MekdesNeural",
];

const GROUPS = {
  transcription: { title: "Transcription", hint: "Defaults for Whisper jobs." },
  ai: { title: "AI & semantic search", hint: "LLM provider and embeddings." },
  recomposition: { title: "Recomposition & workflow defaults",
                   hint: "Pre-filled when you export, search and dub." },
};

function Card({ title, hint, right, children }) {
  return (
    <section className="border border-zinc-800 bg-zinc-900 rounded-xl mb-5">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <div>
          <h2 className="font-semibold">{title}</h2>
          {hint && <p className="text-xs text-zinc-500">{hint}</p>}
        </div>
        {right}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function Field({ spec, value, onChange, languages }) {
  const label = <label className="text-xs text-zinc-400 block mb-1">{spec.label}</label>;
  if (spec.type === "bool") {
    return (
      <label className="flex items-center gap-2 text-sm py-1.5">
        <input type="checkbox" className="accent-indigo-500" checked={!!value}
          onChange={(e) => onChange(e.target.checked)} />
        {spec.label}
      </label>
    );
  }
  if (spec.type === "select") {
    return <div>{label}
      <select className={inputCls} value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        {(spec.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
      </select></div>;
  }
  if (spec.type === "lang") {
    const opts = [{ v: "en", l: "English" },
      ...languages.filter((l) => l.code !== "en").map((l) => ({ v: l.code, l: l.name }))];
    if (spec.key === "default_search_lang") opts.push({ v: "all", l: "All languages" });
    return <div>{label}
      <select className={inputCls} value={value ?? "en"} onChange={(e) => onChange(e.target.value)}>
        {opts.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
      </select></div>;
  }
  if (spec.type === "int") {
    return <div>{label}
      <input type="number" className={inputCls} value={value ?? 0}
        onChange={(e) => onChange(Number(e.target.value))} /></div>;
  }
  return <div>{label}
    <input className={inputCls} value={value ?? ""} onChange={(e) => onChange(e.target.value)} /></div>;
}

/* AI provider status + test + index controls, shown inside the AI card. */
function AiPanel() {
  const [ai, setAi] = useState(null);
  const [embed, setEmbed] = useState(null);
  const [test, setTest] = useState(null);
  const [busy, setBusy] = useState("");

  const refresh = () => {
    api.get("/api/ai/status").then(setAi).catch(() => {});
    api.get("/api/embed/status").then(setEmbed).catch(() => {});
  };
  useEffect(refresh, []);

  const runTest = async () => {
    setBusy("test"); setTest(null);
    try { setTest(await api.post("/api/ai/test")); }
    catch (e) { setTest({ ok: false, error: e.message }); }
    setBusy("");
  };
  const buildIndex = async () => {
    setBusy("index");
    try { const r = await api.post("/api/embed/all"); alert(`Indexing ${r.queued.length} media…`); }
    catch (e) { alert(e.message); }
    setBusy(""); setTimeout(refresh, 1500);
  };

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-sm space-y-2 mt-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="text-zinc-400">LLM:
          {ai?.llm ? <b className="text-emerald-400 ml-1">{ai.llm_provider} · {ai.llm_model}</b>
                   : <span className="text-amber-400 ml-1">not configured</span>}
        </span>
        {ai?.llm_configured?.length > 0 && (
          <span className="text-xs text-zinc-500">configured: {ai.llm_configured.join(", ")}</span>
        )}
        <button className={`${btnGhost} ml-auto`} disabled={busy === "test"} onClick={runTest}>
          {busy === "test" ? "Testing…" : "Test LLM"}
        </button>
      </div>
      {test && (
        <p className={`text-xs ${test.ok ? "text-emerald-400" : "text-red-400"}`}>
          {test.ok ? `✓ ${test.provider} replied: ${JSON.stringify(test.sample)}`
                   : `✗ ${test.error}`}
        </p>
      )}
      <div className="flex items-center gap-3 border-t border-zinc-800 pt-2">
        <span className="text-zinc-400">Semantic index:
          {embed?.available
            ? <b className="text-emerald-400 ml-1">{embed.embedded}/{embed.segments} segments</b>
            : <span className="text-amber-400 ml-1">embeddings unavailable</span>}
        </span>
        <button className={`${btnGhost} ml-auto`} disabled={!embed?.available || busy === "index"}
          onClick={buildIndex}>{busy === "index" ? "Queued…" : "Build / refresh index"}</button>
      </div>
      <p className="text-[11px] text-zinc-600">
        Cloud API keys (Anthropic/OpenAI/Gemini) are read from environment variables for safety;
        Ollama & GPT4All run locally with no key.
      </p>
    </div>
  );
}

function SettingsGroups({ languages }) {
  const [schema, setSchema] = useState([]);
  const [vals, setVals] = useState({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [transOpts, setTransOpts] = useState(null);

  const load = () => api.get("/api/settings").then((r) => {
    setSchema(r.schema); setVals(r.values);
  }).catch(() => {});
  useEffect(() => {
    load();
    api.get("/api/transcribe/options").then(setTransOpts).catch(() => {});
  }, []);

  const change = (k, v) => { setVals((p) => ({ ...p, [k]: v })); setSaved(false); };
  const save = async () => {
    setSaving(true);
    try { const r = await api.put("/api/settings", { values: vals }); setVals(r.values); setSaved(true); }
    catch (e) { alert(e.message); }
    setSaving(false);
  };

  const byGroup = (g) => schema.filter((s) => s.group === g);

  return (
    <>
      {Object.entries(GROUPS).map(([g, meta]) => (
        <Card key={g} title={meta.title} hint={meta.hint}>
          {g === "transcription" && transOpts && (
            <p className="text-xs text-zinc-500 mb-2">
              Detected: <b>{transOpts.device}</b> · engine <b>{transOpts.engine || "none"}</b>
            </p>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2">
            {byGroup(g).map((spec) => (
              <Field key={spec.key} spec={spec} value={vals[spec.key]}
                languages={languages} onChange={(v) => change(spec.key, v)} />
            ))}
          </div>
          {g === "ai" && <AiPanel />}
        </Card>
      ))}
      <div className="flex items-center justify-end gap-3 -mt-2 mb-6">
        {saved && <span className="text-xs text-emerald-400">saved</span>}
        <button className={btnCls} disabled={saving} onClick={save}>
          {saving ? "Saving…" : "Save settings"}
        </button>
      </div>
    </>
  );
}

function ProfileCard({ user, onUser }) {
  const [name, setName] = useState(user?.name || "");
  const [color, setColor] = useState(user?.color || "#6366f1");
  const [busy, setBusy] = useState(false);
  if (!user) return null;
  const save = async () => {
    setBusy(true);
    try {
      const u = await api.patch(`/api/users/${user.id}`, { name, color });
      onUser?.(u);
    } catch (e) { alert(e.message); }
    setBusy(false);
  };
  return (
    <Card title="Profile">
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <label className="text-xs text-zinc-400 block mb-1">Display name</label>
          <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="text-xs text-zinc-400 block mb-1">Colour</label>
          <input type="color" className="h-9 w-14 bg-zinc-950 border border-zinc-700 rounded p-1"
            value={color} onChange={(e) => setColor(e.target.value)} />
        </div>
        <button className={btnCls} disabled={busy} onClick={save}>Save</button>
      </div>
    </Card>
  );
}

const STAT_LABELS = {
  media: "Media", media_ready: "Ready", segments: "Segments", tracks: "Tracks",
  cuts: "Cuts", recompositions: "Recompositions", folders: "Folders", tags: "Tags",
  translations: "Translations", dubs: "Dubs", audio_assets: "Audio beds",
  embedded: "Embedded segs", exports: "Exports", users: "Users",
};

function StatsCard() {
  const [stats, setStats] = useState(null);
  useEffect(() => { api.get("/api/stats").then(setStats).catch(() => {}); }, []);
  return (
    <Card title="Library stats">
      {!stats ? <div className="flex gap-2 text-zinc-400"><Spinner /> Loading</div> : (
        <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          {Object.entries(STAT_LABELS).map(([k, label]) => (
            <div key={k} className="rounded-lg bg-zinc-950 border border-zinc-800 p-2 text-center">
              <div className="text-xl font-semibold">{stats[k] ?? 0}</div>
              <div className="text-[11px] text-zinc-500">{label}</div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function LanguagesCard() {
  const [languages, setLanguages] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ code: "", name: "", tts_engine: "edge",
    tts_voice: "", tts_voice_female: "", tts_voice_male: "" });

  const refresh = () => api.get("/api/languages")
    .then((rows) => { setLanguages(rows); setLoaded(true); })
    .catch((e) => { setErr(e.message); setLoaded(true); });
  useEffect(() => { refresh(); }, []);

  const add = async () => {
    if (!form.code.trim()) return;
    setBusy(true); setErr("");
    try {
      await api.post("/api/languages", form);
      setForm({ code: "", name: "", tts_engine: "edge", tts_voice: "",
                tts_voice_female: "", tts_voice_male: "" });
      refresh();
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  return (
    <Card title="Languages & voices"
      right={<span className="text-xs text-zinc-500">
        {languages.filter((l) => l.dub_capable).length} dub-capable</span>}>
      <div className="overflow-x-auto">
        <div className="min-w-[760px]">
          <div className="px-3 py-2 border-b border-zinc-800 grid grid-cols-[72px_1.2fr_88px_1.5fr_96px] gap-2 text-xs uppercase text-zinc-500">
            <span>Code</span><span>Name</span><span>Engine</span><span>TTS voice</span>
            <span className="text-right">Actions</span>
          </div>
          <div className="grid grid-cols-[72px_1.2fr_88px_1.5fr_96px] gap-2 items-center px-3 py-3 border-b border-zinc-800 bg-zinc-950/50">
            <input className={inputCls} placeholder="sw" value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })} />
            <input className={inputCls} placeholder="Language name" value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input className={inputCls} value={form.tts_engine}
              onChange={(e) => setForm({ ...form, tts_engine: e.target.value })} />
            <div className="space-y-1">
              <input className={inputCls} list="voice-hints" placeholder="default voice (optional)"
                value={form.tts_voice}
                onChange={(e) => setForm({ ...form, tts_voice: e.target.value })} />
              <div className="flex gap-1">
                <input className={inputCls} list="voice-hints" placeholder="♀ female"
                  value={form.tts_voice_female}
                  onChange={(e) => setForm({ ...form, tts_voice_female: e.target.value })} />
                <input className={inputCls} list="voice-hints" placeholder="♂ male"
                  value={form.tts_voice_male}
                  onChange={(e) => setForm({ ...form, tts_voice_male: e.target.value })} />
              </div>
            </div>
            <button className={btnCls} disabled={busy || !form.code.trim()} onClick={add}>Add</button>
          </div>
          <datalist id="voice-hints">
            {VOICE_HINTS.map((v) => <option key={v} value={v} />)}
          </datalist>
          {!loaded && <div className="flex items-center gap-2 p-6 text-zinc-400"><Spinner /> Loading</div>}
          {loaded && languages.length === 0 && <p className="p-6 text-sm text-zinc-500">No languages.</p>}
          {languages.map((lang) => (
            <LanguageRow key={lang.code} lang={lang} onSaved={refresh} onDeleted={refresh} />
          ))}
        </div>
      </div>
      {err && <p className="mt-3 text-sm text-red-400">{err}</p>}
    </Card>
  );
}

function LanguageRow({ lang, onSaved, onDeleted }) {
  const [draft, setDraft] = useState({
    name: lang.name, tts_engine: lang.tts_engine || "edge", tts_voice: lang.tts_voice || "",
    tts_voice_female: lang.tts_voice_female || "", tts_voice_male: lang.tts_voice_male || "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const dirty = useMemo(() =>
    draft.name !== lang.name || draft.tts_engine !== (lang.tts_engine || "edge") ||
    draft.tts_voice !== (lang.tts_voice || "") ||
    draft.tts_voice_female !== (lang.tts_voice_female || "") ||
    draft.tts_voice_male !== (lang.tts_voice_male || ""), [draft, lang]);
  const dubReady = draft.tts_voice.trim() || draft.tts_voice_female.trim() || draft.tts_voice_male.trim();

  const save = async () => {
    setBusy(true); setErr("");
    try { await api.patch(`/api/languages/${lang.code}`, draft); onSaved(); }
    catch (e) { setErr(e.message); }
    setBusy(false);
  };
  const remove = async () => {
    if (!confirm(`Delete language "${lang.name}"?`)) return;
    setBusy(true); setErr("");
    try { await api.del(`/api/languages/${lang.code}`); onDeleted(); }
    catch (e) { setErr(e.message); setBusy(false); }
  };

  return (
    <div className="grid grid-cols-[72px_1.2fr_88px_1.5fr_96px] gap-2 items-center px-3 py-2 border-b border-zinc-800">
      <div>
        <p className="font-mono text-sm text-zinc-200">{lang.code}</p>
        <p className={`text-[11px] ${dubReady ? "text-emerald-400" : "text-zinc-600"}`}>
          {dubReady ? "dub ready" : "text only"}</p>
      </div>
      <input className={inputCls} value={draft.name}
        onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
      <input className={inputCls} value={draft.tts_engine}
        onChange={(e) => setDraft({ ...draft, tts_engine: e.target.value })} />
      <div className="space-y-1">
        <input className={inputCls} list="voice-hints" placeholder="default voice"
          value={draft.tts_voice} onChange={(e) => setDraft({ ...draft, tts_voice: e.target.value })} />
        <div className="flex gap-1">
          <input className={inputCls} list="voice-hints" placeholder="♀ female voice"
            value={draft.tts_voice_female}
            onChange={(e) => setDraft({ ...draft, tts_voice_female: e.target.value })} />
          <input className={inputCls} list="voice-hints" placeholder="♂ male voice"
            value={draft.tts_voice_male}
            onChange={(e) => setDraft({ ...draft, tts_voice_male: e.target.value })} />
        </div>
      </div>
      <div className="flex items-center justify-end gap-1">
        <button className={`${btnCls} !px-2`} disabled={busy || !dirty} onClick={save}>Save</button>
        <button className="text-zinc-500 hover:text-red-400 px-1 text-sm" disabled={busy}
          onClick={remove} title="Delete language">delete</button>
      </div>
      {err && <p className="col-span-5 text-xs text-red-400">{err}</p>}
    </div>
  );
}

export default function Settings({ user, onUser }) {
  const [languages, setLanguages] = useState([]);
  useEffect(() => { api.get("/api/languages").then(setLanguages).catch(() => {}); }, []);
  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto">
        <h1 className="text-xl font-semibold mb-5">Settings</h1>
        <ProfileCard user={user} onUser={onUser} />
        <StatsCard />
        <SettingsGroups languages={languages} />
        <LanguagesCard />
      </div>
    </div>
  );
}
