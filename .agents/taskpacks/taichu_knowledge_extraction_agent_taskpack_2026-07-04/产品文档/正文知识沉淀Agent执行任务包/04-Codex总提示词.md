# Codex 总提示词

> 更新日期：2026-07-04

下面提示词必须原样交给 Codex 使用。Codex 不得脱离任务包临场设计正文知识沉淀 Agent 方案。

```text
你现在是 qingluo201816/taichu 仓库的 Coding Agent。请执行“正文知识沉淀 Agent 第一版”任务。

这是太初第一个真实 LLM + LangGraph Agent。你不能重新设计产品方案，必须严格执行仓库根目录《正文知识沉淀Agent方案.md》和《产品文档/正文知识沉淀Agent执行任务包/》中的任务包。

你必须先读取：
- AGENTS.md
- docs/rule.md
- TAICHU_DESIGN.md
- 正文知识沉淀Agent方案.md
- 产品文档/正文知识沉淀Agent执行任务包/00-任务包总览.md
- 产品文档/正文知识沉淀Agent执行任务包/01-阶段任务.md
- 产品文档/正文知识沉淀Agent执行任务包/02-验收清单.md
- 产品文档/正文知识沉淀Agent执行任务包/03-证据返回模板.md
- 产品文档/正文知识沉淀Agent执行任务包/05-固定Prompt模板.md
- 产品文档/正文知识沉淀Agent执行任务包/06-运行JSON示例.md
- 产品文档/正文知识沉淀Agent执行任务包/07-API契约.md
- 产品文档/正文知识沉淀Agent执行任务包/08-数据模型与Repository契约.md
- 产品文档/正文知识沉淀Agent执行任务包/09-LangGraph节点契约.md
- 产品文档/正文知识沉淀Agent执行任务包/10-前端工作台契约.md
- 产品文档/正文知识沉淀Agent执行任务包/11-禁止事项与停止条件.md
- 产品文档/正文知识沉淀Agent执行任务包/12-测试策略.md
- 产品文档/正文知识沉淀Agent执行任务包/13-候选与知识卡示例.md

如果涉及 web/ 前端，还必须读取：
- .agents/skills/taichu-ui-components/SKILL.md

核心目标固定为：
Markdown 正文 → 候选知识卡 / 更新建议 → 作者审核 → 当前 JSON 有效知识库。

第一版只做当前章节抽取，只抽角色、地点、势力、物品。抽取结果先写入 JSON 中间态，作者逐条确认后才写入有效知识库。

第一版使用真实 LLM，但不评测文学质量，不评测写作页回答质量。评测重点是结构、链路、候选、节点状态、prompt/response、作者处理结果。

硬禁止：
1. 不引入 MongoDB。
2. 不做 RAG。
3. 不做向量库。
4. 不做 ES。
5. 不做 Neo4j。
6. 不做 GraphRAG。
7. 不做当前卷抽取。
8. 不做全书抽取。
9. 不做批量确认。
10. 不做后台队列。
11. 不做 streaming。
12. 不做复杂 LangGraph interrupt / resume。
13. 不自动写入有效知识库。
14. 不复用 /api/agents/chat。
15. 不复活旧 /chat 独立对话页。
16. 不把候选内容写入 project_assets/source/knowledge/。
17. 不修改 project_assets/source 用户数据，除非使用测试 fixture。
18. 不让用户界面显示英文内部枚举。
19. 不输出 body、tags、fields、confidence、source_refs、relations、foreshadow、personality、motivation、appearance。
20. 不让 Codex 自己临场设计 prompt；必须使用任务包固定 prompt。

阶段执行规则：
- 默认只执行用户指定的一个阶段。
- 如果用户未指定阶段，先执行 Phase 0：Preflight。
- 每个阶段完成后必须运行本阶段检查命令，按 03-证据返回模板.md 返回证据，然后停止。
- 不得在停机点前自动 commit。
- 若发现当前仓库与任务包冲突，先列出冲突并停止，不得擅自重设方案。

现在请先执行 Phase 0：Preflight / 文档与仓库状态确认。只检查，不写业务代码。完成后按证据模板返回。
```
