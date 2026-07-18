from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from validate_framework import SOURCE_TO_TARGET


ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = ROOT / ".agents" / "skills" / "codex-sdd"

SOURCE_REPLACEMENTS = (
    (".claude/agents/kiro/", ".agents/skills/codex-sdd/references/agents/"),
    (".claude/commands/kiro/", ".agents/skills/codex-sdd/references/commands/"),
    (".kiro/settings/templates/specs/", ".agents/skills/codex-sdd/assets/specs/"),
    (".kiro/settings/rules/", ".agents/skills/codex-sdd/references/rules/"),
    (".kiro/steering/*.md", "AGENTS.md、README.md、DESIGN.md 与适用的当前项目资料"),
    (".kiro/steering/", "当前项目权威资料"),
    (".kiro/specs/", ".sdd/specs/"),
    ("/kiro:", "$codex-sdd "),
    (".claude/", ".codex/"),
    (".kiro/", ".sdd/"),
    ("TodoWrite", "state.py、spec.json 与 progress.log"),
    ("AskUserQuestion", "用户输入工具（仅显式交互模式）"),
    ("SlashCommand", "Codex 子 Agent 调用"),
    ("CC-SDD", "Codex SDD"),
    ("cc-sdd", "codex-sdd"),
    ("Claude Code", "Codex"),
    ("Claude", "Codex"),
    ("Kiro", "Codex SDD"),
    ("codegraph", "本地代码证据"),
    ("{feature-name}", "{版本号}/{大需求模块名称}"),
    ("{feature}", "{规格标识}"),
    ("{规格名}", "{规格标识}"),
)

STRUCTURAL_EXPECTATIONS: dict[str, tuple[str, ...]] = {
    "references/orchestration/command-calling-spec.md": (
        "不可绕过的原则",
        "Codex 机制映射",
        "规格标识与目录",
        "操作与角色映射",
        "统一委派协议",
        "### 6.1 `spec-init`",
        "### 6.2 `spec-requirements`",
        "spec-init",
        "spec-requirements",
        "validate-gap",
        "spec-design",
        "validate-design",
        "spec-tasks",
        "spec-impl",
        "validate-impl",
        "validate-independent",
        "流程日志规范",
        "用户提示中的命令引用",
    ),
    "references/orchestration/skill-orchestrator-pattern.md": (
        "职责模型",
        "默认自动推进",
        "启动与恢复",
        "阶段循环",
        "统一收尾检查单",
        "阶段专属收尾",
        "自动修复循环",
        "持久化任务树",
        "并行规则",
        "异常处理",
        "完成定义",
        "交互确认与推进信号",
        "状态追踪机制",
    ),
    "references/rules/asset-discovery.md": (
        "项目事实源查阅",
        "代码与测试探查",
        "Graphify 关系探查",
        "影响面核对",
        "代码验证兜底",
        "前端触发条件",
        "完成门禁",
        "graphify-out/.graphify_root",
    ),
    "references/rules/frontend-exploration-rules.md": (
        "Step 1：页面与导航定位",
        "Step 2：组件层级与职责",
        "Step 3：组件准入调查",
        "Step 4：API 与类型契约",
        "Step 5：状态与交互",
        "Step 6：视觉与内容",
        "Step 7：测试与可验证性",
        "输出到 `research.md`",
        "Next.js",
        "shadcn/ui",
        "DESIGN.md",
    ),
    "references/rules/gap-analysis.md": (
        "现状调查",
        "需求可行性分析",
        "方案 A：扩展现有组件",
        "方案 B：创建新组件/边界",
        "方案 C：混合方案",
        "范围外",
        "复杂度与风险",
        "不含时间",
        "输出",
    ),
    "references/rules/independent-validation-gate.md": (
        "requirements 模式",
        "design 模式",
        "implementation 模式",
        "阶段一禁止读取",
        "阶段二",
        "证据规则",
        "分类与严重性",
        "PASS",
        "FAIL",
        "不得删除 discovery",
        "SHA-256",
    ),
    "references/rules/steering-principles.md": (
        "权威资料",
        "黄金法则",
        "应记录",
        "不应记录",
        "单一归属",
        "同步流程",
        "模板使用",
        "目录规则",
        "质量",
    ),
    "assets/specs/frontend-design-section.md": (
        "1. 页面与导航",
        "2. 组件结构与职责",
        "3. 组件复用与准入",
        "4. API 与类型契约",
        "5. 页面布局与信息层级",
        "6. 状态模型",
        "7. 交互与事件流程",
        "8. 视觉与文案",
        "9. 动效、可访问性与性能",
        "10. 文件、测试与验收",
    ),
    "assets/specs/init.json": (
        '"id"',
        '"version"',
        '"module"',
        '"description"',
        '"phase"',
        '"target_phase"',
        '"artifacts"',
        '"validations"',
        '"created_at"',
        '"updated_at"',
    ),
    "assets/specs/requirements-init.md": (
        "需求规格",
        "原始需求",
        "{{PROJECT_DESCRIPTION}}",
        "待完成",
        "EARS",
        "独立需求校验",
    ),
    "assets/specs/requirements.md": (
        "概述",
        "现有资产探查",
        "Graphify 覆盖",
        "范围边界",
        "需求列表",
        "验收标准",
        "When",
        "If",
        "非功能期望",
        "需求追踪摘要",
    ),
    "assets/specs/research.md": (
        "文档信息",
        "需求与约束摘要",
        "当前项目事实",
        "Graphify",
        "前端架构分析",
        "外部依赖与技术研究",
        "架构候选",
        "设计决策",
        "风险与缓解",
        "参考文献",
    ),
    "assets/specs/tasks.md": (
        "[BE]",
        "[FE]",
        "_Requirements:",
        "_Boundary:",
        "_Depends:",
        "(P)",
        "可选测试覆盖",
        "计划收尾必须覆盖",
        "Graphify",
    ),
}

DIRECT_THRESHOLDS = {"assets/specs/design.md": 0.80}

# 结构化适配文件允许因 Codex、太初事实和失真内容清理而重写措辞，不能用逐行相似度判定；
# 但仍必须保留与原件相称的信息密度，防止只留下几个命中关键词的压缩摘要。
STRUCTURAL_MIN_CHAR_RATIO = 0.50
STRUCTURAL_MIN_LINE_RATIO = 0.65

TRUNCATION_MARKERS = (
    "tokens truncated",
    "chars truncated",
    "content truncated",
    "output truncated",
)

TOML_TO_REFERENCE = {
    "codex-sdd-context-custom.toml": "references/agents/steering-custom.md",
    "codex-sdd-context-sync.toml": "references/agents/steering.md",
    "codex-sdd-design-reviewer.toml": "references/agents/validate-design.md",
    "codex-sdd-design.toml": "references/agents/spec-design.md",
    "codex-sdd-gap-validator.toml": "references/agents/validate-gap.md",
    "codex-sdd-impl-validator.toml": "references/agents/validate-impl.md",
    "codex-sdd-impl.toml": "references/agents/spec-impl.md",
    "codex-sdd-requirements.toml": "references/agents/spec-requirements.md",
    "codex-sdd-tasks.toml": "references/agents/spec-tasks.md",
    "codex-sdd-validator.toml": "references/agents/spec-independent-validator.md",
}


def run_git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )


def read_source_from_history(source: str) -> str:
    current = run_git("show", f"HEAD:{source}")
    if current.returncode == 0:
        return current.stdout.decode("utf-8-sig")
    history = run_git("rev-list", "--all", "--", source)
    if history.returncode != 0:
        raise RuntimeError(history.stderr.decode("utf-8", errors="replace").strip())
    for commit in history.stdout.decode("ascii").splitlines():
        candidate = run_git("show", f"{commit}:{source}")
        if candidate.returncode == 0:
            return candidate.stdout.decode("utf-8-sig")
    raise FileNotFoundError(f"Git 历史中找不到原始参考：{source}")


def adapt_source(text: str) -> str:
    for old, new in SOURCE_REPLACEMENTS:
        text = text.replace(old, new)
    return text


def normalized(text: str) -> str:
    parts = re.findall(r"[A-Za-z0-9\u3400-\u9fff]+", text)
    return "".join(parts).lower()


def source_line_coverage(source: str, target: str) -> tuple[int, int, float]:
    target_blob = normalized(target)
    source_lines = [normalized(line) for line in adapt_source(source).splitlines()]
    source_lines = [line for line in source_lines if len(line) >= 10]
    if not source_lines:
        return 0, 0, 1.0
    hits = sum(line in target_blob for line in source_lines)
    return hits, len(source_lines), hits / len(source_lines)


def check_sources_and_content(
    errors: list[str],
) -> tuple[
    int,
    int,
    list[tuple[str, float]],
    list[tuple[str, float, float]],
]:
    direct_passed = 0
    structural_passed = 0
    coverages: list[tuple[str, float]] = []
    structural_ratios: list[tuple[str, float, float]] = []
    for source_path, target_path in SOURCE_TO_TARGET:
        try:
            source = read_source_from_history(source_path)
        except (OSError, RuntimeError, UnicodeDecodeError) as exc:
            errors.append(str(exc))
            continue
        target_file = SKILL_ROOT / target_path
        try:
            target = target_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"无法读取迁移目标 {target_path}：{exc}")
            continue

        structural = STRUCTURAL_EXPECTATIONS.get(target_path)
        if structural is not None:
            missing = [token for token in structural if token not in target]
            source_chars = len(normalized(adapt_source(source)))
            target_chars = len(normalized(target))
            char_ratio = target_chars / max(source_chars, 1)
            line_ratio = len(target.splitlines()) / max(len(source.splitlines()), 1)
            structural_ratios.append((target_path, char_ratio, line_ratio))
            passed = True
            if missing:
                errors.append(f"结构适配缺项：{target_path} -> {missing}")
                passed = False
            if char_ratio < STRUCTURAL_MIN_CHAR_RATIO:
                errors.append(
                    f"结构适配内容量不足：{target_path} 的有效字符比为 "
                    f"{char_ratio:.1%}，门禁 {STRUCTURAL_MIN_CHAR_RATIO:.0%}"
                )
                passed = False
            if line_ratio < STRUCTURAL_MIN_LINE_RATIO:
                errors.append(
                    f"结构适配展开不足：{target_path} 的物理行数比为 "
                    f"{line_ratio:.1%}，门禁 {STRUCTURAL_MIN_LINE_RATIO:.0%}"
                )
                passed = False
            if passed:
                structural_passed += 1
            continue

        hits, total, coverage = source_line_coverage(source, target)
        coverages.append((target_path, coverage))
        threshold = DIRECT_THRESHOLDS.get(target_path, 0.90)
        if coverage < threshold:
            errors.append(
                f"原始约束覆盖不足：{target_path} 为 {coverage:.1%} "
                f"（{hits}/{total}），门禁 {threshold:.0%}"
            )
        else:
            direct_passed += 1
    return direct_passed, structural_passed, coverages, structural_ratios


def check_fences(path: Path, lines: list[str], errors: list[str]) -> None:
    active: str | None = None
    for number, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        match = re.match(r"^(`{3,}|~{3,})", stripped)
        if not match:
            continue
        marker = match.group(1)[0]
        if active is None:
            active = marker
        elif active == marker:
            active = None
        else:
            errors.append(f"Markdown 围栏交错：{path.relative_to(ROOT)}:{number}")
    if active is not None:
        errors.append(f"Markdown 围栏未闭合：{path.relative_to(ROOT)}")


def check_markdown_runs(path: Path, lines: list[str], errors: list[str]) -> None:
    in_fence = False
    in_frontmatter = path.name == "SKILL.md"
    run = 0
    run_start = 0
    for number, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if number == 1 and in_frontmatter and line.strip() == "---":
            continue
        if in_frontmatter:
            if line.strip() == "---":
                in_frontmatter = False
            continue
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            run = 0
            continue
        marked = (
            not line.strip()
            or in_fence
            or line.endswith("  ")
            or re.match(
                r"^(?:#{1,6}\s|\s*[-*+]\s|\s*\d+(?:\.\d+)?[.)]\s|\||>|<|---$)",
                line,
            )
        )
        if marked:
            run = 0
            continue
        if run == 0:
            run_start = number
        run += 1
        if run == 9:
            errors.append(
                f"Markdown 连续普通行可能被折叠：{path.relative_to(ROOT)}:"
                f"{run_start}-{number}"
            )


def check_format(errors: list[str]) -> tuple[int, int, int]:
    markdown_count = 0
    toml_count = 0
    auxiliary_count = 0
    files = [
        *SKILL_ROOT.rglob("*.md"),
        *SKILL_ROOT.rglob("*.json"),
        *SKILL_ROOT.rglob("*.yaml"),
        *SKILL_ROOT.rglob("*.yml"),
        *(ROOT / ".codex" / "agents").glob("*.toml"),
    ]
    for path in sorted(files):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if path.suffix == ".md":
            markdown_count += 1
            check_fences(path, lines, errors)
            check_markdown_runs(path, lines, errors)
            if not any(re.match(r"^#{1,6}\s", line) for line in lines):
                errors.append(f"Markdown 缺少标题结构：{path.relative_to(ROOT)}")
        elif path.suffix == ".toml":
            toml_count += 1
        else:
            auxiliary_count += 1
        lowered = text.lower()
        for marker in TRUNCATION_MARKERS:
            if marker in lowered:
                errors.append(
                    f"发现工具截断占位符：{path.relative_to(ROOT)} -> {marker!r}"
                )
        if "\\n" in text:
            errors.append(f"疑似把换行写成字面量：{path.relative_to(ROOT)}")
        for number, line in enumerate(lines, start=1):
            if len(line) > 120:
                errors.append(
                    f"行过长：{path.relative_to(ROOT)}:{number} 为 {len(line)} 字符"
                )
    return markdown_count, toml_count, auxiliary_count


def check_toml_sync(errors: list[str]) -> int:
    synced = 0
    for filename, reference in TOML_TO_REFERENCE.items():
        path = ROOT / ".codex" / "agents" / filename
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            expected = (SKILL_ROOT / reference).read_text(encoding="utf-8").rstrip()
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"Agent TOML 同步检查失败：{filename}（{exc}）")
            continue
        actual = data.get("developer_instructions")
        if not isinstance(actual, str) or actual.rstrip() != expected:
            errors.append(f"Agent TOML 未完整内嵌对应协议：{filename} -> {reference}")
        else:
            synced += 1
    return synced


def main() -> int:
    parser = argparse.ArgumentParser(description="审计 Codex SDD 内容与格式保真度")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    direct, structural, coverages, structural_ratios = check_sources_and_content(errors)
    markdown_count, toml_count, auxiliary_count = check_format(errors)
    synced = check_toml_sync(errors)

    if errors:
        print("Codex SDD 保真度审计：FAIL", file=sys.stderr)
        for index, error in enumerate(errors, start=1):
            print(f"{index}. {error}", file=sys.stderr)
        return 1

    if not args.quiet:
        lowest = min(coverages, key=lambda item: item[1])
        structural_lowest = min(structural_ratios, key=lambda item: item[1])
        print("Codex SDD 保真度审计：PASS")
        print(f"原始参考可读取：{len(SOURCE_TO_TARGET)} / 56")
        print(f"直接内容覆盖：{direct} / {len(SOURCE_TO_TARGET) - len(STRUCTURAL_EXPECTATIONS)}")
        print(f"结构化适配覆盖：{structural} / {len(STRUCTURAL_EXPECTATIONS)}")
        print(f"直接覆盖最低项：{lowest[0]} = {lowest[1]:.1%}")
        print(
            "结构适配最低内容量："
            f"{structural_lowest[0]} = {structural_lowest[1]:.1%} 原件有效字符，"
            f"{structural_lowest[2]:.1%} 原件物理行数"
        )
        print(f"Agent TOML 完整协议同步：{synced} / {len(TOML_TO_REFERENCE)}")
        print(
            f"格式检查：Markdown={markdown_count}，TOML={toml_count}，"
            f"JSON/YAML={auxiliary_count}，最长允许行=120"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
