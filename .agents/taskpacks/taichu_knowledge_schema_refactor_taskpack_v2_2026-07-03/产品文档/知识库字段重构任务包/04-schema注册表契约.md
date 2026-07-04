更新日期：2026-07-03


# 后端 schema 注册表契约

## 目标

后端必须维护每种知识卡的 schema 注册表。前端通过 schema 渲染编辑表单，不把字段结构写死在前端。

## schema 字段

每个字段配置至少包括：

| 配置项 | 说明 |
|---|---|
| `field_key` | 字段键名，正式英文 |
| `label` | 中文展示名 |
| `field_type` | 文本、长文本、枚举、数字、布尔、章节引用、知识卡引用、数组、记录数组 |
| `required_when_active` | 标记有效时是否必填 |
| `options` | 枚举选项 |
| `placeholder` | 输入提示 |
| `display_group` | 编辑界面分组 |
| `list_display` | 是否在收缩条目中展示 |
| `ai_usage` | 供 AI 检索时的用途提示 |

## 禁止规则

schema 注册表里不得注册这些字段：

```text
body
tags
fields
confidence
source_refs
relations
personality
motivation
appearance
```

schema 注册表不得包含 `foreshadow` 类型。

## required_when_active 第一版建议

通用字段：

| 字段 | required_when_active |
|---|---|
| `name` | true |
| `summary` | true |
| `source_origin` | true |
| `source_note` | true |

类型字段第一版原则上不强制必填，避免作者新建知识卡成本过高。

## 前端渲染分组建议

通用字段分组：

```text
基础信息：name, aliases, summary, importance, status
来源：source_origin, source_note
```

类型字段分组：

```text
类型字段：按当前知识类型 schema 展示
```

禁止创建「高级字段」分组来塞入被取消字段。

## API 建议

建议提供：

```text
GET /api/knowledge/schemas
GET /api/knowledge/schemas/{type}
```

返回所有支持类型及字段定义。前端创建和编辑表单必须以该 schema 为准。
