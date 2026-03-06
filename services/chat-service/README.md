# chat-service 运维说明

## 一句话说明
`chat-service` 是 TradeMaster 的解释层：它会先读取市场上下文，再调用 LLM，把系统数据翻译成更容易理解的自然语言回答。

## 它在系统里的位置
它不是原始数据生产者，而是“解释器”。前端 Chatbox 和其他问答入口通过它把复杂市场数据转成一句一句的回答。

## 非技术读者可理解的输入 / 输出
- 输入：用户问题、市场上下文、LLM 配置。
- 输出：文本回答、请求审计记录。
- 你可以把它理解成“把数据库里的分析结果说成人话”。

## 服务职责
- 提供 `POST /chat` 对话接口与 `GET /health` 健康接口。
- 做输入校验和基础注入防护。
- 从 `api-service` 拉取行情、指标、市场上下文。
- 调用 LLM Provider，优先 Responses API，失败回退 Chat Completions。
- 写审计日志到文件，数据库可用时同时落库到 `audit.chat_requests`。

## 依赖与端口
- Python 3.12+
- 默认端口：`8001`
- 上游依赖：
  - `api-service`
  - LLM Provider（OpenAI-compatible）
- 可选依赖：数据库（用于审计落库）

## 启动、停止、状态
全链路托管：

```bash
make dev
make status
make stop
```

单独启动：

```bash
make chat
```

直接运行（调试）：

```bash
cd services/chat-service
.venv/bin/python -m src
```

## 关键配置
来自 `config/.env`：

- `CHAT_SERVICE_HOST/PORT`
- `CORS_ALLOW_ORIGINS`
- `CHAT_RATE_LIMIT_PER_MINUTE`
- `CHAT_MAX_CONCURRENCY_PER_IP`
- `CHAT_MAX_INPUT_CHARS`
- `CHAT_MAX_TURNS`
- `API_SERVICE_BASE_URL`
- `API_SERVICE_TOKEN`
- `LLM_PROVIDER`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `LLM_API_KEY`
- `LLM_TIMEOUT_SECONDS`
- `LLM_MAX_OUTPUT_CHARS`
- `CHAT_TEMPERATURE`
- `CHAT_AUDIT_LOG`
- `DATABASE_URL`

## Chatbox LLM 配置步骤

### 1) 配置 LLM 连接参数
在仓库根目录编辑 `config/.env`：

```bash
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-5.2
LLM_API_KEY=<YOUR_LLM_API_KEY>

CHAT_TEMPERATURE=0.2
LLM_TIMEOUT_SECONDS=30
LLM_MAX_OUTPUT_CHARS=4000
```

说明：
- `LLM_API_KEY` 为空时会回退读取 `OPENAI_API_KEY`。
- 服务会优先调用 `POST /responses`，失败后自动回退 `POST /chat/completions`。

### 2) 配置上下文 API 访问
`chat-service` 要先访问 `api-service`，因此还需要：

```bash
AUTH_ENABLED=true
API_TOKEN=<CHANGE_ME_STRONG_TOKEN>
API_SERVICE_TOKEN=<SAME_AS_API_TOKEN_FOR_INTERNAL_CALLS>
API_SERVICE_BASE_URL=http://localhost:8000
```

当 `AUTH_ENABLED=true` 时，`API_SERVICE_TOKEN` 应与 `API_TOKEN` 保持一致。

### 3) 启动并验证
```bash
make chat
curl -fsS http://localhost:8001/health | jq .
curl -fsS -X POST "http://localhost:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"分析一下 BTCUSDT 1h 的走势"}' | jq .
```

## 健康检查
```bash
curl -fsS http://localhost:8001/health | jq .
```

最小对话请求：

```bash
curl -fsS -X POST "http://localhost:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"分析一下 BTCUSDT 1h 的走势"}' | jq .
```

## 日志与 PID
- 日志：`logs/chat.log`
- 分组启动日志：`logs/edge/chat-service.log`
- 审计文件：`logs/chat_audit.jsonl`
- PID：`run/pids/edge/chat-service.pid`

快速查看：

```bash
tail -n 100 logs/chat.log
tail -n 100 logs/edge/chat-service.log
tail -n 50 logs/chat_audit.jsonl
```

## 常见故障与处理

### 1) LLM Key 缺失或失效
- 现象：返回固定提示或 5xx。
- 先做：检查 `LLM_API_KEY` 是否存在、是否过期。
- 处理：更新 key 后重试。

### 2) 上下文 API 不可达
- 现象：回答泛化，缺少市场细节。
- 先做：`curl $API_SERVICE_BASE_URL/api/health`
- 处理：修复 `api-service` 或 token 配置。

### 3) 限流触发
- 现象：大量 429。
- 先做：检查来源 IP 的请求频率与并发。
- 处理：降低调用频率或调整限流参数。

### 4) 回答缺少上下文
- 现象：系统提示信息不足。
- 先做：请求中显式带上如 `BTCUSDT 1h`。
- 处理：同时检查指标接口和行情接口是否返回正常。

## 日常巡检清单
- 每 5 分钟：检查 `/health`，抽样发 1 条低成本请求。
- 每小时：看 `chat_audit.jsonl` 是否持续写入，错误是否异常升高。
- 每日：确认 `LLM_MODEL`、`LLM_BASE_URL` 未被误改。

## 安全提醒
- 禁止把真实 `LLM_API_KEY` 写进仓库。
- chat 输出只用于分析解释，不构成投资建议。

## 与其他服务依赖关系
- 强依赖：`api-service`
- 间接依赖：`pipeline-service`
- 典型使用方：`web-dashboard`
