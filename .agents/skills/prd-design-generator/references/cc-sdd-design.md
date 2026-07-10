# cc-sdd 技术设计规则

## 输入

- 已审批的 `requirements.md`。
- 当前代码和根目录 `AGENTS.md`。
- 涉及前端时读取根目录 `DESIGN.md` 和 `taichu-ui-components` Skill。

## 输出

生成中文 `design.md`，至少说明：

1. 目标与非目标。
2. 受影响的 API、应用、领域、基础设施、前端和数据目录。
3. 数据结构、接口契约与状态流转。
4. 依赖方向和扩展边界。
5. 旧实现与旧配置清理范围。
6. 测试、静态检查、启动或页面验证方式。

完成后将 `spec.json.stage` 更新为 `design`。只有用户审批后才能设置 `approvals.design.completed=true`。

## 设计评审

检查需求覆盖、单本小说边界、分层依赖、数据事实源、旧实现清理和验证命令。评审结论必须列出阻塞问题、非阻塞风险和建议修正。
