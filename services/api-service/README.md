# api-service 运维说明

## 服务职责
- 对外提供 REST API（行情、指标、市场统计、信号查询）。
- 对外提供 WS 推送接口（`/ws/market`、`/ws/signal`）。
- 负责基础鉴权（可配置开关）与 IP 限流。

核心路由分组：
- `health`：`/api/health`
- `futures`：`/api/futures/*`
- `indicator`：`/api/indicator/*`
- `markets`：`/api/markets/*`
- `signal`：`/api/signal/cooldown`、`/api/signal/events`、`/api/signal/events/latest`、`/api/signal/rules`

## 依赖与端口
- Python 3.12+。
- TimescaleDB/PostgreSQL（读数据）。
- 端口：`API_SERVICE_PORT`（默认 `8000`）。
- 依赖 `pipeline-service` 持续写入数据。

## 启动/停止/状态

在仓库根目录执行。

全链路托管（推荐）：

```bash
make dev
make status
make stop
```

仅启动 API：

```bash
make api
```

直接运行（调试）：

```bash
cd services/api-service
.venv/bin/python -m src
```

预期结果：
- `http://localhost:8000/api/health` 返回成功。

异常时下一步动作：
- 查看 `logs/api.log`。
- 检查 `DATABASE_URL` 连通与表数据是否存在。

## 关键配置

来自 `config/.env`：

- `API_SERVICE_HOST/PORT`：监听地址。
- `DATABASE_URL`：数据库连接串。
- `DEFAULT_EXCHANGE`：默认交易所。
- `AUTH_ENABLED`：是否启用鉴权。
- `API_TOKEN`：鉴权 token（启用鉴权时生效）。
- `CORS_ALLOW_ORIGINS`：逗号分隔白名单。
- `API_RATE_LIMIT_PER_MINUTE`、`API_RATE_LIMIT_BURST`：IP 限流参数。

鉴权与限流说明：
- 当 `AUTH_ENABLED=true` 时，除 `/api/health`、文档相关路径外，需要 `X-API-Token`。
- 非白名单路径会执行 IP 限流，超限返回 429。

## 健康检查

```bash
curl -fsS http://localhost:8000/api/health | jq .
curl -fsS "http://localhost:8000/api/futures/supported-coins" | jq .
curl -fsS "http://localhost:8000/api/indicator/list" | jq .
```

WS 连通性：

```bash
python - <<'PY'
import asyncio, websockets
async def main():
    async with websockets.connect("ws://localhost:8000/ws/market?symbol=BTCUSDT&interval=1m") as ws:
        msg = await ws.recv()
        print(msg[:200])
    async with websockets.connect("ws://localhost:8000/ws/signal?symbol=BTCUSDT&interval=1h") as ws:
        msg = await ws.recv()
        print(msg[:200])
asyncio.run(main())
PY
```

预期结果：
- REST 接口返回统一结构 `{"code":"0","success":true,...}`。
- `/ws/market` 可收到 `kline` 或 `ping` 事件。
- `/ws/signal` 可收到 `signal` 或 `ping` 事件。

Signal Flow bootstrap（推荐）：

```bash
curl -fsS "http://localhost:8000/api/signal/events/latest?limit=60" | jq .
curl -fsS "http://localhost:8000/api/signal/events/latest?limit=60&symbol=BTCUSDT&interval=1h" | jq .
```

说明：
- `events/latest` 用于前端启动时获取最近事件窗口（默认 60 条，最大 200 条）。
- 前端取最大 `id` 后连接 `/ws/signal?since_id=<max_id>` 获取增量，避免历史全量回放。

异常时下一步动作：
- REST 失败先看 `logs/api.log`，再查 DB 是否有对应 symbol 数据。
- WS 失败时先检查鉴权、symbol/interval 参数是否合法。

## 日志与 PID
- 日志：`logs/api.log`。
- PID：`run/pids/api.pid`。

快速查看：

```bash
tail -n 100 logs/api.log
cat run/pids/api.pid
```

## 常见故障与处理

### 1) 401 未授权
- 现象：接口返回 `40101`。
- 先做：确认 `AUTH_ENABLED` 与请求头 `X-API-Token` 是否匹配。
- 处理：同步 API 与调用方 token 配置。

### 2) 429 限流
- 现象：短时间请求激增后返回 429。
- 先做：确认流量来源与 IP。
- 处理：优化调用频率，必要时调大 `API_RATE_LIMIT_*`。

### 3) 500 内部错误
- 现象：接口返回 `50002`。
- 先做：查看 `logs/api.log` 中异常堆栈。
- 处理：优先排查 DB 连接、参数校验、数据缺失。

### 4) WS 无持续数据
- 现象：连接建立但长期无 `kline`。
- 先做：检查 pipeline 是否在写 `candles_1m`。
- 处理：先恢复 pipeline 写入，再复测 WS。

### 5) 信号接口为空
- 现象：`/api/signal/cooldown`、`/api/signal/events` 或 `/api/signal/events/latest` 长时间为空数组。
- 先做：检查 `signal-service` 是否运行、`signal_engine` 心跳是否刷新。
- 处理：确认 `signal_rule_configs.enabled=true`，并检查 `indicator_values` 是否有增量。

## 日常巡检清单
- 每 1-5 分钟：
- `curl /api/health`。
- 抽样调用 1-2 个核心接口确认有数据。
- 每小时：
- 检查 `401/429/500` 发生比例。
- 对比 API 返回最新时间与 DB 最新时间是否一致。
- 每日：
- 复核 CORS、鉴权开关是否符合环境策略（特别是 staging/prod）。

## 与其他服务依赖关系
- 上游依赖：`pipeline-service` 写入的 `market_data` 数据。
- 下游依赖：`web-dashboard` 与 `chat-service` 都依赖本服务提供上下文数据。
- `chat-service` 可通过 `API_SERVICE_TOKEN` 调用受保护接口。
