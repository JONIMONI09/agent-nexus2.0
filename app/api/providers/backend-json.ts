import { NextResponse } from "next/server";

/**
 * Parse a backend response body that may not be JSON.
 *
 * The FastAPI backend is guarded so it never answers with plain text, but any
 * proxy in front of it (reverse proxy, sandbox gateway, crash during response
 * writing) can still return something like `Internal Server Error`. Parsing that
 * with `response.json()` used to surface as `Unexpected token 'I', "Internal S"...
 * is not valid JSON` — useless for the user. This helper turns every failure mode
 * into a structured JSON error the UI can render and copy.
 */
export async function parseBackendJson(
  response: Response,
  fallback: Record<string, unknown>,
): Promise<NextResponse> {
  const raw = await response.text();
  if (!raw.trim()) {
    return NextResponse.json(
      { ...fallback, ok: false, error: `The backend answered HTTP ${response.status} with an empty body.` },
      { status: 502 },
    );
  }
  try {
    const payload = JSON.parse(raw);
    return NextResponse.json(payload, { status: response.status });
  } catch {
    const snippet = raw.trim().replace(/\s+/g, " ").slice(0, 300);
    return NextResponse.json(
      {
        ...fallback,
        ok: false,
        error: `The backend answered HTTP ${response.status} with a non-JSON body: ${snippet}`,
      },
      { status: 502 },
    );
  }
}
