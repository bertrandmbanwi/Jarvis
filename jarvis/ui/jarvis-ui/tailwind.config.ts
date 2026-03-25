import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // JARVIS color palette: cyan/blue holographic tones
        jarvis: {
          cyan: "#00d4ff",
          "cyan-dim": "#0099cc",
          "cyan-bright": "#22d3ee",
          blue: "#0066ff",
          "blue-dark": "#001a4d",
          glow: "#00e5ff",
          panel: "rgba(0, 20, 40, 0.85)",
          "panel-border": "rgba(0, 212, 255, 0.12)",
          surface: "rgba(0, 10, 25, 0.95)",
          "surface-hover": "rgba(0, 15, 35, 0.95)",
          text: "#e0f0ff",
          "text-dim": "#6699bb",
          "text-muted": "#5588aa",
          gold: "#ffe18c",
          "gold-dim": "#ccaa44",
          accent: "#ff6600",
          success: "#00ff88",
          warning: "#ffaa00",
          error: "#ff4444",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
      },
      fontSize: {
        "2xs": ["10px", { lineHeight: "14px" }],
        "3xs": ["9px", { lineHeight: "12px" }],
      },
      borderRadius: {
        "2xl": "16px",
        "3xl": "20px",
      },
      animation: {
        "pulse-glow": "pulseGlow 3s ease-in-out infinite",
        "spin-slow": "spin 8s linear infinite",
        "fade-in": "fadeInUp 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards",
        "scale-in": "scaleFadeIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) forwards",
        "breathe": "breatheGlow 2.5s ease-in-out infinite",
        "shimmer": "shimmer 2s ease-in-out infinite",
        "float": "subtleFloat 4s ease-in-out infinite",
      },
      keyframes: {
        pulseGlow: {
          "0%, 100%": { opacity: "0.6", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.02)" },
        },
        fadeInUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        scaleFadeIn: {
          "0%": { opacity: "0", transform: "scale(0.96)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        breatheGlow: {
          "0%, 100%": {
            boxShadow: "0 0 12px rgba(0, 212, 255, 0.15), 0 0 4px rgba(0, 212, 255, 0.1)",
          },
          "50%": {
            boxShadow: "0 0 24px rgba(0, 212, 255, 0.3), 0 0 8px rgba(0, 212, 255, 0.2)",
          },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        subtleFloat: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-3px)" },
        },
      },
      backdropBlur: {
        xs: "2px",
        "2xl": "24px",
        "3xl": "32px",
      },
      transitionTimingFunction: {
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
        "spring": "cubic-bezier(0.34, 1.56, 0.64, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
