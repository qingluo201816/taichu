# API 契约

> 更新日期：2026-07-04

## 1. 接口前缀

```text
/api/agent-workbench/knowledge-extraction
```

第一版接口只做运行、详情、候选审核三类。metrics、nodes、llm_calls 包含在 run detail 中，不单独拆 metrics/logs API。

## 2. 创建运行

```text
POST /api/agent-workbench/knowledge-extraction/runs
```

请求：

```json
{
  "chapter_id": "chapter_0012",
  "model_name": null,
  "force": false
}
```

响应：

```json
{
  "run": {
    "run_id": "extract_run_20260704_153022_a1b2c3",
    "agent_name": "knowledge_extraction",
    "status": "completed",
    "chapter_id": "chapter_0012",
    "chapter_title": "第12章 xxx",
    "candidate_count": 8,
    "pending_count": 8,
    "confirmed_count": 0,
    "rejected_count": 0,
    "started_at": "2026-07-04T15:30:22+09:00",
    "finished_at": "2026-07-04T15:30:58+09:00"
  }
}
```

规则：

```text
1. 第一版同步执行。
2. 无 streaming。
3. 无后台队列。
4. 只允许当前章节。
5. LLM 配置缺失时返回中文错误，并记录 failed run 或清晰错误响应。
```

## 3. 运行列表

```text
GET /api/agent-workbench/knowledge-extraction/runs?page=1&page_size=20&status=all
```

status 可选：

```text
all
pending
running
completed
failed
```

前端显示中文：

```text
全部
等待中
运行中
已完成
失败
```

## 4. 运行详情

```text
GET /api/agent-workbench/knowledge-extraction/runs/{run_id}
```

必须返回完整 run detail，包括：

```text
run
nodes
llm_calls
raw_candidates
typed_candidates
review_items
metrics
errors
```

## 5. 候选列表

```text
GET /api/agent-workbench/knowledge-extraction/runs/{run_id}/candidates?status=pending&action=all
```

status 可选：

```text
all
pending
confirmed
rejected
deferred
```

action 可选：

```text
all
create_card
update_card
conflict
ignore
```

前端必须映射中文，不得显示英文枚举。

## 6. 确认候选

```text
POST /api/agent-workbench/knowledge-extraction/candidates/{candidate_id}/confirm
```

规则：

```text
create_card：把 suggested_card 写成 active 知识卡。
update_card：只补充已有 active 卡的空字段，或追加 source_note；不覆盖已有非空字段。
conflict：不允许直接 confirm，必须 edit-confirm。
ignore：不允许 confirm。
```

## 7. 编辑后确认

```text
POST /api/agent-workbench/knowledge-extraction/candidates/{candidate_id}/edit-confirm
```

请求：

```json
{
  "card_updates": {
    "name": "秦浩轩",
    "summary": "作者编辑后的摘要"
  },
  "target_card_id": null
}
```

规则：

```text
1. card_updates 必须通过知识卡 schema 校验。
2. 若 target_card_id 存在，只能 patch active 卡。
3. 不允许覆盖已有非空字段，除非 edit-confirm 明确包含作者覆盖动作字段；第一版默认不支持覆盖已有非空字段。
4. 更新 source_note 时采用追加方式，并保留原来源说明。
```

## 8. 废弃候选

```text
POST /api/agent-workbench/knowledge-extraction/candidates/{candidate_id}/reject
```

规则：

```text
candidate_status = rejected
author_action = reject
不删除 run 文件
不删除候选记录
```

## 9. 稍后处理

```text
POST /api/agent-workbench/knowledge-extraction/candidates/{candidate_id}/defer
```

规则：

```text
candidate_status = deferred
author_action = defer
不删除候选记录
```

## 10. 错误响应

所有用户可见错误必须是中文。例如：

```json
{
  "error": {
    "code": "chapter_not_found",
    "message": "未找到指定章节。"
  }
}
```

不得把 Python 异常、英文内部枚举或 stack trace 暴露给用户。
