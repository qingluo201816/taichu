# Skills 编写规范

## 目录结构

每个技能必须放在独立子目录中：

```
.claude/skills/
├── rule.md              # 本文件 - 技能编写规范
├── Changelog.md         # 所有技能的索引与变更记录
└── <skill-name>/
    ├── SKILL.md         # 技能定义文件（Claude Code 要求此文件名）
    ├── example.md       # 使用示例（可选）
    └── script.py        # 配套脚本（可选）
```

## 规则

1. **独立子目录**：新增技能时，在 `.claude/skills/` 下新建一个以技能名命名的子目录，技能定义文件放在该子目录内。
2. **技能定义文件命名**：每个技能子目录下的定义文件必须命名为 `SKILL.md`（全大写），目录名使用 kebab-case。
3. **必须注册到 settings**：任何新增技能必须同步在项目根目录的 `.claude/settings.json` 中注册，格式为 `"skills": ["skill-name"]` 或 `"skills": "all"`。未注册的技能不会被系统发现，表现为 `/skill-name` 命令不可用。
4. **更新索引**：每次新增或修改技能后，必须在 `.claude/skills/Changelog.md` 中更新索引表和变更记录。
