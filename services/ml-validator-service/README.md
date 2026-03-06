# ml-validator-service 运维说明

## 一句话说明
`ml-validator-service` 是 TradeMaster 的“第二意见系统”：它会对部分 RSI 信号做机器学习复核，但当前只提供参考，不直接替代规则结果。

## 它在系统里的位置
它位于 `signal-service` 之后。规则信号先产生，ML 再对其中一部分候选信号进行打分、记录和展示。

## 非技术读者可理解的输入 / 输出
- 输入：规则信号、技术指标、历史行情。
- 输出：某条信号是否更值得关注的 ML 评分、训练记录、漂移监控结果。
- 它的定位是“辅助判断”，不是“自动决策器”。

## 1. 服务职责（影子模式）
- 对 `RSI_OVERBOUGHT` / `RSI_OVERSOLD` candidate 信号做机器学习验证。
- 训练 `LogisticRegression + StandardScaler (+ isotonic calibration)`，维护 champion / challenger。
- 增量消费 `signal_events`，写入 `signal_ml_validation`。
- 执行每日训练、每周阈值再校准、每 6 小时漂移检查（PSI）。
- 影子模式：ML 结果只做解释与标记，不阻断原有规则信号。

## 2. 数据流
```text
signal_events
  -> ml-validator(validate worker)
  -> signal_ml_validation / signal_ml_training_runs / signal_ml_runtime_state
  -> signal_ml_drift_checks / signal_ml_recalibration_runs
  -> api-service /api/ml/*
  -> web-dashboard
```

白话解释：
1. 规则信号先生成。
2. ML 再判断“这条信号是否更值得信任”。
3. 最终结果被前端和 API 用于展示，而不是直接改写规则结果。

## 3. 特征字典（训练与在线推理同构）
- RSI：`rsi_current`, `rsi_previous`, `rsi_delta`
- EMA：`ema20_ema50_gap`, `ema50_ema200_gap`
- MACD：`macd`, `signal`, `hist`
- 波动：`atr14_norm`, `ret_vol_6`
- 通道：`donchian_pos`, `bb_width`, `price_to_vwap`
- 云图：`price_to_cloud_top`
- 价格/量能：`ret_1`, `ret_3`, `ret_6`, `volume_z_6`
- 上下文：`direction_long`, `hour_of_day`, `day_of_week`, `cooldown_seconds`

如果你不是建模同学，可以把这些理解成“系统用来描述当前市场状态的一组特征”。

## 4. 标签定义
- 主标签 `y_pass`：triple-barrier
- `entry=close_t`，方向来自事件 `direction`
- `TP=+1.0*ATR14/entry`，`SL=-1.0*ATR14/entry`，`H=6 bars`
- 先触达 TP => `1`
- 先触达 SL 或到期未达 TP => `0`
- 辅助标签 `y_rsi_revert`：未来 3 bars RSI 是否回到 `[45,55]`

## 5. 模型与更新策略
- 训练切分：`train 136d / val 30d / test 14d`
- 阈值选择：`0.30~0.80` 网格搜索，目标 `F0.5`
- 晋升规则：
  - Precision 提升至少 `+3pp`
  - PR-AUC 不下降
  - Brier 不显著劣化
  - Coverage 保持在合理范围
- 调度：
  - 每日 `02:10` 训练 challenger
  - 每周日 `02:40` 再校准阈值
  - 每 6 小时做一次漂移检查

术语说明：
- `champion`：当前在用的最佳模型版本。
- `challenger`：新训练出来、等待比较的版本。
- `drift`：数据分布和历史相比发生明显变化。

## 6. 启动命令
仓库根目录：

```bash
make ml-service
make ml-validate-loop
make ml-train-once
make ml-train-loop
make ml-recalibrate-once
make ml-drift-check-once
make ml-monitor-loop
```

直接运行：

```bash
cd services/ml-validator-service
.venv/bin/python -m src serve
.venv/bin/python -m src validate
.venv/bin/python -m src train --once
.venv/bin/python -m src train-loop
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
- `GET /ml/training/runs`（鉴权）
- `GET /ml/training/runs/{run_id}`（鉴权）
- `GET /ml/validation/summary`（鉴权）
- `GET /ml/drift/latest`（鉴权）
- `GET /ml/recalibration/runs`（鉴权）

鉴权说明：
- 当 `AUTH_ENABLED=true` 时，除 `/ml/health` 外都需要 `X-API-Token`

## 8. 结果如何查看
1. 命令行：`make ml-train-once`
2. 模型文件：`models/<version>/features.json`、`metadata.json`
3. 数据库表：
   - `market_data.signal_ml_training_runs`
   - `market_data.signal_ml_validation`
   - `market_data.signal_ml_drift_checks`
   - `market_data.signal_ml_recalibration_runs`
4. API：通过 `api-service` 的 `/api/ml/*`
5. 报告：`make ml-report` 生成 `logs/ml_report.md`

## 9. 环境变量
基础：
- `ML_VALIDATOR_SERVICE_HOST`
- `ML_VALIDATOR_SERVICE_PORT`
- `AUTH_ENABLED`
- `API_TOKEN`
- `CORS_ALLOW_ORIGINS`

在线验证：
- `ML_VALIDATE_LOOP_SECONDS`
- `ML_VALIDATE_BATCH_SIZE`

训练与调度：
- `ML_MODEL_NAME`
- `ML_MODEL_REGISTRY_DIR`
- `ML_DECISION_THRESHOLD`
- `ML_LOOKBACK_DAYS`
- `ML_VAL_DAYS`
- `ML_TEST_DAYS`
- `ML_MIN_SAMPLES`
- `ML_TRAIN_SCHEDULE_HOUR`
- `ML_TRAIN_SCHEDULE_MINUTE`
- `ML_TRAIN_TIMEZONE`

漂移：
- `ML_DRIFT_CHECK_HOURS`
- `ML_DRIFT_PSI_THRESHOLD`
- `ML_DRIFT_LOOKBACK_HOURS`
- `ML_DRIFT_SAMPLE_LIMIT`

## 10. 故障排查与回滚
1. `runtime.queue_lag` 持续升高：确认 `validate` worker 是否运行。
2. `model unavailable`：检查 champion 模型文件是否存在。
3. 漂移触发重训失败：查看 `logs/ml-validator.log` 和数据库写权限。
4. 再校准无晋升：检查 coverage 是否落在设定范围内。
5. 回滚 champion：把 `signal_ml_runtime_state.champion_version` 指回 last-good 版本。

## 日志与 PID
- 服务日志：`logs/ml-validator.log`
- 分组启动日志：
  - `logs/data/ml-validate-loop.log`
  - `logs/data/ml-monitor-loop.log`
  - `logs/edge/ml-validator-service.log`
- PID：
  - `run/pids/data/ml-validate-loop.pid`
  - `run/pids/data/ml-monitor-loop.pid`
  - `run/pids/edge/ml-validator-service.pid`

## 11. 安全边界
- 不在日志打印 token / key。
- 对外错误返回通用消息。
- 除 `/ml/health` 外无新增公开端点。
- SQL 全参数化。

## 安全提醒
- 影子模式不等于零风险，仍需监控训练和推理日志。
- 不要把模型文件、训练结果截图与真实凭证混放到公开文档里。
