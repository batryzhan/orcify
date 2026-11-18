/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Segoe UI", "system-ui", "-apple-system", "Roboto", "sans-serif"],
        mono: ["Cascadia Code", "Consolas", "ui-monospace", "monospace"],
      },
      colors: {
        ink: { DEFAULT: "#16181d", soft: "#4a4f5a", mute: "#8a909c" },
        paper: { DEFAULT: "#f6f5f1", card: "#ffffff", line: "#e4e2db" },
        local: { DEFAULT: "#0f7a5c", soft: "#e3f2ec" },
        warn: { DEFAULT: "#a15c07", soft: "#fbf0dc" },
        fail: { DEFAULT: "#b3261e", soft: "#fbe7e5" },
        // Категориальные слоты графиков (dataviz: проверено validate_palette.js, light).
        series: { 1: "#2a78d6", 2: "#eb6834" },
      },
    },
  },
  plugins: [],
};
