/* Tiny shared UI primitives. */
export function Modal({ title, onClose, children, wide }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl w-full ${
        wide ? "max-w-3xl" : "max-w-md"} max-h-[85vh] flex flex-col`}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h2 className="font-semibold">{title}</h2>
          <button onClick={onClose} className="text-zinc-400 hover:text-white text-xl leading-none">×</button>
        </div>
        <div className="p-4 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}

export const inputCls =
  "w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm outline-none focus:border-indigo-500";

export const btnCls =
  "px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed";

export const btnGhost =
  "px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-500 text-sm";

export function Tag({ name, onClick, active }) {
  return (
    <button onClick={onClick}
      className={`text-xs px-2 py-0.5 rounded-full border ${
        active ? "bg-indigo-600 border-indigo-500 text-white"
               : "border-zinc-700 text-zinc-300 hover:border-zinc-500"}`}>
      #{name}
    </button>
  );
}

export function Spinner() {
  return <div className="w-5 h-5 border-2 border-zinc-600 border-t-indigo-400 rounded-full animate-spin" />;
}
