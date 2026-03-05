import { NextRequest, NextResponse } from "next/server";
import { applyRateLimit, getClientKey } from "../_lib/rate-limit";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function resolveChatBase(): URL | null {
  const raw = process.env.CHAT_SERVICE_BASE_URL?.trim() || "http://localhost:8001";
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

export async function POST(request: NextRequest): Promise<NextResponse> {
  const clientKey = getClientKey(request);
  const limit = applyRateLimit("bff:chat", clientKey, {
    ratePerMinute: 20,
    burst: 20,
    maxConcurrency: 5,
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

  const baseUrl = resolveChatBase();
  if (!baseUrl) {
    limit.release();
    return NextResponse.json(
      { code: "50001", msg: "service unavailable", data: null, success: false, degraded: true },
      { status: 500 }
    );
  }

  try {
    const body = (await request.json()) as Record<string, unknown>;
    if (!body || typeof body.message !== "string" || !body.message.trim()) {
      return NextResponse.json(
        { code: "40001", msg: "invalid payload", data: null, success: false, degraded: true },
        { status: 400 }
      );
    }

    const upstream = new URL("/chat", baseUrl);
    const response = await fetch(upstream, {
      method: "POST",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
      cache: "no-store",
    });

    const contentType = response.headers.get("content-type") || "application/json";
    const responseBody = await response.text();
    return new NextResponse(responseBody, {
      status: response.status,
      headers: {
        "content-type": contentType,
        "cache-control": "no-store",
        ...(response.headers.get("retry-after") ? { "retry-after": response.headers.get("retry-after") as string } : {}),
      },
    });
  } catch {
    return NextResponse.json(
      { code: "50001", msg: "service unavailable", data: null, success: false, degraded: true },
      { status: 502 }
    );
  } finally {
    limit.release();
  }
}
