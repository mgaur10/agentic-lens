import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx,js,jsx}"
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter Tight", "Inter", "system-ui", "ui-sans-serif", "sans-serif"],
        heading: ["Inter Tight", "Inter", "system-ui", "ui-sans-serif", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        surface: {
          base: "#F9FAFB",
          glassLight: "rgba(255, 255, 255, 0.85)",
          glassDark: "rgba(15, 23, 42, 0.80)",
          cardDark: "#0A0A0A",
        },
        accent: {
          powerBlue: "#4285F4",
          powerBlueSoft: "rgba(66, 133, 244, 0.20)",
          indigo: "#6366F1",
          indigoSoft: "rgba(99, 102, 241, 0.25)",
        },
        status: {
          supervisor: "#FBBC04",
          security: "#EA4335",
          engineering: "#34A853",
          events: "#4285F4",
          xray: "#651FFF",
          chat: "#5F6368",
        },
      },
      borderRadius: {
        squircle: "999px",
        xl2: "1.25rem",
        xl3: "1.75rem",
        cardInner: "12px",
      },
      boxShadow: {
        "glass-soft":
          "0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24)",
        "glass-dark":
          "0 1px 3px rgba(0,0,0,0.25), 0 1px 2px rgba(0,0,0,0.2)",
        "inner-glow":
          "inset 0 0 0 1px rgba(255, 255, 255, 0.25), 0 0 32px rgba(56, 189, 248, 0.15)",
        "inner-recessed": "inset 0 1px 2px rgba(0,0,0,0.06)",
        "glass-soft-recessed":
          "0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24), inset 0 1px 2px rgba(0,0,0,0.06)",
        "btn-primary-glow": "0 0 15px rgba(59, 130, 246, 0.4)",
        "pill-glow": "0 0 15px rgba(66, 133, 244, 0.35)",
        "matte-top-edge": "inset 0 1px 0 0 rgba(255, 255, 255, 0.1)",
        "omni-float": "0 8px 30px rgb(0,0,0,0.04)",
        "indigo-soft": "0 4px 14px rgba(99, 102, 241, 0.25)",
        "indigo-ambient": "0 8px 30px rgba(99, 102, 241, 0.15)",
        "pill-hover": "0 2px 8px rgba(0,0,0,0.06)",
      },
      backdropBlur: {
        sm: "8px",
        DEFAULT: "18px",
        xl: "24px",
      },
      spacing: {
        4.5: "1.125rem",
        5.5: "1.375rem",
      },
      fontWeight: {
        "sharp": "550",
      },
      transitionTimingFunction: {
        "soft-spring": "cubic-bezier(0.18, 0.89, 0.32, 1.28)",
        smooth: "cubic-bezier(0.4, 0, 0.2, 1)",
        "spring-wow": "cubic-bezier(0.175, 0.885, 0.32, 1.275)",
      },
      transitionDuration: {
        fast: "120ms",
        normal: "180ms",
        slow: "260ms",
        motion: "300ms",
      },
      keyframes: {
        "fade-rise": {
          "0%": { opacity: "0", transform: "translateY(20px) scale(0.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "pulse-orb": {
          "0%, 100%": { transform: "scale(1)", opacity: "0.9" },
          "50%": { transform: "scale(1.08)", opacity: "1" },
        },
        "shield-ripple": {
          "0%": { transform: "scale(0.85)", opacity: "0.6" },
          "100%": { transform: "scale(1.35)", opacity: "0" },
        },
      },
      animation: {
        "fade-rise": "fade-rise 260ms ease-out",
        "fade-rise-soft": "fade-rise 320ms ease-out",
        "pulse-orb": "pulse-orb 1.8s ease-in-out infinite",
        "shield-ripple": "shield-ripple 700ms ease-out",
      },
    },
  },
  plugins: [],
};

export default config;

