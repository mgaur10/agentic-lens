## Glass Prism UI – React + Tailwind Service

This folder contains the **Glass Prism UI** for AI Agentic Prism: a React + Tailwind frontend that runs as its own Cloud Run service and talks to the Python backend over HTTP.

- **Glass Prism UI**: React + Tailwind app deployed as a Cloud Run service (e.g. `ai-prism-agent-glass-ui`).
- **Backend / Agent Engine**: shared Python orchestration, exposed via `glass_ui_api.py` (FastAPI) at `/api/query`, `/api/logs`, etc.

This file gives you:

- A **Tailwind configuration** aligned to the Glass Prism visual identity.
- A **React Omnibar component** that implements the new Command Center input.
- A minimal **API contract** between the Omnibar and the backend.

You can copy these into a Vite/Next.js app once Node/npm are available on your environment.

---

## 1. Tailwind configuration (`tailwind.config.ts`)

Use this as the starting Tailwind config in the new React app:

```ts
// tailwind.config.ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx,js,jsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["InterVariable", "Inter", "system-ui", "ui-sans-serif", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        surface: {
          base: "#F9FAFB",
          glassLight: "rgba(255, 255, 255, 0.85)",
          glassDark: "rgba(15, 23, 42, 0.80)", // slate-900 w/ alpha
        },
        accent: {
          powerBlue: "#4285F4",
          powerBlueSoft: "rgba(66, 133, 244, 0.2)",
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
        // For squircles / continuous curves we approximate with higher radii
        squircle: "999px",
        xl2: "1.25rem",
        xl3: "1.75rem",
      },
      boxShadow: {
        "glass-soft":
          "0 18px 45px rgba(15, 23, 42, 0.12), 0 0 0 1px rgba(148, 163, 184, 0.25)",
        "glass-dark":
          "0 24px 60px rgba(15, 23, 42, 0.7), 0 0 0 1px rgba(148, 163, 184, 0.4)",
        "inner-glow":
          "inset 0 0 0 1px rgba(255, 255, 255, 0.25), 0 0 32px rgba(56, 189, 248, 0.15)",
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
      transitionTimingFunction: {
        "soft-spring": "cubic-bezier(0.18, 0.89, 0.32, 1.28)",
      },
      transitionDuration: {
        fast: "120ms",
        normal: "180ms",
        slow: "260ms",
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
```

This config encodes the **Glass Prism tokens**:

- **Surfaces**: light and dark glass with blur.
- **Accent**: Power Blue + soft variant.
- **Status colors**: Supervisor, Security, Engineering, Events, X-Ray, Chat.
- **Radius/shadows**: for glass panels and squircles.
- **Motion tokens**: `fade-rise`, `pulse-orb`, and `shield-ripple`.

---

## 2. Omnibar component (`Omnibar.tsx`)

Below is a self-contained React Omnibar that you can drop into `src/components/Omnibar.tsx` in the new app.

### 2.1 API types

```ts
// src/types/ui.ts
export type OmnibarStatus =
  | "idle"
  | "connecting"
  | "processing"
  | "error";

export interface OmnibarSuggestion {
  id: string;
  label: string;
  value: string;
}
```

### 2.2 Component

```tsx
// src/components/Omnibar.tsx
import React, { useEffect, useMemo, useState } from "react";
import type { OmnibarStatus, OmnibarSuggestion } from "../types/ui";

interface OmnibarProps {
  status: OmnibarStatus;
  placeholderSuggestions: string[];
  pillSuggestions?: OmnibarSuggestion[];
  disabled?: boolean;
  autoFocus?: boolean;
  onSubmit: (value: string) => void;
  onSuggestionClick?: (suggestion: OmnibarSuggestion) => void;
}

export const Omnibar: React.FC<OmnibarProps> = ({
  status,
  placeholderSuggestions,
  pillSuggestions = [],
  disabled = false,
  autoFocus = true,
  onSubmit,
  onSuggestionClick,
}) => {
  const [value, setValue] = useState("");
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const isBusy = status === "processing" || status === "connecting";

  const currentPlaceholder = useMemo(() => {
    if (placeholderSuggestions.length === 0) return "Ask anything about GCP…";
    return placeholderSuggestions[placeholderIndex % placeholderSuggestions.length];
  }, [placeholderIndex, placeholderSuggestions]);

  // Ghost suggestion rotation (typing placeholder effect)
  useEffect(() => {
    if (placeholderSuggestions.length <= 1) return;
    const interval = setInterval(() => {
      setPlaceholderIndex((i) => i + 1);
    }, 4000);
    return () => clearInterval(interval);
  }, [placeholderSuggestions.length]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled || isBusy) return;
    onSubmit(trimmed);
    setValue("");
  };

  const handlePillClick = (s: OmnibarSuggestion) => {
    if (onSuggestionClick) {
      onSuggestionClick(s);
    } else {
      onSubmit(s.value);
    }
  };

  return (
    <div className="relative z-10 mx-auto w-full max-w-3xl animate-fade-rise-soft">
      {/* Glass panel */}
      <form
        onSubmit={handleSubmit}
        className="group relative flex items-center gap-3 rounded-xl3 border border-white/20 bg-surface-glassLight/80 px-4.5 py-3.5 shadow-glass-soft backdrop-blur"
      >
        {/* Leading icon / status */}
        <div className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-accent-powerBlueSoft/50 text-accent-powerBlue shadow-inner-glow">
          {status === "processing" || status === "connecting" ? (
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-accent-powerBlue" />
          ) : (
            <span className="text-lg">⌘</span>
          )}
        </div>

        {/* Input */}
        <input
          type="text"
          className="flex-1 bg-transparent text-base text-slate-900 placeholder:text-slate-400 focus:outline-none"
          placeholder={currentPlaceholder}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={disabled || isBusy}
          autoFocus={autoFocus}
        />

        {/* Right-side status text */}
        <div className="hidden text-xs text-slate-500 sm:block">
          {status === "processing" && "Agent is working…"}
          {status === "connecting" && "Connecting…"}
          {status === "error" && (
            <span className="text-status-security">Something went wrong</span>
          )}
        </div>

        {/* Send button (squircle) */}
        <button
          type="submit"
          disabled={disabled || isBusy}
          className="flex h-10 w-10 flex-none items-center justify-center rounded-squircle bg-accent-powerBlue text-white shadow-inner-glow transition-all duration-fast ease-soft-spring hover:bg-accent-powerBlue/90 hover:shadow-glass-soft active:scale-95 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none"
        >
          <span className="text-base font-semibold">⇪</span>
        </button>
      </form>

      {/* Ghost suggestion pills */}
      {pillSuggestions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {pillSuggestions.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => handlePillClick(s)}
              className="animate-fade-rise rounded-full border border-white/30 bg-surface-glassLight/60 px-3 py-1 text-xs text-slate-700 shadow-sm backdrop-blur transition-all duration-fast ease-soft-spring hover:border-accent-powerBlue hover:bg-accent-powerBlueSoft/40 hover:text-slate-900 active:scale-95"
            >
              {s.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
```

This implements:

- **Floating glass Omnibar** with Power Blue accent, inner glow, and rounded squircles.
- **Ghost suggestions** via rotating placeholder text.
- **Suggestion pills** that can be clicked to submit preset prompts.
- **Busy/connecting states** with a pulsing orb and status text.

---

## 3. Minimal backend contract for the Glass UI

The new React UI should talk to a small HTTP API that wraps the existing Python orchestration. A minimal contract:

- `POST /api/query`
  - **Body**: `{ "message": string, "sessionId"?: string }`
  - **Response**: `{ "sessionId": string, "answer": string, "department": string, "executionLog": string[], "sources"?: any }`
- `GET /api/logs?sessionId=...`
  - Returns a structured list of telemetry entries in the same shape as `telemetry_logs` today.
- `POST /api/feedback`
  - Mirrors the existing `feedback_ui` behavior (rating, routing correctness, comments).

The Omnibar only needs:

- `onSubmit(message)` → call `POST /api/query`.
- Then the surrounding page can use the same `sessionId` to fetch logs and other panes.

Once you have Node/npm available, we can:

1. Scaffold a Vite/Next.js app under `agentic-lens/glass_ui`.
2. Drop this `tailwind.config.ts` and `Omnibar.tsx` into it.
3. Deploy via `deploy-glass-ui.sh` to Cloud Run service `ai-prism-agent-glass-ui`.

