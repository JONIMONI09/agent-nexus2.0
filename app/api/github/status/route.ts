import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8001";

export async function GET() {
  try {
    const response = await fetch(`${backendUrl}/github/status`, {
      method: "GET",
      cache: "no-store",
    });
    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { error: `GitHub service unavailable: ${error instanceof Error ? error.message : "unknown error"}` },
      { status: 503 },
    );
  }
}
