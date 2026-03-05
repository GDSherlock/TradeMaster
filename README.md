# TradeMaster

## 1. 项目简介（当前实现）
TradeMaster 是一个面向加密衍生品行情分析的本地可运行微服务系统，围绕「行情采集 -> 指标计算 -> 规则信号 -> ML 影子验证 -> API/前端/Chat 消费」提供端到端实现。

阶段目标：
1. 打通从历史回填到实时写入的统一数据底座（TimescaleDB）。
2. 提供可解释的指标与规则信号能力，支持前端与 API 实时消费。
3. 提供 `chat-service` 上下文增强问答与审计能力。
4. 在不阻断规则引擎的前提下，以影子模式引入 RSI candidate 的 ML 验证链路。

非目标：
1. 不做多交易所接入编排（当前默认 Binance Futures UM）。
2. 不做自动下单、做市与资金管理执行系统。
3. 不做黑盒策略平台（信号与 ML 结果均可追踪解释）。
4. 不覆盖全量币种与无限指标集合（以配置白名单为主）。

### 1.1 服务实现概览
| 服务 | 主要实现内容 |
|---|---|
| `pipeline-service` | 历史回填（HuggingFace）+ 实时采集（WS/REST 补洞）+ 指标计算（10 个常用指标） |
| `signal-service` | 12 条 rule-based 规则信号计算、信号查询 REST、实时增量 WS |
| `api-service` | 统一 REST/WS 聚合入口，提供行情/指标/信号/ML 查询接口给前端与内部服务 |
| `chat-service` | 消息校验与注入防护、行情指标上下文构建、LLM 调用、审计日志落盘/可选落库 |
| `ml-validator-service` | RSI candidate 影子验证、训练调度、漂移检查、阈值再校准、运行态查询 API |
| `web-dashboard` | Next.js 前端展示层与同源代理，统一消费 `api-service` 与 `chat-service` |

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
| ml-validator-service | 8003 | RSI candidate 机器学习验证（训练 + 在线打分 + 运行态 API） |
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
[ml-validator-service] -> [TimescaleDB signal_events + indicator_values + candles_1m]
[api-service] <-> [signal_ml_validation / signal_ml_training_runs]
[chat-service] -> [LLM Provider]
```

---

## 4. 快速开始（5 步）
1. 进入目录并初始化
```bash
cd /Users/kingjason/Desktop/Trademaster
make init
```

2. 配置环境变量（安全默认）
```bash
cp config/.env.example config/.env
chmod 600 config/.env
# 必填：将 API_TOKEN / API_SERVICE_TOKEN 改成强随机值
```

本地快速调试可选：
```bash
cp config/.env.dev.example config/.env
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
make dev #启动全部服务，并且前端出错不会导致后端停止
make status #查看状态
```

访问地址：
1. API: http://localhost:8000
2. Chat: http://localhost:8001
3. Signal: http://localhost:8002/signal/health
4. ML Validator: http://localhost:8003/ml/health
5. Dashboard: http://localhost:8088
6. Pipeline Live Health: http://localhost:9101/health
7. Pipeline Indicator Health: http://localhost:9102/health

---

## 5. 配置说明（关键 env）
配置文件：`config/.env`（模板：`config/.env.example`）

| 变量 | 默认值 | 说明 |
|---|---|---|
| DATABASE_URL | postgresql://postgres:postgres@localhost:5434/market_data | TimescaleDB 连接串 |
| DEFAULT_EXCHANGE | binance_futures_um | 默认交易所 |
| AUTH_ENABLED | true | 默认开启鉴权（推荐） |
| API_TOKEN | <CHANGE_ME_STRONG_TOKEN> | 鉴权 token（必须改成强随机值） |
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
| ML_VALIDATOR_SERVICE_HOST/PORT | 0.0.0.0 / 8003 | ML Validator 服务监听 |
| ML_VALIDATE_LOOP_SECONDS | 30 | 在线验证 worker 轮询周期 |
| ML_TRAIN_SCHEDULE_HOUR/MINUTE | 2 / 10 | 每日训练触发时间 |
| ML_TRAIN_TIMEZONE | Asia/Singapore | 训练调度时区 |
| ML_RECALIBRATE_SCHEDULE_WEEKDAY/HOUR/MINUTE | 6 / 2 / 40 | 每周阈值再校准触发时间（周日 02:40） |
| ML_LOOKBACK_DAYS | 180 | 训练样本滚动窗口天数 |
| ML_HORIZON_BARS | 6 | triple-barrier 标签预测窗口 bars |
| ML_DRIFT_CHECK_HOURS | 6 | PSI 漂移检查周期 |
| ML_DRIFT_PSI_THRESHOLD | 0.2 | 漂移触发阈值 |
| API_SERVICE_HOST/PORT | 0.0.0.0 / 8000 | API 服务监听 |
| CHAT_SERVICE_HOST/PORT | 0.0.0.0 / 8001 | Chat 服务监听 |
| API_SERVICE_BASE_URL | http://localhost:8000 | Chat 拉取上下文的 API 地址 |
| API_SERVICE_TOKEN | <SAME_AS_API_TOKEN_FOR_INTERNAL_CALLS> | 内部服务（chat/dashboard 代理）访问 API 的 token |
| CHAT_SERVICE_BASE_URL | http://localhost:8001 | web-dashboard BFF 转发 chat 的上游地址 |
| LLM_BASE_URL | https://api.openai.com/v1 | LLM 基地址 |
| LLM_MODEL | gpt-5.2 | 模型名 |
| LLM_API_KEY | 空 | LLM 密钥 |

---

## 6. 启动/停止/状态命令
启动（推荐）：
```bash
make dev
```

`make dev` 默认会先启动 data + edge，再尝试启动 web。若 web-dashboard 失败，会输出告警但保持后端运行并返回成功。

严格模式（web 失败即返回非零）：
```bash
DEVCTL_WEB_REQUIRED=1 make dev
```

`make dev` 会尝试启动：
1. pipeline-live（实时采集）
2. pipeline-indicator（指标循环）
3. signal-engine（规则计算 loop，data 组）
4. ml-validate-loop（在线验证 worker，data 组）
5. ml-monitor-loop（训练/漂移/再校准调度，data 组）
6. api-service（edge 组）
7. chat-service（edge 组）
8. signal-service serve（edge 组）
9. ml-validator-service serve（edge 组）
10. web-dashboard（web 组）

查看状态：
```bash
make status
```

停止全部服务：
```bash
make stop
```

`make stop` 会停止全部组（data + edge + web）。

仅停止前端（不影响后端）：
```bash
./scripts/devctl.sh stop --group web
```

分组启动（解耦发布推荐）：
```bash
make dev-data
make dev-edge
make dev-web
```

等价脚本（支持分组）：
```bash
./scripts/devctl.sh start
./scripts/devctl.sh stop
./scripts/devctl.sh status
./scripts/devctl.sh start --group data
./scripts/devctl.sh start --group edge
./scripts/devctl.sh start --group web
./scripts/devctl.sh restart --group web
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

# 终端 6：ML Validator
make ml-service

# 训练调度（可选）
make ml-monitor-loop

# 终端 7：Dashboard
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

### 11.0 鉴权与公开端点边界
| 服务 | 公开端点（无需 token） | 受保护端点（需 `X-API-Token`） |
|---|---|---|
| api-service (8000) | `/api/health`、`/docs`、`/openapi.json`、`/redoc` | 其余 `/api/*` 与 `/ws/*` |
| signal-service (8002) | `/signal/health`、`/docs`、`/openapi.json`、`/redoc` | 其余 `/signal/*` 与 `/ws/signal` |
| ml-validator-service (8003) | `/ml/health`、`/docs`、`/openapi.json`、`/redoc` | 其余 `/ml/*` |

启用 `AUTH_ENABLED=true` 时，先设置 token：
```bash
export API_TOKEN='<CHANGE_ME_STRONG_TOKEN>'
```

### 11.1 API 健康检查（公开）
```bash
curl http://localhost:8000/api/health
```

### 11.2 支持币种
```bash
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/futures/supported-coins"
```

### 11.3 K线历史
```bash
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/futures/ohlc/history?symbol=BTCUSDT&interval=1h&limit=5"
```

### 11.4 指标列表
```bash
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/indicator/list"
```

### 11.5 指标数据
```bash
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/indicator/data?table=rsi_14&symbol=BTCUSDT&interval=1h&limit=1"
```

### 11.6 市场动量
```bash
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/markets/momentum?exchange=binance_futures_um"
```

### 11.7 涨跌榜
```bash
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/markets/top-movers?limit=20&order=abs&exchange=binance_futures_um"
```

### 11.8 信号冷却（兼容前端）
```bash
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/signal/cooldown"
```

### 11.9 信号事件查询
```bash
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/signal/events?limit=20&symbol=BTCUSDT&interval=1h"
```

### 11.9.1 最新信号事件窗口（Signal Flow bootstrap）
```bash
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/signal/events/latest?limit=60"
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/signal/events/latest?limit=60&symbol=BTCUSDT&interval=1h"
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
3. 当 `AUTH_ENABLED=true` 时，WS 需携带 `X-API-Token` 请求头，或通过 query 参数 `token=<API_TOKEN>`。

### 11.10 Signal 规则配置
```bash
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/signal/rules"
```

### 11.11 WS 行情
```bash
# 方式 A：wscat 通过 Header 鉴权（推荐）
wscat -H "X-API-Token: $API_TOKEN" \
  -c "ws://localhost:8000/ws/market?symbol=BTCUSDT&interval=1m"

# 方式 B：query token（仅用于本地调试）
ws://localhost:8000/ws/market?symbol=BTCUSDT&interval=1m&token=<API_TOKEN>
```

推送示例：
```json
{"event":"kline","data":{"time":1760000000000,"open":"96000","high":"96500","low":"95500","close":"96200","volume":"123.45"}}
```

### 11.12 WS 信号推送
```bash
# 方式 A：wscat 通过 Header 鉴权（推荐）
wscat -H "X-API-Token: $API_TOKEN" \
  -c "ws://localhost:8000/ws/signal?symbol=BTCUSDT&interval=1h"

# 方式 B：query token（仅用于本地调试）
ws://localhost:8000/ws/signal?symbol=BTCUSDT&interval=1h&token=<API_TOKEN>
```

推送示例：
```json
{"event":"signal","data":{"id":101,"symbol":"BTCUSDT","interval":"1h","rule_key":"EMA_BULL_CROSS","type":"EMA_CROSS","direction":"bullish","timestamp":1760000000000}}
```

### 11.13 Signal Service 直连接口
```bash
curl "http://localhost:8002/signal/health"
curl -H "X-API-Token: $API_TOKEN" "http://localhost:8002/signal/cooldown"
```

### 11.14 ML 结果查询（前端统一入口）
```bash
curl -H "X-API-Token: $API_TOKEN" "http://localhost:8000/api/ml/runtime"
curl -H "X-API-Token: $API_TOKEN" "http://localhost:8000/api/ml/training/runs?limit=5"
curl -H "X-API-Token: $API_TOKEN" "http://localhost:8000/api/ml/training/runs/1"
curl -H "X-API-Token: $API_TOKEN" "http://localhost:8000/api/ml/drift/latest?limit=5"
curl -H "X-API-Token: $API_TOKEN" "http://localhost:8000/api/ml/validation/summary?window=7d"
curl -H "X-API-Token: $API_TOKEN" "http://localhost:8000/api/ml/validation/metrics?window=7d"
```

### 11.15 ML 候选事件查询（新增）
```bash
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/ml/validation/candidates?limit=20&status=pending"
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/ml/validation/candidates/123"
```

### 11.16 ML 报告
```bash
make ml-report
cat logs/ml_report.md
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
5. [ml-validator-service README](./services/ml-validator-service/README.md)
6. [web-dashboard README](./services-preview/web-dashboard/README.md)
7. [DB 查询与时效性指南](./db/README.md)
8. [服务依赖矩阵](./docs/service_dependency_matrix.md)
9. [DB 兼容策略](./docs/db_compatibility_policy.md)

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
1. `make dev` 启动后，`api/chat/pipeline/signal/ml-validator/dashboard` 均可达
2. 回填后可查询到历史范围，重复回填不爆量
3. WS 运行后 `candles_1m` 持续更新
4. 指标引擎刷新后 `indicator_values` 有最新记录
5. 信号引擎刷新后 `signal_events` 有新增记录
6. 前端可拉到 K 线、指标、信号并展示
7. `/api/ml/*` 可查询到验证摘要、候选列表和训练指标
8. `make ml-report` 生成 `logs/ml_report.md`，可查看 champion、训练历史与漂移告警
9. chat-service 可回答并引用行情/指标上下文
10. `make security-check` 执行成功，并生成 `logs/security_report.md` 供告警审阅

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
