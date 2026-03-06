# 数据库说明与查询手册

这份文档同时服务两类读者：
1. 非技术读者：先了解数据库在系统里的作用，以及主要表分别代表什么。
2. 技术读者：继续使用后面的 SQL 查询、时效性检查和巡检动作。

## 一句话说明
数据库是 TradeMaster 的“事实底座”，所有行情、指标、信号、ML 结果和审计信息最终都落在这里。

## 它在系统里的位置
- `pipeline-service` 写入行情和指标
- `signal-service` 写入规则信号
- `ml-validator-service` 写入 ML 评分和训练记录
- `chat-service` 可写入审计记录
- `api-service` 和前端主要从这里读取结果

## 非技术读者可理解的输入 / 输出
- 输入：各服务持续写入的数据
- 输出：给 API、前端、排障和回溯分析使用的统一数据源
- 可以把它理解成“系统唯一可信的数据账本”

## 1. 数据模型总览

### 1.1 主数据表
- `market_data.candles_1m`
  - 白话说明：最原始的分钟级行情
  - 谁在用：指标、信号、ML、图表
- `market_data.indicator_values`
  - 白话说明：系统算出来的技术指标结果
  - 谁在用：signal、api、chat、ml
- `market_data.signal_events`
  - 白话说明：规则引擎判断出的事件记录
  - 谁在用：前端、api、ml
- `market_data.signal_rule_configs`
  - 白话说明：规则开关和参数配置
  - 谁在用：signal-service

### 1.2 状态表
- `market_data.backfill_state`：历史回填进行到哪里、是否中断、写了多少行
- `market_data.indicator_state`：每个币种和周期的指标处理进度
- `market_data.ingest_heartbeat`：各组件最近一次“我还活着”的时间
- `market_data.signal_state`：规则引擎当前状态和 cooldown 状态

### 1.3 审计表
- `audit.chat_requests`
  - 白话说明：记录 Chatbox 的请求结果、延迟、错误

### 1.4 主键与常用过滤列
- `candles_1m` 主键：`(exchange, symbol, bucket_ts)`
- `indicator_values` 主键：`(exchange, symbol, interval, indicator, ts)`
- `signal_events` 主键：`id`

查询建议：
- 看行情优先带 `exchange + symbol`
- 看指标优先带 `symbol + interval + indicator`
- 看时效性优先看时间列 `bucket_ts` 或 `ts`

## 2. 如何连接数据库
在仓库根目录执行：

```bash
source config/.env
psql "$DATABASE_URL"
```

如果只想试一条命令：

```bash
source config/.env
psql "$DATABASE_URL" -c "SELECT now();"
```

## 3. 常用查询清单
这一节是面向运维和排障的实用查询。

### 3.1 查询某交易对最新 K 线时间
适用场景：
- 怀疑实时数据停了
- 想确认某个币种有没有新行情

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

看结果时关注：
- `latest_bucket_ts` 是否接近当前时间
- 是否所有目标 symbol 都有结果

### 3.2 查询指标最新记录与 stale 状态
适用场景：
- 想知道指标有没有算出来
- 怀疑指标已经滞后

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

看结果时关注：
- `latest_ts` 是否还在推进
- `any_stale` 是否异常变多

### 3.3 查询回填断点状态
适用场景：
- 回填被打断后，想看能否续跑
- 想知道已经处理到哪个时间段

```sql
SELECT
  source,
  symbol,
  interval,
  last_ts,
  scan_chunk_index,
  requested_start_ts,
  requested_end_ts,
  rows_written,
  dataset_revision,
  status,
  error_message,
  updated_at
FROM market_data.backfill_state
ORDER BY updated_at DESC
LIMIT 200;
```

看结果时关注：
- `status`
- `updated_at`
- `error_message`
- `rows_written`

### 3.4 查询 candle retention 策略
适用场景：
- 想确认历史数据会保留多久

```sql
SELECT hypertable_name, drop_after
FROM timescaledb_information.drop_chunks_policies
WHERE hypertable_schema = 'market_data'
  AND hypertable_name = 'candles_1m';
```

### 3.5 查询组件心跳
适用场景：
- 怀疑服务还活着但其实不工作了

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

看结果时关注：
- `lag_seconds` 是否持续扩大
- `pipeline`、`live_ws`、`indicator_engine` 是否都在更新

### 3.6 查询 chat 审计最近请求与错误分布
适用场景：
- Chatbox 回答不稳定
- 想看错误是否集中在某个时间段

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
白话解释：
- `lag = now() - latest_ts`
- 如果 lag 超过 2 倍周期，就可以认为这个数据明显滞后

### 4.1 K 线时效性
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

### 4.2 指标时效性
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

### 4.3 K 线 + 心跳联合检查
适用场景：
- 想快速判断是“数据没写进来”还是“服务整体停了”

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

## 5. 运维巡检节奏
- 分钟级：看 K 线最新时间、心跳 lag
- 小时级：看指标是否滞后、`stale` 是否升高
- 日级：看回填异常、审计错误趋势、数据保留策略

## 6. 异常动作矩阵
| 现象 | 常见原因 | 优先动作 |
|---|---|---|
| candles 滞后 | WS 断连、写库失败 | 查 `ingest_heartbeat` 与 pipeline 日志 |
| indicator 滞后 | 调度未跑、上游行情停了 | 查 `indicator_state` 与 pipeline 状态 |
| signal 为空 | 规则未启用、指标缺失 | 查 `signal_rule_configs`、`indicator_values` |
| chat 审计异常 | LLM 或上游 API 不稳定 | 查 `audit.chat_requests` 与 chat 日志 |

## 7. 与其他服务依赖关系
- `pipeline-service`：写入原始行情和指标
- `signal-service`：写入信号事件
- `ml-validator-service`：写入 ML 运行结果
- `chat-service`：写入审计日志
- `api-service` / `web-dashboard`：读取数据库结果

## 安全提醒
- 数据库是全链路共享底座，排障前先确认连接的不是错误环境。
- 查询结果可能包含业务敏感信息，分享截图前先脱敏。
