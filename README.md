# 太初仓库地图

> 更新日期：2026-07-20

太初是面向个人作者的单本玄幻长篇 AI 写作工作台。本文件只回答两件事：仓库每个区域负责什么，以及想找某类资料应该去哪里。

## 最常用入口

| 我想做什么 | 去哪里 |
|---|---|
| 查看 Codex 必须遵守的项目规则 | `AGENTS.md` |
| 修改当前前端视觉、布局或交互 | `DESIGN.md` |
| 查看当前入口页状态与历史点云备份位置 | `docs/前端风格/7-11入口页状态说明.md` |
| 查看前端主题的精确实现 | `web/src/components/theme/`、`web/src/app/globals.css` |
| 查看全部项目级 Skills | `.agents/索引.md` |
| 查看 Skill 编写规则 | `.agents/skills/rule.md` |
| 查看某个 Skill | `.agents/skills/{名称}/SKILL.md` |
| 启动规格驱动开发 | `$codex-sdd`，规则位于 `.agents/skills/codex-sdd/` |
| 查看后端和系统架构设想 | `docs/临时架构/7-10太初系统架构图.md` |
| 查看通用写作助手 Agent 的已确认架构决策 | `docs/已讨论功能/7-13通用写作助手智能体架构与能力演进决策.md` |
| 查看子 Agent 结构化执行器形态与升级评测决策 | `docs/已讨论功能/7-20子Agent结构化执行器与升级评测决策.md` |
| 查看已实现的第一版 Tool、子 Agent 能力边界与后续调优项 | `docs/临时架构/7-13工具与子智能体能力层技术设计.md` |
| 查看通用写作助手能力层实现与验证报告 | `docs/历史/7-13通用写作助手能力层实现报告.md` |
| 查看通用 Agent Runtime 已实现后端边界与后续技术设计 | `docs/临时架构/7-13通用智能体运行时编排技术设计.md` |
| 查看通用 Agent 全链路、上下文、能力调用、恢复与纠偏排查地图 | `docs/临时架构/7-20通用Agent运行链路上下文与能力调用排查地图.md` |
| 查看通用 Agent Runtime 实现与验证报告 | `docs/历史/7-14通用写作助手运行时实现报告.md` |
| 查看通用写作助手作者工作台实现与验证报告 | `docs/历史/7-14通用写作助手工作台实现报告.md` |
| 查看通用写作助手节点监控实现与验证报告 | `docs/历史/7-14通用写作助手节点监控实现报告.md` |
| 查看通用写作助手效果评测、评测集与参考答案实现报告 | `docs/历史/7-14通用写作助手效果评测实现报告.md` |
| 查看通用智能体后续基础设施的真实运行基线与缺口审计 | `docs/历史/7-18通用智能体后续基础设施基线报告.md` |
| 查看统一知识召回策略、独立评测与词法基线 | `docs/历史/7-18统一知识召回评测基线报告.md` |
| 查看通用 Agent 后续阶段任务包 | `docs/任务包/太初-通用Agent后续推进任务包-20260717/` |
| 查看 Qdrant 与本地 Qwen 向量能力设计和实机记录 | `docs/临时架构/7-18向量知识召回技术设计.md` |
| 查看独立向量召回三次评测与融合 HOLD 结论 | `docs/历史/7-19向量知识召回实验报告.md` |
| 查看通用写作助手运行时记忆、上下文压缩与多轮评测报告 | `docs/历史/7-19通用写作助手运行时记忆与上下文压缩报告.md` |
| 查看知识沉淀智能体效果评估设计 | `docs/临时架构/7-11知识沉淀智能体效果评估方案.md` |
| 查看知识沉淀智能体效果评估的使用报告 | `docs/历史/7-11知识沉淀智能体效果评估使用报告.md` |
| 核对真实后端代码分层 | `src/taichu/api/`、`src/taichu/application/`、`src/taichu/domain/`、`src/taichu/infrastructure/` |
| 查看本地数据态目录结构 | `project_assets/readme.md` |
| 查看当前结构化字段和状态 | `src/taichu/domain/models/` |
| 查看 API 输入输出 | `src/taichu/api/schemas/` |
| 查看存储与检索契约 | `src/taichu/application/contracts/` |
| 查看当前产品需求草案 | `docs/临时产品文档/6-30太初当前产品需求.md` |
| 查看其他未确认产品设想 | `docs/临时产品文档/` |
| 查看已讨论的功能、需求与决策 | `docs/已讨论功能/` |
| 查看历史快照 | `docs/历史/` |
| 查看测试与评测样本 | `tests/`、`tests/fixtures/evaluations/` |
| 安全探测 Right Code 模型名称与协议 | `.agents/scripts/probe_rightcode_models.py` |
| 探测、重建和评测独立知识向量能力 | `scripts/probe_embedding_models.py`、`scripts/rebuild_knowledge_vector_index.py`、`python -m taichu.application.evaluations.retrieval.cli` |

`docs/临时架构/` 和 `docs/临时产品文档/` 可能包含未实现、只实现一部分或已经被代码超越的内容。开发前必须以当前代码、`AGENTS.md` 和数据目录说明复核，不得把临时文档直接当作已落地事实。

## 仓库目录

```text
Taichu/
├── AGENTS.md                 # Codex 项目硬规则
├── README.md                 # 本仓库地图
├── DESIGN.md                 # 当前前端唯一设计规则
├── .env.example              # 环境变量示例
├── .gitignore                # Git 忽略规则
├── .python-version           # Python 版本提示
├── pyproject.toml            # Python 项目与 uv 依赖
├── uv.lock                   # Python 依赖锁文件，应提交 Git
├── start.bat                 # Windows 一键启动入口
├── .agents/                  # Codex Skills、开发工作流与维护脚本
├── .codex/                   # 项目级 Codex 自定义 Agent 与多 Agent 配置
├── .sdd/                     # 按需生成的 codex-sdd 规格、状态与验证证据
├── docs/                     # 文档规则、临时资料、参考资料和历史快照
├── project_assets/           # 当前单本小说的数据态资产
├── scripts/                  # 可显式运行的向量探测与索引维护命令
├── src/                      # FastAPI 后端代码
├── tests/                    # 后端测试和评测夹具
└── web/                      # Next.js 前端代码
```

`prd-docs/` 只在用户明确提供 PRD 输入时按需创建，用作输入暂存目录；仓库不使用 `.gitkeep` 保存空目录。规格流程通过 `$codex-sdd` 启动，运行状态与产物写入 `.sdd/specs/{版本号}/{大需求模块名称}/`。

## 运行方式

首次准备依赖：

```powershell
uv sync
cd web
npm install
```

日常启动双击根目录 `start.bat`。它调用 `.agents/scripts/start.ps1`，依次启动或复用 MongoDB、Qdrant、本地 Qwen Embedding，再完成固定端口清理和前后端就绪检查：

- 前端：`http://localhost:3000`
- 后端：`http://127.0.0.1:8000`
- MongoDB：`mongodb://127.0.0.1:27017`
- Qdrant REST：`http://127.0.0.1:6333`
- Qdrant 控制台：`http://127.0.0.1:6333/dashboard`
- 本地 Embedding：`http://127.0.0.1:8011/v1`

## 阶段 02 独立向量基础设施

当前已经把基础设施和独立业务链路真实落到本机：

- **Qdrant** 是向量数据库，负责保存和检索可重建的知识向量索引。
- **Qwen3-Embedding-4B** 是本地向量模型，负责把中文查询和知识片段转换为 2560 维向量；由 llama.cpp 在 RTX 4080 SUPER 上运行，不调用官方云端 API，也不需要模型 API Key。
- **knowledge_vector** 是只供召回专项评测显式调用的独立向量后端；它不会注册到生产 `retrieval_service`。

这不代表向量已经替换或融合词法召回。当前生产默认仍是 `mongo_lexical`；独立 `knowledge_vector` 已用同一套60条专项题完成三次稳定对比。由于任务包要求“语义改写 Recall@5 比词法提升至少8个百分点”，而词法基线已经是100%，融合结论为 `HOLD_HYBRID_QUALITY`，阶段03暂不接入。独立向量能力、索引和评测入口继续保留。

### 已安装版本和位置

| 组件 | 版本或模型 | 本机位置 |
|---|---|---|
| Qdrant | `qdrant/qdrant:v1.18.3` | Docker 容器 `taichu-qdrant`，命名卷 `taichu_qdrant_data` |
| Qdrant Python 客户端 | `qdrant-client 1.18.0` | 由 `uv.lock` 锁定在项目虚拟环境 |
| llama.cpp | `b10066` Windows Vulkan x64 | `E:\Taichu\Runtime\llama.cpp\b10066` |
| Qwen Embedding | `Qwen3-Embedding-4B-Q4_K_M.gguf` | `E:\Taichu\Models\Qwen3-Embedding-4B\` |
| Embedding 日志 | 标准输出与错误日志 | `E:\Taichu\Embedding\log` |

模型文件 SHA-256：

```text
2b0cf8f17b4c723c27303015383c27ec4bf2d8314bb677d05e920dd70bb0f16b
```

Qdrant active alias 为 `taichu_knowledge_vectors`。当前索引由57张 MongoDB confirmed 卡投影为161个片段，active alias 指向校验通过的物理集合；清单位于 `project_assets/generated/vector_indexes/knowledge_cards/`。Qdrant 载荷不保存完整知识卡，命中后必须回读 MongoDB 当前 confirmed 卡。

## 阶段 04 运行时记忆与上下文压缩

通用写作助手以一个侧栏“新对话”窗口对应一个 `conversation_id（会话标识）`；窗口内每次用户请求各自产生一个 `run_id（运行标识）` 和递增的 `request_index（请求序号）`。只要用户没有点击“新对话”，后续请求始终续接同一会话。旧运行会按共同 `task_id（任务标识）` 归并，避免把同一窗口错误拆成多条最近对话。

`ContextAssembler（上下文组装器）` 从第一次请求开始生成“稳定背景、工作记忆、相关记忆、过程历史、当前请求”五层上下文。运行记忆保存在 `project_assets/derived/general_agent_memory/`，由 Runtime 自动写入和按请求序号过期，不设作者确认生命周期；章节和长资源只保存摘要与来源引用。总预算不足时按“相关记忆 → 过程历史 → 工作记忆 → 稳定背景”收缩，当前请求完整保留，无法容纳时明确拒绝而不是静默截断。

外层运行图使用 LangGraph 节点检查点，持久化在 `project_assets/derived/general_agent_graph_checkpoints/`；异常或重启后以同一 `run_id` 恢复待执行节点，不重跑已成功图节点。工作台可查看和删除自动运行记忆，任务监控可查看本次记忆数量、压缩状态、Token 估算和恢复差异。完整实现与验证证据见 `docs/历史/7-19通用写作助手运行时记忆与上下文压缩报告.md`。

### 日常检查

正常情况下只需运行 `start.bat`，不需要重复下载。也可以手动检查：

```powershell
Invoke-WebRequest http://127.0.0.1:6333/healthz -UseBasicParsing
Invoke-RestMethod http://127.0.0.1:8011/health
Invoke-RestMethod http://127.0.0.1:8011/v1/models
docker ps --filter name=taichu-qdrant
uv run python scripts/probe_embedding_models.py
uv run python scripts/rebuild_knowledge_vector_index.py --verify-only
```

### 索引重建与专项评测

```powershell
# 只核对待构建卡片数、片段数和快照，不写 Qdrant
uv run python scripts/rebuild_knowledge_vector_index.py --dry-run

# 全量构建新物理集合，校验成功后原子切换 active alias
uv run python scripts/rebuild_knowledge_vector_index.py

# 同一60题分别运行词法和独立向量，并重复三次
uv run python -m taichu.application.evaluations.retrieval.cli --strategy both --repeat 3
```

重建失败不会切换 active alias；清单写入失败会回滚到旧集合。专项向量评测禁止把回退到词法的结果当成向量效果证据。

### 全新机器的下载方式

Qdrant 使用官方 Docker 镜像。以下命令只用于新机器首次安装；当前机器已经完成：

```powershell
docker pull qdrant/qdrant:v1.18.3
docker volume create taichu_qdrant_data
docker run -d --name taichu-qdrant --restart unless-stopped `
  -p 127.0.0.1:6333:6333 `
  -p 127.0.0.1:6334:6334 `
  -v taichu_qdrant_data:/qdrant/storage `
  qdrant/qdrant:v1.18.3
```

Qwen 模型优先从官方 Hugging Face 仓库按提交号下载：

```powershell
uvx --from huggingface_hub hf download `
  Qwen/Qwen3-Embedding-4B-GGUF `
  Qwen3-Embedding-4B-Q4_K_M.gguf `
  --revision f4602530db1d980e16da9d7d3a70294cf5c190be `
  --local-dir E:\Taichu\Models\Qwen3-Embedding-4B
```

本机 Hugging Face 直连当时不可用，因此实际从 Qwen 官方魔搭仓库下载同一个文件：

```powershell
New-Item -ItemType Directory -Force E:\Taichu\Models\Qwen3-Embedding-4B
curl.exe --ssl-no-revoke --fail --location `
  --output E:\Taichu\Models\Qwen3-Embedding-4B\Qwen3-Embedding-4B-Q4_K_M.gguf `
  https://www.modelscope.cn/models/Qwen/Qwen3-Embedding-4B-GGUF/resolve/master/Qwen3-Embedding-4B-Q4_K_M.gguf
Get-FileHash -Algorithm SHA256 `
  E:\Taichu\Models\Qwen3-Embedding-4B\Qwen3-Embedding-4B-Q4_K_M.gguf
```

llama.cpp 使用官方 GitHub 的固定版本 Vulkan 构建：

```powershell
New-Item -ItemType Directory -Force E:\Taichu\Runtime\llama.cpp
curl.exe --ssl-no-revoke --fail --location `
  --output E:\Taichu\Runtime\llama.cpp\llama-b10066-bin-win-vulkan-x64.zip `
  https://github.com/ggml-org/llama.cpp/releases/download/b10066/llama-b10066-bin-win-vulkan-x64.zip
Expand-Archive `
  E:\Taichu\Runtime\llama.cpp\llama-b10066-bin-win-vulkan-x64.zip `
  E:\Taichu\Runtime\llama.cpp\b10066
```

llama.cpp 依赖最新 Microsoft Visual C++ x64 运行库。本机已升级为 `14.51.36247.0`；若其他机器启动时报 `MSVCP140.dll`，安装[微软官方 x64 运行库](https://aka.ms/vc14/vc_redist.x64.exe)。

完整选型、哈希、实测数据和后续索引约束见 `docs/临时架构/7-18向量知识召回技术设计.md`。

## 本机外部数据位置

以下内容在仓库外，不应重新复制到根目录：

| 内容 | 本机位置 | 说明 |
|---|---|---|
| MongoDB 数据 | `E:\Taichu\MongoDB\data\db` | 当前唯一结构事实存储位置 |
| MongoDB 日志 | `E:\Taichu\MongoDB\log` | MongoDB 本地运行日志 |
| Qdrant 向量索引 | Docker 命名卷 `taichu_qdrant_data` | 可删除、可从 MongoDB confirmed 卡重建的派生索引 |
| Qwen Embedding 模型 | `E:\Taichu\Models\Qwen3-Embedding-4B` | 本地 GGUF 模型，不是小说事实源 |
| llama.cpp 运行时 | `E:\Taichu\Runtime\llama.cpp\b10066` | 本地模型服务程序 |
| Embedding 日志 | `E:\Taichu\Embedding\log` | 本地推理服务日志，不保存为知识事实 |
| 原小说导入资料 | `E:\Taichu\导入资料\太初原小说` | PDF、EPUB、TXT 原始导入包 |
| 旧知识 JSON 迁移备份 | `E:\Taichu\迁移备份\知识库-20260711-151915` | 88 张旧卡和迁移清单的只读备份 |

原小说导入包只是外部导入材料。太初当前正文的文本事实源仍是 `project_assets/source/manuscripts/chapters/` 下的 Markdown。

## 数据边界

- Markdown 是唯一文本事实源。
- MongoDB `taichu.knowledge_cards` 是唯一结构事实源；默认事实查询只使用 `lifecycle=confirmed` 的记录。
- 旧知识迁移已备份 88 张 JSON：58 张有效卡导入为 `confirmed`，30 张已弃用重复卡只保留在 E 盘备份中。
- 迁移 `finalize` 已完成，`project_assets/source/knowledge/` 已删除；存储骨架和业务代码不得重新创建它。
- AI、Agent、评测和 Inbox 保存的 JSON/JSONL 仅是候选、运行、审计或工作区中间态；只有经过校验和作者确认的结构事实才能写入 MongoDB。
- Qdrant 只是可重建派生索引；命中结果必须按 `card_id` 回读 MongoDB 当前 confirmed 卡，不能反向成为事实源。
- SQLite/FTS 已废弃，不参与后续架构决策；未来若增加向量、Elasticsearch、图索引或缓存，也只能作为可重建派生层。

更完整的物理目录职责以 `project_assets/readme.md` 为准。
