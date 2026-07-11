# 太初仓库地图

> 更新日期：2026-07-11

太初是面向个人作者的单本玄幻长篇 AI 写作工作台。本文件只回答两件事：仓库每个区域负责什么，以及想找某类资料应该去哪里。

## 最常用入口

| 我想做什么 | 去哪里 |
|---|---|
| 查看 Codex 必须遵守的项目规则 | `AGENTS.md` |
| 修改当前前端视觉、布局或交互 | `DESIGN.md` |
| 查看前端主题的精确实现 | `web/src/components/theme/`、`web/src/app/globals.css` |
| 查看全部项目级 Skills | `.agents/索引.md` |
| 查看 Skill 编写规则 | `.agents/skills/rule.md` |
| 查看某个 Skill | `.agents/skills/{名称}/SKILL.md` |
| 查看后端和系统架构设想 | `docs/临时架构/太初系统架构图.md` |
| 查看知识沉淀智能体效果评估设计 | `docs/临时架构/知识沉淀智能体效果评估方案.md` |
| 查看知识沉淀智能体效果评估的使用报告 | `docs/历史/知识沉淀智能体效果评估使用报告.md` |
| 核对真实后端代码分层 | `src/taichu/api/`、`src/taichu/application/`、`src/taichu/domain/`、`src/taichu/infrastructure/` |
| 查看本地数据态目录结构 | `project_assets/readme.md` |
| 查看当前结构化字段和状态 | `src/taichu/domain/models/` |
| 查看 API 输入输出 | `src/taichu/api/schemas/` |
| 查看存储与检索契约 | `src/taichu/application/contracts/` |
| 查看当前产品需求草案 | `docs/临时产品文档/太初当前产品需求.md` |
| 查看其他未确认产品设想 | `docs/临时产品文档/` |
| 查看历史快照 | `docs/历史/` |
| 查看测试与评测样本 | `tests/`、`tests/fixtures/evaluations/` |

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
├── start.bat                 # Windows 一键启动
├── .agents/                  # Codex Skills 与开发工作流
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

日常启动双击根目录 `start.bat`。脚本会启动或复用 MongoDB，并启动：

- 前端：`http://localhost:3000`
- 后端：`http://127.0.0.1:8000`
- MongoDB：`mongodb://127.0.0.1:27017`

## 本机外部数据位置

以下内容在仓库外，不应重新复制到根目录：

| 内容 | 本机位置 | 说明 |
|---|---|---|
| MongoDB 数据 | `E:\Taichu\MongoDB\data\db` | 结构化事实目标存储位置 |
| MongoDB 日志 | `E:\Taichu\MongoDB\log` | MongoDB 本地运行日志 |
| 原小说导入资料 | `E:\Taichu\导入资料\太初原小说` | PDF、EPUB、TXT 原始导入包 |

原小说导入包只是外部导入材料。太初当前正文的文本事实源仍是 `project_assets/source/manuscripts/chapters/` 下的 Markdown。

## 数据边界

- Markdown 是唯一文本事实源。
- MongoDB 中 `lifecycle=confirmed` 的记录是目标结构事实源。
- `project_assets/source/knowledge/` 当前仍是迁移前 JSON 兼容实现，不代表 MongoDB 已完成业务接入。
- AI 结果先形成 JSON 中间态，经过校验和作者确认后才能晋升为结构事实。
- SQLite、向量、Elasticsearch、图索引和缓存都是可重建派生层。

更完整的物理目录职责以 `project_assets/readme.md` 为准。
