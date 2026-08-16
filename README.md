# 太初仓库地图

> 更新日期：2026-08-15

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
| 查看通用写作智能体当前 37 条固定评测基准、落实规格、历史审计与实现验收 | `tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json`、`.sdd/specs/1.1/通用写作智能体37类Benchmark落实/`、`docs/历史/7-30通用写作AgentBenchmark完整重新审计报告.md`、`docs/历史/7-31通用写作智能体37类Benchmark落实报告.md` |
| 查看已被固定基准替换的旧效果评测历史报告 | `docs/历史/7-14通用写作助手效果评测实现报告.md` |
| 查看通用智能体后续基础设施的真实运行基线与缺口审计 | `docs/历史/7-18通用智能体后续基础设施基线报告.md` |
| 查看统一知识召回策略、独立评测与词法基线 | `docs/历史/7-18统一知识召回评测基线报告.md` |
| 查看通用 Agent 后续阶段任务包 | `docs/任务包/太初-通用Agent后续推进任务包-20260717/` |
| 查看 Milvus Vector Graph RAG、多跳推理与双来源建模设计 | `docs/已讨论功能/8-15Milvus向量图谱多跳召回决策.md` |
| 查看已被替换的旧向量召回实验 | `docs/历史/7-19向量知识召回实验报告.md` |
| 查看通用写作助手运行时记忆、上下文压缩与多轮评测报告 | `docs/历史/7-19通用写作助手运行时记忆与上下文压缩报告.md` |
| 查看太初实际使用的 LangGraph 原生能力、项目封装与冗余判断 | `docs/历史/7-26太初LangGraph原生能力与项目封装盘点.md` |
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
| 探测本地嵌入并重建 Milvus 多跳图索引 | `scripts/probe_embedding_models.py`、`scripts/rebuild_vector_graph_index.py` |

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

日常启动双击根目录 `start.bat`。它调用 `.agents/scripts/start.ps1`，依次启动或复用 MongoDB、Milvus、本地 BGE Reranker 与 Qwen Embedding，再完成固定端口清理和前后端就绪检查：

- 前端：`http://localhost:3000`
- 后端：`http://127.0.0.1:8000`
- MongoDB：`mongodb://127.0.0.1:27017`
- Milvus：`http://127.0.0.1:19530`
- Milvus 健康检查：`http://127.0.0.1:9091/healthz`
- 本地 Embedding：`http://127.0.0.1:8011/v1`

## Milvus Vector Graph RAG

当前多跳召回使用 Milvus 团队开源的 `vector-graph-rag 0.2.2`。系统把实体、关系和来源 passage 存在同一 Milvus 实例的三组集合中，通过 ID 引用扩展子图，不再维护第二个图数据库。

- 正文 Markdown 默认切成约 1000 字符的子块，目标重叠 200 字符；下一片起点优先对齐段落，其次对齐完整句首，并保留章节、子块序号、字符区间和来源引用。
- 每张 MongoDB `lifecycle=confirmed` 知识卡形成一个完整 passage，不再拆成身份、摘要和类型字段三个向量。
- 两类 passage 一起抽取实体和关系，因此可以沿“正文事实 → 桥接实体 → 知识卡设定”或反向路径完成多跳召回。
- `retrieve_story_graph` 是生产只读 Tool，只返回关系链与可追溯证据，最终答案仍由高层编排 Agent 生成。
- Milvus 仍是可删除、可重建的派生层；Markdown 与 MongoDB 的事实源地位不变。

生产查询由 Milvus 单库完成第一阶段混合检索：中文 BM25 Top 30 与经 Vector Graph 多跳关系增强的 HNSW Dense Top 30，通过 Milvus 原生 `RRFRanker(k=60)` 融合为 30 条候选，再由 `BAAI/bge-reranker-v2-m3` 重排到 Top 10。HNSW 参数固定为 `M=24`、`efConstruction=300`、`efSearch=150`。

BGE Top 10 之后，正文命中以当前子块为中心按需读取前一块和后一块，按原文字符区间去重合并为补充上下文；章节首尾只读取实际存在的两个子块，且不跨章节。邻块不参与 BM25、ANN、图关系抽取或 BGE 重排，命中子块与补充上下文在 Tool 返回契约中保持独立来源字段。

运行组件：

| 组件 | 版本或模型 | 位置 |
|---|---|---|
| Milvus Standalone | `milvusdb/milvus:v2.6.9` | Docker Compose，入口 `127.0.0.1:19530` |
| Vector Graph RAG | `vector-graph-rag 0.2.2` | 由 `uv.lock` 固定 |
| Qwen Embedding | `Qwen3-Embedding-4B-Q4_K_M.gguf`，2560 维 | `E:\Taichu\Models\Qwen3-Embedding-4B\` |
| BGE Reranker | `BAAI/bge-reranker-v2-m3` | Hugging Face TEI CPU 服务，入口 `127.0.0.1:8012` |
| llama.cpp | `b10066` Windows Vulkan x64 | `E:\Taichu\Runtime\llama.cpp\b10066` |

实体/关系抽取、查询实体识别和关系重排全部通过太初统一 `LLMGatewayContract` 调用，复用现有 RightCode 密钥、模型目录、Responses/Anthropic 协议转换、用量审计和降级策略，不再维护 Vector Graph RAG 专用密钥或地址。`.env` 中的 `VECTOR_GRAPH_LLM_MODEL` 只负责选择模型，当前使用 `deepseek-v4-pro`；本地 Qwen Embedding 只负责向量化。

## 阶段 04 运行时记忆与上下文压缩

通用写作助手以一个侧栏“新对话”窗口对应一个 `conversation_id（会话标识）`；窗口内每次用户请求各自产生一个 `run_id（运行标识）` 和递增的 `request_index（请求序号）`。只要用户没有点击“新对话”，后续请求始终续接同一会话。旧运行会按共同 `task_id（任务标识）` 归并，避免把同一窗口错误拆成多条最近对话。

`ContextAssembler（上下文组装器）` 从第一次请求开始生成“稳定背景、工作记忆、相关记忆、过程历史、当前请求”五层上下文。运行记忆保存在 `project_assets/derived/general_agent_memory/`，由 Runtime 自动写入和按请求序号过期，不设作者确认生命周期；章节和长资源只保存摘要与来源引用。总预算不足时按“相关记忆 → 过程历史 → 工作记忆 → 稳定背景”收缩，当前请求完整保留，无法容纳时明确拒绝而不是静默截断。

外层运行图使用 LangGraph 节点检查点，持久化在 `project_assets/derived/general_agent_graph_checkpoints/`；异常或重启后以同一 `run_id` 恢复待执行节点，不重跑已成功图节点。工作台只读展示自动运行记忆及其来源，不提供单条记忆的手动新增、修改或删除入口；作者只通过正常对话或人工介入节点影响 Agent。任务监控可查看本次记忆数量、压缩状态、Token 估算和恢复差异。完整实现与验证证据见 `docs/历史/7-19通用写作助手运行时记忆与上下文压缩报告.md`。

### 日常检查

正常情况下只需运行 `start.bat`，不需要重复下载。也可以手动检查：

```powershell
Invoke-WebRequest http://127.0.0.1:9091/healthz -UseBasicParsing
Invoke-RestMethod http://127.0.0.1:8011/health
Invoke-RestMethod http://127.0.0.1:8011/v1/models
docker ps --filter name=taichu-milvus
Invoke-RestMethod http://127.0.0.1:8012/health
uv run python scripts/probe_embedding_models.py
uv run python scripts/rebuild_vector_graph_index.py --dry-run
```

### 索引重建与专项评测

```powershell
# 只核对章节数、正文片段数、知识卡数和快照，不写 Milvus
uv run python scripts/rebuild_vector_graph_index.py --dry-run

# 全量重建实体、关系和 passage 集合
uv run python scripts/rebuild_vector_graph_index.py

```

全量重建会从当前正文 Markdown 和 MongoDB 已确认知识卡重新生成派生图索引。构建完成后，摘要清单写入 `project_assets/generated/milvus_vector_graph/active_manifest.json`；清单不保存正文、知识卡或向量。

### 全新机器的下载方式

Milvus 使用仓库内的官方 Standalone 组件编排。一般由 `start.bat` 自动拉取并启动；也可手动执行：

```powershell
docker compose -f infra/milvus/docker-compose.yml up -d
docker compose -f infra/reranker/docker-compose.yml up -d
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

完整数据模型、多跳流程和索引约束见 `docs/已讨论功能/8-15Milvus向量图谱多跳召回决策.md`。

## 本机外部数据位置

以下内容在仓库外，不应重新复制到根目录：

| 内容 | 本机位置 | 说明 |
|---|---|---|
| MongoDB 数据 | `E:\Taichu\MongoDB\data\db` | 当前唯一结构事实存储位置 |
| MongoDB 日志 | `E:\Taichu\MongoDB\log` | MongoDB 本地运行日志 |
| Milvus 多跳图索引 | Docker 命名卷 `taichu_milvus_data`、`taichu_milvus_etcd`、`taichu_milvus_minio` | 可从正文 Markdown 与 MongoDB confirmed 卡重建的派生索引 |
| BGE Reranker 模型 | `E:\Taichu\Models\bge-reranker-v2-m3` | 本地重排模型权重，不是小说事实源 |
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
- Milvus 只保存可重建的实体、关系和来源 passage 索引；命中内容必须携带正文区间或知识卡来源引用，不能反向成为事实源。
- SQLite/FTS 已废弃，不参与后续架构决策；Milvus 向量、BM25、图索引及未来缓存都只能作为可重建派生层。

更完整的物理目录职责以 `project_assets/readme.md` 为准。
