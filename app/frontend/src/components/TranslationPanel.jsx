import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, fmtTime } from "../api";
import { Modal, inputCls, btnCls, btnGhost, Spinner } from "./ui";

function TranslationEditor({ translation, onChanged }) {
  const [saving, setSaving] = useState(null);

  const saveSegment = async (seg, value) => {
    if (value === seg.text) return;
    setSaving(seg.segment_id);
    try {
      await api.patch(`/api/translations/${translation.id}/segments/${seg.segment_id}`, {
        text: value,
      });
      onChanged();
    } catch (e) {
      alert(e.message);
    }
    setSaving(null);
  };

  const createDub = async () => {
    try {
      await api.post(`/api/translations/${translation.id}/dub`);
      onChanged();
    } catch (e) {
      alert(e.message);
    }
  };

  return (
    <div className="min-h-0 flex flex-col">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-zinc-800 bg-zinc-950/40">
        <div className="min-w-0 flex-1">
          <p className="font-medium truncate">
            {translation.language_name || translation.lang_code}
            <span className="text-zinc-500 text-xs ml-2">{translation.source}</span>
          </p>
          <p className="text-xs text-zinc-500">
            {translation.segments.length} subtitle lines
          </p>
        </div>
        <button className={btnCls} disabled={!translation.dub_capable}
          title={translation.dub_capable ? "Generate audio from this translated subtitle text" : "Configure a TTS voice for this language first"}
          onClick={createDub}>
          Generate dub
        </button>
      </div>

      <div className="overflow-y-auto">
        {translation.segments.map((seg) => (
          <div key={seg.segment_id}
            className="grid grid-cols-[92px_1fr_1fr_44px] gap-2 px-3 py-2 border-b border-zinc-800/70 items-start">
            <div className="text-xs text-zinc-500 pt-2">
              {fmtTime(seg.start_s)}<br />{fmtTime(seg.end_s)}
            </div>
            <p className="text-sm text-zinc-400 py-2">{seg.source_text}</p>
            <textarea className={`${inputCls} min-h-20 resize-y`}
              defaultValue={seg.text || ""}
              onBlur={(e) => saveSegment(seg, e.target.value)}
              placeholder="Translated subtitle text" />
            <div className="pt-2 text-xs text-zinc-500">
              {saving === seg.segment_id ? "saving" : ""}
            </div>
          </div>
        ))}
      </div>

      {translation.dubs.length > 0 && (
        <div className="border-t border-zinc-800 p-3 space-y-2 bg-zinc-950/50">
          {translation.dubs.map((dub) => (
            <div key={dub.id} className="flex items-center gap-3 text-sm">
              <span className={`w-20 ${
                dub.status === "done" ? "text-emerald-400" :
                dub.status === "failed" ? "text-red-400" : "text-amber-400"
              }`}>
                {dub.status}
              </span>
              <span className="text-zinc-500 flex-1 truncate">{dub.voice || dub.engine}</span>
              {dub.status === "done" && (
                <audio controls src={`/api/dubs/${dub.id}/audio`} className="h-8 max-w-xs" />
              )}
              {dub.detail && dub.status !== "done" && (
                <span className="text-xs text-zinc-500 truncate max-w-xs">{dub.detail}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function TranslationPanel({ cut, onClose, onChanged }) {
  const [data, setData] = useState(null);
  const [languages, setLanguages] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [lang, setLang] = useState("");
  const [mode, setMode] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const pollRef = useRef();
  const onChangedRef = useRef(onChanged);

  useEffect(() => { onChangedRef.current = onChanged; }, [onChanged]);

  const refresh = useCallback(() =>
    api.get(`/api/cuts/${cut.id}/translations`).then((d) => {
      setData(d);
      setSelectedId((cur) =>
        d.translations.some((t) => t.id === cur) ? cur : d.translations[0]?.id ?? null);
      onChangedRef.current?.();
    }), [cut.id]);

  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
    api.get("/api/languages").then((rows) => {
      setLanguages(rows);
      setLang((cur) => cur || rows[0]?.code || "");
    }).catch(() => {});
  }, [cut.id, refresh]);

  const hasRunningDub = useMemo(() =>
    data?.translations?.some((t) =>
      t.dubs.some((d) => d.status === "queued" || d.status === "running")),
    [data]);

  useEffect(() => {
    clearInterval(pollRef.current);
    if (!hasRunningDub) return;
    pollRef.current = setInterval(() => refresh().catch(() => {}), 2500);
    return () => clearInterval(pollRef.current);
  }, [hasRunningDub, cut.id, refresh]);

  const createTranslation = async () => {
    if (!lang) return;
    setBusy(true); setErr("");
    try {
      const tr = await api.post(`/api/cuts/${cut.id}/translations`, {
        lang_code: lang,
        source: mode,
        user_id: null,
      });
      await refresh();
      setSelectedId(tr.id);
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  const removeTranslation = async () => {
    if (!selectedId) return;
    if (!confirm("Delete this translation and its dubs?")) return;
    await api.del(`/api/translations/${selectedId}`);
    refresh().catch((e) => setErr(e.message));
  };

  const selected = data?.translations.find((t) => t.id === selectedId);

  return (
    <Modal title={`Translate & dub — ${cut.title}`} onClose={onClose} wide>
      <div className="h-[72vh] flex flex-col border border-zinc-800 rounded-lg overflow-hidden bg-zinc-900">
        <div className="shrink-0 border-b border-zinc-800 p-3 flex items-center gap-2 flex-wrap">
          <select className={`${inputCls} w-44`} value={lang}
            onChange={(e) => setLang(e.target.value)}>
            {languages.map((l) => (
              <option key={l.code} value={l.code}>
                {l.name} ({l.code}){l.dub_capable ? "" : " · no voice"}
              </option>
            ))}
          </select>
          <select className={`${inputCls} w-32`} value={mode}
            onChange={(e) => setMode(e.target.value)}>
            <option value="auto">Auto</option>
            <option value="manual">Manual</option>
          </select>
          <button className={btnCls} disabled={busy || !lang} onClick={createTranslation}>
            {busy ? "Creating…" : "Create translation"}
          </button>
          {data?.translations?.length > 0 && (
            <select className={`${inputCls} flex-1 min-w-48`} value={selectedId ?? ""}
              onChange={(e) => setSelectedId(Number(e.target.value))}>
              {data.translations.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.language_name || t.lang_code} · {t.source}
                </option>
              ))}
            </select>
          )}
          {selected && (
            <button className={btnGhost} onClick={removeTranslation}>Delete</button>
          )}
        </div>

        {err && <p className="shrink-0 px-3 py-2 text-sm text-red-400">{err}</p>}
        {!data && (
          <div className="flex items-center gap-2 p-6 text-zinc-400">
            <Spinner /> Loading
          </div>
        )}
        {data && !selected && (
          <div className="p-6 text-sm text-zinc-500">
            <p className="font-medium text-zinc-300 mb-2">{cut.title}</p>
            {data.source_segments.map((s) => (
              <p key={s.id} className="mb-2">
                <span className="text-zinc-600">{fmtTime(s.start_s)} </span>{s.text}
              </p>
            ))}
          </div>
        )}
        {selected && (
          <TranslationEditor translation={selected} onChanged={refresh} />
        )}
      </div>
    </Modal>
  );
}
