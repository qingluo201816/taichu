# 给 Codex 使用者的总 Prompt

将本文件和整个任务包交给 Codex 后，每次按下面模板发起一个阶段任务。

```text
你现在是太初项目的 Coding Agent。请只执行太初 MVP v1 的 Phase {PHASE_NUMBER}：{PHASE_NAME}。

你必须先阅读并遵守以下任务包文件：
- README.md
- 00_context/product_baseline.md
- 00_context/non_negotiable_decisions.md
- 01_architecture/target_architecture.md
- 01_architecture/data_contract.md
- 01_architecture/source_ref_contract.md
- 01_architecture/fact_scope_and_pollution_guard.md
- 03_execution/codex_rules.md
- 03_execution/evidence_return_template.md
- 02_phases/phase_{PHASE_NUMBER}_{PHASE_SLUG}.md

项目当前固定决策：
1. 太初是单个作者、单本玄幻长篇小说的个人 AI 创作 IDE，不是多小说平台、协作 SaaS、发布平台或自动写书工具。
2. 正文 Markdown 和作者确认 Knowledge JSON 是正式小说事实源。
3. `project_assets/source/` 是用户资产源；其中 fact scope 与 workspace scope 必须区分。
4. `project_assets/generated/` 是可删除、可重建派生数据。
5. SQLite 只能作为 generated projection，不能保存唯一用户资产。
6. Selection AI 是编辑器应用工作流，由 Service 承载，不注册为 MVP Agent。
7. AI 输出必须是 AIResultCard，不能返回裸字符串给前端。
8. PendingFact 未确认前不能进入 Knowledge，也不能进入默认 fact_scope。
9. SourceRef v1 是段落级/字段级证据定位，选区可保存段内偏移。
10. 本阶段完成后必须停止，不能顺手做下一阶段。

执行流程：
1. 先检查当前仓库结构，确认是否符合架构基线。
2. 输出一个极简执行计划，列出将修改的模块和不会修改的模块。
3. 按 Phase 文件执行任务。
4. 补充或更新必要测试。
5. 运行可用测试、类型检查、格式检查；如果某命令因环境缺失失败，要说明原因和替代验证。
6. 按 `03_execution/evidence_return_template.md` 返回证据。

禁止事项：
- 不要引入 `project_id`、`novel_id` 到产品 API / Service / Agent / Tool。
- 不要让前端直接访问 `project_assets/`、LLM、SQLite、向量库。
- 不要在 API route 写业务逻辑。
- 不要让 application 直接 import infrastructure 具体实现。
- 不要重新引入旧 `src/taichu/core/`、顶层 `agents/`、顶层 `models/`。
- 不要把 Selection AI 写进 `application/agents/selection_assistant/` 作为主逻辑。
- 不要把 AI 卡片、灵感、待确认设定当小说事实。
- 不要为了“以后扩展”提前做复杂多 Agent 可视化、地图、时间线、协作、发布、模型看板。

请开始执行 Phase {PHASE_NUMBER}。
```

## 推荐执行顺序

从 Phase 0 开始。只有当上一 Phase 的验收证据完整、测试通过、没有阻塞风险时，才进入下一 Phase。
