# Phase 1：Project Asset Skeleton / Corpus Importer

## 1. 阶段目标

建立单本小说数据骨架，支持开发态测试语料分批导入，生成章节 Markdown 和 manifest。

## 2. 本阶段要实现

- 创建 project_assets/source/generated 目标骨架。
- 实现 metadata.yaml、manuscripts/manifest.json 读写。
- 实现章节文件路径规范和安全校验。
- 实现最小 TXT/Markdown 导入器，支持 3-5 章测试语料切分。
- 实现 active data root 配置，但产品 API 不暴露多小说选择。
- 实现 generated 删除后的空重建入口 stub。

## 3. 本阶段不要实现

- 不要导入全量 662 万字。
- 不要做知识抽取。
- 不要做摘要。
- 不要做向量索引。
- 不要在产品 UI 做多小说切换。

## 4. 涉及模块

- `application/services/import_service.py`
- `application/services/chapter_service.py`
- `infrastructure/storage/markdown_backend.py`
- `infrastructure/storage/json_backend.py`
- `api/routes/chapters.py 或 manuscript.py`
- `tests/fixtures/project_assets`

## 5. 涉及数据对象

- Chapter
- ChapterManifest
- SourceRef
- ImportBatch

## 6. AI 工作流

不涉及 AI。

## 7. 验收标准

- 新建 source/generated 骨架。
- 导入 3-5 章后生成 Markdown 和 manifest。
- 原创 source 与测试语料 source 可通过开发配置隔离。
- API/Service 无 project_id/novel_id。
- 删除 generated 不影响 source。

## 8. 测试要求

- 章节标题切分测试
- 重复标题测试
- 路径安全测试
- active root 隔离测试
- generated 删除测试

## 9. 主要风险

- 章节切分规则不稳定影响 SourceRef。
- 测试语料混入原创 source。

## 10. 给 Codex 的任务拆解建议

- 实现 project_assets 路径服务。
- 实现 manifest repository。
- 实现 importer。
- 实现章节列表/读取 API。
- 补隔离 fixture 和测试。

## 11. 停止条件

- 本阶段验收标准满足后立即停止。
- 如果必须跨到下一 Phase 才能完成当前功能，先返回冲突报告。
- 如果发现需要违反不可变架构决策，立即停止。
