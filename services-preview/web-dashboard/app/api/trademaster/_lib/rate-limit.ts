import { NextRequest } from "next/server";

type RateLimitConfig = {
  ratePerMinute: number;
  burst: number;
  maxConcurrency?: number;
};

type BucketState = {
  tokens: number;
  ts: number;
};

const buckets = new Map<string, BucketState>();
const inflight = new Map<string, number>();

function nowSeconds(): number {
  return Date.now() / 1000;
}

function keyFor(namespace: string, clientKey: string): string {
  return `${namespace}:${clientKey}`;
}

function refillTokens(state: BucketState, ratePerMinute: number, burst: number): BucketState {
  const now = nowSeconds();
  const refill = (now - state.ts) * (ratePerMinute / 60);
  const tokens = Math.min(burst, state.tokens + Math.max(0, refill));
  return { tokens, ts: now };
}

function resolveClientIp(request: NextRequest): string {
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) {
    const first = forwarded.split(",")[0]?.trim();
    if (first) {
      return first;
    }
  }
  const realIp = request.headers.get("x-real-ip");
  if (realIp) {
    return realIp.trim();
  }
  return "unknown";
}

export function getClientKey(request: NextRequest): string {
  return resolveClientIp(request);
}

export function applyRateLimit(
  namespace: string,
  clientKey: string,
  config: RateLimitConfig
): {
  allowed: boolean;
  retryAfterSeconds: number;
  release: () => void;
} {
  const scopedKey = keyFor(namespace, clientKey || "unknown");
  const maxConcurrency = Math.max(0, config.maxConcurrency ?? 0);
  let acquiredConcurrency = false;

  if (maxConcurrency > 0) {
    const active = inflight.get(scopedKey) ?? 0;
    if (active >= maxConcurrency) {
      return {
        allowed: false,
        retryAfterSeconds: 1,
        release: () => {},
      };
    }
    inflight.set(scopedKey, active + 1);
    acquiredConcurrency = true;
  }

  const ratePerMinute = Math.max(1, config.ratePerMinute);
  const burst = Math.max(1, config.burst);
  const current = buckets.get(scopedKey) ?? { tokens: burst, ts: nowSeconds() };
  const refilled = refillTokens(current, ratePerMinute, burst);

  if (refilled.tokens < 1) {
    buckets.set(scopedKey, refilled);
    if (acquiredConcurrency) {
      const active = inflight.get(scopedKey) ?? 0;
      if (active <= 1) {
        inflight.delete(scopedKey);
      } else {
        inflight.set(scopedKey, active - 1);
      }
    }
    const missing = Math.max(0, 1 - refilled.tokens);
    const retryAfterSeconds = Math.max(1, Math.ceil(missing / (ratePerMinute / 60)));
    return {
      allowed: false,
      retryAfterSeconds,
      release: () => {},
    };
  }

  buckets.set(scopedKey, { tokens: refilled.tokens - 1, ts: refilled.ts });

  return {
    allowed: true,
    retryAfterSeconds: 0,
    release: () => {
      if (!acquiredConcurrency) {
        return;
      }
      const active = inflight.get(scopedKey) ?? 0;
      if (active <= 1) {
        inflight.delete(scopedKey);
      } else {
        inflight.set(scopedKey, active - 1);
      }
    },
  };
}
