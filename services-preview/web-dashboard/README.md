# web-dashboard 说明

## 一句话说明
`web-dashboard` 是 TradeMaster 的网页界面，负责把行情、指标、信号、ML 结果和 Chatbox 展示给用户。

## 它在系统里的位置
它位于最外层，直接面向使用者。用户通常不会直接调用后端 API，而是先通过这个网页看到结果。

## 非技术读者可理解的输入 / 输出
- 输入：来自 `api-service` 和 `chat-service` 的数据。
- 输出：浏览器中的页面、图表、信号流和 Chatbox。
- 你可以把它理解成“TradeMaster 的用户操作台”。

## 运行方式
从仓库根目录：

```bash
make init
make dev
make status
```

只启动前端：

```bash
make dev-web
```

或：

```bash
cd services-preview/web-dashboard
./scripts/start.sh run
```

默认地址：`http://localhost:8088`

## 页面行为
- `/`：主页面，展示行情、信号和 Chatbox
- `/app`：为了兼容旧入口，自动跳转到 `/`
- `/ml-validation`：ML 验证面板，展示运行态、候选事件、训练记录、漂移结果

## 用户能看到什么
1. 市场概览：比如涨跌、热门币种、基础趋势
2. 指标与图表：便于快速看当前市场状态
3. Signal Flow：系统最近触发了哪些规则信号
4. Chatbox：用自然语言提问并获得解释
5. ML Validation 页面：查看机器学习模块对信号的辅助判断

## 数据从哪里来
### 实时数据流
- REST bootstrap：`/api/trademaster/signal/events/latest?limit=60`
- WS stream：`ws://<host>:8000/ws/signal?since_id=<max_id>`
- Fallback polling：每 15 秒轮询一次最新事件

### 其他主要数据
- 市场与指标：
  - `/api/trademaster/markets/momentum`
  - `/api/trademaster/futures/ohlc/history`
  - `/api/trademaster/indicator/list`
  - `/api/trademaster/indicator/data`
- Chat：
  - `POST /api/trademaster/chat`
- ML：
  - `/api/trademaster/ml/runtime`
  - `/api/trademaster/ml/validation/summary`
  - `/api/trademaster/ml/validation/candidates`
  - `/api/trademaster/ml/training/runs`
  - `/api/trademaster/ml/drift/latest`

## BFF 与代理说明
前端并不把 token 暴露给浏览器，而是通过同源代理访问后端。

### 默认 REST 入口
- `/api/trademaster/[...path]`
- 只允许 `GET`
- 允许的前缀：`health`、`futures`、`indicator`、`markets`、`signal`、`ml`

### Chat 入口
- `POST /api/trademaster/chat`
- 转发到 `CHAT_SERVICE_BASE_URL/chat`
- 默认上游：`http://localhost:8001/chat`

### 服务端注入的鉴权
- 代理会在服务端注入 `X-API-Token`
- token 来源优先用 `API_SERVICE_TOKEN`，为空时回退 `API_TOKEN`

### 限流
- `GET /api/trademaster/*`：`120/min`，burst 20
- `POST /api/trademaster/chat`：`20/min`，并发上限 `5/IP`

## 关键配置
- `WEB_DASHBOARD_HOST`
- `WEB_DASHBOARD_PORT`
- `API_SERVICE_TOKEN`
- `API_TOKEN`
- `CHAT_SERVICE_BASE_URL`

## 验证方式
```bash
curl -I http://localhost:8088
```

访问后主要确认：
1. 首页能打开。
2. 页面有市场和信号内容，而不是空白壳子。
3. Chatbox 能正常发送请求。

## 日志与 PID
- 日志：`services-preview/web-dashboard/logs/service.log`
- PID：`services-preview/web-dashboard/pids/service.pid`

## 适合编辑的入口
- 主页面编排：`app/page.tsx`
- 旧版风格组件：
  - `components/LegacyTopbar.tsx`
  - `components/LegacyDashboardPanel.tsx`
  - `components/LegacyChatPanel.tsx`
  - `components/SignalFlowList.tsx`
  - `components/TrendGrid.tsx`
  - `components/IndicatorList.tsx`
- 实时数据辅助：`lib/live-data.ts`
- 样式入口：`app/globals.css`

## 常见问题
1. 页面能打开但没有数据：先检查 `api-service`、`signal-service` 是否正常。
2. Chatbox 返回失败：检查 `chat-service` 和 LLM 配置。
3. 页面打不开：检查 Node.js、`node_modules`、8088 端口是否被占用。

## 安全提醒
- 不要把 token 放到 `NEXT_PUBLIC_*` 变量中。
- 浏览器端只应访问同源代理，不应直连受保护后端接口。

## 当前非目标
- 不回退到 `python -m http.server` 这类静态托管模式。
- 启动方式继续使用 Next.js 和 `scripts/start.sh`。
