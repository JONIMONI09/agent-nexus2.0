"use client";

import { useCallback, useState } from "react";

type CopyButtonProps = {
  value: string;
  label?: string;
  className?: string;
};

/** One-tap copy for anything the system produces: errors, tool calls, traces. */
export function CopyButton({ value, label = "Copy", className = "" }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      // Older Android WebViews block the async clipboard API — hidden-textarea fallback.
      const area = document.createElement("textarea");
      area.value = value;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try {
        document.execCommand("copy");
      } catch {
        // Nothing else a web page can do.
      }
      document.body.removeChild(area);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }, [value]);

  return (
    <button
      type="button"
      onClick={() => void copy()}
      className={`shrink-0 rounded-lg border px-2 py-1 font-mono text-[9px] uppercase tracking-wide transition-colors ${
        copied
          ? "border-lime/40 bg-lime/10 text-lime"
          : "border-white/15 bg-white/[0.04] text-fog/70 hover:border-cyan/40 hover:text-cyan"
      } ${className}`}
    >
      {copied ? "Copied ✓" : label}
    </button>
  );
}
