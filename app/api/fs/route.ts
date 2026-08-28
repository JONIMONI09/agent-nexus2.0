import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8001";

export async function GET() {
  try {
    const response = await fetch(`${backendUrl}/fs/settings`, { cache: "no-store" });
    const payload = await response.text();
    return new Response(payload, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch (error) {
    return Response.json(
      { error: `The local agent service is unavailable: ${error instanceof Error ? error.message : "unknown error"}` },
      { status: 503 },
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.text();
    const response = await fetch(`${backendUrl}/fs/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      cache: "no-store",
    });
    const payload = await response.text();
    return new Response(payload, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch (error) {
    return Response.json(
      { error: `The local agent service is unavailable: ${error instanceof Error ? error.message : "unknown error"}` },
      { status: 503 },
    );
  }
}
