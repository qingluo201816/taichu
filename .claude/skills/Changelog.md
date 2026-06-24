# Skills 索引

## 当前目录

```
.claude/skills/
├── rule.md              # 技能编写规范
├── Changelog.md         # 本文件 - 技能索引与变更记录
├── quick-answer/
│   └── quick-answer.md   # /quick-answer - 快速问答，不调用工具
└── discuss/
    └── discuss.md         # /discuss - 技术方案前置探讨与决策
```

## 技能列表

| 命令 | 用途 | 最后变更 |
|---|---|---|
| `/quick-answer` | 基于当前上下文快速回答，不做额外搜索 | 2026-06-24 |
| `/discuss` | 技术方案前置探讨与决策，先讨论再写代码 | 2026-06-24 |

## 变更记录

### 2026-06-24
- 创建 `/quick-answer`：快速问答技能，禁止工具调用，仅基于对话上下文回答
- 创建 `/discuss`：技术方案前置探讨与决策技能，先讨论方案再写代码
- 建立 Skills 目录规范（独立子目录、文件命名、变更索引）
- **修复**：技能定义文件重命名为 `SKILL.md`（Claude Code 要求的约定文件名）
- **新增规则**：技能必须在 `.claude/settings.json` 中注册，否则 `/skill-name` 命令不可用
- **更新 rule.md**：增加第 3 条规则（必须注册到 settings），修正文件命名规范
- 安装 `/brand-guidelines`：Notion Avatar 手绘极简风格指南，设为 `user-invocable-only`（仅显式调用）
