# backtest-service 运维说明

## 一句话说明
`backtest-service` 负责保存版本化策略、提交异步回测任务，并输出资金曲线、交易明细与回撤保护结果。

## 它在系统里的位置
- 上游：`market_data.candles_1m`、`market_data.indicator_values`、`market_data.signal_rule_configs`
- 下游：`web-dashboard` 的 `/backtest` 页面与同源 BFF

## 服务职责
- 提供策略 DSL 校验与版本保存
- 维护异步任务队列（`queued/running/completed/failed/canceled`）
- 执行单标的、单周期永续合约回测
- 输出运行摘要、交易记录、资金曲线、回撤触发事件

## 运行模式
- `serve`：启动 REST API
- `worker`：轮询数据库队列并执行回测

## 关键配置
来自 `config/.env`：

- `BACKTEST_SERVICE_HOST/PORT`
- `BACKTEST_RATE_LIMIT_PER_MINUTE`
- `BACKTEST_RATE_LIMIT_BURST`
- `BACKTEST_MAX_BARS_PER_RUN`
- `BACKTEST_MAX_CONCURRENT_RUNS`
- `BACKTEST_QUEUE_POLL_SECONDS`
- `BACKTEST_INITIAL_EQUITY`
- `AUTH_ENABLED`
- `API_TOKEN`

## 对外接口
- `GET /backtest/health`
- `GET /backtest/catalog`
- `GET/POST /backtest/strategies`
- `GET /backtest/strategies/{strategy_id}`
- `GET /backtest/strategies/{strategy_id}/versions`
- `POST /backtest/runs`
- `GET /backtest/runs`
- `GET /backtest/runs/{run_id}`
- `GET /backtest/runs/{run_id}/equity`
- `GET /backtest/runs/{run_id}/trades`
- `POST /backtest/runs/{run_id}/cancel`

## 启动方式
整链路托管：

```bash
make dev
make status
```

单独启动：

```bash
make backtest-service
make backtest-worker
```

说明：
- `make dev` / `./scripts/devctl.sh` 才是仓库默认的后台托管入口。
- `make backtest-service` 适合临时单独调试；如果已经手工启动了 `backtest-service`，再次执行 `make dev` 会因为 `8004` 端口被占用而直接报出冲突诊断。
- `devctl` 不会自动接管或停止这个手工实例，需要手工释放端口后再重试托管启动。

## 数据表
- `market_data.backtest_strategies`
- `market_data.backtest_strategy_versions`
- `market_data.backtest_runs`
- `market_data.backtest_run_trades`
- `market_data.backtest_run_equity_points`
- `market_data.backtest_run_events`

对应读视图：
- `market_data_api.v_backtest_strategies_v1`
- `market_data_api.v_backtest_strategy_versions_v1`
- `market_data_api.v_backtest_runs_v1`
- `market_data_api.v_backtest_run_trades_v1`
- `market_data_api.v_backtest_run_equity_points_v1`
- `market_data_api.v_backtest_run_events_v1`

## 安全提醒
- 仅 `/backtest/health` 为公开端点，其余接口必须带 `X-API-Token`
- 不要在策略 DSL、日志或错误响应里写入密钥
- 失败响应只返回最小化错误，不透传原始异常文本
