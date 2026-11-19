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
        // Холодная «трекерная» палитра: текст, фон колонок, линии.
        ink: { DEFAULT: "#172b4d", soft: "#44546f", mute: "#626f86" },
        paper: { DEFAULT: "#f7f8f9", card: "#ffffff", line: "#dcdfe4", col: "#f1f2f4" },
        brand: { DEFAULT: "#0c66e4", hover: "#0055cc", soft: "#e9f2ff" },
        local: { DEFAULT: "#0f7a5c", soft: "#e3f2ec" },
        warn: { DEFAULT: "#a15c07", soft: "#fbf0dc" },
        fail: { DEFAULT: "#b3261e", soft: "#fbe7e5" },
        // Категориальные слоты графиков (dataviz: проверено validate_palette.js, light).
        series: { 1: "#2a78d6", 2: "#eb6834" },
        // Рамка выделения, которую «рисуют» агенты (как в редакторах дизайна).
        select: "#1d7afc",
      },
      boxShadow: {
        card: "0 1px 1px rgba(9,30,66,.25), 0 0 1px rgba(9,30,66,.31)",
        raised: "0 8px 12px rgba(9,30,66,.15), 0 0 1px rgba(9,30,66,.31)",
      },
      keyframes: {
        caret: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0" } },
        "fade-up": { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "none" } },
        dash: { to: { strokeDashoffset: "-20" } },
      },
      animation: {
        caret: "caret 0.9s step-end infinite",
        "fade-up": "fade-up 0.25s ease-out both",
        dash: "dash 0.8s linear infinite",
      },
    },
  },
  plugins: [],
};
