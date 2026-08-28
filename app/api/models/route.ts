import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8001";

export async function GET() {
  try {
    const response = await fetch(`${backendUrl}/models`, {
      cache: "no-store",
    });
    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { ok: false, models: [], error: `Cannot reach local Ollama: ${error instanceof Error ? error.message : "unknown error"}` },
      { status: 503 },
    );
  }
}
