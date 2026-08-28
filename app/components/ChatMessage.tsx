"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";

import { CopyButton } from "./CopyButton";
import type { ChatMessage as ChatMessageType } from "./types";

type ChatMessageProps = {
  message: ChatMessageType;
};

function formatTime(timestamp: number) {
  if (timestamp === 0) return "READY";
  return new Intl.DateTimeFormat("en", {
    hour: "numeric",
    minute: "2-digit",
  }).format(timestamp);
}

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}

/**
 * Shows how long the message has been generating: a live ticking timer while the
 * message streams, then the final duration once committed. Hidden for user/system rows
 * and for instantly completed messages.
 */
function RunTimer({ streaming, startedAt, elapsedMs }: { streaming?: boolean; startedAt?: number; elapsedMs?: number }) {
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!streaming || !startedAt) return;
    const timer = setInterval(() => setTick((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, [streaming, startedAt]);

  const ms = streaming && startedAt ? Date.now() - startedAt : elapsedMs;
  if (!ms || ms < 1000) return null;
  return (
    <p className={`mt-2 flex items-center gap-1.5 px-1 font-mono text-[10px] ${streaming ? "text-cyan/85" : "text-fog/45"}`}>
      <span aria-hidden>⏱</span>
      <span>{formatDuration(ms)}</span>
      <span>{streaming ? "· generating" : "· generation time"}</span>
    </p>
  );
}

function renderInlineMarkdown(content: string) {
  return content.split(/(https?:\/\/[^\s)]+|\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith("http://") || part.startsWith("https://")) {
      return (
        <a
          key={`${part}-${index}`}
          href={part}
          target="_blank"
          rel="noreferrer"
          className="break-all text-cyan underline decoration-cyan/40 underline-offset-2 hover:decoration-cyan"
        >
          {part}
        </a>
      );
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${part}-${index}`} className="font-semibold text-white">{part.slice(2, -2)}</strong>;
    }
    return <span key={`${part}-${index}`}>{part}</span>;
  });
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";
  const agentLabel = message.agent === "scout" ? "Agent A / Scout" : message.agent === "synthesizer" ? "Agent B / Synthesizer" : message.agent === "main" ? "AI" : "System";

  return (
    <motion.article
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: "easeOut" }}
      className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div className={`w-full max-w-2xl ${isUser ? "max-w-[88%] sm:max-w-xl" : ""}`}>
        <div className={`mb-2 flex items-center gap-2 px-1 ${isUser ? "justify-end" : "justify-start"}`}>
          {!isUser && <span className={`font-mono-label ${message.agent === "scout" ? "text-cyan" : message.agent === "synthesizer" ? "text-lime" : "text-fog"}`}>{agentLabel}</span>}
          <span className="font-mono-label text-white/25">{formatTime(message.createdAt)}</span>
          {isUser && <span className="font-mono-label text-fog">You</span>}
        </div>
        <div
          className={
            isUser
              ? "rounded-2xl rounded-br-md border border-lime/20 bg-lime px-4 py-3 text-sm leading-6 text-ink shadow-[0_12px_30px_rgba(212,255,107,0.12)]"
              : isSystem
                ? "rounded-xl border border-coral/20 bg-coral/[0.08] px-4 py-3 text-sm leading-6 text-coral"
                : "rounded-2xl rounded-bl-md border border-white/10 bg-white/[0.045] px-4 py-4 text-sm leading-6 text-white/85 shadow-panel"
          }
        >
          <div className="copy-safe whitespace-pre-wrap">{renderInlineMarkdown(message.content)}</div>
          {message.streaming && (
            <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-lime align-[-2px]" aria-label="Streaming" />
          )}
        </div>
        {isUser && message.translation && (
          <p className="copy-safe mt-1 break-words px-1 text-right font-mono text-[10px] leading-4 text-cyan/70">🌐 {message.translation}</p>
        )}
        {isSystem && (
          <div className="mt-1.5 flex justify-start px-1">
            <CopyButton value={message.content} label="Copy error" />
          </div>
        )}
        {!isUser && <RunTimer streaming={message.streaming} startedAt={message.startedAt} elapsedMs={message.elapsedMs} />}
        {message.sources && message.sources.length > 0 && (
          <div className="mt-3 grid gap-2 pl-1 sm:grid-cols-2">
            {message.sources.map((source) => (
              <a
                key={`${source.url}-${source.title}`}
                href={source.url}
                target="_blank"
                rel="noreferrer"
                className="group min-w-0 rounded-lg border border-white/10 bg-white/[0.025] px-3 py-2 transition-colors hover:border-cyan/35 hover:bg-cyan/[0.06]"
              >
                <p className="truncate text-xs font-medium text-white/80 group-hover:text-cyan">{source.title}</p>
                <p className="mt-1 line-clamp-2 text-[11px] leading-4 text-fog/60">{source.snippet}</p>
              </a>
            ))}
          </div>
        )}
      </div>
    </motion.article>
  );
}
