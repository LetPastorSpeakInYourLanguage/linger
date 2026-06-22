/** @type {import('tailwindcss').Config} */
// Re-skin to the design-handoff token system (dark + indigo accent): the app is
// written in zinc/indigo utility classes, so remapping those two scales to the
// handoff's exact values re-skins every surface at once. Opacity modifiers
// (bg-zinc-900/50, border-indigo-500/40, …) keep working since these are hex.
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Public Sans"', "ui-sans-serif", "system-ui", "-apple-system", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        zinc: {
          50: "#fafafb",
          100: "#f4f4f6",   // --text
          200: "#e4e4e9",
          300: "#c9c9d1",
          400: "#a6a6b0",   // --text-1
          500: "#74747f",   // --text-2
          600: "#55555e",   // --text-3
          700: "#2e2e36",   // input / control lines
          800: "#232329",   // --bg-4 (borders, active)
          850: "#1c1c21",   // --bg-3
          900: "#16161a",   // --bg-2 (panels)
          925: "#0f0f12",   // --bg-1
          950: "#0a0a0c",   // --bg (deepest)
        },
        indigo: {
          200: "#c3c9ff",
          300: "#a5b0ff",   // --accent-text (dark)
          400: "#818cf8",   // --accent-2
          500: "#6366f1",   // --accent
          600: "#5457e6",   // button base
          700: "#4144c9",
        },
      },
      boxShadow: {
        "2xl": "0 16px 40px -16px rgba(0,0,0,.75)",
      },
    },
  },
  plugins: [],
};
