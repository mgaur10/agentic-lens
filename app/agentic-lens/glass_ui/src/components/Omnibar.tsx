import React, { useEffect, useMemo, useRef, useState } from "react";
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
   const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const currentPlaceholder = useMemo(() => {
    if (placeholderSuggestions.length === 0) return "Ask anything about GCP…";
    return placeholderSuggestions[placeholderIndex % placeholderSuggestions.length];
  }, [placeholderIndex, placeholderSuggestions]);

  useEffect(() => {
    if (placeholderSuggestions.length <= 1) return;
    const interval = setInterval(() => {
      setPlaceholderIndex((i) => i + 1);
    }, 4000);
    return () => clearInterval(interval);
  }, [placeholderSuggestions.length]);

  // Auto-resize the textarea height based on content, up to ~6 lines.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "0px";
    const next = Math.min(el.scrollHeight, 6 * 24); // 6 lines * 24px line-height
    el.style.height = `${next}px`;
  }, [value]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled || isBusy) return;
    onSubmit(trimmed);
    setValue("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      const trimmed = value.trim();
      if (!trimmed || disabled || isBusy) return;
      onSubmit(trimmed);
      setValue("");
    }
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
      <form
        onSubmit={handleSubmit}
        className="group/form relative flex min-h-[52px] items-center gap-3 rounded-xl3 border border-black/5 bg-white/80 px-4.5 py-3.5 shadow-omni-float backdrop-blur-md transition-shadow duration-300 ease-spring-wow focus-within:shadow-[0_0_0_2px_rgba(99,102,241,0.3)]"
      >
        <div className="flex h-9 w-9 flex-none items-center justify-center rounded-cardInner bg-accent-indigo/10 text-accent-indigo shadow-indigo-soft">
          {status === "processing" || status === "connecting" ? (
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-accent-indigo" />
          ) : (
            <span className="text-lg">⌘</span>
          )}
        </div>

        <textarea
          ref={textareaRef}
          className="min-h-[24px] flex-1 resize-none bg-transparent text-[15px] leading-6 text-slate-900 placeholder:text-slate-400 focus:outline-none"
          placeholder={currentPlaceholder}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled || isBusy}
          autoFocus={autoFocus}
          rows={1}
        />

        <div className="hidden text-xs text-slate-500 sm:block">
          {status === "processing" && "Agent is working…"}
          {status === "connecting" && "Connecting…"}
          {status === "error" && (
            <span className="text-status-security">Something went wrong</span>
          )}
        </div>

        <button
          type="submit"
          disabled={disabled || isBusy}
          className="group/btn relative flex h-10 w-10 flex-none items-center justify-center overflow-hidden rounded-cardInner bg-accent-indigo text-white shadow-indigo-soft transition-all duration-200 ease-spring-wow hover:bg-accent-indigo/90 hover:shadow-indigo-ambient active:scale-95 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none"
          aria-label="Send"
        >
          <span className="relative flex h-full w-full items-center justify-center">
            <span className="inline-block text-base font-semibold transition-all duration-200 ease-spring-wow group-hover/btn:-translate-y-1 group-hover/btn:translate-x-1 group-hover/btn:opacity-0">
              ⇪
            </span>
            <span className="absolute inline-block translate-y-1 translate-x-1 text-base font-semibold opacity-0 transition-all duration-200 ease-spring-wow group-hover/btn:translate-y-0 group-hover/btn:translate-x-0 group-hover/btn:opacity-100">
              ⇪
            </span>
          </span>
        </button>
      </form>

      {pillSuggestions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {pillSuggestions.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => handlePillClick(s)}
              className="animate-fade-rise rounded-cardInner border border-black/5 bg-white/60 px-3 py-1.5 text-xs text-slate-700 shadow-sm backdrop-blur transition-all duration-200 ease-spring-wow hover:-translate-y-px hover:scale-[1.01] hover:shadow-pill-hover hover:border-accent-indigo hover:bg-accent-indigoSoft/40 hover:text-slate-900 active:scale-95"
            >
              {s.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

