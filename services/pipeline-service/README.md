# pipeline-service 运维说明

## 服务职责
- 负责历史回填（HuggingFace 数据入库）。
- 负责实时流采集（Binance WebSocket + REST gap fill）。
- 负责指标增量计算与刷新。
- 对外提供健康与基础指标接口（`/health`、`/metrics`）。

运行模式：
- `backfill`：仅历史回填。
- `live`：仅实时采集。
- `indicator`：仅指标刷新（支持 `--once`）。
- `all`：启动时先回填，再并行实时采集与指标调度。

## 依赖与端口
- Python 3.12+。
- TimescaleDB/PostgreSQL（`DATABASE_URL`）。
- 端口：`PIPELINE_SERVICE_PORT`（默认 `9101`，健康服务）。
- 外部依赖：`wss://fstream.binance.com/stream`、Binance REST、HuggingFace 数据集。

## 启动/停止/状态

在仓库根目录执行。

全链路托管（推荐）：

```bash
make dev
make status
make stop
```

仅 pipeline 相关命令：

```bash
make backfill SYMBOLS=BTCUSDT,ETHUSDT DAYS=180 RESUME=1
make live SYMBOLS=BTCUSDT,ETHUSDT
make indicators-once SYMBOLS=BTCUSDT INTERVALS=1m,1h
make indicators-loop SYMBOLS=BTCUSDT,ETHUSDT INTERVALS=1m,5m,1h
```

直接运行（调试）：

```bash
cd services/pipeline-service
.venv/bin/python -m src backfill --symbols "BTCUSDT,ETHUSDT" --days 180 --resume 1
.venv/bin/python -m src live --symbols "BTCUSDT,ETHUSDT"
.venv/bin/python -m src indicator --symbols "BTCUSDT,ETHUSDT" --intervals "1m,1h"
.venv/bin/python -m src all --symbols "BTCUSDT,ETHUSDT" --intervals "1m,1h"
```

预期结果：
- 进程存活，且 `make status` 显示 pipeline 为 `[ok]`。

异常时下一步动作：
- 查看 `logs/pipeline.log`。
- 检查 `DATABASE_URL` 与外网连通性（Binance/HF）。

## 关键配置

来自 `config/.env`：

- `DATABASE_URL`：数据库连接串。
- `DEFAULT_EXCHANGE`：交易所标识（默认 `binance_futures_um`）。
- `PIPELINE_SERVICE_HOST/PORT`：健康服务监听地址。
- `SYMBOLS`：采集交易对。
- `INTERVALS`：指标周期。
- `BACKFILL_DAYS`：默认回填天数。
- `BACKFILL_CHUNK_ROWS`：回填批量写入大小。
- `HF_DATASET`、`HF_CANDLES_FILE`：历史数据源配置。
- `WS_URL`、`WS_RECONNECT_MAX_SECONDS`、`WS_FLUSH_SECONDS`：实时流参数。
- `REST_FALLBACK_INTERVAL_SECONDS`：REST 补洞周期。
- `INDICATOR_SCHEDULE_SECONDS`：指标调度周期。

## 健康检查

```bash
curl -fsS http://localhost:9101/health | jq .
curl -fsS http://localhost:9101/metrics | jq .
```

预期结果：
- `/health` 返回 `status=healthy`，`components` 中 `pipeline/live_ws/indicator_engine` 的 `last_seen_at` 持续刷新。
- `/metrics` 返回 `candles_total`、`indicators_total` 为递增或稳定合理值。

异常时下一步动作：
- 若 `/health` 不通：检查 pipeline 进程与端口占用。
- 若组件心跳滞后：结合日志定位（采集链路、调度、DB）。

## 日志与 PID
- 日志：`logs/pipeline.log`。
- PID：`run/pids/pipeline.pid`。

快速查看：

```bash
tail -n 100 logs/pipeline.log
cat run/pids/pipeline.pid
```

## 常见故障与处理

### 1) WebSocket 断连频繁
- 现象：日志反复出现 reconnect 警告。
- 先做：检查公网网络与 Binance 连通，确认 `WS_URL` 可访问。
- 处理：适当增大 `WS_RECONNECT_MAX_SECONDS`；观察 REST fallback 是否能补数据。

### 2) 回填中断
- 现象：`backfill` 退出或进度停滞。
- 先做：查询 `market_data.backfill_state` 的 `status/error_message`。
- 处理：修复后使用 `RESUME=1` 继续。

### 3) 指标不更新
- 现象：`indicator_values.ts` 不前进或 `stale` 升高。
- 先做：检查 `INDICATOR_SCHEDULE_SECONDS` 与 `indicator_state`。
- 处理：先执行 `make indicators-once` 验证计算链路，再恢复 loop。

### 4) heartbeat 不刷新
- 现象：`ingest_heartbeat.last_seen_at` 长时间不更新。
- 先做：确认 pipeline 进程仍存活。
- 处理：重启 pipeline，并检查 DB 写权限与连接池状态。

## 日常巡检清单
- 每 1-5 分钟：
- 检查 `http://localhost:9101/health` 是否可达。
- 核查 `live_ws` 心跳 lag 是否持续增大。
- 每小时：
- 检查 `candles_1m` 最新时间是否前进。
- 检查 `indicator_values` 最新 `ts` 与 `stale` 比例。
- 每日：
- 检查 `backfill_state` 是否存在长期 error。
- 复核日志中异常峰值时段并做复盘。

## 与其他服务依赖关系
- 上游依赖：HuggingFace、Binance WS/REST、TimescaleDB。
- 下游依赖：`api-service` 读取其写入的行情与指标数据。
- `chat-service` 通过 `api-service` 间接消费 pipeline 数据。
- `web-dashboard` 通过 API 展示 pipeline 产出的数据。
