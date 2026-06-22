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
        // mapped to index.css token variables → live theme/accent switching
        zinc: {
          50: "rgb(var(--z-50) / <alpha-value>)",
          100: "rgb(var(--z-100) / <alpha-value>)",
          200: "rgb(var(--z-200) / <alpha-value>)",
          300: "rgb(var(--z-300) / <alpha-value>)",
          400: "rgb(var(--z-400) / <alpha-value>)",
          500: "rgb(var(--z-500) / <alpha-value>)",
          600: "rgb(var(--z-600) / <alpha-value>)",
          700: "rgb(var(--z-700) / <alpha-value>)",
          800: "rgb(var(--z-800) / <alpha-value>)",
          850: "rgb(var(--z-850) / <alpha-value>)",
          900: "rgb(var(--z-900) / <alpha-value>)",
          925: "rgb(var(--z-925) / <alpha-value>)",
          950: "rgb(var(--z-950) / <alpha-value>)",
        },
        indigo: {
          200: "rgb(var(--i-200) / <alpha-value>)",
          300: "rgb(var(--i-300) / <alpha-value>)",
          400: "rgb(var(--i-400) / <alpha-value>)",
          500: "rgb(var(--i-500) / <alpha-value>)",
          600: "rgb(var(--i-600) / <alpha-value>)",
          700: "rgb(var(--i-700) / <alpha-value>)",
        },
      },
      boxShadow: {
        "2xl": "0 16px 40px -16px rgba(0,0,0,.75)",
      },
    },
  },
  plugins: [],
};
