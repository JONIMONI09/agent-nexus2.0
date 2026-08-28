import { NextRequest, NextResponse } from "next/server";

import { parseBackendJson } from "../backend-json";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8001";

export async function POST(request: NextRequest) {
  try {
    const response = await fetch(`${backendUrl}/providers/detect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
      cache: "no-store",
    });
    return await parseBackendJson(response, { ok: false, error: "" });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: `Cannot probe the provider URL: ${error instanceof Error ? error.message : "unknown error"}` },
      { status: 503 },
    );
  }
}
