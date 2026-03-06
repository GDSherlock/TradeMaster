# TradeMaster

TradeMaster 是一个面向加密衍生品分析场景的本地微服务系统。它把“市场数据采集、技术指标计算、规则信号判断、机器学习影子验证、对外 API、聊天解释、前端展示”串成一条完整链路，方便团队在同一套数据上做观察、分析和验证。

如果你不是技术人员，可以先把它理解成一套“市场分析后台”：
1. 它先收集和补齐历史行情。
2. 再把这些行情加工成指标和信号。
3. 然后通过网页、接口和 Chatbox 把结果展示出来。
4. 机器学习模块目前是“旁路参考”，不会直接替代原有规则判断。

## 1. 项目简介（当前实现）

### 1.1 它解决什么问题
TradeMaster 主要解决两类问题：
1. 把分散的行情、指标、信号、模型结果放到同一个系统里，避免人工拼数据。
2. 让技术团队、产品、运营、研究同学看到的是同一套结果，而不是各自口径不同的报表。

### 1.2 适合谁阅读
1. 项目负责人：先看本 README，了解系统边界和整体价值。
2. 产品/运营/研究：重点看“服务实现概览”“web-dashboard README”“chat-service README”。
3. 开发/运维：继续看各服务 README 与 `db/README.md`。

### 1.3 当前目标
1. 打通从历史回填到实时写入的统一数据底座。
2. 提供可解释的指标与规则信号能力，支撑前端和 API 查询。
3. 提供带上下文的 Chatbox 问答能力。
4. 以影子模式运行 ML 验证链路，为后续策略优化提供参考。

### 1.4 当前非目标
1. 不做多交易所统一接入平台，当前默认 Binance Futures UM。
2. 不做自动下单、做市、风控执行。
3. 不做完全黑盒的策略平台。
4. 不覆盖无限币种和无限指标，默认使用白名单配置。

### 1.5 服务实现概览
| 服务 | 白话说明 | 主要输入 | 主要输出 |
|---|---|---|---|
| `pipeline-service` | 把外部行情拉进来，并算出指标 | HuggingFace 历史数据、Binance WS/REST | `candles_1m`、`indicator_values` |
| `signal-service` | 把指标和价格变化翻译成“规则事件” | K 线和指标 | `signal_events`、信号查询/推送 |
| `api-service` | 给前端和其他服务一个统一访问入口 | 数据库视图层和聚合结果 | REST/WS 接口 |
| `chat-service` | 把市场上下文整理后交给 LLM 生成解释 | 用户问题、API 上下文、LLM | 文本回答、审计日志 |
| `ml-validator-service` | 给部分 RSI 信号做机器学习复核 | `signal_events`、指标、K 线 | ML 评分、训练记录、漂移检查 |
| `web-dashboard` | 把系统结果展示成网页，并做同源代理 | API/Chat 服务 | 用户可见的页面与 BFF 接口 |
| `TimescaleDB` | 存放整套系统的数据和运行状态 | 各服务写入 | 查询、监控、回溯的数据基础 |

---

## 2. 系统要求
这一节是运行 TradeMaster 的基础条件。

1. OS：macOS / Linux（推荐）
2. Python：3.12+
3. PostgreSQL：16+
4. TimescaleDB：2.14+
5. 命令行工具：`psql`、`pg_isready`、`npm`

---

## 3. 架构概览
这一节回答“数据从哪里来，最后去哪里”。

### 3.1 服务与端口
| 服务 | 端口 | 作用 |
|---|---:|---|
| TimescaleDB | 5434 | 统一存储历史行情、实时行情、指标、信号、ML 结果、审计数据 |
| pipeline-service | 9101 / 9102 | 回填历史数据、实时采集行情、刷新指标 |
| signal-service | 8002 | 生成规则信号，并提供信号查询与推送 |
| api-service | 8000 | 对前端和内部调用方提供统一 REST/WS |
| chat-service | 8001 | 提供带市场上下文的问答接口 |
| ml-validator-service | 8003 | 训练、验证和展示 ML 影子结果 |
| web-dashboard | 8088 | 网页界面和 BFF 代理层 |

### 3.2 数据流
```text
[HuggingFace 历史数据] -> [pipeline backfill] ----\
                                                    -> [TimescaleDB candles_1m] -> [indicator_engine] -> [indicator_values]
[Binance WS / REST] -> [pipeline live] -----------/
                                                    -> [signal_engine] -> [signal_events]
                                                    -> [ml-validator] -> [signal_ml_*]

[web-dashboard] <-> [api-service] <-> [DB 视图层 / signal / ml]
[chat-service] -> [api-service] -> [DB]
[chat-service] -> [LLM Provider]
```

### 3.3 给非技术读者的理解方式
1. `pipeline-service` 像“数据采集与加工车间”。
2. `signal-service` 像“规则判断器”。
3. `ml-validator-service` 像“第二意见系统”，但当前不直接替代规则结果。
4. `api-service` 和 `web-dashboard` 像“对外窗口”。
5. `chat-service` 像“把系统结果翻译成人话的解释层”。

---

## 4. 快速开始（5 步）
如果你只想把系统跑起来，按这一节做即可。

1. 进入仓库并安装依赖
```bash
cd /Users/kingjason/Desktop/Trademaster
make init
```

2. 配置环境变量
```bash
cp config/.env.example config/.env
chmod 600 config/.env
```

必须修改：
```bash
API_TOKEN=<强随机值>
API_SERVICE_TOKEN=<通常与 API_TOKEN 保持一致>
```

如果要使用 Chatbox，还需要配置 LLM：
```bash
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-5.2
LLM_API_KEY=<YOUR_LLM_API_KEY>
```

仅本地调试时，可选使用开发模板：
```bash
cp config/.env.dev.example config/.env
chmod 600 config/.env
```

3. 初始化数据库结构
```bash
make db-init
```

4. 回填默认目标币种的历史数据
```bash
make backfill \
  SYMBOLS=BTCUSDT,BNBUSDT,ETHUSDT,SOLUSDT \
  START_TS=2020-01-01T00:00:00Z \
  RESUME=1 \
  WITH_INDICATORS=1
```

5. 启动全部服务
```bash
make dev
make status
```

访问地址：
1. API: [http://localhost:8000](http://localhost:8000)
2. Chat: [http://localhost:8001](http://localhost:8001)
3. Signal: [http://localhost:8002/signal/health](http://localhost:8002/signal/health)
4. ML Validator: [http://localhost:8003/ml/health](http://localhost:8003/ml/health)
5. Dashboard: [http://localhost:8088](http://localhost:8088)
6. Pipeline Live Health: [http://localhost:9101/health](http://localhost:9101/health)
7. Pipeline Indicator Health: [http://localhost:9102/health](http://localhost:9102/health)

---

## 5. 关键配置说明
这一节只保留最常用、最影响结果的配置。

### 5.1 全局与安全
| 变量 | 默认值 | 白话说明 |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5434/market_data` | 数据库地址 |
| `DEFAULT_EXCHANGE` | `binance_futures_um` | 当前默认市场来源 |
| `AUTH_ENABLED` | `true` | 是否开启鉴权 |
| `API_TOKEN` | `<CHANGE_ME_STRONG_TOKEN>` | 受保护接口访问令牌 |
| `CORS_ALLOW_ORIGINS` | `http://localhost:8088` | 允许网页访问的来源名单 |

### 5.2 数据采集与指标
| 变量 | 默认值 | 白话说明 |
|---|---|---|
| `SYMBOLS` | `BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT` | 默认跟踪币种 |
| `INTERVALS` | `1m,5m,15m,1h,4h,1d` | 默认计算周期 |
| `BACKFILL_START_TS` | `2020-01-01T00:00:00Z` | 回填起点 |
| `BACKFILL_END_TS` | 空 | 回填终点，空则自动选安全时间 |
| `BACKFILL_WITH_INDICATORS` | `true` | 回填后是否顺带补算历史指标 |
| `WS_RECONNECT_MAX_SECONDS` | `60` | 实时断线后的最大退避时间 |
| `INDICATOR_SCHEDULE_SECONDS` | `60` | 指标刷新频率 |

### 5.3 API、Chat、ML
| 变量 | 默认值 | 白话说明 |
|---|---|---|
| `API_SERVICE_HOST/PORT` | `0.0.0.0 / 8000` | API 服务监听地址 |
| `CHAT_SERVICE_HOST/PORT` | `0.0.0.0 / 8001` | Chat 服务监听地址 |
| `API_SERVICE_BASE_URL` | `http://localhost:8000` | Chat 拉取市场上下文的 API 地址 |
| `API_SERVICE_TOKEN` | `<SAME_AS_API_TOKEN_FOR_INTERNAL_CALLS>` | Chat/BFF 访问 API 时使用的 token |
| `CHAT_SERVICE_BASE_URL` | `http://localhost:8001` | web-dashboard 转发 chat 的地址 |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | LLM 提供商地址 |
| `LLM_MODEL` | `gpt-5.2` | Chatbox 使用的模型名 |
| `LLM_API_KEY` | 空 | LLM 密钥 |
| `ML_DRIFT_CHECK_HOURS` | `6` | ML 漂移检查周期 |
| `ML_DRIFT_PSI_THRESHOLD` | `0.2` | 触发重训的漂移阈值 |

---

## 6. 启动、停止、状态
这一节回答“怎么把整套系统开起来，怎么分组启动”。

### 6.1 一键启动
```bash
make dev
```

默认行为：
1. 先启动 data 组
2. 再启动 edge 组
3. 最后尝试启动 web 组

说明：
1. `make dev` 默认允许前端失败但后端继续运行。
2. 若要求 web 失败时整体返回非零，可用：
```bash
DEVCTL_WEB_REQUIRED=1 make dev
```

### 6.2 分组启动
```bash
make dev-data
make dev-edge
make dev-web
```

组别说明：
1. `data`：负责算数据，不直接对用户提供页面。
2. `edge`：负责对外提供 API、Chat、Signal、ML 查询。
3. `web`：网页界面。

### 6.3 状态与停止
```bash
make status
make stop
```

脚本等价命令：
```bash
./scripts/devctl.sh start
./scripts/devctl.sh status
./scripts/devctl.sh stop
./scripts/devctl.sh restart --group web
```

---

## 7. 历史数据回填
这一节是“补历史数据”的说明。`backfill` 可以理解成把过去缺失的数据补进数据库。

```bash
make backfill \
  SYMBOLS=BTCUSDT,BNBUSDT,ETHUSDT,SOLUSDT \
  START_TS=2020-01-01T00:00:00Z \
  RESUME=1 \
  WITH_INDICATORS=1
```

你需要知道的要点：
1. 当前默认只支持 4 个目标币种：`BTCUSDT,BNBUSDT,ETHUSDT,SOLUSDT`。
2. `RESUME=1` 表示中断后从断点续跑，而不是全量重来。
3. `WITH_INDICATORS=1` 表示补完原始 K 线后，再补历史指标，方便 signal / ML 直接使用。

---

## 8. WebSocket 实时采集
这一节是“怎么持续写入最新行情”。WS 可以理解成实时推送通道。

```bash
make live
```

确认是否持续写入：
```bash
psql "$DATABASE_URL" -c "SELECT max(bucket_ts) FROM market_data.candles_1m WHERE symbol='BTCUSDT';"
```

如果你看到最新时间持续前进，说明实时采集正常。

---

## 9. 指标计算与刷新
这一节是“怎么把原始价格变成 RSI、MACD、EMA 等分析结果”。

一次性刷新：
```bash
make indicators-once SYMBOLS=BTCUSDT,ETHUSDT INTERVALS=1m,1h
```

循环刷新：
```bash
make indicators-loop
```

当前默认指标包括：
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

## 10. 信号计算与刷新
这一节是“系统怎样把指标变化转换成事件”。

一次性运行：
```bash
make signal-once SYMBOLS=BTCUSDT,ETHUSDT INTERVALS=1m,1h
```

循环运行：
```bash
make signal-loop
```

启动对外 signal 服务：
```bash
make signal
```

需要理解的术语：
1. `rule-based`：按明确规则判断，不是黑盒模型。
2. `cooldown`：同类信号短时间内不重复触发，避免刷屏。
3. `WS`：把新信号实时推给前端或订阅方。

---

## 11. API 与实时接口
这一节是“其他系统和前端怎么读取结果”。

### 11.1 鉴权边界
| 服务 | 公开路径 | 需要 `X-API-Token` 的路径 |
|---|---|---|
| `api-service` | `/api/health`、`/docs`、`/openapi.json`、`/redoc` | 其他 `/api/*` 与 `/ws/*` |
| `signal-service` | `/signal/health`、文档路径 | 其他 `/signal/*` 与 `/ws/signal` |
| `ml-validator-service` | `/ml/health`、文档路径 | 其他 `/ml/*` |

```bash
export API_TOKEN='<CHANGE_ME_STRONG_TOKEN>'
```

### 11.2 最常用接口示例
健康检查：
```bash
curl http://localhost:8000/api/health
```

支持币种：
```bash
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/futures/supported-coins"
```

指标列表：
```bash
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/indicator/list"
```

Signal Flow 初始化窗口：
```bash
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/signal/events/latest?limit=60"
```

ML 摘要：
```bash
curl -H "X-API-Token: $API_TOKEN" \
  "http://localhost:8000/api/ml/validation/summary?window=7d"
```

### 11.3 WebSocket 示例
行情推送：
```bash
wscat -H "X-API-Token: $API_TOKEN" \
  -c "ws://localhost:8000/ws/market?symbol=BTCUSDT&interval=1m"
```

信号推送：
```bash
wscat -H "X-API-Token: $API_TOKEN" \
  -c "ws://localhost:8000/ws/signal?symbol=BTCUSDT&interval=1h"
```

---

## 12. chat-service 使用说明
这一节是“怎么让 Chatbox 解释当前市场状态”。

### 12.1 它是怎么工作的
1. 用户输入问题。
2. `chat-service` 先去 `api-service` 拉取相关行情、指标、市场上下文。
3. 然后把这些上下文交给 LLM。
4. 最后返回一句更容易理解的解释，并写审计日志。

### 12.2 LLM 配置方法
在 `config/.env` 中设置：
```bash
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-5.2
LLM_API_KEY=<YOUR_LLM_API_KEY>

API_SERVICE_BASE_URL=http://localhost:8000
AUTH_ENABLED=true
API_TOKEN=<CHANGE_ME_STRONG_TOKEN>
API_SERVICE_TOKEN=<SAME_AS_API_TOKEN_FOR_INTERNAL_CALLS>
```

验证：
```bash
make chat
curl -fsS http://localhost:8001/health | jq .
curl -fsS -X POST "http://localhost:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"分析一下 BTCUSDT 1h 的走势"}' | jq .
```

补充说明：
1. `LLM_API_KEY` 为空时，服务会回退读取 `OPENAI_API_KEY`。
2. 服务优先尝试 `Responses API`，失败后回退 `Chat Completions`。

---

## 13. 文档导航
这一节按“读者角色”组织文档，而不是按目录组织。

### 13.1 如果你想看整体
1. [README.md](./README.md)
2. [服务依赖矩阵](./docs/service_dependency_matrix.md)

### 13.2 如果你想看前端和用户体验
1. [web-dashboard README](./services-preview/web-dashboard/README.md)
2. [chat-service README](./services/chat-service/README.md)

### 13.3 如果你想看数据与底层
1. [pipeline-service README](./services/pipeline-service/README.md)
2. [db/README.md](./db/README.md)
3. [DB 兼容策略](./docs/db_compatibility_policy.md)

### 13.4 如果你想看接口与信号
1. [api-service README](./services/api-service/README.md)
2. [signal-service README](./services/signal-service/README.md)
3. [ml-validator-service README](./services/ml-validator-service/README.md)

---

## 14. 验收标准
1. `make dev` 启动后，`api/chat/pipeline/signal/ml-validator/dashboard` 都可访问。
2. 回填后能查到历史数据，重复回填不会失控增量。
3. 实时行情写入持续前进。
4. 指标引擎刷新后 `indicator_values` 有新记录。
5. 信号引擎刷新后 `signal_events` 有新记录。
6. 前端能看到行情、指标、信号和 ML 摘要。
7. Chatbox 能返回带上下文的解释。
8. `make security-check` 成功，并生成 `logs/security_report.md`。

---

## 15. Troubleshooting（常见问题）
| 问题 | 现象 | 优先处理 |
|---|---|---|
| 数据库连不上 | `connection refused` | 检查 `DATABASE_URL`、5434 端口、数据库是否启动 |
| 历史数据没补进来 | 回填命令退出或卡住 | 看 `backfill_state`、日志、网络 |
| 实时数据不更新 | 最新分钟时间停住 | 检查 WS、REST fallback、网络 |
| 指标不更新 | `indicator_values` 长时间不变 | 看 `indicator_state` 和 pipeline 状态 |
| 信号为空 | 前端没有事件 | 看 `signal_rule_configs`、signal engine 心跳 |
| Chat 没有上下文 | 回答泛化 | 检查 `API_SERVICE_BASE_URL` 与 `API_SERVICE_TOKEN` |
| 前端打不开 | 8088 无响应 | 单独执行 `make dev-web` 或看 web-dashboard 日志 |

---

## 16. 安全注意事项
1. 不要提交真实 `.env`。
2. `config/.env` 权限应为 `600`。
3. 生产环境必须开启鉴权和 CORS 白名单。
4. 所有对外文档示例都默认以 `AUTH_ENABLED=true` 为准。
5. Chat 输出仅供分析参考，不构成投资建议。
