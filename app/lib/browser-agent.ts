import type { MLCEngine } from "@mlc-ai/web-llm";

export type BrowserAgentEvent = {
  agent: "scout" | "synthesizer" | "main";
  content: string;
};

export type BrowserAgentResult = {
  scout: string;
  answer: string;
  degraded: boolean;
};

// If the in-browser model produces no token for this long (wedged GPU driver, dead
// WebGPU device), the generation is interrupted so callers can fall back.
const STALL_TIMEOUT_MS = 25_000;

function isDegenerate(text: string, tiny: boolean): boolean {
  // Small models often collapse into repetition loops ("...latest things online, I'vea, ...").
  // Stop the run as soon as the output clearly repeats itself.
  const minimum = tiny ? 60 : 120;
  if (text.length < minimum) return false;

  const alnum = text.toLowerCase().replace(/[^a-z0-9]/g, "");
  if (alnum.length > 60) {
    const unique = new Set(alnum).size;
    if (unique / alnum.length < 0.18) return true;
  }

  const tail = text.slice(-90);
  const chunk = tail.slice(-24).trim();
  if (chunk.length < 12) return false;
  let count = 0;
  let idx = text.indexOf(chunk);
  while (idx !== -1) {
    count += 1;
    idx = text.indexOf(chunk, idx + 1);
  }
  return count >= 3;
}

async function streamCompletion(
  engine: MLCEngine,
  agent: BrowserAgentEvent["agent"],
  messages: Array<{ role: "system" | "user"; content: string }>,
  maxTokens: number,
  temperature: number,
  tiny: boolean,
  onDelta: (event: BrowserAgentEvent) => void,
): Promise<{ text: string; degraded: boolean }> {
  let text = "";
  let degraded = false;
  const stream = await engine.chat.completions.create({ messages, stream: true, temperature, max_tokens: maxTokens });
  const iterator = stream[Symbol.asyncIterator]();
  let stalledSeconds = 0;
  while (true) {
    let stallTimer: ReturnType<typeof setTimeout> | null = null;
    let stalled = false;
    const next = await Promise.race([
      iterator.next(),
      new Promise<"stall">((resolve) => {
        stallTimer = setTimeout(() => {
          stalled = true;
          resolve("stall");
        }, STALL_TIMEOUT_MS);
      }),
    ]);
    if (stallTimer) clearTimeout(stallTimer);
    if (stalled || next === "stall") {
      stalledSeconds = Math.round(STALL_TIMEOUT_MS / 1000);
      try {
        await engine.interruptGenerate();
      } catch {
        // The engine may already be dead — interrupting is best effort.
      }
      throw new Error(`The browser model stalled (no output for ${stalledSeconds}s). Generation was stopped.`);
    }
    const result = next as IteratorResult<{ choices?: Array<{ delta?: { content?: string } }> }>;
    if (result.done) break;
    const delta = result.value?.choices?.[0]?.delta?.content ?? "";
    if (!delta) continue;
    text += delta;
    onDelta({ agent, content: delta });
    if (isDegenerate(text, tiny)) {
      degraded = true;
      break;
    }
  }
  return { text, degraded };
}

export async function runBrowserAgents(
  engine: MLCEngine,
  userMessage: string,
  history: Array<{ role: "user" | "assistant"; content: string }>,
  systemPrompt: string,
  onDelta: (event: BrowserAgentEvent) => void,
  singleAgent: boolean,
  tinyModel: boolean,
): Promise<BrowserAgentResult> {
  const recent = history.slice(-12).map((item) => `${item.role}: ${item.content}`).join("\n");
  const context = `Conversation context:\n${recent}\n\nUser request:\n${userMessage}`;
  // Tiny models (360M / 0.5B) collapse with long instructions; keep prompts minimal.
  const extra = systemPrompt.trim() && !tinyModel ? `\nWorkspace instruction: ${systemPrompt.trim()}` : "";
  const temperature = tinyModel ? 0.1 : 0.35;

  if (singleAgent) {
    const mainMessages = [
      {
        role: "system" as const,
        content: tinyModel
          ? `You are a helpful AI running in the browser. Answer the user's request briefly and directly. You have no tools. Never repeat yourself.${extra}`
          : `You are the main AI assistant, running fully inside the browser. There is no web_search tool available here, so when the request needs fresh or current web evidence, state clearly that live web research is unavailable in browser mode and answer with your own knowledge. Answer the request directly and completely.${extra}`,
      },
      { role: "user" as const, content: context },
    ];
    const { text, degraded } = await streamCompletion(engine, "main", mainMessages, 640, temperature, tinyModel, onDelta);
    return { scout: "", answer: text, degraded };
  }

  const scoutMessages = [
    {
      role: "system" as const,
      content: tinyModel
        ? `You are the Scout. Produce a short brief on the request. No tools. Never repeat yourself.${extra}`
        : `You are Agent A, the Scout. Work locally in the browser. Do not claim web access or invent current sources. Produce a concise evidence-free brief unless the user supplied evidence.${extra}`,
    },
    { role: "user" as const, content: context },
  ];
  const scout = await streamCompletion(engine, "scout", scoutMessages, 384, tinyModel ? 0.1 : 0.2, tinyModel, onDelta);

  const synthesizerMessages = [
    {
      role: "system" as const,
      content: tinyModel
        ? `You are the Synthesizer. Give a short, direct answer to the request. Never repeat yourself.${extra}`
        : `You are Agent B, the Synthesizer. Answer the user clearly using only the request and Scout brief. State limits when fresh web research is unavailable.${extra}`,
    },
    { role: "user" as const, content: `User request:\n${userMessage}\n\nScout brief:\n${scout.text}` },
  ];
  const answer = await streamCompletion(engine, "synthesizer", synthesizerMessages, 640, temperature, tinyModel, onDelta);

  return { scout: scout.text, answer: answer.text, degraded: scout.degraded || answer.degraded };
}
