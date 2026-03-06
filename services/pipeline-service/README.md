# pipeline-service 运维说明

## 一句话说明
`pipeline-service` 是 TradeMaster 的“数据工厂”：负责把外部市场数据拉进来，再加工成后续服务要用的指标。

## 它在系统里的位置
它位于整条链路最上游。没有它，后面的 `signal-service`、`api-service`、`ml-validator-service`、`chat-service` 和前端都拿不到新数据。

## 非技术读者可理解的输入 / 输出
- 输入：历史行情文件、交易所实时行情、少量 REST 补洞请求。
- 输出：数据库里的原始 K 线和技术指标。
- 你可以把它理解成“原料进厂 -> 加工 -> 产出标准化数据”。

## 服务职责
- 历史回填：把过去缺失的行情补进数据库。
- 实时采集：持续订阅最新价格变动。
- 指标计算：把原始价格计算成 RSI、MACD、EMA 等指标。
- 健康输出：对外暴露 `/health`、`/metrics` 方便巡检。

运行模式：
- `backfill`：只补历史数据。
- `live`：只采集实时数据。
- `indicator`：只刷新指标。
- `all`：先尝试回填，再同时跑实时采集和指标刷新。

## 依赖与端口
- Python 3.12+
- TimescaleDB / PostgreSQL（`DATABASE_URL`）
- 默认健康端口：`9101`
- 指标循环默认健康端口：`9102`
- 外部依赖：HuggingFace 数据集、Binance WS / REST

## 启动、停止、状态
如果你只想让整套系统跑起来，通常不单独启动这个服务，而是执行：

```bash
make dev
make status
make stop
```

如果你只想操作数据链路：

```bash
make backfill \
  SYMBOLS=BTCUSDT,BNBUSDT,ETHUSDT,SOLUSDT \
  START_TS=2020-01-01T00:00:00Z \
  RESUME=1 \
  WITH_INDICATORS=1

make live SYMBOLS=BTCUSDT,ETHUSDT
make indicators-once SYMBOLS=BTCUSDT INTERVALS=1m,1h
make indicators-loop SYMBOLS=BTCUSDT,ETHUSDT INTERVALS=1m,5m,1h
```

直接运行（调试）：

```bash
cd services/pipeline-service
.venv/bin/python -m src backfill \
  --symbols "BTCUSDT,BNBUSDT,ETHUSDT,SOLUSDT" \
  --start-ts "2020-01-01T00:00:00Z" \
  --resume 1 \
  --with-indicators 1
.venv/bin/python -m src live --symbols "BTCUSDT,ETHUSDT"
.venv/bin/python -m src indicator --symbols "BTCUSDT,ETHUSDT" --intervals "1m,1h"
```

## 关键配置
来自 `config/.env`：

- `DATABASE_URL`：数据库连接串。
- `DEFAULT_EXCHANGE`：默认交易所标识。
- `PIPELINE_SERVICE_HOST/PORT`：健康检查监听地址。
- `SYMBOLS`：默认处理的币种列表。
- `INTERVALS`：默认计算周期。
- `BACKFILL_START_TS` / `BACKFILL_END_TS`：历史回填的时间范围。
- `BACKFILL_WITH_INDICATORS`：补 K 线后是否顺带补指标。
- `BACKFILL_LIVE_GUARD_MINUTES`：保护最新实时窗口，避免历史数据覆盖实时数据。
- `WS_URL`、`WS_RECONNECT_MAX_SECONDS`：实时订阅相关配置。
- `REST_FALLBACK_INTERVAL_SECONDS`：WS 缺口的补洞频率。
- `INDICATOR_SCHEDULE_SECONDS`：指标刷新周期。

术语说明：
- `backfill`：补历史数据。
- `resume`：断点续跑。
- `REST gap fill`：实时 WS 缺口时，用 REST 补回缺失分钟。

## 健康检查
```bash
curl -fsS http://localhost:9101/health | jq .
curl -fsS http://localhost:9101/metrics | jq .
```

你主要关心：
- `/health` 是否能访问。
- `pipeline`、`live_ws`、`indicator_engine` 的心跳是否在刷新。
- `candles_total`、`indicators_total` 是否持续增长。

## 日志与 PID
- 日志：`logs/pipeline.log`
- 分组启动日志：`logs/data/pipeline-live.log`、`logs/data/pipeline-indicator.log`
- PID：`run/pids/` 下的对应文件

快速查看：

```bash
tail -n 100 logs/pipeline.log
tail -n 100 logs/data/pipeline-live.log
tail -n 100 logs/data/pipeline-indicator.log
```

## 常见故障与处理

### 1) WebSocket 断连频繁
- 现象：日志持续出现 reconnect。
- 先做：检查公网、代理、Binance 连通性。
- 处理：观察 REST 补洞是否正常，必要时调大 `WS_RECONNECT_MAX_SECONDS`。

### 2) 回填中断
- 现象：`backfill` 提前退出或长时间卡住。
- 先做：查询 `market_data.backfill_state`。
- 处理：修复后保留 `RESUME=1` 继续运行。

### 3) 指标不更新
- 现象：`indicator_values` 最新时间不前进。
- 先做：检查原始 K 线是否有新数据。
- 处理：先跑一次 `make indicators-once` 验证，再恢复循环任务。

### 4) 心跳不刷新
- 现象：`ingest_heartbeat` 中对应组件长时间不更新。
- 先做：确认进程还活着。
- 处理：重启服务并检查数据库写权限。

## 日常巡检清单
- 每 1-5 分钟：确认 `/health` 可达，最新分钟数据在前进。
- 每小时：检查 `indicator_values` 最新时间与 `stale` 比例。
- 每日：检查 `backfill_state` 是否存在长期错误记录。

## 安全提醒
- 不要把真实凭证写进命令历史或日志截图。
- 回填和实时采集都默认写入数据库，生产环境必须先确认 `DATABASE_URL` 指向正确实例。

## 与其他服务依赖关系
- 上游：HuggingFace、Binance WS / REST、TimescaleDB
- 下游：`api-service`、`signal-service`、`ml-validator-service`
- 间接消费者：`chat-service`、`web-dashboard`
