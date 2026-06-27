# 测试策略

> 更新日期：2026-06-27

## 自动检查

优先运行：

```text
cd web
npm run lint
npm run build
npm run test:editor
```

若脚本不存在，以 `web/package.json` 为准。

## 手动检查

至少检查：

- `/`
- `/editor`
- `/dashboard`
- `/knowledge`
- `/chat`
- `/entry`，如果存在
- 其他 `STYLE_LOCK.md` 纳入页面

## 编辑器专项

- 中文输入。
- 选中文本。
- AI 触发入口是否仍可见。
- 保存状态是否仍可见。
- 长章节滚动。
- 标题、段落、引用、分割线。

## 卡片专项

- 正文候选卡。
- 建议卡。
- 待确认设定卡。
- 证据卡。
- 灵感卡。
- 操作按钮 focus/hover/disabled。

## 可访问性

- Tab 顺序。
- focus-visible。
- reduced motion。
- 文本对比度。
- 窄屏不遮挡关键操作。

## 回归重点

样式任务不得破坏业务功能。若测试中发现业务功能破坏，优先回退样式改动，不要改业务逻辑修样式问题。
