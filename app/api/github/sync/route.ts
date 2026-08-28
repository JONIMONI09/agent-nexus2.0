import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// eslint-disable-next-line @typescript-eslint/no-require-imports
const git = require("isomorphic-git");
// eslint-disable-next-line @typescript-eslint/no-require-imports
const http = require("isomorphic-git/http/node");
const fs = require("fs");

const REPOSITORY = "JONIMONI09/agent-nexus2.0";
const BRANCH = "feature/github-integration";
const BASE = "main";
const PR_TITLE = "Add GitHub repository integration";
const PR_BODY = [
  "## What",
  "Server-side GitHub integration: repository info, branch creation and pull requests",
  "via the GitHub REST API, proxied through FastAPI and Next.js.",
  "",
  "- `python_backend/github_service.py` — secure client (token from `GITHUB_TOKEN` only, never logged)",
  "- FastAPI endpoints: `/github/status`, `/github/repo`, `/github/branch`, `/github/pr`",
  "- Next.js proxy routes under `app/api/github/*`",
  "- 6 validation tests; full backend suite 69 passed, `tsc` clean",
  "- `.gitignore` added; generated artifacts (`.next`, `__pycache__`, `.venv`) untracked",
].join("\n");

async function openPullRequest(token: string) {
  const response = await fetch(`https://api.github.com/repos/${REPOSITORY}/pulls`, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title: PR_TITLE, body: PR_BODY, head: BRANCH, base: BASE }),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    return { ok: false, status: response.status, error: payload?.message ?? "request rejected" };
  }
  return { ok: true, number: payload.number, url: payload.html_url, state: payload.state };
}

export async function POST(request: NextRequest) {
  const token = process.env.GITHUB_TOKEN?.trim() ?? "";
  const body = await request.json().catch(() => ({}));
  const action = typeof body.action === "string" ? body.action : "all";

  if (!token) {
    return Response.json(
      { ok: false, error: "GITHUB_TOKEN is not set in the server environment. Add it in the Keys tab." },
      { status: 401 },
    );
  }

  if (action === "check") {
    return Response.json({ ok: true, configured: true, branch: BRANCH, repository: REPOSITORY });
  }

  // 1) Push the branch via isomorphic-git (pure-HTTP git client).
  let pushed: { ok: boolean; ref?: string; error?: string | null };
  try {
    const result = await git.push({
      fs,
      http,
      dir: process.cwd(),
      remote: "origin",
      ref: BRANCH,
      onAuth: () => ({ username: "x-access-token", password: token }),
      onProgress: () => undefined,
    });
    pushed = { ok: Boolean(result.ok), ref: result.ref ?? undefined, error: result.error ?? null };
  } catch (error) {
    return Response.json(
      { ok: false, step: "push", error: error instanceof Error ? error.message : String(error) },
      { status: 502 },
    );
  }
  if (!pushed.ok) {
    return Response.json({ step: "push", ...pushed }, { status: 502 });
  }

  if (action === "push") {
    return Response.json({ step: "push", ...pushed });
  }

  // 2) Open the pull request.
  const pr = await openPullRequest(token);
  return Response.json({ step: "pr", pushed: pushed.ok, ...pr }, { status: pr.ok ? 200 : 502 });
}
