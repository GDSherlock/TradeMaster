import { NextRequest, NextResponse } from "next/server";
import { applyRateLimit, getClientKey } from "../_lib/rate-limit";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const ALLOWED_PREFIXES = new Set(["health", "futures", "indicator", "markets", "signal", "ml"]);

function resolveApiBase(): URL | null {
  const raw = process.env.API_SERVICE_BASE_URL?.trim() || "http://localhost:8000";
  try {
    const url = new URL(raw);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return null;
    }
    return url;
  } catch {
    return null;
  }
}

function resolveApiToken(): string {
  const explicit = process.env.API_SERVICE_TOKEN?.trim();
  if (explicit) {
    return explicit;
  }
  return process.env.API_TOKEN?.trim() || "";
}

type RouteContext = {
  params: { path: string[] };
};

export async function GET(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  const clientKey = getClientKey(request);
  const limit = applyRateLimit("bff:get", clientKey, {
    ratePerMinute: 120,
    burst: 20,
  });
  if (!limit.allowed) {
    return NextResponse.json(
      {
        code: "42901",
        msg: "rate limited",
        data: null,
        success: false,
        degraded: true,
        retry_after_ms: limit.retryAfterSeconds * 1000,
      },
      {
        status: 429,
        headers: {
          "retry-after": String(limit.retryAfterSeconds),
          "cache-control": "no-store",
        },
      }
    );
  }

  const baseUrl = resolveApiBase();
  if (!baseUrl) {
    return NextResponse.json({ code: "50001", msg: "service unavailable", data: null, success: false }, { status: 500 });
  }

  const segments = (context.params.path || []).filter(Boolean);
  if (segments.length === 0) {
    return NextResponse.json({ code: "40001", msg: "invalid path", data: null, success: false }, { status: 400 });
  }

  if (segments.some((segment) => segment.includes(".."))) {
    return NextResponse.json({ code: "40001", msg: "invalid path", data: null, success: false }, { status: 400 });
  }

  const [prefix] = segments;
  if (!ALLOWED_PREFIXES.has(prefix)) {
    return NextResponse.json({ code: "40001", msg: "path not allowed", data: null, success: false }, { status: 400 });
  }

  const upstream = new URL(`/api/${segments.map(encodeURIComponent).join("/")}`, baseUrl);
  for (const [key, value] of request.nextUrl.searchParams.entries()) {
    upstream.searchParams.set(key, value);
  }

  const headers = new Headers();
  const token = resolveApiToken();
  if (token) {
    headers.set("X-API-Token", token);
  }
  const accept = request.headers.get("accept");
  if (accept) {
    headers.set("accept", accept);
  }

  try {
    const response = await fetch(upstream, {
      method: "GET",
      headers,
      cache: "no-store",
    });

    const contentType = response.headers.get("content-type") || "application/json";
    const body = await response.text();

    return new NextResponse(body, {
      status: response.status,
      headers: {
        "content-type": contentType,
        "cache-control": "no-store",
        ...(response.headers.get("retry-after") ? { "retry-after": response.headers.get("retry-after") as string } : {}),
      },
    });
  } catch {
    return NextResponse.json({ code: "50001", msg: "service unavailable", data: null, success: false }, { status: 502 });
  }
}
