# Crypto Analyst Dashboard (Next.js, legacy single-page style)

## Run

From repo root:

```bash
make init
make dev
make status
```

Or dashboard only:

```bash
cd services-preview/web-dashboard
./scripts/start.sh run
```

URL: `http://localhost:8088`

## Route behavior

- `/` renders the legacy-style single dashboard page (market + signal + chat).
- `/app` redirects to `/` for backward compatibility.
- `/ml-validation` renders ML validation console (runtime + candidates + training runs + drift).

## Data flow (realtime)

- REST bootstrap: `/api/trademaster/signal/events/latest?limit=60`（由 Next.js 服务端代理转发到 api-service）
- WS stream: `ws://<host>:8000/ws/signal?since_id=<max_id>`
- Fallback polling: latest events every 15 seconds
- Market/indicator data:
  - `/api/trademaster/markets/momentum`
  - `/api/trademaster/futures/ohlc/history`
  - `/api/trademaster/indicator/list`
  - `/api/trademaster/indicator/data`
- Chat: `POST /api/trademaster/chat`（由 Next.js BFF 转发到 chat-service）
- ML panel:
  - `/api/trademaster/ml/runtime`
  - `/api/trademaster/ml/validation/summary`
  - `/api/trademaster/ml/validation/candidates`
  - `/api/trademaster/ml/training/runs`
  - `/api/trademaster/ml/drift/latest`

## Auth proxy

- 默认 REST 入口是同源代理：`/api/trademaster/[...path]`。
- 代理只允许 `GET` 且只允许前缀：`health`、`futures`、`indicator`、`markets`、`signal`、`ml`。
- 代理在服务端注入 `X-API-Token`（来源：`API_SERVICE_TOKEN`，为空时回退 `API_TOKEN`）。
- Chat 入口是同源代理：`POST /api/trademaster/chat`（转发到 `CHAT_SERVICE_BASE_URL/chat`，默认 `http://localhost:8001/chat`）。
- BFF 限流：`GET /api/trademaster/*` 为 `120/min`（burst 20），`POST /api/trademaster/chat` 为 `20/min`（并发上限 5/IP）。
- 该设计避免在浏览器暴露 token；禁止把 token 放到 `NEXT_PUBLIC_*` 变量中。

## Edit points

- Main page orchestration: `app/page.tsx`
- Legacy components:
  - `components/LegacyTopbar.tsx`
  - `components/LegacyDashboardPanel.tsx`
  - `components/LegacyChatPanel.tsx`
  - `components/SignalFlowList.tsx`
  - `components/TrendGrid.tsx`
  - `components/IndicatorList.tsx`
- Realtime data helpers: `lib/live-data.ts`
- Legacy visual system: `app/globals.css`

## Non-goal

- This rollback does not switch back to `python -m http.server` static mode.
- Startup remains Next.js via `scripts/start.sh` and `scripts/devctl.sh`.
