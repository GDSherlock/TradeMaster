#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_BASE="${BASE_API:-http://localhost:8000/api}"
REPORT="$ROOT/logs/ml_report.md"

mkdir -p "$ROOT/logs"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

HEADER_ARGS=()
if [ -n "${API_TOKEN:-}" ]; then
  HEADER_ARGS=(-H "X-API-Token: ${API_TOKEN}")
fi

curl -fsS "${HEADER_ARGS[@]}" "$API_BASE/ml/runtime" > "$TMP_DIR/runtime.json"
curl -fsS "${HEADER_ARGS[@]}" "$API_BASE/ml/validation/summary?window=7d" > "$TMP_DIR/summary.json"
curl -fsS "${HEADER_ARGS[@]}" "$API_BASE/ml/validation/metrics?window=7d" > "$TMP_DIR/metrics.json"
curl -fsS "${HEADER_ARGS[@]}" "$API_BASE/ml/drift/latest?limit=5" > "$TMP_DIR/drift.json"
curl -fsS "${HEADER_ARGS[@]}" "$API_BASE/ml/training/runs?limit=5" > "$TMP_DIR/runs.json"

python3 - "$TMP_DIR" "$REPORT" <<'PY'
import json
import pathlib
import sys
from datetime import datetime, timezone

root = pathlib.Path(sys.argv[1])
report_path = pathlib.Path(sys.argv[2])

def read(name):
    payload = json.loads((root / f"{name}.json").read_text())
    return payload.get("data") if isinstance(payload, dict) else payload

runtime = read("runtime") or {}
summary = read("summary") or {}
metrics = read("metrics") or {}
drift = read("drift") or []
runs = read("runs") or []

now = datetime.now(tz=timezone.utc).isoformat()

lines = []
lines.append("# ML Report")
lines.append("")
lines.append(f"- generated_at_utc: `{now}`")
lines.append("")

lines.append("## Runtime")
lines.append("")
lines.append(f"- champion_version: `{runtime.get('champion_version')}`")
lines.append(f"- queue_lag: `{runtime.get('queue_lag')}`")
lines.append(f"- last_train_at: `{runtime.get('last_train_at')}`")
lines.append(f"- last_drift_check_at: `{runtime.get('last_drift_check_at')}`")
lines.append("")

lines.append("## Validation (7d)")
lines.append("")
lines.append(f"- total: `{summary.get('total', 0)}`")
lines.append(f"- passed: `{summary.get('passed', 0)}`")
lines.append(f"- pass_ratio: `{summary.get('pass_ratio', 0):.4f}`")
lines.append(f"- avg_probability: `{summary.get('avg_probability', 0):.4f}`")
lines.append("")

current_model = metrics.get("current_model") if isinstance(metrics, dict) else {}
lines.append("## Current Model")
lines.append("")
lines.append(f"- model_version: `{(current_model or {}).get('model_version')}`")
lines.append(f"- threshold: `{(current_model or {}).get('threshold')}`")
lines.append(f"- promoted: `{(current_model or {}).get('promoted')}`")
lines.append("")

lines.append("## Latest Training Runs")
lines.append("")
if runs:
    lines.append("| id | version | run_type | promoted | threshold | sample_count | created_at |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for row in runs:
        lines.append(
            f"| {row.get('id')} | {row.get('model_version')} | {row.get('run_type')} | {row.get('promoted')} | {row.get('threshold')} | {row.get('sample_count')} | {row.get('created_at')} |"
        )
else:
    lines.append("- no training runs")
lines.append("")

lines.append("## Drift Alerts")
lines.append("")
if drift:
    lines.append("| id | version | sample_count | max_feature_psi | threshold | triggered_retrain | created_at |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for row in drift:
        lines.append(
            f"| {row.get('id')} | {row.get('model_version')} | {row.get('sample_count')} | {row.get('max_feature_psi')} | {row.get('threshold')} | {row.get('triggered_retrain')} | {row.get('created_at')} |"
        )
else:
    lines.append("- no drift checks")
lines.append("")

report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"report written: {report_path}")
PY

echo "ml report generated: $REPORT"
