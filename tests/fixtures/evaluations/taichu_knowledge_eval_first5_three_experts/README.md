# 太初前5章知识抽取评估样本（三专家版）

来源路径：`project_assets/source/manuscripts/chapters/volume_001_第一卷`。
范围：第1章到第5章。

目录说明：
- `single_chapter/chapter_001` 到 `chapter_005`：逐章独立抽取结果，允许同一实体在不同章节重复出现，用于评估单章抽取能力。
- `batch_001_005`：第1—5章综合抽取结果，已做同名/同指代合并，用于评估批量抽取、去重、更新与 first_seen/last_seen。
- 每个 scope 下按三个专家拆分：
  - `character_expert`：character。
  - `entity_expert`：location / faction / item。
  - `worldview_expert`：realm / technique / rule / event。
- `cards/*.json` 为严格知识卡字段；`evidence_index.json` 为评估用证据回放，不写入正式知识卡。

重要校准：
- 本包只使用前5章信息。
- 因此没有把“徐羽女性身份”“张狂紫种”“李靖紫种”等后续章节信息写入前5章综合卡。
- `白玉瓶` 在第5章信息不足，放入 ignored，建议等第6章与涎灵草一起判断。
