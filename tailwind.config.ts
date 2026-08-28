import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#080b12",
        panel: "#101722",
        line: "#263142",
        lime: "#d4ff6b",
        cyan: "#68e3e8",
        coral: "#ff8b77",
        fog: "#a6b2c3",
      },
      boxShadow: {
        panel: "0 22px 70px rgba(0, 0, 0, 0.28)",
        glow: "0 0 0 1px rgba(212, 255, 107, 0.22), 0 18px 60px rgba(104, 227, 232, 0.08)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
