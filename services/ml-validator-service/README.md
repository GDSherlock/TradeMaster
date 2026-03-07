# ml-validator-service 运维说明

## 1. 服务职责（影子模式）
- 对 `RSI_OVERBOUGHT` / `RSI_OVERSOLD` candidate 信号做机器学习验证。
- 训练 `LogisticRegression + StandardScaler (+ isotonic calibration)` 并维护 champion/challenger。
- 增量消费 `signal_events`，写入 `signal_ml_validation`。
- 执行每日训练、每周阈值再校准、每 6 小时漂移检查（PSI）。
- 影子模式：ML 结果只做解释与打标，不阻断原有规则信号。

## 2. 数据流
`signal_events -> ml-validator(validate worker) -> signal_ml_validation / signal_ml_training_runs / signal_ml_runtime_state / signal_ml_drift_checks / signal_ml_recalibration_runs -> api-service /api/ml/* -> frontend`

## 3. 特征字典（训练与在线推理同构）
- RSI: `rsi_current`, `rsi_previous`, `rsi_delta`
- EMA: `ema20_ema50_gap`, `ema50_ema200_gap`
- MACD: `macd`, `signal`, `hist`
- 波动: `atr14_norm`, `ret_vol_6`
- 通道: `donchian_pos`, `bb_width`, `price_to_vwap`
- 云图: `price_to_cloud_top`
- 价格/量能: `ret_1`, `ret_3`, `ret_6`, `volume_z_6`
- 上下文: `direction_long`, `hour_of_day`, `day_of_week`, `cooldown_seconds`

## 4. 标签定义
- 主标签 `y_pass`：triple-barrier。
- `entry=close_t`，方向来自事件 `direction`。
- `TP=+1.0*ATR14/entry`，`SL=-1.0*ATR14/entry`，`H=6 bars (1h -> 6h)`。
- 先触达 TP => `1`；先触达 SL 或到期未达 TP => `0`。
- 辅助标签 `y_rsi_revert`：未来 3 bars RSI 是否回到 `[45,55]`（仅分析展示）。

## 5. 模型与更新策略
- 训练切分：`train 136d / val 30d / test 14d`（滚动 180d）。
- 阈值选择：`0.30~0.80` 网格搜索，目标 `F0.5`。
- 晋升规则：
  - Precision 提升 >= `+3pp`
  - PR-AUC 不下降
  - Brier 不劣化超过 `0.01`
  - Coverage 在 `[0.15, 0.60]`
- 调度：
  - 每日 `02:10`（`Asia/Singapore`）训练 challenger
  - 每周日 `02:40` 阈值再校准（仅改 threshold）
  - 每 6 小时 PSI 漂移检查，`PSI > 0.2` 触发临时重训

## 6. 启动命令
仓库根目录：

```bash
make ml-service
make ml-validate-loop
make ml-train-once
make ml-train-loop
make ml-revalidate-once
make ml-recalibrate-once
make ml-drift-check-once
make ml-monitor-loop
```

服务目录直接运行：

```bash
cd services/ml-validator-service
.venv/bin/python -m src serve
.venv/bin/python -m src validate
.venv/bin/python -m src train --once
.venv/bin/python -m src train-loop
.venv/bin/python -m src revalidate --once
.venv/bin/python -m src recalibrate --once
.venv/bin/python -m src drift-check --once
.venv/bin/python -m src monitor-loop
.venv/bin/python -m src all
```

测试：

```bash
cd services/ml-validator-service
python3 -m unittest discover -s tests -p 'test_*.py'
```

## 7. 运行态 API
- `GET /ml/health`（公开）
- `GET /ml/runtime`（鉴权）
- `GET /ml/training/runs?limit=20`（鉴权）
- `GET /ml/training/runs/{run_id}`（鉴权）
- `GET /ml/validation/summary?window=1d|7d|30d`（鉴权）
- `GET /ml/drift/latest?limit=20`（鉴权）
- `GET /ml/recalibration/runs?limit=20`（鉴权）

鉴权：当 `AUTH_ENABLED=true` 时，除 `/ml/health` 外都需要 `X-API-Token`。
安全默认：`config/.env.example` 中 `AUTH_ENABLED=true`，且 `API_TOKEN` 必须为非默认强随机值，否则服务启动失败。

## 8. 结果如何查看
1. 命令行：`make ml-train-once` 查看 `run_id/model_version/promoted/threshold/metrics`。
2. 模型文件：`models/<version>/features.json` 查看训练特征清单。
3. 模型文件：`models/<version>/metadata.json` 查看阈值、验证指标、系数 TopK、feature_stats。
4. 数据库：
   - `market_data.signal_ml_training_runs`（训练历史、晋升、特征）
   - `market_data.signal_ml_validation`（在线验证结果）
   - `market_data.signal_ml_drift_checks`（PSI 漂移）
   - `market_data.signal_ml_recalibration_runs`（阈值再校准）
5. API：通过 `api-service` 的 `/api/ml/*` 给前端统一消费。
6. 报告：`make ml-report` 生成 `logs/ml_report.md`。

## 9. 环境变量
基础：
- `ML_VALIDATOR_SERVICE_HOST` / `ML_VALIDATOR_SERVICE_PORT`
- `AUTH_ENABLED` / `API_TOKEN` / `CORS_ALLOW_ORIGINS`
- `ML_VALIDATOR_RATE_LIMIT_PER_MINUTE` / `ML_VALIDATOR_RATE_LIMIT_BURST`

在线验证：
- `ML_VALIDATE_LOOP_SECONDS` / `ML_VALIDATE_BATCH_SIZE`

训练：
- `ML_MODEL_NAME` / `ML_MODEL_REGISTRY_DIR` / `ML_DECISION_THRESHOLD`
- `ML_LOOKBACK_DAYS` / `ML_VAL_DAYS` / `ML_TEST_DAYS` / `ML_MIN_SAMPLES`
- `ML_INTERVAL` / `ML_HORIZON_BARS`
- `ML_BARRIER_TP_ATR_MULT` / `ML_BARRIER_SL_ATR_MULT`
- `ML_TOP_FEATURES`

调度与晋升：
- `ML_TRAIN_LOOP_SECONDS` / `ML_TRAIN_SCHEDULE_HOUR` / `ML_TRAIN_SCHEDULE_MINUTE` / `ML_TRAIN_TIMEZONE`
- `ML_MONITOR_LOOP_SECONDS`
- `ML_RECALIBRATE_SCHEDULE_WEEKDAY` / `ML_RECALIBRATE_SCHEDULE_HOUR` / `ML_RECALIBRATE_SCHEDULE_MINUTE`
- `ML_RECALIBRATE_LOOKBACK_DAYS`
- `ML_PROMOTE_MIN_PRECISION_GAIN` / `ML_PROMOTE_MAX_BRIER_DEGRADE`
- `ML_COVERAGE_MIN` / `ML_COVERAGE_MAX`
- `ML_REVALIDATE_ON_PROMOTION` / `ML_REVALIDATE_LOOKBACK_DAYS` / `ML_REVALIDATE_BATCH_SIZE`
- `ML_REVALIDATE_MAX_BATCHES`

漂移：
- `ML_DRIFT_CHECK_HOURS` / `ML_DRIFT_PSI_THRESHOLD`
- `ML_DRIFT_LOOKBACK_HOURS` / `ML_DRIFT_SAMPLE_LIMIT` / `ML_DRIFT_MIN_SAMPLES`

## 10. 故障排查与回滚
1. `runtime.queue_lag` 持续升高：确认 `validate` worker 正在运行，`champion` 模型可加载。
2. `model unavailable`：检查 `models/<champion_version>/model.joblib` 是否存在；若 champion 已生成但旧候选仍未刷新，执行 `make ml-revalidate-once`。
3. `last_train_status=failed`：优先查看 `runtime.last_train_error` 与 `logs/data/ml-monitor-loop.log` 中的 `training dataset built`、`daily train failed`。
4. 漂移触发重训失败：查看 `logs/ml-validator.log`，并确认 DB 写入权限。
5. 再校准无晋升：检查 `coverage` 是否落在 `[0.15,0.60]`。
6. 回滚 champion：将 `signal_ml_runtime_state.champion_version` 指回 last-good 版本。

## 11. 安全边界
- 不在日志打印 token/key。
- 对外错误返回通用消息，不透传 `str(exc)`。
- 除 `/ml/health` 外无新增公开端点。
- SQL 全参数化；动态输入只用白名单与边界校验。
