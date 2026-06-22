/* Appearance = the design-handoff's theme / accent / density switches, applied
 * to <html data-theme data-accent data-density>. The CSS-variable token system
 * in index.css does the rest (Tailwind's zinc/indigo map to those variables),
 * so changing an attribute re-skins the whole app live. */
const KEY = "recomposer_appearance";

export const THEMES = ["dark", "light"];
export const ACCENTS = ["indigo", "violet", "cyan", "emerald", "rose"];
export const DENSITIES = ["comfortable", "dense"];
export const ACCENT_SWATCH = {
  indigo: "#6366f1", violet: "#8b5cf6", cyan: "#06b6d4", emerald: "#10b981", rose: "#f43f5e",
};

const DEFAULTS = { theme: "dark", accent: "indigo", density: "comfortable" };

export function getAppearance() {
  try { return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") }; }
  catch { return { ...DEFAULTS }; }
}

export function applyAppearance(a = getAppearance()) {
  const r = document.documentElement;
  r.dataset.theme = THEMES.includes(a.theme) ? a.theme : "dark";
  r.dataset.accent = ACCENTS.includes(a.accent) ? a.accent : "indigo";
  r.dataset.density = DENSITIES.includes(a.density) ? a.density : "comfortable";
  return a;
}

export function setAppearance(patch) {
  const a = { ...getAppearance(), ...patch };
  localStorage.setItem(KEY, JSON.stringify(a));
  return applyAppearance(a);
}
