import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8001";

export async function POST(request: NextRequest) {
  try {
    const response = await fetch(`${backendUrl}/approve-tool`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
      cache: "no-store",
    });
    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: `Cannot reach the local consent broker: ${error instanceof Error ? error.message : "unknown error"}` },
      { status: 503 },
    );
  }
}
