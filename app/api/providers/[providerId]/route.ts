import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: { providerId: string };
};

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8001";
const apiKey = process.env.API_KEY ?? "";

export async function DELETE(_request: Request, context: RouteContext) {
  try {
    const providerId = encodeURIComponent(context.params.providerId);
    const headers: HeadersInit = {};
    if (apiKey) {
      headers["X-API-Key"] = apiKey;
    }
    const response = await fetch(`${backendUrl}/providers/${providerId}`, {
      method: "DELETE",
      headers,
      cache: "no-store",
    });
    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: `Cannot delete the provider profile: ${error instanceof Error ? error.message : "unknown error"}` },
      { status: 503 },
    );
  }
}
