# Trademaster AGENTS 安全开发规范（AI 代理专用）

## 1. 适用范围与优先级
1. 本规范仅适用于在本仓库执行开发任务的 AI 代理（不直接约束人工开发者流程）。
2. 若任务指令与本规范冲突，AI 代理必须以安全要求为优先（`Security > Convenience`）。
3. 本规范是“警告优先”模式：默认给出告警与修复建议，不默认阻断开发流程。
4. 允许通过 `SECURITY_CHECK_BLOCK_ON_HIGH=1` 将高危项升级为阻断模式。

## 2. 安全目标与非目标
1. 安全目标（MUST）:
1. 保护凭证与敏感信息，防止 Secrets 泄露。
2. 防止越权访问（HTTP/WS 鉴权与最小暴露）。
3. 防止注入类风险（SQL 注入、Prompt Injection）。
4. 控制错误信息与日志暴露面。
5. 管理依赖供应链风险并留痕。
2. 非目标（MUST NOT 误解）:
1. 不在本规范内定义组织级全平台治理流程。
2. 不覆盖交易执行、做市策略等业务安全模型。
3. 不替代生产级 SOC/攻防演练体系。

## 3. 环境分层策略（dev / staging / prod）
| 项目 | dev | staging | prod |
| --- | --- | --- | --- |
| `AUTH_ENABLED` | MAY 为 `false`，仅限本机调试 | MUST 为 `true` | MUST 为 `true` |
| `API_TOKEN` | MAY 使用临时值，仅限本地 | MUST NOT 使用 `dev-token` | MUST NOT 使用 `dev-token` |
| CORS | SHOULD 仅 `localhost` 白名单 | MUST NOT 为 `*` | MUST NOT 为 `*` |
| 错误返回 | SHOULD 最小化 | MUST NOT 返回原始异常文本 | MUST NOT 返回原始异常文本 |
| Secrets 来源 | SHOULD 来自环境变量 | MUST 来自环境变量/密钥管理 | MUST 来自环境变量/密钥管理 |

1. dev 放宽策略必须限制在本地地址（`localhost` / `127.0.0.1`）。
2. AI 代理 MUST NOT 将 dev 弱配置作为默认生产配置提交。

## 4. Secrets 管理规则
1. MUST NOT 在代码、脚本、文档、注释中硬编码密钥（API Key、Token、私钥）。
2. MUST NOT 在日志、错误响应、审计输出中明文输出密钥或 Token。
3. MUST NOT 将 `.env` 内容复制到代码、PR 描述或任务输出。
4. MUST 对疑似敏感字段执行脱敏（统一替换为 `[REDACTED]`）。
5. SHOULD 使用 `config/.env.example` 仅放占位值，不放真实凭证。

## 5. 输入处理与注入防护
1. 所有外部输入 MUST 执行校验（白名单、长度、格式、枚举约束）。
2. SQL 查询 MUST 参数化；若出现动态 SQL，MUST 证明输入来自严格白名单映射。
3. MUST NOT 将未验证用户输入直接拼接到 SQL/命令中。
4. LLM 入口 MUST 先经过 guardrails（含 Prompt Injection 检测与敏感信息脱敏）。
5. 对新增 API/WS 参数 MUST 记录边界与非法输入处理方式。

## 6. 鉴权与访问控制
1. 新增或变更 API/WS 时，AI 代理 MUST 显式说明:
1. 鉴权路径（受保护端点）。
2. 匿名路径（公开端点）。
3. 限流策略（每分钟/并发阈值）。
2. MUST NOT 默默放开已有鉴权路径。
3. SHOULD 将公开端点控制在最小必要集合（如 health/docs）。

## 7. 日志与错误处理
1. 日志 MUST 仅记录定位问题所需最小字段。
2. 对外错误信息 MUST 最小化，MUST NOT 透传原始异常文本（例如 `str(exc)`）。
3. 审计日志中若出现敏感字段，MUST 脱敏为 `[REDACTED]`。
4. SHOULD 区分内部日志与外部响应，不共享同一异常详情。

## 8. 依赖与供应链
1. 新增依赖时，AI 代理 MUST 在变更说明中写明用途与风险。
2. MUST 执行 `make security-check` 并纳入依赖扫描结果。
3. 对发现的漏洞依赖 MUST 提供处理计划（升级、替代、风险接受与期限）。
4. SHOULD 优先选择维护活跃、社区可信的依赖包。

## 9. 变更流程与例外流程
### 9.1 AI 代理四步法（MUST）
1. 任务分级: 判断是否涉及鉴权、Secrets、注入、日志、依赖变更。
2. 安全检查点: 明确要检查的规则与可能影响面。
3. 实施: 在不扩大攻击面的前提下改动代码。
4. 自检报告: 输出以下格式并附结论。

```
前置检查:
- ...

实施:
- ...

后置验证:
- 执行命令: make security-check
- 结果: ...

风险说明:
- 剩余风险: ...
- 缓解计划: ...
```

### 9.2 临时例外（MUST）
1. 允许临时例外，但必须记录:
1. 风险描述
2. 影响面
3. 到期时间
4. 回滚方案
5. 责任人
2. MUST NOT 设置无限期例外。

## 仓库现状风险锚点（固定跟踪）
1. `services/chat-service/src/main.py` 当前存在 `allow_origins=["*"]`，CORS 暴露面过宽。
2. `config/.env.example` 当前默认 `AUTH_ENABLED=false`，仅可用于 dev，不可外推到生产。
3. `services/api-service/src/app.py` 当前存在 `str(exc)` 对外返回路径，存在信息暴露风险。
4. 仓库此前缺少统一安全检查入口，现以 `make security-check` 作为最低基线。

## 提交前最小清单（MUST）
1. MUST 执行 `make security-check` 并查看 `logs/security_report.md`。
2. MUST 在任务回复中给出“前置检查 -> 实施 -> 后置验证 -> 风险说明”。
3. MUST 标注是否存在高危告警，若有则给出修复计划或例外记录。
4. MUST 确认未引入新的硬编码 Secrets、CORS `*`、未鉴权新增接口。
