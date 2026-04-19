import { NextRequest, NextResponse } from "next/server";
import { applyRateLimit, getClientKey } from "../_lib/rate-limit";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const ALLOWED_PREFIXES = new Set(["health", "futures", "indicator", "markets", "signal", "ml", "backtest"]);

function resolveUpstreamBase(prefix: string): { url: URL | null; pathPrefix: string } {
  const raw =
    prefix === "backtest"
      ? process.env.BACKTEST_SERVICE_BASE_URL?.trim() || "http://localhost:8004"
      : process.env.API_SERVICE_BASE_URL?.trim() || "http://localhost:8000";

  try {
    const url = new URL(raw);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return { url: null, pathPrefix: "" };
    }
    return { url, pathPrefix: prefix === "backtest" ? "" : "/api" };
  } catch {
    return { url: null, pathPrefix: "" };
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

function validateSegments(segments: string[]): string | null {
  if (segments.length === 0) {
    return "invalid path";
  }
  if (segments.some((segment) => segment.includes(".."))) {
    return "invalid path";
  }
  if (!ALLOWED_PREFIXES.has(segments[0] ?? "")) {
    return "path not allowed";
  }
  return null;
}

function buildUpstreamUrl(request: NextRequest, segments: string[]): URL | null {
  const [prefix] = segments;
  const upstreamBase = resolveUpstreamBase(prefix);
  if (!upstreamBase.url) {
    return null;
  }
  const upstream = new URL(`${upstreamBase.pathPrefix}/${segments.map(encodeURIComponent).join("/")}`, upstreamBase.url);
  for (const [key, value] of request.nextUrl.searchParams.entries()) {
    upstream.searchParams.set(key, value);
  }
  return upstream;
}

function buildForwardHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  const token = resolveApiToken();
  if (token) {
    headers.set("X-API-Token", token);
  }
  const accept = request.headers.get("accept");
  if (accept) {
    headers.set("accept", accept);
  }
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }
  return headers;
}

async function proxyRequest(request: NextRequest, context: RouteContext, method: "GET" | "POST"): Promise<NextResponse> {
  const clientKey = getClientKey(request);
  const [prefix] = (context.params.path || []).filter(Boolean);
  const isBacktest = prefix === "backtest";

  const limit = applyRateLimit(
    method === "GET" ? `bff:get:${prefix}` : `bff:post:${prefix}`,
    clientKey,
    method === "GET"
      ? { ratePerMinute: isBacktest ? 60 : 120, burst: 20 }
      : { ratePerMinute: 10, burst: 5, maxConcurrency: 3 }
  );
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

  try {
    const segments = (context.params.path || []).filter(Boolean);
    const validationError = validateSegments(segments);
    if (validationError) {
      return NextResponse.json({ code: "40001", msg: validationError, data: null, success: false }, { status: 400 });
    }

    const upstream = buildUpstreamUrl(request, segments);
    if (!upstream) {
      return NextResponse.json({ code: "50001", msg: "service unavailable", data: null, success: false }, { status: 500 });
    }

    const headers = buildForwardHeaders(request);
    const response = await fetch(upstream, {
      method,
      headers,
      body: method === "POST" ? await request.text() : undefined,
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
  } finally {
    limit.release();
  }
}

export async function GET(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxyRequest(request, context, "GET");
}

export async function POST(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxyRequest(request, context, "POST");
}
