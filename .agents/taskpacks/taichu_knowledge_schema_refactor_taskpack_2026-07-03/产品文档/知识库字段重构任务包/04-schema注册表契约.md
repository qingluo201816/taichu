# 后端 Schema 注册表契约

更新日期：2026-07-03

## 1. 目标

后端维护每种知识卡的字段 schema，前端通过 schema 动态渲染表单。不要把每种知识卡的字段结构写死在前端。

## 2. Schema 字段

每个字段 schema 至少包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| field_key | string | 英文字段名 |
| label | string | 中文展示名 |
| field_type | enum | 字段类型 |
| required_when_active | boolean | 标记有效时是否必填 |
| options | array | 枚举选项 |
| placeholder | string | 输入提示 |
| display_group | string | 编辑界面分组 |
| list_display | boolean | 是否在收缩列表中展示 |
| ai_usage | string | 供后续 AI 检索时理解字段用途 |

## 3. 字段类型

第一版支持：

| field_type | 含义 |
|---|---|
| text | 短文本 |
| long_text | 长文本 |
| enum | 枚举 |
| number | 数字 |
| boolean | 布尔 |
| chapter_ref | 章节引用 |
| knowledge_ref | 知识卡引用 |
| string_array | 字符串数组 |
| record_array | 记录数组 |

## 4. 分组建议

实现默认分组：

| 分组键 | 用户可见中文名 |
|---|---|
| basic | 基础信息 |
| type_fields | 类型字段 |
| state_records | 状态记录 |
| source | 来源说明 |

## 5. API 建议

可以按仓库现有风格调整，但建议提供：

```text
GET /api/knowledge/types
GET /api/knowledge/schemas
GET /api/knowledge/schemas/{type}
```

返回内容必须包含用户可见中文 label，但字段键名必须是正式英文。

## 6. 前端渲染规则

前端根据 schema：

1. 选择输入控件。
2. 显示中文 label。
3. 显示 placeholder。
4. 根据 display_group 分组。
5. 根据 list_display 控制列表展示。
6. 对 `chapter_ref` 使用章节选择器。
7. 对 `knowledge_ref` 使用知识卡选择器。
8. 对 `record_array` 使用可增删的记录列表。

前端不得把英文内部枚举、字段名、field_type 直接展示给用户。
