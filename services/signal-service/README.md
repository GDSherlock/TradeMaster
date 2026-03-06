# signal-service 运维说明

## 一句话说明
`signal-service` 负责把价格和指标变化翻译成结构化信号事件，供前端、API 和分析模块消费。

## 它在系统里的位置
它位于指标引擎之后、展示层之前。可以把它理解成“系统规则判断器”。

## 非技术读者可理解的输入 / 输出
- 输入：K 线价格、技术指标、规则配置。
- 输出：带方向和触发原因的信号事件。
- 它回答的问题是：“系统现在认为什么事值得提醒？”

## 服务职责
- 运行 12 条 rule-based 信号规则。
- 周期性读取 `indicator_values` + `candles_1m`。
- 把判断结果写入 `signal_events`。
- 对外提供 REST 查询和 WS 实时推送。

## 依赖与端口
- Python 3.12+
- TimescaleDB / PostgreSQL（`DATABASE_URL`）
- 默认端口：`8002`

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

说明：
- `signal-once`：只跑一轮规则。
- `signal-loop`：持续跑规则但不提供对外接口。
- `signal`：启动对外 REST / WS 服务。

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

术语说明：
- `cooldown`：同类信号短时间内不重复触发。
- `WS`：实时推送通道。
- `rule-based`：按明确规则判断，不是黑盒模型。

## 对外接口
- `GET /signal/health`
- `GET /signal/events`
- `GET /signal/cooldown`
- `GET /signal/rules`
- `WS /ws/signal`

## 规则范围（当前 12 条）
- RSI_OVERBOUGHT / RSI_OVERSOLD
- EMA_BULL_CROSS / EMA_BEAR_CROSS
- MACD_BULL_CROSS / MACD_BEAR_CROSS
- DONCHIAN_BREAKOUT_UP / DONCHIAN_BREAKOUT_DOWN
- VWAP_CROSS_UP / VWAP_CROSS_DOWN
- ICHIMOKU_CLOUD_BREAK_UP / ICHIMOKU_CLOUD_BREAK_DOWN

规则配置保存在 `market_data.signal_rule_configs`，支持热更新。

## 数据表
- `market_data.signal_rule_configs`
- `market_data.signal_events`
- `market_data.signal_state`

对应迁移：`db/migrations/004_signal_tables.sql`

## 健康检查
```bash
curl -fsS http://localhost:8002/signal/health | jq .
curl -fsS -H "X-API-Token: $API_TOKEN" "http://localhost:8002/signal/cooldown" | jq .
```

## 常见排查

### 1) `signal/cooldown` 为空
- 先做：检查 `indicator_values` 是否有最新数据。
- 再看：`signal_rule_configs.enabled=true` 是否存在。
- 最后看：`signal_engine` 心跳是否更新。

### 2) WS 无推送
- 先做：检查 `/signal/events?since_id=...` 是否有新增。
- 再看：鉴权头 `X-API-Token` 是否正确。

### 3) 信号过多或过少
- 先做：检查规则参数是否过松或过严。
- 处理：调整 `params`、`cooldown_seconds`、`scope_symbols`、`scope_intervals`。

## 日志与 PID
- 对外服务日志：`logs/signal.log`
- 分组启动日志：
  - `logs/data/signal-engine.log`
  - `logs/edge/signal-service.log`
- PID：`run/pids/data/signal-engine.pid`、`run/pids/edge/signal-service.pid`

## 安全提醒
- 生产环境下除 `/signal/health` 外应保持鉴权开启。
- 不要把调试 token 放进公开文档或截图。

## 与其他服务依赖关系
- 上游：`pipeline-service`
- 下游：`api-service`、`web-dashboard`、`ml-validator-service`
