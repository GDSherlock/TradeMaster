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

## Data flow (realtime)

- REST bootstrap: `/api/signal/events/latest?limit=60`
- WS stream: `ws://<host>:8000/ws/signal?since_id=<max_id>`
- Fallback polling: latest events every 15 seconds
- Market/indicator data:
  - `/api/markets/momentum`
  - `/api/futures/ohlc/history`
  - `/api/indicator/list`
  - `/api/indicator/data`
- Chat: `POST http://<host>:8001/chat`

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
