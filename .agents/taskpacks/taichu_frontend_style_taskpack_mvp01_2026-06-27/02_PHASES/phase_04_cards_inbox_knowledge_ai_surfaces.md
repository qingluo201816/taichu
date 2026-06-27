# Phase 4：Cards / Inbox / Knowledge / AI Surfaces

> 更新日期：2026-06-27

## 阶段目标

统一 AI 卡片、收件箱、知识库、证据展示等产品核心表面，让它们符合深色工作台层，并能清晰区分正文候选、建议、待确认设定、证据、灵感等状态。

## 要实现什么

1. AIResultCard 视觉统一。
2. TextCandidateCard 使用纸质稿件层或纸质片段风格。
3. SuggestionCard / IdeaCard 使用深色信息卡。
4. PendingFactCard 状态明确，不能看成已确认事实。
5. EvidenceCard 来源清楚、可扫读。
6. Inbox 页面形成轻量看板/列表风格。
7. Knowledge 页面形成知识卡列表 + 详情阅读风格。
8. 空态、错误态、加载态统一。

## 不要实现什么

- 不改 AI 卡片状态机。
- 不改 PendingFact 确认逻辑。
- 不改 Knowledge 数据结构。
- 不改 Retrieval API。
- 不做复杂项目管理看板。

## 涉及模块

- `web/src/components/ai-card/**`，若存在
- `web/src/components/inbox/**`，若存在
- `web/src/components/knowledge/**`，若存在
- `web/src/app/inbox/**`
- `web/src/app/knowledge/**`
- `web/src/app/editor/**` 右侧 AI 面板
- `web/src/app/chat/**` 输出区域

## 验收标准

- 不同卡片类型视觉可区分。
- 待确认设定和已确认知识不会混淆。
- 来源证据可见。
- 卡片操作按钮可见、可聚焦。
- 收件箱不变成复杂项目管理软件。
- 知识库详情适合阅读长设定。

## 测试要求

- 手动构造/使用 mock 卡片。
- 检查各状态：generated、inserted、saved、pending、confirmed、ignored、discarded。
- 检查键盘 focus。
- 检查窄屏滚动。

## 主要风险

- 卡片类型太多导致视觉混乱。
- 状态色过重。
- 重要操作藏得太深。
- 证据卡不够可信。

## 给 Codex 的任务拆解

1. 查找现有 card 组件。
2. 先抽共用 CardShell。
3. 给每类卡片应用 token 和状态样式。
4. 改页面容器和列表密度。
5. 保留所有 action callback 和数据 props。
