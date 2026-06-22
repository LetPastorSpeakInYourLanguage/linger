/* Tiny shared UI primitives. */
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/* size: undefined|"wide"(legacy `wide` prop)|"full". For "full" the body fills
 * the dialog and the child owns its own scroll regions (pass bodyClass to drop
 * the default padding/scroll). */
export function Modal({ title, onClose, children, wide, size, bodyClass }) {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") { e.stopPropagation(); onClose(); }
    };
    window.addEventListener("keydown", onKey, true); // capture: beats page shortcuts
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  const full = size === "full";
  const shape = full
    ? "w-[95vw] max-w-[1240px] h-[90vh]"
    : `w-full ${wide ? "max-w-3xl" : "max-w-md"} max-h-[85vh]`;

  return (
    <div data-modal className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl flex flex-col ${shape}`}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 shrink-0">
          <h2 className="font-semibold">{title}</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-white text-xl leading-none"
            title="Close (Esc)">×</button>
        </div>
        <div className={bodyClass ?? (full ? "flex-1 min-h-0 flex" : "p-4 overflow-y-auto")}>
          {children}
        </div>
      </div>
    </div>
  );
}

/* True while any modal is open — page-level keyboard shortcuts should bail. */
export const modalOpen = () => !!document.querySelector("[data-modal]");

export const inputCls =
  "w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-indigo-500";

export const btnCls =
  "px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed";

export const btnGhost =
  "px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 text-sm";

export function Tag({ name, onClick, active, prefix = "#" }) {
  return (
    <button onClick={onClick}
      className={`text-xs px-2 py-0.5 rounded-full border whitespace-nowrap ${
        active ? "bg-indigo-600 border-indigo-500 text-white"
               : "border-zinc-700 text-zinc-300 hover:border-zinc-500"}`}>
      {prefix}{name}
    </button>
  );
}

export function Spinner() {
  return <div className="w-5 h-5 border-2 border-zinc-600 border-t-indigo-400 rounded-full animate-spin" />;
}

/* Labelled range slider with a live numeric readout. Familiar native <input
 * type=range> under the hood, accent-tinted to match the app. */
export function Slider({ label, value, min, max, step = 1, onChange, fmt, hint }) {
  return (
    <label className="block select-none">
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-xs text-zinc-300 font-medium">
          {label}
          {hint && <span className="text-zinc-600 ml-1 font-normal">{hint}</span>}
        </span>
        <span className="text-xs text-zinc-400 tabular-nums font-mono">
          {fmt ? fmt(value) : value}
        </span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1.5 appearance-none rounded-full bg-zinc-700 accent-indigo-500 cursor-pointer" />
    </label>
  );
}

/* ----------------------------------------------------- resizable panels */

/** Drag-to-resize a panel. invert=true when the panel is on the right
 *  (dragging left should grow it). Width persists in localStorage. */
export function useResizable(storageKey, initial, min = 220, max = 800, invert = false) {
  const [size, setSize] = useState(() => {
    const v = Number(localStorage.getItem(storageKey));
    return v >= min && v <= max ? v : initial;
  });
  const startDrag = (e) => {
    e.preventDefault();
    const startX = e.clientX, startSize = size;
    const move = (ev) => {
      const delta = invert ? startX - ev.clientX : ev.clientX - startX;
      const s = Math.max(min, Math.min(max, startSize + delta));
      setSize(s);
      localStorage.setItem(storageKey, String(s));
    };
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };
  return [size, startDrag];
}

export function DragBar({ onMouseDown }) {
  return (
    <div onMouseDown={onMouseDown}
      className="w-1.5 shrink-0 cursor-col-resize bg-zinc-800/60 hover:bg-indigo-500 active:bg-indigo-500 transition-colors"
      title="Drag to resize" />
  );
}

/* -------------------------------------------------- searchable picker */

/** "+ Tag" style button that opens a searchable dropdown — scales to
 *  hundreds of folders/tags/media without filling the screen. The panel is
 *  rendered in a body portal at fixed coordinates anchored to the button and
 *  clamped to the viewport, so it never gets clipped by a panel's overflow or
 *  pushed off-screen (e.g. the Assembler's narrow left column). */
const PICKER_W = 256, PICKER_MAXH = 320, PICKER_MARGIN = 8;

export function Picker({ label, icon, items, onPick, align = "left" }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [pos, setPos] = useState(null);
  const btnRef = useRef();
  const popRef = useRef();

  const place = useCallback(() => {
    const b = btnRef.current;
    if (!b) return;
    const r = b.getBoundingClientRect();
    let left = align === "right" ? r.right - PICKER_W : r.left;
    left = Math.max(PICKER_MARGIN, Math.min(left, window.innerWidth - PICKER_W - PICKER_MARGIN));
    const below = window.innerHeight - r.bottom;
    const openUp = below < PICKER_MAXH + PICKER_MARGIN && r.top > below;
    setPos({
      left,
      top: openUp ? undefined : r.bottom + 4,
      bottom: openUp ? window.innerHeight - r.top + 4 : undefined,
      maxH: Math.min(PICKER_MAXH, (openUp ? r.top : below) - PICKER_MARGIN),
    });
  }, [align]);

  useEffect(() => {
    if (!open) return;
    place();
    const reflow = () => place();
    const close = (e) => {
      if (btnRef.current?.contains(e.target) || popRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    const esc = (e) => e.key === "Escape" && setOpen(false);
    window.addEventListener("scroll", reflow, true);
    window.addEventListener("resize", reflow);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("scroll", reflow, true);
      window.removeEventListener("resize", reflow);
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [open, place]);

  const filtered = items
    .filter((i) => i.label.toLowerCase().includes(q.trim().toLowerCase()))
    .slice(0, 60);

  return (
    <div className="relative inline-block">
      <button ref={btnRef} onClick={() => { setOpen(!open); setQ(""); }}
        className={`text-xs px-2 py-1 rounded-lg border whitespace-nowrap ${
          open ? "border-indigo-500 text-white" : "border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-white"}`}>
        {icon} {label} ▾
      </button>
      {open && pos && createPortal(
        <div ref={popRef}
          style={{ position: "fixed", left: pos.left, top: pos.top, bottom: pos.bottom, width: PICKER_W }}
          className="z-[60] bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl flex flex-col">
          <input autoFocus className="w-full bg-zinc-950 border-b border-zinc-800 rounded-t-lg px-3 py-2 text-sm outline-none shrink-0"
            placeholder={`Search ${label.toLowerCase()}…`}
            value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && filtered.length) { onPick(filtered[0]); setOpen(false); }
              if (e.key === "Escape") setOpen(false);
            }} />
          <div className="overflow-y-auto py-1" style={{ maxHeight: pos.maxH }}>
            {filtered.length === 0 && (
              <p className="text-xs text-zinc-500 px-3 py-2">No matches.</p>
            )}
            {filtered.map((i) => (
              <button key={i.key ?? i.label}
                onClick={() => { onPick(i); setOpen(false); }}
                className="block w-full text-left px-3 py-1.5 text-sm hover:bg-zinc-800 truncate">
                {i.icon} {i.label}
                {i.hint != null && <span className="text-zinc-500 text-xs ml-1">{i.hint}</span>}
              </button>
            ))}
          </div>
        </div>, document.body)}
    </div>
  );
}

/* ------------------------------------------------------- context menu */

/** Right-click menu. items: {label, onClick} | {header} | {divider}. */
export function ContextMenu({ x, y, items, onClose }) {
  const ref = useRef();
  useEffect(() => {
    const close = () => onClose();
    const esc = (e) => e.key === "Escape" && onClose();
    // delay so the opening right-click doesn't immediately close it
    const t = setTimeout(() => {
      document.addEventListener("mousedown", close);
      document.addEventListener("keydown", esc);
    }, 0);
    return () => { clearTimeout(t); document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [onClose]);

  // keep on screen
  const style = {
    left: Math.min(x, window.innerWidth - 240),
    top: Math.min(y, window.innerHeight - Math.min(items.length * 30 + 16, 400)),
  };

  return (
    <div ref={ref} style={style}
      className="fixed z-50 w-56 max-h-96 overflow-y-auto bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl py-1"
      onMouseDown={(e) => e.stopPropagation()}>
      {items.map((it, i) =>
        it.divider ? (
          <div key={i} className="my-1 border-t border-zinc-800" />
        ) : it.header ? (
          <p key={i} className="px-3 pt-1.5 pb-0.5 text-[10px] uppercase tracking-wide text-zinc-500">{it.header}</p>
        ) : (
          <button key={i}
            onClick={() => { it.onClick(); onClose(); }}
            className="block w-full text-left px-3 py-1.5 text-sm hover:bg-zinc-800 truncate">
            {it.label}
          </button>
        ))}
    </div>
  );
}
