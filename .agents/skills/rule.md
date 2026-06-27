# 太初项目级 Skill 规则

> 更新日期：2026-06-27

## 作用范围

本文件是太初项目的项目级 Skill 规则。创建、修改或讨论 `.agents/skills/` 下的 Skills 时，必须先读取并遵循本文件。

## 存放位置

- 项目级 Skills 统一放在 `.agents/skills/`。
- 每个 Skill 使用独立目录，目录名使用小写英文、数字和连字符。
- 每个 Skill 目录必须包含 `SKILL.md`。
- 不再使用 `.Codex/skills/rule.md` 作为本项目规则源。

## Skill 编写要求

- `SKILL.md` 必须包含 YAML frontmatter，且至少包含 `name` 和 `description`。
- `name` 必须与目录名一致，使用 kebab-case。
- `description` 必须写清楚触发场景，避免只能靠正文判断是否适用。
- 正文优先使用中文，除非 Skill 面向特定英文工具命令。
- 内容保持克制，只写会影响 Codex 行为的规则、流程、检查项和输出格式。
- 不创建 README、INSTALLATION、CHANGELOG 等额外说明文件。
- 如需复杂细节，优先放入 `references/` 并在 `SKILL.md` 中说明何时读取。

## 太初适配要求

- 任何开发态 Skill 都必须服从根目录 `AGENTS.md` 的项目不可变决策。
- 不得引导 Codex 设计多小说管理、多租户、`project_id` 或跨小说切换。
- 不得引导 `domain` 层依赖 Agent、LangGraph、LLM、MCP 或具体存储技术。
- 不得引导使用 pip、poetry、pipenv；Python 命令统一使用 `uv`。
- 涉及前端时，默认遵循 Next.js、shadcn/ui、Tailwind CSS 和 `web/` 目录约束。
- 涉及启动关键文件时，必须要求验证 `start.bat` 或记录无法验证的原因。

## 工作流边界

- GPT Pro 负责需求讨论、PRD、任务拆解和最终验收。
- Codex 负责按任务包执行、验证、报告、提交和推送。
- 除非用户明确要求，不要让 Codex 重新做需求讨论或任务拆解。
- 自动提交和推送必须由用户明确触发，或由专门的 Git 发布 Skill 触发。

## 校验要求

创建或修改 Skill 后，运行系统的 `quick_validate.py` 校验对应 Skill 目录。
如校验失败，先修复 Skill 格式，再交付。
