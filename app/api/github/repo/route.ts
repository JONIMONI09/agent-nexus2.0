import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8001";

export async function POST(request: NextRequest) {
  const body = await request.text();
  try {
    const response = await fetch(`${backendUrl}/github/repo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      cache: "no-store",
    });
    return new Response(response.body, {
      status: response.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    return Response.json(
      { error: `GitHub service unavailable: ${error instanceof Error ? error.message : "unknown error"}` },
      { status: 503 },
    );
  }
}
