# Codex 执行规则

## 1. 每次只做一个 Phase

不得跨阶段实现后续功能。若某个后续接口为了当前测试必须存在，只能做最小 stub，并在返回报告中明确说明。

## 2. 先读仓库再改代码

执行前必须检查：

- README.md
- `.claude/management/PROJECT_ARCHITECTURE.md`
- AGENTS.md
- pyproject.toml
- web/package.json
- 当前相关目录

如果仓库事实与任务包冲突，先报告冲突，不擅自大改。

## 3. 层边界

- API route 不写业务逻辑。
- Service 不直接 import 具体 infrastructure。
- Domain 不依赖技术实现。
- Infrastructure 不写小说业务规则。
- Frontend 不直接 fetch 分散请求，统一走 API client。

## 4. 数据边界

- 不新增 `project_id`、`novel_id`。
- 不让 SQLite 保存唯一用户资产。
- 不让 generated 反向成为事实。
- 不让 workspace 内容进入默认 fact_scope。

## 5. AI 边界

- Selection AI 是 Service/workflow。
- AI 输出必须是 AIResultCard。
- 设定补充只能生成 Suggestion/PendingFact。
- 续写默认只输出正文。
- Agent 不直接写 Knowledge 或 Markdown。

## 6. 测试边界

- 测试不得污染真实 `project_assets/`。
- 测试 fixtures 放 tests/fixtures/project_assets 或临时目录。
- 每个 Phase 至少覆盖核心正向流和一个防污染/数据安全流。

## 7. 返回格式

必须使用 `evidence_return_template.md`。不要只说“已完成”。
