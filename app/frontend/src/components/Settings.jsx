import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { btnCls, btnGhost, inputCls, Spinner } from "./ui";

const VOICE_HINTS = [
  "en-US-JennyNeural",
  "es-ES-ElviraNeural",
  "fr-FR-DeniseNeural",
  "de-DE-KatjaNeural",
  "pt-BR-FranciscaNeural",
  "ar-SA-ZariyahNeural",
  "hi-IN-SwaraNeural",
  "ja-JP-NanamiNeural",
  "ko-KR-SunHiNeural",
  "zh-CN-XiaoxiaoNeural",
  "am-ET-MekdesNeural",
];

function LanguageRow({ lang, onSaved, onDeleted }) {
  const [draft, setDraft] = useState({
    name: lang.name,
    tts_engine: lang.tts_engine || "edge",
    tts_voice: lang.tts_voice || "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const dirty = useMemo(() =>
    draft.name !== lang.name ||
    draft.tts_engine !== (lang.tts_engine || "edge") ||
    draft.tts_voice !== (lang.tts_voice || ""),
    [draft, lang]);

  const save = async () => {
    setBusy(true); setErr("");
    try {
      await api.patch(`/api/languages/${lang.code}`, draft);
      onSaved();
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  const remove = async () => {
    if (!confirm(`Delete language "${lang.name}"?`)) return;
    setBusy(true); setErr("");
    try {
      await api.del(`/api/languages/${lang.code}`);
      onDeleted();
    } catch (e) { setErr(e.message); setBusy(false); }
  };

  return (
    <div className="grid grid-cols-[72px_1.2fr_88px_1.5fr_96px] gap-2 items-center px-3 py-2 border-b border-zinc-800">
      <div>
        <p className="font-mono text-sm text-zinc-200">{lang.code}</p>
        <p className={`text-[11px] ${draft.tts_voice.trim() ? "text-emerald-400" : "text-zinc-600"}`}>
          {draft.tts_voice.trim() ? "dub ready" : "text only"}
        </p>
      </div>
      <input className={inputCls} value={draft.name}
        onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
      <input className={inputCls} value={draft.tts_engine}
        onChange={(e) => setDraft({ ...draft, tts_engine: e.target.value })} />
      <input className={inputCls} list="voice-hints" placeholder="Edge voice name"
        value={draft.tts_voice}
        onChange={(e) => setDraft({ ...draft, tts_voice: e.target.value })} />
      <div className="flex items-center justify-end gap-1">
        <button className={`${btnCls} !px-2`} disabled={busy || !dirty} onClick={save}>
          Save
        </button>
        <button className="text-zinc-500 hover:text-red-400 px-1 text-sm" disabled={busy}
          onClick={remove} title="Delete language">
          delete
        </button>
      </div>
      {err && <p className="col-span-5 text-xs text-red-400">{err}</p>}
    </div>
  );
}

export default function Settings() {
  const [languages, setLanguages] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    code: "",
    name: "",
    tts_engine: "edge",
    tts_voice: "",
  });

  const refresh = () =>
    api.get("/api/languages")
      .then((rows) => { setLanguages(rows); setLoaded(true); })
      .catch((e) => { setErr(e.message); setLoaded(true); });

  useEffect(() => { refresh(); }, []);

  const add = async () => {
    if (!form.code.trim()) return;
    setBusy(true); setErr("");
    try {
      await api.post("/api/languages", form);
      setForm({ code: "", name: "", tts_engine: "edge", tts_voice: "" });
      refresh();
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between mb-5">
          <h1 className="text-xl font-semibold">Settings</h1>
          <span className="text-xs text-zinc-500">
            {languages.filter((l) => l.dub_capable).length} dub-capable languages
          </span>
        </div>

        <section className="border border-zinc-800 bg-zinc-900 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <div className="min-w-[760px]">
              <div className="px-3 py-2 border-b border-zinc-800 grid grid-cols-[72px_1.2fr_88px_1.5fr_96px] gap-2 text-xs uppercase text-zinc-500">
                <span>Code</span>
                <span>Name</span>
                <span>Engine</span>
                <span>TTS voice</span>
                <span className="text-right">Actions</span>
              </div>

              <div className="grid grid-cols-[72px_1.2fr_88px_1.5fr_96px] gap-2 items-center px-3 py-3 border-b border-zinc-800 bg-zinc-950/50">
                <input className={inputCls} placeholder="sw" value={form.code}
                  onChange={(e) => setForm({ ...form, code: e.target.value })} />
                <input className={inputCls} placeholder="Language name" value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })} />
                <input className={inputCls} value={form.tts_engine}
                  onChange={(e) => setForm({ ...form, tts_engine: e.target.value })} />
                <input className={inputCls} list="voice-hints" placeholder="optional"
                  value={form.tts_voice}
                  onChange={(e) => setForm({ ...form, tts_voice: e.target.value })} />
                <button className={btnCls} disabled={busy || !form.code.trim()} onClick={add}>
                  Add
                </button>
              </div>

              <datalist id="voice-hints">
                {VOICE_HINTS.map((v) => <option key={v} value={v} />)}
              </datalist>

              {!loaded && (
                <div className="flex items-center gap-2 p-6 text-zinc-400">
                  <Spinner /> Loading languages
                </div>
              )}
              {loaded && languages.length === 0 && (
                <p className="p-6 text-sm text-zinc-500">No languages configured.</p>
              )}
              {languages.map((lang) => (
                <LanguageRow key={lang.code} lang={lang}
                  onSaved={refresh} onDeleted={refresh} />
              ))}
            </div>
          </div>
        </section>

        {err && <p className="mt-3 text-sm text-red-400">{err}</p>}
        <div className="mt-4 flex justify-end">
          <button className={btnGhost} onClick={refresh}>Refresh</button>
        </div>
      </div>
    </div>
  );
}
