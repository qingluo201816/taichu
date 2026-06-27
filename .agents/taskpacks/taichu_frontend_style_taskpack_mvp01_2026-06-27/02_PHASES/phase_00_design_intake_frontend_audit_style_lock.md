# Phase 0：Design Intake / Frontend Audit / Style Lock

> 更新日期：2026-06-27

## 阶段目标

在任何样式改造前，先读取 `TAICHU_DESIGN.md`，审计当前前端，生成并让用户确认 `STYLE_LOCK.md`。

## 要实现什么

1. 扫描前端路由、组件、全局样式、package scripts。
2. 读取 `TAICHU_DESIGN.md` 和 `docs/rule.md`。
3. 输出 `STYLE_AUDIT.md`。
4. 输出 `STYLE_LOCK.md`，但不改业务代码。
5. 向用户提出必须确认的问题。

## 不要实现什么

- 不改页面样式。
- 不改组件。
- 不装依赖。
- 不新增功能。
- 不修改后端。

## 必问问题

如果 `TAICHU_DESIGN.md` 已经非常明确，可以少问，但必须确认：

1. 本次是否覆盖 `/` 当前工作台页面？
2. 是否纳入 `/entry`，还是只做入口与工作台的衔接检查？
3. 哪些页面必须在本轮改造：editor、dashboard、inbox、knowledge、chat、settings？
4. 纸质稿件层应用范围：只编辑器正文，还是正文候选卡/知识详情也使用？
5. 是否允许新增 `docs/太初前端视觉冻结说明.md`？
6. 是否允许新增/重命名样式目录，例如 `web/src/styles/`？

## STYLE_LOCK.md 必须包含

- 设计来源：`TAICHU_DESIGN.md` 的更新时间。
- 三层设计系统摘要。
- 本轮纳入页面。
- 本轮纳入组件。
- token 实现方式。
- 不改范围。
- 风险点。
- 验收方式。
- 用户确认区。

## 验收标准

- `STYLE_AUDIT.md` 存在。
- `STYLE_LOCK.md` 存在。
- 用户明确批准后才能进入 Phase 1。

## 停止条件

- 找不到 `TAICHU_DESIGN.md`。
- `TAICHU_DESIGN.md` 与用户描述不一致。
- 当前 MVP0.1 页面不存在，且无法判断改造范围。
- 用户未批准 `STYLE_LOCK.md`。
