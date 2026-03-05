# signal-service 运维说明

## 服务职责
- 运行 rule-based 信号引擎（12 类规则）。
- 周期性读取 `indicator_values` + `candles_1m`，写入 `signal_events`。
- 提供信号查询和实时推送接口：`/signal/*`、`/ws/signal`。

## 依赖与端口
- Python 3.12+。
- TimescaleDB/PostgreSQL（`DATABASE_URL`）。
- 默认端口：`SIGNAL_SERVICE_PORT=8002`。

## 启动方式
在仓库根目录：

```bash
make signal-once
make signal-loop
make signal
```

全链路托管：

```bash
make dev
make status
make stop
```

`make dev` 会通过 `scripts/devctl.sh` 启动 signal-service（命令 `python -m src all`）。

## 关键配置
来自 `config/.env`：

- `SIGNAL_SERVICE_HOST/PORT`
- `SIGNAL_SCHEDULE_SECONDS`
- `SIGNAL_WS_POLL_SECONDS`
- `SIGNAL_RATE_LIMIT_PER_MINUTE`
- `SIGNAL_RATE_LIMIT_BURST`
- `SYMBOLS`
- `INTERVALS`
- `AUTH_ENABLED`
- `API_TOKEN`

## 对外接口
- `GET /signal/health`
- `GET /signal/events`
- `GET /signal/cooldown`
- `GET /signal/rules`
- `WS /ws/signal`

## 规则范围（首版 12 条）
- RSI_OVERBOUGHT / RSI_OVERSOLD
- EMA_BULL_CROSS / EMA_BEAR_CROSS
- MACD_BULL_CROSS / MACD_BEAR_CROSS
- DONCHIAN_BREAKOUT_UP / DONCHIAN_BREAKOUT_DOWN
- VWAP_CROSS_UP / VWAP_CROSS_DOWN
- ICHIMOKU_CLOUD_BREAK_UP / ICHIMOKU_CLOUD_BREAK_DOWN

规则参数与开关保存在 `market_data.signal_rule_configs`，支持热更新。

## 数据表
- `market_data.signal_rule_configs`
- `market_data.signal_events`
- `market_data.signal_state`

migration 文件：`db/migrations/004_signal_tables.sql`。

## 常见排查
1. `signal/cooldown` 为空：
- 检查 `indicator_values` 是否有最新数据。
- 检查 `signal_rule_configs.enabled=true` 是否存在。
- 检查 `signal_engine` 心跳是否更新。

2. WS 无推送：
- 检查 `/signal/events?since_id=...` 是否有新增数据。
- 检查鉴权头 `X-API-Token`（当 `AUTH_ENABLED=true` 时）。

3. 信号过多/过少：
- 调整 `signal_rule_configs.params` 和 `cooldown_seconds`。
- 按 symbol/interval 细化 `scope_symbols/scope_intervals`。
