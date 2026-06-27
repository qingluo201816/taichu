# 当前仓库锚点

> 本文件用于帮助 Codex 快速理解“当前仓库已有哪些基线”。执行任务时仍必须先读取真实仓库文件。

## 1. README 锚点

README 当前定位：

- 太初是一款面向个人作者的单本玄幻长篇 AI 创作工作台。
- 主体验：沉浸式编辑器。
- 主对象：单本玄幻长篇。
- 主用户：个人作者。
- 主价值：减少上下文切换，维护设定一致性，辅助正文推进。
- 主 AI 形态：编辑器内轻量工作流 + 独立 Agent 深度对话。
- 主数据原则：正文和作者确认内容是事实源，索引与缓存可重建。
- 主边界：不做多小说平台，不做协作 SaaS，不做发布平台，不做纯自动写书工具。

## 2. 架构基线锚点

`.claude/management/PROJECT_ARCHITECTURE.md` 当前规定：

- 项目分开发态、运行态、数据态。
- 开发态：`.claude/`、`.agents/`。
- 运行态：`src/`、`web/`。
- 数据态：`project_assets/`。
- `project_assets/source/` 是唯一事实来源，必须备份。
- `project_assets/generated/` 可删除、可完整重建。
- 系统运行期间只有一个小说上下文，不引入小说选择和跨小说歧义。
- API、Service、Agent、Tool、存储契约不接收 `project_id`、`novel_id`。
- Agent、API、前端不得直接读写 `project_assets/`，必须通过存储和检索契约。
- 后端依赖方向：api → application → domain；infrastructure 实现 application contracts；main.py 组合依赖。
- 已完成迁移：不得重新引入 `src/taichu/core/`、顶层 `agents/`、顶层 `models/`。

## 3. 执行前检查

Codex 每次执行前必须检查：

- README 是否仍保持上述定位。
- `.claude/management/PROJECT_ARCHITECTURE.md` 是否仍是当前架构基线。
- 后端是否已迁移到 `api/application/domain/infrastructure`。
- 是否存在旧 `src/taichu/core/`、顶层 `agents/`、顶层 `models/`；如存在，先报告，不要擅自扩展。
- `project_assets/source/` 与 `project_assets/generated/` 是否存在或需要由 Phase 1 创建。
