#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPORT="$ROOT/logs/security_report.md"

mkdir -p "$ROOT/logs"

TMP_FINDINGS="$(mktemp)"
TMP_DEPS="$(mktemp)"
trap 'rm -f "$TMP_FINDINGS" "$TMP_DEPS"' EXIT

TOTAL_COUNT=0
HIGH_COUNT=0
MEDIUM_COUNT=0
LOW_COUNT=0

BLOCK_ON_HIGH="${SECURITY_CHECK_BLOCK_ON_HIGH:-0}"
GENERATED_AT="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
PIP_AUDIT_BIN=""
if [[ -x "$ROOT/.venv-security/bin/pip-audit" ]]; then
  PIP_AUDIT_BIN="$ROOT/.venv-security/bin/pip-audit"
elif command -v pip-audit >/dev/null 2>&1; then
  PIP_AUDIT_BIN="$(command -v pip-audit)"
fi

escape_md() {
  local text="$1"
  text="${text//|/\\|}"
  text="${text//$'\n'/ }"
  printf '%s' "$text"
}

add_finding() {
  local severity="$1"
  local check_name="$2"
  local location="$3"
  local issue="$4"
  local suggestion="$5"

  case "$severity" in
    HIGH) HIGH_COUNT=$((HIGH_COUNT + 1)) ;;
    MEDIUM) MEDIUM_COUNT=$((MEDIUM_COUNT + 1)) ;;
    LOW) LOW_COUNT=$((LOW_COUNT + 1)) ;;
  esac
  TOTAL_COUNT=$((TOTAL_COUNT + 1))

  printf '| %s | %s | `%s` | %s | %s |\n' \
    "$(escape_md "$severity")" \
    "$(escape_md "$check_name")" \
    "$(escape_md "$location")" \
    "$(escape_md "$issue")" \
    "$(escape_md "$suggestion")" >> "$TMP_FINDINGS"
}

scan_pattern() {
  local severity="$1"
  local check_name="$2"
  local pattern="$3"
  local issue="$4"
  local suggestion="$5"

  local matches
  matches="$(
    rg -n --no-heading -S --hidden -uu "$pattern" "$ROOT" \
      --glob '!**/.git/**' \
      --glob '!**/.venv/**' \
      --glob '!**/.venv-security/**' \
      --glob '!**/.next/**' \
      --glob '!**/logs/**' \
      --glob '!**/run/**' \
      --glob '!**/data/**' \
      --glob '!**/services-preview/**/node_modules/**' \
      --glob '!AGENTS.md' \
      --glob '!scripts/security_check.sh' \
      2>/dev/null || true
  )"

  if [[ -z "$matches" ]]; then
    return
  fi

  while IFS=: read -r file_path line_no _; do
    [[ -z "${file_path:-}" || -z "${line_no:-}" ]] && continue
    local rel_path="${file_path#"$ROOT"/}"
    add_finding "$severity" "$check_name" "${rel_path}:${line_no}" "$issue" "$suggestion"
  done <<< "$matches"
}

scan_auth_enabled_false() {
  local matches
  matches="$(
    # Inspect ignored local env files as well, otherwise config/.env is silently skipped.
    rg -n --no-heading -S --hidden -uu '^\s*AUTH_ENABLED\s*=\s*false\s*$' "$ROOT/config" \
      --glob '!**/.venv/**' \
      2>/dev/null || true
  )"

  [[ -z "$matches" ]] && return

  while IFS=: read -r file_path line_no _; do
    [[ -z "${file_path:-}" || -z "${line_no:-}" ]] && continue
    local rel_path="${file_path#"$ROOT"/}"
    if [[ "$rel_path" == "config/.env.dev.example" ]]; then
      continue
    fi
    if [[ "$rel_path" == *".env.example" ]]; then
      add_finding "MEDIUM" "高风险配置扫描" "${rel_path}:${line_no}" \
        "检测到 AUTH_ENABLED=false（示例默认值）" \
        "仅允许 dev 使用；staging/prod 必须设置 AUTH_ENABLED=true。"
    else
      add_finding "HIGH" "高风险配置扫描" "${rel_path}:${line_no}" \
        "检测到 AUTH_ENABLED=false（非示例配置）" \
        "请在非 dev 环境启用鉴权，并限制匿名端点。"
    fi
  done <<< "$matches"
}

scan_default_token() {
  local matches
  matches="$(
    rg -n --no-heading -S --hidden -uu '^\s*API_TOKEN\s*=\s*dev-token\s*$' "$ROOT/config" \
      --glob '!**/.venv/**' \
      2>/dev/null || true
  )"

  [[ -z "$matches" ]] && return

  while IFS=: read -r file_path line_no _; do
    [[ -z "${file_path:-}" || -z "${line_no:-}" ]] && continue
    local rel_path="${file_path#"$ROOT"/}"
    if [[ "$rel_path" == "config/.env.dev.example" ]]; then
      continue
    fi
    if [[ "$rel_path" == *".env.example" ]]; then
      add_finding "MEDIUM" "高风险配置扫描" "${rel_path}:${line_no}" \
        "检测到默认 API_TOKEN=dev-token（示例默认值）" \
        "示例值仅用于 dev；staging/prod 必须使用非默认 Token 并安全下发。"
    else
      add_finding "HIGH" "高风险配置扫描" "${rel_path}:${line_no}" \
        "检测到 API_TOKEN=dev-token（非示例配置）" \
        "请立即更换为强随机 Token，并轮换已暴露凭证。"
    fi
  done <<< "$matches"
}

scan_dependency_vulns() {
  if [[ -z "$PIP_AUDIT_BIN" ]]; then
    printf -- "- status: SKIPPED\n- reason: pip-audit 未安装，依赖漏洞扫描未执行。\n" >> "$TMP_DEPS"
    add_finding "LOW" "依赖漏洞扫描" "N/A" \
      "pip-audit 未安装，依赖漏洞扫描未执行" \
      "先执行 make init 安装安全工具链后，再执行 make security-check。"
    return
  fi

  local found_file=0
  local req_file
  for req_file in "$ROOT"/services/*/requirements.txt; do
    [[ -f "$req_file" ]] || continue
    found_file=1
    local rel_path="${req_file#"$ROOT"/}"
    printf -- "### %s\n" "$rel_path" >> "$TMP_DEPS"

    set +e
    local output
    output="$("$PIP_AUDIT_BIN" -r "$req_file" --progress-spinner off 2>&1)"
    local exit_code=$?
    set -e

    if [[ $exit_code -eq 0 ]]; then
      printf -- "- status: PASS\n- detail: 未发现已知漏洞。\n\n" >> "$TMP_DEPS"
      continue
    fi

    if [[ $exit_code -eq 1 ]]; then
      add_finding "MEDIUM" "依赖漏洞扫描" "$rel_path" \
        "发现已知漏洞依赖（详见依赖扫描输出）" \
        "升级或替代受影响依赖，并评估兼容性影响。"
      printf -- "- status: WARN\n- detail: pip-audit 发现漏洞。\n\n```text\n%s\n```\n\n" "$output" >> "$TMP_DEPS"
      continue
    fi

    add_finding "LOW" "依赖漏洞扫描" "$rel_path" \
      "pip-audit 执行异常，扫描结果不完整" \
      "检查网络/索引配置后重试，必要时在 CI 环境补跑。"
    printf -- "- status: SKIPPED\n- detail: pip-audit 执行失败（exit=%s）。\n\n```text\n%s\n```\n\n" "$exit_code" "$output" >> "$TMP_DEPS"
  done

  if [[ $found_file -eq 0 ]]; then
    printf -- "- status: SKIPPED\n- reason: 未找到 requirements.txt。\n" >> "$TMP_DEPS"
  fi
}

# 1) Secrets 模式扫描
scan_pattern "HIGH" "Secrets 扫描" 'sk-[A-Za-z0-9_-]{16,}' \
  "检测到疑似 API Key（sk-*）" \
  "移除硬编码密钥，改用环境变量，并执行密钥轮换。"
scan_pattern "HIGH" "Secrets 扫描" 'Bearer[[:space:]]+[A-Za-z0-9._-]{12,}' \
  "检测到疑似 Bearer Token" \
  "禁止在代码/日志中存放 Bearer Token，统一改为运行时注入。"
scan_pattern "HIGH" "Secrets 扫描" 'token=[A-Za-z0-9._-]{8,}' \
  "检测到疑似 URL Token 参数" \
  "避免通过 URL 传递敏感凭证，改用受控请求头并进行脱敏。"
scan_pattern "HIGH" "Secrets 扫描" '-----BEGIN[[:space:]]+(RSA|EC|DSA|OPENSSH|PRIVATE)[[:space:]]+PRIVATE KEY-----' \
  "检测到疑似私钥内容" \
  "立即删除仓库内私钥并轮换相关凭证。"

# 2) 高风险配置扫描
scan_pattern "HIGH" "高风险配置扫描" 'allow_origins\s*=\s*\[\s*"\*"\s*\]' \
  "检测到 CORS allow_origins=[\"*\"]" \
  "将 CORS 改为明确白名单，按环境区分配置。"
scan_pattern "HIGH" "高风险配置扫描" '^\s*CORS_ALLOW_ORIGINS\s*=\s*\*\s*$' \
  "检测到 CORS_ALLOW_ORIGINS=*" \
  "禁止使用通配 CORS，改为最小允许域名集合。"
scan_auth_enabled_false
scan_default_token

# 3) 高风险编码模式扫描
scan_pattern "HIGH" "高风险编码扫描" 'error_response\(ErrorCode\.INTERNAL_ERROR,\s*str\(exc\)\)' \
  "检测到原始异常文本对外透传" \
  "返回通用错误消息，将详细异常仅写入内部日志。"
scan_pattern "MEDIUM" "高风险编码扫描" '^\s*sql\s*=\s*f"""' \
  "检测到 f-string SQL，存在注入风险窗口" \
  "仅允许白名单映射片段；其余变量全部参数化。"
scan_pattern "MEDIUM" "高风险编码扫描" '(LOG\.[A-Za-z_]+\(|logger\.[A-Za-z_]+\(|print\().*(token|api[_-]?key|authorization|password|secret|req\.message)' \
  "检测到疑似敏感日志输出" \
  "将敏感字段脱敏为 [REDACTED]，并缩减日志字段。"

# 4) 依赖漏洞扫描
scan_dependency_vulns

{
  printf '# Security Check Report\n\n'
  printf -- '- generated_at_utc: `%s`\n' "$GENERATED_AT"
  printf -- '- workspace: `%s`\n' "$ROOT"
  printf -- '- mode: `warn-only`\n'
  printf -- '- block_on_high: `%s`\n\n' "$BLOCK_ON_HIGH"

  printf '## Summary\n\n'
  printf '| 指标 | 数量 |\n'
  printf '| --- | --- |\n'
  printf '| 总告警数 | %s |\n' "$TOTAL_COUNT"
  printf '| HIGH | %s |\n' "$HIGH_COUNT"
  printf '| MEDIUM | %s |\n' "$MEDIUM_COUNT"
  printf '| LOW | %s |\n\n' "$LOW_COUNT"

  printf '## Findings（问题位置 + 风险级别 + 修复建议）\n\n'
  printf '| 风险级别 | 检查项 | 位置 | 问题 | 修复建议 |\n'
  printf '| --- | --- | --- | --- | --- |\n'
  if [[ -s "$TMP_FINDINGS" ]]; then
    cat "$TMP_FINDINGS"
  else
    printf '| INFO | 全量检查 | `N/A` | 未发现匹配告警 | 无需修复。 |\n'
  fi

  printf '\n## Dependency Scan\n\n'
  if [[ -s "$TMP_DEPS" ]]; then
    cat "$TMP_DEPS"
  else
    printf -- '- status: SKIPPED\n- reason: 依赖扫描未产生输出。\n'
  fi

  printf '\n## Enforcement Hook\n\n'
  printf -- '- 默认策略: 告警优先，不阻断退出。\n'
  printf -- '- 升级阻断: 设置 `SECURITY_CHECK_BLOCK_ON_HIGH=1`，当 HIGH > 0 时返回非零。\n'
} > "$REPORT"

echo "security-check report written: $REPORT"
echo "summary: total=$TOTAL_COUNT high=$HIGH_COUNT medium=$MEDIUM_COUNT low=$LOW_COUNT"

if [[ "$BLOCK_ON_HIGH" == "1" && "$HIGH_COUNT" -gt 0 ]]; then
  echo "high severity findings detected and block mode is enabled."
  exit 2
fi

exit 0
