import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8001";
const validFiles = new Set(["learn", "rules", "agent"]);

export async function PUT(request: NextRequest, context: { params: { file: string } }) {
  const file = context.params.file;
  if (!validFiles.has(file)) {
    return Response.json({ error: "Unknown memory file." }, { status: 404 });
  }
  try {
    const body = await request.text();
    const response = await fetch(`${backendUrl}/learning/files/${file}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body,
      cache: "no-store",
    });
    const payload = await response.text();
    return new Response(payload, { status: response.status, headers: { "Content-Type": "application/json" } });
  } catch (error) {
    return Response.json(
      { error: `The local agent service is unavailable: ${error instanceof Error ? error.message : "unknown error"}` },
      { status: 503 },
    );
  }
}

export async function POST(_request: NextRequest, context: { params: { file: string } }) {
  const file = context.params.file;
  if (!validFiles.has(file)) {
    return Response.json({ error: "Unknown memory file." }, { status: 404 });
  }
  try {
    const response = await fetch(`${backendUrl}/learning/files/${file}/reset`, { method: "POST", cache: "no-store" });
    const payload = await response.text();
    return new Response(payload, { status: response.status, headers: { "Content-Type": "application/json" } });
  } catch (error) {
    return Response.json(
      { error: `The local agent service is unavailable: ${error instanceof Error ? error.message : "unknown error"}` },
      { status: 503 },
    );
  }
}
