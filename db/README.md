# DB 查询与数据时效性指南

本指南面向开发与运维，覆盖 `market_data` 与 `audit` 两个 schema 的日常查询、时效性判定与巡检动作。

## 1. 数据模型总览

### 1.1 主数据表
- `market_data.candles_1m`：1 分钟 K 线主表（历史回填 + 实时写入）。
- `market_data.indicator_values`：指标结果表（EMA/MACD/RSI 等）。
- `market_data.signal_events`：规则信号事件表。
- `market_data.signal_rule_configs`：信号规则配置表。

### 1.2 状态表
- `market_data.backfill_state`：历史回填断点与状态。
- `market_data.indicator_state`：指标引擎每个交易对/周期的最近处理时间。
- `market_data.ingest_heartbeat`：各采集组件心跳（`pipeline/live_ws/indicator_engine` 等）。
- `market_data.signal_state`：信号引擎规则状态与 cooldown 状态。

### 1.3 审计表
- `audit.chat_requests`：chat 请求审计（请求量、延迟、错误等）。

### 1.4 主键/索引与推荐过滤列
- `candles_1m` 主键：`(exchange, symbol, bucket_ts)`。
- `indicator_values` 主键：`(exchange, symbol, interval, indicator, ts)`。
- `signal_events` 主键：`id`（bigserial）。
- 推荐过滤列：
- 行情/指标查询优先带 `exchange + symbol`。
- 指标查询带 `interval + indicator`。
- 时间范围查询带 `bucket_ts` 或 `ts`。

## 2. 连接数据库

在仓库根目录执行：

```bash
source config/.env
psql "$DATABASE_URL"
```

单条执行方式：

```bash
source config/.env
psql "$DATABASE_URL" -c "SELECT now();"
```

## 3. 常用查询清单

### 3.1 查询某交易对最新 K 线时间

```sql
SELECT
  exchange,
  symbol,
  MAX(bucket_ts) AS latest_bucket_ts
FROM market_data.candles_1m
WHERE exchange = 'binance_futures_um'
  AND symbol IN ('BTCUSDT', 'ETHUSDT')
GROUP BY exchange, symbol
ORDER BY symbol;
```

预期结果：
- 返回每个 symbol 的最新时间。

异常时下一步：
- 若 `latest_bucket_ts` 为空，先检查是否执行过回填，再检查实时流是否运行。

### 3.2 查询指标最新记录与 stale 状态

```sql
SELECT
  exchange,
  symbol,
  interval,
  indicator,
  MAX(ts) AS latest_ts,
  BOOL_OR(stale) AS any_stale
FROM market_data.indicator_values
WHERE exchange = 'binance_futures_um'
  AND symbol = 'BTCUSDT'
GROUP BY exchange, symbol, interval, indicator
ORDER BY interval, indicator;
```

预期结果：
- 可看到每个周期/指标的最新计算时间与是否出现 stale。

异常时下一步：
- 若 `latest_ts` 停滞，检查 pipeline 指标调度与 `indicator_state`。

### 3.3 查询回填断点状态

```sql
SELECT
  source,
  symbol,
  interval,
  last_ts,
  status,
  error_message,
  updated_at
FROM market_data.backfill_state
ORDER BY updated_at DESC
LIMIT 200;
```

预期结果：
- `status` 常见为 `running` 或 `idle`，失败时应有 `error_message`。

异常时下一步：
- 如果 `updated_at` 长时间不变，优先排查 backfill 任务是否运行。

### 3.4 查询组件心跳

```sql
SELECT
  component,
  status,
  message,
  last_seen_at,
  EXTRACT(EPOCH FROM (now() - last_seen_at))::int AS lag_seconds
FROM market_data.ingest_heartbeat
ORDER BY last_seen_at DESC;
```

预期结果：
- 关键组件（`pipeline`、`live_ws`、`indicator_engine`）应持续刷新 `last_seen_at`。

异常时下一步：
- 若 `lag_seconds` 持续增大，检查对应进程和日志。

### 3.5 查询 chat 审计最近请求与错误分布

最近请求：

```sql
SELECT
  ts,
  request_id,
  session_id,
  status,
  latency_ms,
  model,
  error_message
FROM audit.chat_requests
ORDER BY ts DESC
LIMIT 100;
```

错误分布：

```sql
SELECT
  date_trunc('hour', ts) AS hour_bucket,
  status,
  COUNT(*) AS cnt
FROM audit.chat_requests
WHERE ts >= now() - interval '24 hours'
GROUP BY 1, 2
ORDER BY 1 DESC, 2;
```

## 4. 数据时效性检查（2x 周期阈值）

判定规则：
- `lag = now() - latest_ts`
- 当 `lag > 2 * interval` 判定为 `LAGGING`，否则为 `OK`。

### 4.1 K 线时效性（按 1m 周期，阈值 120 秒）

```sql
WITH latest AS (
  SELECT
    exchange,
    symbol,
    MAX(bucket_ts) AS latest_ts
  FROM market_data.candles_1m
  WHERE exchange = 'binance_futures_um'
    AND symbol IN ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT')
  GROUP BY exchange, symbol
)
SELECT
  exchange,
  symbol,
  latest_ts,
  EXTRACT(EPOCH FROM (now() - latest_ts))::int AS lag_seconds,
  CASE
    WHEN now() - latest_ts > interval '120 seconds' THEN 'LAGGING'
    ELSE 'OK'
  END AS freshness
FROM latest
ORDER BY lag_seconds DESC;
```

### 4.2 指标时效性（各 interval 对应 2x 阈值）

```sql
WITH latest AS (
  SELECT
    exchange,
    symbol,
    interval,
    MAX(ts) AS latest_ts
  FROM market_data.indicator_values
  WHERE exchange = 'binance_futures_um'
    AND symbol IN ('BTCUSDT', 'ETHUSDT')
  GROUP BY exchange, symbol, interval
),
thresholds AS (
  SELECT * FROM (VALUES
    ('1m', 120),
    ('5m', 600),
    ('15m', 1800),
    ('1h', 7200),
    ('4h', 28800),
    ('1d', 172800)
  ) AS t(interval, threshold_seconds)
)
SELECT
  l.exchange,
  l.symbol,
  l.interval,
  l.latest_ts,
  EXTRACT(EPOCH FROM (now() - l.latest_ts))::int AS lag_seconds,
  t.threshold_seconds,
  CASE
    WHEN EXTRACT(EPOCH FROM (now() - l.latest_ts)) > t.threshold_seconds THEN 'LAGGING'
    ELSE 'OK'
  END AS freshness
FROM latest l
JOIN thresholds t USING (interval)
ORDER BY l.symbol, t.threshold_seconds;
```

### 4.3 批量时效检查（K 线 + 心跳联合）

```sql
WITH candle_lag AS (
  SELECT
    symbol,
    MAX(bucket_ts) AS latest_ts,
    EXTRACT(EPOCH FROM (now() - MAX(bucket_ts)))::int AS lag_seconds
  FROM market_data.candles_1m
  WHERE exchange = 'binance_futures_um'
  GROUP BY symbol
),
hb AS (
  SELECT
    component,
    status,
    last_seen_at,
    EXTRACT(EPOCH FROM (now() - last_seen_at))::int AS hb_lag_seconds
  FROM market_data.ingest_heartbeat
)
SELECT
  c.symbol,
  c.latest_ts,
  c.lag_seconds,
  CASE WHEN c.lag_seconds > 120 THEN 'LAGGING' ELSE 'OK' END AS candle_freshness,
  h.component,
  h.status AS heartbeat_status,
  h.hb_lag_seconds
FROM candle_lag c
LEFT JOIN hb h ON h.component = 'live_ws'
ORDER BY c.lag_seconds DESC
LIMIT 100;
```

判定建议：
- 若 `candle_freshness=LAGGING` 且 `hb_lag_seconds` 同时偏大，优先判定采集链路异常。
- 若 heartbeat 正常但数据滞后，优先检查交易对订阅与写库路径。

## 5. 运维巡检节奏

### 5.1 分钟级巡检
- 检查 `candles_1m` 最新时间是否持续前进。
- 检查 `ingest_heartbeat` 中 `live_ws` 和 `pipeline` 的 `lag_seconds`。

### 5.2 小时级巡检
- 检查 `indicator_values` 最新时间与各 interval 滞后状态。
- 检查 `stale=true` 比例是否异常升高。

```sql
SELECT
  interval,
  COUNT(*) FILTER (WHERE stale) AS stale_cnt,
  COUNT(*) AS total_cnt,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE stale) / NULLIF(COUNT(*), 0),
    2
  ) AS stale_ratio_pct
FROM market_data.indicator_values
WHERE ts >= now() - interval '6 hours'
GROUP BY interval
ORDER BY interval;
```

### 5.3 日级巡检
- 检查 `backfill_state` 是否有长期错误状态。
- 检查数据保留窗口（最近 365 天策略）是否符合预期。
- 检查 `audit.chat_requests` 错误率趋势。

## 6. 异常动作矩阵

| 现象 | 可能原因 | 先做什么 | 下一步 |
| --- | --- | --- | --- |
| candles 滞后 | WS 断连、写库失败 | 查 `ingest_heartbeat` 与 pipeline 日志 | 重启 pipeline 并复查 lag |
| indicator 滞后 | 调度未运行、上游行情滞后 | 查 `indicator_state` 与心跳 | 触发 `make indicators-once` 验证 |
| heartbeat 正常但数据停滞 | 订阅交易对异常或过滤逻辑 | 核查 `SYMBOLS` 与写入统计 | 执行 REST fallback 验证写入 |
| chat 审计写入失败 | DB 不可达、权限不足 | 查 `logs/chat_audit.jsonl` 与 DB 连通 | 修复 DB 后回放关键请求 |

## 7. 与其他服务依赖关系
- `pipeline-service` 写入主数据与心跳，DB 是全链路上游数据源。
- `api-service` 直接读取 `market_data` 提供前端接口。
- `chat-service` 依赖 API 获取上下文，并写入 `audit.chat_requests`。
- `web-dashboard` 通过 API/Chat 对外展示，数据时效由 DB + pipeline 决定。
