# 太初仓库地图

> 更新日期：2026-07-18

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
| 查看后端和系统架构设想 | `docs/临时架构/7-10太初系统架构图.md` |
| 查看通用写作助手 Agent 的已确认架构决策 | `docs/已讨论功能/7-13通用写作助手智能体架构与能力演进决策.md` |
| 查看已实现的第一版 Tool、子 Agent 能力边界与后续调优项 | `docs/临时架构/7-13工具与子智能体能力层技术设计.md` |
| 查看通用写作助手能力层实现与验证报告 | `docs/历史/7-13通用写作助手能力层实现报告.md` |
| 查看通用 Agent Runtime 已实现后端边界与后续技术设计 | `docs/临时架构/7-13通用智能体运行时编排技术设计.md` |
| 查看通用 Agent Runtime 实现与验证报告 | `docs/历史/7-14通用写作助手运行时实现报告.md` |
| 查看通用写作助手作者工作台实现与验证报告 | `docs/历史/7-14通用写作助手工作台实现报告.md` |
| 查看通用写作助手节点监控实现与验证报告 | `docs/历史/7-14通用写作助手节点监控实现报告.md` |
| 查看通用写作助手效果评测、评测集与参考答案实现报告 | `docs/历史/7-14通用写作助手效果评测实现报告.md` |
| 查看通用智能体后续基础设施的真实运行基线与缺口审计 | `docs/历史/7-18通用智能体后续基础设施基线报告.md` |
| 查看统一知识召回策略、独立评测与词法基线 | `docs/历史/7-18统一知识召回评测基线报告.md` |
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
├── .kiro/                    # 按需生成的 PRD 计划和 cc-sdd 规格
├── docs/                     # 文档规则、临时资料、参考资料和历史快照
├── project_assets/           # 当前单本小说的数据态资产
├── src/                      # FastAPI 后端代码
├── tests/                    # 后端测试和评测夹具
└── web/                      # Next.js 前端代码
```

`prd-docs/` 只在用户明确启动 PRD 流程时按需创建，用作输入暂存目录；仓库不使用 `.gitkeep` 保存空目录。PRD 分析结果写入 `.kiro/plans/`，规格写入 `.kiro/specs/`。

## 运行方式

首次准备依赖：

```powershell
uv sync
cd web
npm install
```

日常启动双击根目录 `start.bat`。它调用 `.agents/scripts/start.ps1` 完成固定端口清理、MongoDB 复用和前后端就绪检查，并启动：

- 前端：`http://localhost:3000`
- 后端：`http://127.0.0.1:8000`
- MongoDB：`mongodb://127.0.0.1:27017`

## 本机外部数据位置

以下内容在仓库外，不应重新复制到根目录：

| 内容 | 本机位置 | 说明 |
|---|---|---|
| MongoDB 数据 | `E:\Taichu\MongoDB\data\db` | 当前唯一结构事实存储位置 |
| MongoDB 日志 | `E:\Taichu\MongoDB\log` | MongoDB 本地运行日志 |
| 原小说导入资料 | `E:\Taichu\导入资料\太初原小说` | PDF、EPUB、TXT 原始导入包 |
| 旧知识 JSON 迁移备份 | `E:\Taichu\迁移备份\知识库-20260711-151915` | 88 张旧卡和迁移清单的只读备份 |

原小说导入包只是外部导入材料。太初当前正文的文本事实源仍是 `project_assets/source/manuscripts/chapters/` 下的 Markdown。

## 数据边界

- Markdown 是唯一文本事实源。
- MongoDB `taichu.knowledge_cards` 是唯一结构事实源；默认事实查询只使用 `lifecycle=confirmed` 的记录。
- 旧知识迁移已备份 88 张 JSON：58 张有效卡导入为 `confirmed`，30 张已弃用重复卡只保留在 E 盘备份中。
- 迁移 `finalize` 已完成，`project_assets/source/knowledge/` 已删除；存储骨架和业务代码不得重新创建它。
- AI、Agent、评测和 Inbox 保存的 JSON/JSONL 仅是候选、运行、审计或工作区中间态；只有经过校验和作者确认的结构事实才能写入 MongoDB。
- SQLite/FTS 已废弃，不参与后续架构决策；未来若增加向量、Elasticsearch、图索引或缓存，也只能作为可重建派生层。

更完整的物理目录职责以 `project_assets/readme.md` 为准。
