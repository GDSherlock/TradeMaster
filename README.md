# TradeMaster

## 1. 项目简介（MVP 范围）
1. 历史数据回填（HuggingFace -> TimescaleDB）
2. 实时行情采集（WebSocket -> TimescaleDB）
3. 指标引擎（增量计算 10 个常用指标）
4. 信号引擎（rule-based 12 条规则）
5. 对外 API（兼容现有 Dashboard）
6. chat-service（行情/指标上下文 + LLM 回答）

非目标：
1. 不做多交易所适配
2. 不做机器学习/黑盒信号引擎（当前仅 rule-based）
3. 不做订单执行/做市
4. 不做全量币种和全量指标

---

## 2. 系统要求
1. OS：macOS / Linux（建议）
2. Python：3.12+
3. PostgreSQL：16+
4. TimescaleDB：2.14+
5. psql / pg_isready 可用

---

## 3. 架构概览

### 服务
| 服务 | 端口 | 职责 |
|---|---:|---|
| TimescaleDB | 5434 | 统一存储历史/实时/指标 |
| pipeline-service | 9101 | 回填 + 实时采集 + 指标调度（单服务） |
| signal-service | 8002 | 规则信号计算 + 信号 REST/WS |
| api-service | 8000 | 前端兼容 REST + WS 接口 |
| chat-service | 8001 | Chatbox 上下文增强 + LLM |
| web-dashboard | 8088 | 前端展示（复用） |

### 数据流
```text
[HuggingFace] -> [pipeline backfill] ----\
                                          -> [TimescaleDB candles_1m] -> [indicator_engine] -> [indicator_values]
[Binance WS] -> [pipeline live ws] ------/
                                          -> [signal_engine] -> [signal_events]

[web-dashboard] <-> [api-service] <-> [signal_events]
[web-dashboard] <-> [api-service/ws/signal]
[chat-service] -> [api-service] -> [TimescaleDB]
[signal-service] -> [TimescaleDB]
[chat-service] -> [LLM Provider]
```

---

## 4. 快速开始（5 步）
1. 进入目录并初始化
```bash
cd tradecat-mvp
make init
```

2. 配置环境变量
```bash
cp config/.env.example config/.env
chmod 600 config/.env
```

3. 初始化数据库 schema
```bash
make db-init
```

4. 先回填一段历史数据
```bash
make backfill SYMBOLS=BTCUSDT,ETHUSDT DAYS=180 RESUME=1
```

5. 一键启动核心服务
```bash
make dev
make status
```

访问地址：
1. API: http://localhost:8000
2. Chat: http://localhost:8001
3. Signal: http://localhost:8002/signal/health
4. Dashboard: http://localhost:8088
5. Pipeline Live Health: http://localhost:9101/health
6. Pipeline Indicator Health: http://localhost:9102/health

---

## 5. 配置说明（关键 env）
配置文件：`config/.env`（模板：`config/.env.example`）

| 变量 | 默认值 | 说明 |
|---|---|---|
| DATABASE_URL | postgresql://postgres:postgres@localhost:5434/market_data | TimescaleDB 连接串 |
| DEFAULT_EXCHANGE | binance_futures_um | 默认交易所 |
| AUTH_ENABLED | false | 本地默认关闭鉴权 |
| API_TOKEN | dev-token | 鉴权 token（开启 AUTH 时生效） |
| CORS_ALLOW_ORIGINS | http://localhost:8088 | CORS 白名单 |
| SYMBOLS | BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT | 采集币种 |
| INTERVALS | 1m,5m,15m,1h,4h,1d | 计算/查询周期 |
| BACKFILL_DAYS | 365 | 默认回填天数 |
| BACKFILL_CHUNK_ROWS | 100000 | 回填分块大小 |
| WS_RECONNECT_MAX_SECONDS | 60 | WS 最大退避 |
| INDICATOR_SCHEDULE_SECONDS | 60 | 指标刷新周期 |
| SIGNAL_SERVICE_HOST/PORT | 0.0.0.0 / 8002 | Signal 服务监听 |
| SIGNAL_SCHEDULE_SECONDS | 30 | 信号刷新周期 |
| SIGNAL_WS_POLL_SECONDS | 1.0 | 信号 WS 拉取轮询间隔 |
| SIGNAL_RATE_LIMIT_PER_MINUTE | 120 | Signal REST 限流 |
| SIGNAL_RATE_LIMIT_BURST | 20 | Signal REST 突发配额 |
| API_SERVICE_HOST/PORT | 0.0.0.0 / 8000 | API 服务监听 |
| CHAT_SERVICE_HOST/PORT | 0.0.0.0 / 8001 | Chat 服务监听 |
| API_SERVICE_BASE_URL | http://localhost:8000 | Chat 拉取上下文的 API 地址 |
| LLM_BASE_URL | https://api.openai.com/v1 | LLM 基地址 |
| LLM_MODEL | gpt-5.2 | 模型名 |
| LLM_API_KEY | 空 | LLM 密钥 |

---

## 6. 启动/停止/状态命令
一键启动（推荐）：
```bash
make dev
make stop
make status
```

`make dev` 会同时启动：
1. pipeline-live（实时采集）
2. pipeline-indicator（指标循环）
3. signal-service（规则信号）
4. api-service
5. chat-service
6. web-dashboard

等价脚本（推荐）：
```bash
./scripts/devctl.sh start
./scripts/devctl.sh stop
./scripts/devctl.sh status
```

分步启动（调试用）：
```bash
# 终端 1：实时采集
make live

# 终端 2：指标循环（默认健康端口 9102）
make indicators-loop

# 终端 3：API
make api

# 终端 4：Signal
make signal

# 终端 5：Chat
make chat

# 终端 6：Dashboard
make dashboard
```

---

## 7. 回填历史数据命令
```bash
make backfill SYMBOLS=BTCUSDT,ETHUSDT DAYS=365 RESUME=1
```

说明：
1. `RESUME=1` 会读取 `market_data.backfill_state` 断点继续
2. 导入幂等：主键冲突走 upsert
3. source 优先级：`hf_backfill > rest_gap_fill > ws_live`

---

## 8. WebSocket 实时采集命令
```bash
make live
```

检查是否持续写入：
```bash
psql "$DATABASE_URL" -c "SELECT max(bucket_ts) FROM market_data.candles_1m WHERE symbol='BTCUSDT';"
```

---

## 9. 指标计算/刷新命令
一次性刷新：
```bash
make indicators-once SYMBOLS=BTCUSDT,ETHUSDT INTERVALS=1m,1h
```

循环调度：
```bash
make indicators-loop
```

端口说明：
1. `make live` 默认占用 `9101`
2. `make indicators-loop` 默认占用 `9102`（可通过 `INDICATOR_PORT` 覆盖）

默认指标（10）：
1. EMA20
2. EMA50
3. EMA200
4. MACD(12,26,9)
5. RSI14
6. ATR14
7. BBands(20,2)
8. VWAP
9. Donchian20
10. Ichimoku(9,26,52)

---

## 10. 信号计算/刷新命令
一次性刷新：
```bash
make signal-once SYMBOLS=BTCUSDT,ETHUSDT INTERVALS=1m,1h
```

循环调度：
```bash
make signal-loop
```

信号服务 REST/WS：
```bash
make signal
```

首版内置规则（12）：
1. RSI_OVERBOUGHT
2. RSI_OVERSOLD
3. EMA_BULL_CROSS
4. EMA_BEAR_CROSS
5. MACD_BULL_CROSS
6. MACD_BEAR_CROSS
7. DONCHIAN_BREAKOUT_UP
8. DONCHIAN_BREAKOUT_DOWN
9. VWAP_CROSS_UP
10. VWAP_CROSS_DOWN
11. ICHIMOKU_CLOUD_BREAK_UP
12. ICHIMOKU_CLOUD_BREAK_DOWN

---

## 11. API 文档（主要 endpoints + 示例）

统一响应：
```json
{"code":"0","msg":"success","data":{},"success":true}
```

错误码：
- `0` 成功
- `40001` 参数错误
- `40002` symbol 无效
- `40003` interval 无效
- `40101` 未授权
- `42901` 限流
- `50001` 服务不可用
- `50002` 内部错误

### 11.1 健康检查
```bash
curl http://localhost:8000/api/health
```

### 11.2 支持币种
```bash
curl http://localhost:8000/api/futures/supported-coins
```

### 11.3 K线历史
```bash
curl "http://localhost:8000/api/futures/ohlc/history?symbol=BTCUSDT&interval=1h&limit=5"
```

### 11.4 指标列表
```bash
curl http://localhost:8000/api/indicator/list
```

### 11.5 指标数据
```bash
curl "http://localhost:8000/api/indicator/data?table=rsi_14&symbol=BTCUSDT&interval=1h&limit=1"
```

### 11.6 市场动量
```bash
curl "http://localhost:8000/api/markets/momentum?exchange=binance_futures_um"
```

### 11.7 涨跌榜
```bash
curl "http://localhost:8000/api/markets/top-movers?limit=20&order=abs&exchange=binance_futures_um"
```

### 11.8 信号冷却（兼容前端）
```bash
curl "http://localhost:8000/api/signal/cooldown"
```

### 11.9 信号事件查询
```bash
curl "http://localhost:8000/api/signal/events?limit=20&symbol=BTCUSDT&interval=1h"
```

### 11.9.1 最新信号事件窗口（Signal Flow bootstrap）
```bash
curl "http://localhost:8000/api/signal/events/latest?limit=60"
curl "http://localhost:8000/api/signal/events/latest?limit=60&symbol=BTCUSDT&interval=1h"
```

### 11.9.2 Signal Flow 实时推送（Dashboard）

Signal Flow 采用 `REST bootstrap + WS 增量`：
1. 页面初始化调用 `GET /api/signal/events/latest?limit=60` 获取最近事件窗口。
2. 记录 `max(id)` 后连接 `WS /ws/signal?since_id=<max_id>` 接收增量。
3. 前端支持双模式：
- `Events`：逐条显示最新触发事件。
- `Summary`：按 `symbol + interval` 聚合摘要展示。

说明：
1. 前端统一走 `api-service`（8000），不直接连接 `signal-service`（8002）。
2. 若 WS 断开，前端自动回退到 `events/latest` 轮询兜底。

### 11.10 Signal 规则配置
```bash
curl "http://localhost:8000/api/signal/rules"
```

### 11.11 WS 行情
```bash
# 浏览器或 ws 客户端连接
ws://localhost:8000/ws/market?symbol=BTCUSDT&interval=1m
```

推送示例：
```json
{"event":"kline","data":{"time":1760000000000,"open":"96000","high":"96500","low":"95500","close":"96200","volume":"123.45"}}
```

### 11.12 WS 信号推送
```bash
ws://localhost:8000/ws/signal?symbol=BTCUSDT&interval=1h
```

推送示例：
```json
{"event":"signal","data":{"id":101,"symbol":"BTCUSDT","interval":"1h","rule_key":"EMA_BULL_CROSS","type":"EMA_CROSS","direction":"bullish","timestamp":1760000000000}}
```

### 11.13 Signal Service 直连接口
```bash
curl "http://localhost:8002/signal/health"
curl "http://localhost:8002/signal/cooldown"
```

### 11.14 鉴权
启用 `AUTH_ENABLED=true` 时：
```bash
curl -H "X-API-Token: dev-token" http://localhost:8000/api/health
```

---

## 12. chat-service 使用说明

### 12.1 请求示例
```bash
curl -X POST "http://localhost:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message":"BTCUSDT 1h 的 RSI 和 MACD 怎么看？",
    "session_id":"demo-session-1"
  }'
```

---

## 13. 文档导航索引

按服务拆分的运维说明与数据库查询指南：

1. [pipeline-service README](./services/pipeline-service/README.md)
2. [api-service README](./services/api-service/README.md)
3. [signal-service README](./services/signal-service/README.md)
4. [chat-service README](./services/chat-service/README.md)
5. [web-dashboard README](./services-preview/web-dashboard/README.md)
6. [DB 查询与时效性指南](./db/README.md)

### 13.1 上下文注入策略（最小实现）
1. 从用户消息提取 symbol/interval，默认 `BTCUSDT/1h`
2. 并发拉取：
   - `/api/futures/ohlc/history?limit=30`
   - `/api/indicator/list` + `/api/indicator/data?limit=1`
   - `/api/markets/momentum`
3. 生成结构化 context 注入 system prompt
4. 上下文失败时会退化回答并记录审计日志

### 13.2 LLM 配置
1. `LLM_PROVIDER=openai_compatible`
2. `LLM_BASE_URL`
3. `LLM_MODEL`
4. `LLM_API_KEY`

### 13.3 安全与审计（最小）
1. 输入限长 + 注入关键词拦截
2. 输出限长
3. 审计日志：`logs/chat_audit.jsonl`
4. 若 DB 可用，同时写入 `audit.chat_requests`

---

## 14. 验收标准
1. `make dev` 启动后，`api/chat/pipeline/signal/dashboard` 均可达
2. 回填后可查询到历史范围，重复回填不爆量
3. WS 运行后 `candles_1m` 持续更新
4. 指标引擎刷新后 `indicator_values` 有最新记录
5. 信号引擎刷新后 `signal_events` 有新增记录
6. 前端可拉到 K 线、指标、信号并展示
7. chat-service 可回答并引用行情/指标上下文

---

## 15. Troubleshooting（常见问题）
| 问题 | 现象 | 处理 |
|---|---|---|
| 1. DB 连不上 | `connection refused` | 检查 `DATABASE_URL`、5434 端口、`pg_isready` |
| 2. Timescale 扩展缺失 | migration 报 `timescaledb` | 执行 `CREATE EXTENSION timescaledb;` |
| 3. 回填卡住 | 日志无进展 | 降低 `BACKFILL_CHUNK_ROWS`，检查网络和磁盘 |
| 4. 回填重复 | 行数异常增长 | 检查主键和 upsert 是否生效 |
| 5. WS 频繁断开 | 日志持续 reconnect | 检查网络/代理，增大退避上限 |
| 6. 指标不更新 | `indicator_values` 无新数据 | 确认 `candles_1m` 有新数据，检查调度器 |
| 7. 前端跨域失败 | 浏览器 CORS 报错 | 设置 `CORS_ALLOW_ORIGINS=http://localhost:8088` |
| 8. chat 无上下文 | 回答泛化 | 检查 `API_SERVICE_BASE_URL` 和 `/api/*` 可用 |
| 9. chat 401/429 | 鉴权或限流错误 | 传 token，降低请求频率 |
| 10. API 慢 | 查询延迟上升 | 缩小时间范围，检查索引 |
| 11. 信号为空 | `signal_events` 无记录 | 检查 `signal_rule_configs` 开关、`signal_engine` 心跳、规则 cooldown |

---

## 16. 安全注意事项
1. 不要提交 `.env`
2. `.env` 权限必须 `600`
3. 任何密钥禁止输出到前端和普通日志
4. 生产环境必须开启鉴权和 CORS 白名单
5. chat 输出仅供参考，不构成投资建议
