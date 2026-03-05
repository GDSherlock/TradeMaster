SHELL := /bin/bash

SYMBOLS ?= BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT
INTERVALS ?= 1m,5m,15m,1h,4h,1d
DAYS ?= 365
RESUME ?= 1
TABLE ?= rsi_14
INDICATOR_PORT ?= 9102

.PHONY: help init db-init dev dev-data dev-edge dev-web stop status restart backfill live stop-live indicators-once indicators-loop signal-once signal-loop signal api chat dashboard ml-service ml-validate-loop ml-train-once ml-train-loop ml-recalibrate-once ml-drift-check-once ml-monitor-loop ml-report smoke security-check clean

help:
	@echo "TradeCat MVP commands"
	@echo "  make init            - create venvs and install deps"
	@echo "  make db-init         - apply DB migrations"
	@echo "  make dev             - start pipeline-live/indicator/api/chat/signal/ml/dashboard"
	@echo "  make dev-data        - start data workers only (pipeline/signal-engine/ml-loops)"
	@echo "  make dev-edge        - start edge services only (api/chat/signal-serve/ml-serve)"
	@echo "  make dev-web         - start web-dashboard only"
	@echo "  make stop            - stop all services"
	@echo "  make status          - show service status"
	@echo "  make backfill        - run HF backfill"
	@echo "  make live            - run websocket collector"
	@echo "  make indicators-once - run indicator calculation once"
	@echo "  make indicators-loop - run indicator scheduler loop"
	@echo "  make signal-once     - run signal rule engine once"
	@echo "  make signal-loop     - run signal rule engine loop"
	@echo "  make signal          - run signal REST/WS service only"
	@echo "  make ml-service      - run ml-validator REST service only"
	@echo "  make ml-validate-loop - run ml validation worker loop"
	@echo "  make ml-train-once   - run ml training once"
	@echo "  make ml-train-loop   - run ml daily training scheduler"
	@echo "  make ml-recalibrate-once - run weekly threshold recalibration once"
	@echo "  make ml-drift-check-once - run drift check once (with optional retrain trigger)"
	@echo "  make ml-monitor-loop - run combined train/recalibrate/drift monitor loop"
	@echo "  make ml-report       - generate logs/ml_report.md from /api/ml/*"
	@echo "  make smoke           - run quick API smoke checks"
	@echo "  make security-check  - run warn-only security checks and write logs/security_report.md"

init:
	@./scripts/init.sh

db-init:
	@./scripts/db_init.sh

dev:
	@./scripts/devctl.sh start

dev-data:
	@./scripts/devctl.sh start --group data

dev-edge:
	@./scripts/devctl.sh start --group edge

dev-web:
	@./scripts/devctl.sh start --group web

stop:
	@./scripts/devctl.sh stop

status:
	@./scripts/devctl.sh status

restart:
	@./scripts/devctl.sh restart

backfill:
	@cd services/pipeline-service && .venv/bin/python -m src backfill --symbols "$(SYMBOLS)" --days "$(DAYS)" --resume "$(RESUME)"

live:
	@cd services/pipeline-service && .venv/bin/python -m src live --symbols "$(SYMBOLS)"

stop-live:
	@pkill -f "python -m src live" >/dev/null 2>&1 || true

indicators-once:
	@cd services/pipeline-service && PIPELINE_SERVICE_PORT="$(INDICATOR_PORT)" .venv/bin/python -m src indicator --symbols "$(SYMBOLS)" --intervals "$(INTERVALS)" --once

indicators-loop:
	@cd services/pipeline-service && PIPELINE_SERVICE_PORT="$(INDICATOR_PORT)" .venv/bin/python -m src indicator --symbols "$(SYMBOLS)" --intervals "$(INTERVALS)"

signal-once:
	@cd services/signal-service && .venv/bin/python -m src engine --symbols "$(SYMBOLS)" --intervals "$(INTERVALS)" --once

signal-loop:
	@cd services/signal-service && .venv/bin/python -m src engine --symbols "$(SYMBOLS)" --intervals "$(INTERVALS)"

signal:
	@cd services/signal-service && .venv/bin/python -m src serve

api:
	@cd services/api-service && .venv/bin/python -m src

chat:
	@cd services/chat-service && .venv/bin/python -m src

dashboard:
	@cd services-preview/web-dashboard && ./scripts/start.sh run

ml-service:
	@cd services/ml-validator-service && .venv/bin/python -m src serve

ml-validate-loop:
	@cd services/ml-validator-service && .venv/bin/python -m src validate

ml-train-once:
	@cd services/ml-validator-service && .venv/bin/python -m src train --once

ml-train-loop:
	@cd services/ml-validator-service && .venv/bin/python -m src train-loop

ml-recalibrate-once:
	@cd services/ml-validator-service && .venv/bin/python -m src recalibrate --once

ml-drift-check-once:
	@cd services/ml-validator-service && .venv/bin/python -m src drift-check --once

ml-monitor-loop:
	@cd services/ml-validator-service && .venv/bin/python -m src monitor-loop

ml-report:
	@./scripts/ml_report.sh

smoke:
	@./scripts/smoke.sh

security-check:
	@./scripts/security_check.sh

clean:
	@rm -rf run logs
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@echo "cleaned"
