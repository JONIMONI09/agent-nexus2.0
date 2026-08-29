import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8001";

export async function POST(request: NextRequest) {
  const body = await request.text();
  try {
    const response = await fetch(`${backendUrl}/fs/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      cache: "no-store",
    });
    
    // Pass through the approval token header from the backend
    const headers: Record<string, string> = {
      "Cache-Control": "no-cache, no-transform",
      "Content-Type": response.headers.get("content-type") ?? "text/event-stream",
    };
    
    const approvalToken = response.headers.get("X-Approval-Token");
    if (approvalToken) {
      headers["X-Approval-Token"] = approvalToken;
    }
    
    return new Response(response.body, {
      status: response.status,
      headers,
    });
  } catch (error) {
    return Response.json(
      { error: `The local agent service is unavailable: ${error instanceof Error ? error.message : "unknown error"}` },
      { status: 503 },
    );
  }
}
