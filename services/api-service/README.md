# api-service 运维说明

## 一句话说明
`api-service` 是 TradeMaster 的统一对外入口，负责把数据库里的行情、指标、信号、ML 结果整理成前端和其他服务能直接使用的接口。

## 它在系统里的位置
它位于“数据服务层”与“用户界面层”之间。前端、Chatbox、外部调用方通常不直接连数据库，而是通过这个服务获取数据。

## 非技术读者可理解的输入 / 输出
- 输入：数据库中的行情、指标、信号和 ML 结果。
- 输出：标准化的 REST 和 WebSocket 接口。
- 你可以把它理解成“系统总接口台”。

## 服务职责
- 提供 REST API：行情、指标、市场统计、信号、ML 摘要。
- 提供实时推送：`/ws/market`、`/ws/signal`。
- 负责基础鉴权和 IP 限流。
- 从数据库视图层读数据，对调用方隐藏内部表结构变化。

核心路由分组：
- `health`：`/api/health`
- `futures`：`/api/futures/*`
- `indicator`：`/api/indicator/*`
- `markets`：`/api/markets/*`
- `signal`：`/api/signal/*`
- `ml`：`/api/ml/*`

## 依赖与端口
- Python 3.12+
- TimescaleDB / PostgreSQL（读数据）
- 默认端口：`8000`
- 上游数据主要来自 `pipeline-service`、`signal-service`、`ml-validator-service`

## 启动、停止、状态
全链路托管：

```bash
make dev
make status
make stop
```

单独启动 API：

```bash
make api
```

直接运行（调试）：

```bash
cd services/api-service
.venv/bin/python -m src
```

## 关键配置
来自 `config/.env`：

- `API_SERVICE_HOST/PORT`
- `DATABASE_URL`
- `DEFAULT_EXCHANGE`
- `AUTH_ENABLED`
- `API_TOKEN`
- `CORS_ALLOW_ORIGINS`
- `API_RATE_LIMIT_PER_MINUTE`
- `API_RATE_LIMIT_BURST`

白话解释：
- `AUTH_ENABLED=true`：受保护接口需要 token。
- `API_TOKEN`：访问接口的“通行证”。
- `CORS_ALLOW_ORIGINS`：允许哪些网页来源访问接口。

## 公开与受保护接口
- 公开：`/api/health`、`/docs`、`/openapi.json`、`/redoc`
- 受保护：其余 `/api/*` 与 `/ws/*`

启用鉴权时：

```bash
export API_TOKEN='<CHANGE_ME_STRONG_TOKEN>'
```

## 健康检查
```bash
curl -fsS http://localhost:8000/api/health | jq .
curl -fsS -H "X-API-Token: $API_TOKEN" "http://localhost:8000/api/futures/supported-coins" | jq .
curl -fsS -H "X-API-Token: $API_TOKEN" "http://localhost:8000/api/indicator/list" | jq .
```

WS 连通性说明：
- `/ws/market`：实时行情推送。
- `/ws/signal`：实时信号推送。
- 若 `AUTH_ENABLED=true`，需要使用 `X-API-Token` 或 query token。

## 最常用接口
- `GET /api/futures/supported-coins`：当前系统有哪些币种可查。
- `GET /api/futures/ohlc/history`：历史 K 线。
- `GET /api/indicator/list`：支持哪些指标。
- `GET /api/indicator/data`：某个指标的具体结果。
- `GET /api/signal/events/latest`：Signal Flow 前端初始化窗口。
- `GET /api/ml/validation/summary`：ML 验证摘要。
- `GET /api/ml/validation/candidates`：ML 候选事件列表。

## 日志与 PID
- 日志：`logs/api.log`
- 分组启动日志：`logs/edge/api-service.log`
- PID：`run/pids/edge/api-service.pid`

快速查看：

```bash
tail -n 100 logs/api.log
tail -n 100 logs/edge/api-service.log
```

## 常见故障与处理

### 1) 401 未授权
- 现象：接口返回 `40101`。
- 先做：确认 `AUTH_ENABLED` 与 `X-API-Token` 是否匹配。
- 处理：统一 API 与调用方的 token 配置。

### 2) 429 限流
- 现象：请求量高时返回 429。
- 先做：确认来源 IP 与调用频率。
- 处理：降低频率，或按容量调整限流参数。

### 3) 500 内部错误
- 现象：接口返回 `50002`。
- 先做：查看 `logs/api.log`。
- 处理：优先排查数据库连通、数据缺失、参数错误。

### 4) WS 无持续数据
- 现象：连接成功但很久没有新消息。
- 先做：确认上游是否仍在写库。
- 处理：先恢复 `pipeline-service` / `signal-service`，再重测。

## 日常巡检清单
- 每 1-5 分钟：访问 `/api/health`，抽查 1-2 个核心接口。
- 每小时：看 `401/429/500` 的比例。
- 每日：复核鉴权、CORS 与前端代理配置是否符合环境要求。

## 安全提醒
- 不要把 `API_TOKEN` 放到浏览器公开变量里。
- 所有对外错误都应保持最小化，详细异常只看内部日志。

## 与其他服务依赖关系
- 上游：`pipeline-service`、`signal-service`、`ml-validator-service`
- 下游：`web-dashboard`、`chat-service`
