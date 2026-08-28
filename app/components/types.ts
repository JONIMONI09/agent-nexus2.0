export type AgentName = "scout" | "analyst" | "synthesizer" | "system" | "main";

export type ProviderKind = "ollama" | "openai_compatible" | "custom_script";

export type ProviderProfile = {
  id: string;
  name: string;
  description: string;
  kind: ProviderKind;
  base_url: string;
  auth_env_var: string;
  models_path: string;
  chat_path: string;
  default_model: string;
  allowed_hosts: string[];
  capabilities: Record<string, boolean>;
  builtin: boolean;
  has_script?: boolean;
};

export type ProviderDetection = {
  detected: boolean;
  kind: ProviderKind | "unknown";
  normalized_base_url: string;
  name_suggestion: string;
  models: string[];
  capabilities: Record<string, boolean>;
  status_code?: number;
  message: string;
  checked_urls: string[];
};

export type Source = {
  title: string;
  url: string;
  snippet: string;
};

export type Delegation = {
  tool: string;
  arguments: Record<string, unknown>;
  approved: boolean;
  reason?: string;
  ok: boolean;
  error?: string;
  sources: Source[];
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  agent?: AgentName;
  sources?: Source[];
  delegations?: Delegation[];
  debate?: DebatePanel;
  createdAt: number;
  streaming?: boolean;
  /** Wall-clock time the generation for this message started (ms epoch). */
  startedAt?: number;
  /** Final generation duration, set once the stream committed. */
  elapsedMs?: number;
  /** For user messages: the English auto-translation note shown under the bubble. */
  translation?: string;
};

export type ToolRequest = {
  call_id: string;
  run_id: string;
  agent: AgentName;
  tool: string;
  arguments: Record<string, unknown>;
};

export type AgentState = {
  phase: "idle" | "working" | "waiting" | "complete" | "error";
  label: string;
  detail: string;
};

export type AgentActivityKind = "think" | "status" | "tool" | "decision" | "error" | "fallback" | "debate" | "learning";

export type AgentActivity = {
  id: string;
  agent: AgentName;
  kind: AgentActivityKind;
  text: string;
  detail?: string;
  ts: number;
  payload?: {
    tool?: string;
    arguments?: Record<string, unknown>;
    approved?: boolean;
    reason?: string;
    debate?: DebatePanel;
    sources?: Source[];
  };
};

export type DebateSpeech = {
  role: string;
  speech: string;
};

export type DebatePanel = {
  topic: string;
  speeches: DebateSpeech[];
  synthesis: string;
};

export type ThinkingStyle = "concise" | "balanced" | "deep" | "creative";

export type LearningMemory = {
  learn: string;
  rules: string;
  agent: string;
};

export type LearningUpdate = {
  lessons: string[];
  rules: string[];
  added_lessons: number;
  added_rules: number;
};
