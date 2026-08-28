import { NextResponse } from "next/server";

import { parseBackendJson } from "../../backend-json";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: { providerId: string };
};

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8001";

export async function GET(_request: Request, context: RouteContext) {
  try {
    const providerId = encodeURIComponent(context.params.providerId);
    const response = await fetch(`${backendUrl}/providers/${providerId}/models`, { cache: "no-store" });
    return await parseBackendJson(response, { ok: false, models: [], error: "" });
  } catch (error) {
    return NextResponse.json(
      { ok: false, models: [], error: `Cannot discover provider models: ${error instanceof Error ? error.message : "unknown error"}` },
      { status: 503 },
    );
  }
}
