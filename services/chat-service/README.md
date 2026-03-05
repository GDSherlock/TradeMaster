# chat-service 运维说明

## 服务职责
- 提供对话接口（`POST /chat`）与健康接口（`GET /health`）。
- 执行请求生命周期：
- 输入校验与注入防护（`validate_message`）。
- 通过 `api-service` 构建行情/指标上下文。
- 调用 LLM Provider（Responses API，失败时回退 Chat Completions）。
- 写审计日志到文件和 DB（`audit.chat_requests`）。

## 依赖与端口
- Python 3.12+。
- 端口：`CHAT_SERVICE_PORT`（默认 `8001`）。
- 上游依赖：
- `api-service`（上下文拉取）。
- LLM Provider（例如 OpenAI Compatible 接口）。
- 可选依赖：数据库（用于审计落库，`DATABASE_URL` 为空时只写文件）。

## 启动/停止/状态

在仓库根目录执行。

全链路托管（推荐）：

```bash
make dev
make status
make stop
```

仅启动 chat：

```bash
make chat
```

直接运行（调试）：

```bash
cd services/chat-service
.venv/bin/python -m src
```

预期结果：
- `http://localhost:8001/health` 返回 `healthy`。

异常时下一步动作：
- 查看 `logs/chat.log`。
- 检查 `API_SERVICE_BASE_URL` 与 `LLM_*` 配置。

## 关键配置

来自 `config/.env`：

- `CHAT_SERVICE_HOST/PORT`：服务监听地址。
- `CORS_ALLOW_ORIGINS`：逗号分隔 CORS 白名单（默认 `http://localhost:8088`）。
- `CHAT_RATE_LIMIT_PER_MINUTE`：每 IP 每分钟请求配额。
- `CHAT_MAX_CONCURRENCY_PER_IP`：每 IP 最大并发。
- `CHAT_MAX_INPUT_CHARS`：输入长度限制。
- `CHAT_MAX_TURNS`：会话内历史轮次保留上限。
- `API_SERVICE_BASE_URL`：上下文 API 地址。
- `API_SERVICE_TOKEN`：调用受保护 API 时的 token（当 `AUTH_ENABLED=true` 时应与 `API_TOKEN` 保持一致）。
- `LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`。
- `LLM_TIMEOUT_SECONDS`、`LLM_MAX_OUTPUT_CHARS`、`CHAT_TEMPERATURE`。
- `CHAT_AUDIT_LOG`：本地审计日志路径（默认 `logs/chat_audit.jsonl`）。
- `DATABASE_URL`：审计落库连接串（为空则不落库）。

## 健康检查

健康接口：

```bash
curl -fsS http://localhost:8001/health | jq .
```

最小对话请求：

```bash
curl -fsS -X POST "http://localhost:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"分析一下 BTCUSDT 1h 的走势"}' | jq .
```

预期结果：
- `/health` 返回模型名与时间戳。
- `/chat` 返回 `reply/session_id/model/timestamp_ms`。

异常时下一步动作：
- 若返回 429：检查限流配置与来源 IP 流量。
- 若返回 `LLM_API_KEY is not configured.`：补齐 `LLM_API_KEY`。
- 若上下文为空：检查 `api-service` 是否可达及鉴权 token 是否匹配。

## 日志与 PID
- 进程日志：`logs/chat.log`（由 `scripts/devctl.sh` 托管时）。
- 审计文件：`logs/chat_audit.jsonl`（或 `CHAT_AUDIT_LOG` 指定路径）。
- PID：`run/pids/chat.pid`。

快速查看：

```bash
tail -n 100 logs/chat.log
tail -n 50 logs/chat_audit.jsonl
cat run/pids/chat.pid
```

## 常见故障与处理

### 1) LLM Key 缺失或失效
- 现象：返回固定提示或 5xx。
- 先做：检查 `LLM_API_KEY` 是否存在、是否过期。
- 处理：更新 key 后重试最小请求。

### 2) 上游 API 超时/不可达
- 现象：上下文缺失，回答泛化。
- 先做：`curl $API_SERVICE_BASE_URL/api/health` 检查可达性。
- 处理：修复 api-service 后再验证 chat。

### 3) 限流触发
- 现象：短时间内大量 429。
- 先做：确认来源 IP 请求速率与并发。
- 处理：降低调用频率，或按容量调整 `CHAT_RATE_LIMIT_PER_MINUTE`、`CHAT_MAX_CONCURRENCY_PER_IP`。

### 4) 回答缺少行情上下文
- 现象：回答中提示上下文不足。
- 先做：检查请求内容是否含 symbol/interval，或是否能被默认提取。
- 处理：请求里显式写出如 `BTCUSDT 1h`，并检查 API 指标接口返回是否正常。

## 日常巡检清单
- 每 5 分钟：
- `curl /health` 确认状态正常。
- 抽样发一条低成本 `POST /chat` 请求。
- 每小时：
- 检查 `audit.chat_requests` 错误比例与延迟分布。
- 检查 `chat_audit.jsonl` 是否持续写入。
- 每日：
- 检查 `LLM_MODEL`、`LLM_BASE_URL` 配置是否被非预期修改。

## 与其他服务依赖关系
- 强依赖 `api-service` 作为上下文数据入口。
- 间接依赖 `pipeline-service` 产生实时行情与指标数据。
- 前端 `web-dashboard` 可将用户交互导向 chat-service。
