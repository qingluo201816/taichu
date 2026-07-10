---
name: prd-to-plan
description: PRD 到代码实现全流程编排工具，适用于用户要求从 prd-docs 读取 PRD、拆分功能点、生成 cc-sdd 规格并推进设计和实现时。每个阶段必须等待用户确认。
---

# PRD to Plan

## 定位

将 `prd-docs/` 中的 PRD 文档转成可执行规格，并按 cc-sdd 流程推进到需求、设计、任务和实现。该 Skill 是编排器，只负责阶段顺序、输入校验、确认闸门和失败处理。

## 太初约束

- 遵循根目录 `AGENTS.md` 与 `.agents/skills/rule.md`。
- 项目级 Skill 统一位于 `.agents/skills/`。
- Python 命令统一使用 `uv run python`，不得提示使用其他 Python 包管理器。
- 面向用户的说明、提示、报告和文档正文使用中文。
- 只服务太初这一本玄幻小说，不设计多小说、多租户、`project_id` 或跨小说切换。

## 输入

- PRD 文件：位于 `prd-docs/`，支持 `.md`、`.txt`、`.pdf`、`.docx`。
- 版本号：由用户提供，例如 `V1.0`。

## 流程

### Step 0 启动 Dashboard

可选。检查端口 `8686`，未被占用时运行：

```bash
uv run python .claude/scripts/spec_dashboard_server.py --port 8686
```

浏览器访问 `http://localhost:8686/dashboard.html` 查看规格进度。

### 阶段一：需求分析

使用 `prd-plan-analyze`：

1. 从 `prd-docs/` 读取 PRD。
2. 按 `.claude/rules/FUNCTION_SPLIT.md` 拆分功能点。
3. 生成 `out/{版本号}/功能点清单.md`。
4. 展示功能点清单摘要并等待用户确认。

用户未确认前不得进入阶段二。

### 阶段二：规格开发

用户确认功能点清单后，使用 `prd-spec-develop`：

1. 规格初始化与需求生成：`prd-to-ccsdd`。
2. 技术设计文档生成：`prd-design-generator`。
3. 任务生成与代码实现：`prd-spec-impl`。
4. 输出实现报告并等待用户确认。

## 强制规则

- 严格按阶段一到阶段二执行，不得跳步。
- 每个阶段完成后必须等待用户确认；当前环境没有专用提问工具时，用普通中文问题等待用户回复。
- 执行任何代码变更前先说明方案并获得用户确认。
- 子流程输入缺失或失败时，展示具体错误，并让用户选择重试、跳过或终止。
- 不自动提交或推送；除非用户明确要求，或其他太初 Skill 的发布规则被显式触发。

## 异常处理

| 场景 | 处理 |
|---|---|
| PRD 文件不存在 | 提示用户检查 `prd-docs/` |
| 版本号缺失 | 提示用户补充版本号 |
| 功能点清单未确认 | 停在阶段一，不进入规格开发 |
| 子 Skill 失败 | 展示错误、保留现场，等待用户选择 |
