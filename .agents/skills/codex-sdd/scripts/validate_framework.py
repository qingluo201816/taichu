from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SKILL_ROOT = ROOT / ".agents" / "skills" / "codex-sdd"
LEDGER = SKILL_ROOT / "references" / "migration-ledger.md"


# 每一项都对应 migration-ledger.md 中的一条原始非空参考文件。
# 最低行数只作为“禁止重新压成摘要”的机械下限，不替代内容审查。
MIGRATIONS: dict[str, dict[str, int]] = {
    "agents": {
        "references/agents/spec-design.md": 130,
        "references/agents/spec-impl.md": 120,
        "references/agents/spec-independent-validator.md": 280,
        "references/agents/spec-requirements.md": 120,
        "references/agents/spec-tasks.md": 110,
        "references/agents/steering-custom.md": 48,
        "references/agents/steering.md": 50,
        "references/agents/validate-design.md": 60,
        "references/agents/validate-gap.md": 65,
        "references/agents/validate-impl.md": 65,
    },
    "commands": {
        "references/commands/spec-design.md": 95,
        "references/commands/spec-impl.md": 110,
        "references/commands/spec-init.md": 70,
        "references/commands/spec-quick.md": 120,
        "references/commands/spec-requirements.md": 82,
        "references/commands/spec-status.md": 60,
        "references/commands/spec-tasks.md": 90,
        "references/commands/steering-custom.md": 58,
        "references/commands/steering.md": 55,
        "references/commands/validate-design.md": 60,
        "references/commands/validate-gap.md": 65,
        "references/commands/validate-impl.md": 72,
    },
    "orchestration": {
        "references/orchestration/command-calling-spec.md": 180,
        "references/orchestration/skill-orchestrator-pattern.md": 170,
    },
    "rules": {
        "references/rules/asset-discovery.md": 150,
        "references/rules/design-discovery-full.md": 85,
        "references/rules/design-discovery-light.md": 48,
        "references/rules/design-principles.md": 135,
        "references/rules/design-review-gate.md": 32,
        "references/rules/design-review.md": 75,
        "references/rules/design-synthesis.md": 18,
        "references/rules/ears-format.md": 32,
        "references/rules/frontend-exploration-rules.md": 190,
        "references/rules/gap-analysis.md": 125,
        "references/rules/independent-validation-gate.md": 165,
        "references/rules/requirements-review-gate.md": 33,
        "references/rules/steering-principles.md": 85,
        "references/rules/tasks-generation.md": 165,
        "references/rules/tasks-parallel-analysis.md": 28,
    },
    "templates": {
        "assets/specs/design.md": 280,
        "assets/specs/frontend-design-section.md": 260,
        "assets/specs/init.json": 28,
        "assets/specs/requirements-init.md": 10,
        "assets/specs/requirements.md": 100,
        "assets/specs/research.md": 100,
        "assets/specs/tasks.md": 60,
        "assets/project-context/api-standards.md": 40,
        "assets/project-context/authentication.md": 40,
        "assets/project-context/database.md": 30,
        "assets/project-context/deployment.md": 35,
        "assets/project-context/error-handling.md": 38,
        "assets/project-context/security.md": 35,
        "assets/project-context/testing.md": 30,
        "assets/project-context/product.md": 10,
        "assets/project-context/structure.md": 20,
        "assets/project-context/tech.md": 28,
    },
}


SOURCE_TO_TARGET: tuple[tuple[str, str], ...] = (
    ("taichu/agents/spec-design.txt", "references/agents/spec-design.md"),
    ("taichu/agents/spec-impl.txt", "references/agents/spec-impl.md"),
    ("taichu/agents/spec-independent-validator.txt", "references/agents/spec-independent-validator.md"),
    ("taichu/agents/spec-requirements.txt", "references/agents/spec-requirements.md"),
    ("taichu/agents/spec-tasks.txt", "references/agents/spec-tasks.md"),
    ("taichu/agents/steering-custom.txt", "references/agents/steering-custom.md"),
    ("taichu/agents/steering.txt", "references/agents/steering.md"),
    ("taichu/agents/validate-design.txt", "references/agents/validate-design.md"),
    ("taichu/agents/validate-gap.txt", "references/agents/validate-gap.md"),
    ("taichu/agents/validate-impl.txt", "references/agents/validate-impl.md"),
    ("taichu/commands/spec-design.txt", "references/commands/spec-design.md"),
    ("taichu/commands/spec-impl.txt", "references/commands/spec-impl.md"),
    ("taichu/commands/spec-init.txt", "references/commands/spec-init.md"),
    ("taichu/commands/spec-quick.txt", "references/commands/spec-quick.md"),
    ("taichu/commands/spec-requirements.txt", "references/commands/spec-requirements.md"),
    ("taichu/commands/spec-status.txt", "references/commands/spec-status.md"),
    ("taichu/commands/spec-tasks.txt", "references/commands/spec-tasks.md"),
    ("taichu/commands/steering-custom.txt", "references/commands/steering-custom.md"),
    ("taichu/commands/steering.txt", "references/commands/steering.md"),
    ("taichu/commands/validate-design.txt", "references/commands/validate-design.md"),
    ("taichu/commands/validate-gap.txt", "references/commands/validate-gap.md"),
    ("taichu/commands/validate-impl.txt", "references/commands/validate-impl.md"),
    (
        "taichu/orchestration-rules/KIRO_COMMAND_CALLING_SPEC.txt",
        "references/orchestration/command-calling-spec.md",
    ),
    (
        "taichu/orchestration-rules/SKILL_ORCHESTRATOR_PATTERN.txt",
        "references/orchestration/skill-orchestrator-pattern.md",
    ),
    ("taichu/rules/asset-discovery.txt", "references/rules/asset-discovery.md"),
    ("taichu/rules/design-discovery-full.txt", "references/rules/design-discovery-full.md"),
    ("taichu/rules/design-discovery-light.txt", "references/rules/design-discovery-light.md"),
    ("taichu/rules/design-principles.txt", "references/rules/design-principles.md"),
    ("taichu/rules/design-review-gate.txt", "references/rules/design-review-gate.md"),
    ("taichu/rules/design-review.txt", "references/rules/design-review.md"),
    ("taichu/rules/design-synthesis.txt", "references/rules/design-synthesis.md"),
    ("taichu/rules/ears-format.txt", "references/rules/ears-format.md"),
    (
        "taichu/rules/frontend-exploration-rules.txt",
        "references/rules/frontend-exploration-rules.md",
    ),
    ("taichu/rules/gap-analysis.txt", "references/rules/gap-analysis.md"),
    (
        "taichu/rules/independent-validation-gate.txt",
        "references/rules/independent-validation-gate.md",
    ),
    (
        "taichu/rules/requirements-review-gate.txt",
        "references/rules/requirements-review-gate.md",
    ),
    ("taichu/rules/steering-principles.txt", "references/rules/steering-principles.md"),
    ("taichu/rules/tasks-generation.txt", "references/rules/tasks-generation.md"),
    (
        "taichu/rules/tasks-parallel-analysis.txt",
        "references/rules/tasks-parallel-analysis.md",
    ),
    ("taichu/templates/specs/design.txt", "assets/specs/design.md"),
    (
        "taichu/templates/specs/frontend-design-section.txt",
        "assets/specs/frontend-design-section.md",
    ),
    ("taichu/templates/specs/init.json", "assets/specs/init.json"),
    ("taichu/templates/specs/requirements-init.txt", "assets/specs/requirements-init.md"),
    ("taichu/templates/specs/requirements.txt", "assets/specs/requirements.md"),
    ("taichu/templates/specs/research.txt", "assets/specs/research.md"),
    ("taichu/templates/specs/tasks.txt", "assets/specs/tasks.md"),
    (
        "taichu/templates/steering-custom/api-standards.txt",
        "assets/project-context/api-standards.md",
    ),
    (
        "taichu/templates/steering-custom/authentication.txt",
        "assets/project-context/authentication.md",
    ),
    ("taichu/templates/steering-custom/database.txt", "assets/project-context/database.md"),
    ("taichu/templates/steering-custom/deployment.txt", "assets/project-context/deployment.md"),
    (
        "taichu/templates/steering-custom/error-handling.txt",
        "assets/project-context/error-handling.md",
    ),
    ("taichu/templates/steering-custom/security.txt", "assets/project-context/security.md"),
    ("taichu/templates/steering-custom/testing.txt", "assets/project-context/testing.md"),
    ("taichu/templates/steering/product.txt", "assets/project-context/product.md"),
    ("taichu/templates/steering/structure.txt", "assets/project-context/structure.md"),
    ("taichu/templates/steering/tech.txt", "assets/project-context/tech.md"),
)


TOML_AGENTS: dict[str, tuple[str, int, tuple[str, ...]]] = {
    "codex-sdd-context-custom.toml": (
        "codex_sdd_context_custom",
        550,
        ("steering-custom.md", "写入边界", "事实"),
    ),
    "codex-sdd-context-sync.toml": (
        "codex_sdd_context_sync",
        650,
        ("steering.md", "权威", "平行"),
    ),
    "codex-sdd-design.toml": (
        "codex_sdd_design",
        1500,
        ("spec-design.md", "research.md", "不实现", "DESIGN.md"),
    ),
    "codex-sdd-design-reviewer.toml": (
        "codex_sdd_design_reviewer",
        800,
        ("validate-design.md", "GO", "NO-GO", "不修改"),
    ),
    "codex-sdd-gap-validator.toml": (
        "codex_sdd_gap_validator",
        750,
        ("validate-gap.md", "gap-analysis.md", "不做最终设计"),
    ),
    "codex-sdd-impl.toml": (
        "codex_sdd_impl",
        1300,
        ("spec-impl.md", "TDD", "旧实现", "start.bat"),
    ),
    "codex-sdd-impl-validator.toml": (
        "codex_sdd_impl_validator",
        1100,
        ("validate-impl.md", "结论：PASS | FAIL", "不得修复"),
    ),
    "codex-sdd-requirements.toml": (
        "codex_sdd_requirements",
        1500,
        ("spec-requirements.md", "EARS", "不自我判定"),
    ),
    "codex-sdd-tasks.toml": (
        "codex_sdd_tasks",
        1050,
        ("spec-tasks.md", "追踪", "不实现", "工时"),
    ),
    "codex-sdd-validator.toml": (
        "codex_sdd_validator",
        5500,
        (
            "独立校验 Agent 定义",
            "阶段一",
            "validation-discovery-requirements.md",
            "validation-discovery-design.md",
            "SHA-256",
            "结论：PASS",
            "结论：FAIL",
            "写入边界",
        ),
    ),
}


REQUIRED_TEXT: dict[str, tuple[str, ...]] = {
    "SKILL.md": (
        "$codex-sdd",
        "spec-init",
        "spec-requirements",
        "spec-design",
        "spec-tasks",
        "spec-impl",
        "status",
        "resume",
        "默认自动推进",
        "阶段一禁止读取目标",
    ),
    "references/orchestration/command-calling-spec.md": (
        ".sdd/specs/{版本号}/{大需求模块名称}",
        "禁止模拟",
        "目标 SHA-256",
        "默认自动流程",
    ),
    "references/orchestration/skill-orchestrator-pattern.md": (
        "默认自动推进",
        "全自动链路",
        "两轮",
        "恢复",
    ),
    "references/agents/spec-independent-validator.md": (
        "阶段一：独立需求发现",
        "阶段一：独立设计发现",
        "validation-discovery-requirements.md",
        "validation-discovery-design.md",
        "SHA-256",
        "结论：PASS",
        "结论：FAIL",
        "写入边界",
    ),
    "references/rules/independent-validation-gate.md": (
        "先发现",
        "哈希",
        "PASS",
        "FAIL",
        "禁止",
    ),
    "references/rules/frontend-exploration-rules.md": (
        "Next.js",
        "React",
        "shadcn/ui",
        "Tailwind CSS",
        "DESIGN.md",
        "桌面浏览器",
    ),
    "references/rules/asset-discovery.md": (
        "graphify-out/.graphify_root",
        "覆盖",
        "rg",
        "Git",
    ),
    "references/rules/ears-format.md": ("The system shall", "When", "If", "While", "Where"),
    "references/state-contract.md": (
        ".sdd/state.json",
        "tasks-status.json",
        "design-review-report.md",
        "对象哈希",
    ),
    "assets/specs/design.md": ("需求追踪", "架构", "数据", "接口", "错误", "测试"),
    "assets/specs/requirements.md": ("EARS", "验收标准", "需求追踪"),
    "assets/specs/tasks.md": ("依赖", "并行", "验收", "需求追踪"),
}


EXTRA_REQUIRED: dict[str, int] = {
    "agents/openai.yaml": 5,
    "assets/specs/design-review-report.md": 20,
    "assets/specs/implementation-report.md": 60,
    "assets/specs/validation-discovery.md": 40,
    "assets/specs/validation-report.md": 75,
    "references/migration-ledger.md": 120,
    "references/state-contract.md": 65,
    "scripts/self_test.py": 100,
    "scripts/state.py": 250,
    "scripts/audit_fidelity.py": 250,
}


FORBIDDEN_RUNTIME_TOKENS: tuple[str, ...] = (
    ".claude",
    ".kiro",
    "/kiro:",
    "codegraph",
    "TodoWrite",
    "TaskCreate",
    "TaskUpdate",
    "AskUserQuestion",
    "CC-SDD",
    "cc-sdd",
    "Vue 3",
    "Ant Design Vue",
    "Vuex",
    "{工号}",
)


REMOVED_COMPRESSED_FILES: tuple[str, ...] = (
    "references/codex-adaptation.md",
    "references/design.md",
    "references/independent-validation.md",
    "references/requirements.md",
    "references/tasks-and-implementation.md",
    "references/workflow.md",
)


REMOVED_OLD_SKILLS: tuple[str, ...] = (
    "prd-design-generator",
    "prd-plan-analyze",
    "prd-spec-develop",
    "prd-spec-impl",
    "prd-to-ccsdd",
    "prd-to-plan",
)


def line_count(text: str) -> int:
    return len(text.splitlines())


def read_text(path: Path, errors: list[str]) -> str:
    if not path.is_file():
        errors.append(f"缺少文件：{path.relative_to(ROOT).as_posix()}")
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        errors.append(f"文件不是有效 UTF-8：{path.relative_to(ROOT).as_posix()}（{exc}）")
        return ""


def check_migrations(errors: list[str]) -> None:
    expected_counts = {
        "agents": 10,
        "commands": 12,
        "orchestration": 2,
        "rules": 15,
        "templates": 17,
    }
    actual_counts = {category: len(items) for category, items in MIGRATIONS.items()}
    if actual_counts != expected_counts:
        errors.append(f"迁移分类计数错误：期望 {expected_counts}，实际 {actual_counts}")

    flattened = {target for items in MIGRATIONS.values() for target in items}
    if len(flattened) != 56:
        errors.append(f"迁移目标不是 56 个唯一文件：实际 {len(flattened)}")
    if len(SOURCE_TO_TARGET) != 56:
        errors.append(f"源到目标映射不是 56 条：实际 {len(SOURCE_TO_TARGET)}")
    if {target for _, target in SOURCE_TO_TARGET} != flattened:
        errors.append("SOURCE_TO_TARGET 与 MIGRATIONS 目标集合不一致")

    ledger_text = read_text(LEDGER, errors)
    for source, target in SOURCE_TO_TARGET:
        if source not in ledger_text:
            errors.append(f"迁移台账缺少原始项：{source}")
        if target not in ledger_text:
            errors.append(f"迁移台账缺少目标项：{target}")

    for category, targets in MIGRATIONS.items():
        for relative, minimum in targets.items():
            text = read_text(SKILL_ROOT / relative, errors)
            if text and line_count(text) < minimum:
                errors.append(
                    f"{category} 文件疑似被压缩：{relative} "
                    f"仅 {line_count(text)} 行，门禁下限 {minimum} 行"
                )


def check_required_content(errors: list[str]) -> None:
    for relative, minimum in EXTRA_REQUIRED.items():
        text = read_text(SKILL_ROOT / relative, errors)
        if text and line_count(text) < minimum:
            errors.append(
                f"运行文件内容不足：{relative} 仅 {line_count(text)} 行，门禁下限 {minimum} 行"
            )

    for relative, required in REQUIRED_TEXT.items():
        text = read_text(SKILL_ROOT / relative, errors)
        for token in required:
            if token not in text:
                errors.append(f"关键条款缺失：{relative} 未包含 {token!r}")

    try:
        json.loads((SKILL_ROOT / "assets" / "specs" / "init.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"init.json 无法解析：{exc}")


def check_custom_agents(errors: list[str]) -> None:
    agent_dir = ROOT / ".codex" / "agents"
    actual_names = {path.name for path in agent_dir.glob("*.toml")}
    expected_names = set(TOML_AGENTS)
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        errors.append(f"Codex Agent 注册集不一致：缺少 {missing}，多出 {extra}")

    for filename, (expected_name, minimum_chars, required) in TOML_AGENTS.items():
        path = agent_dir / filename
        text = read_text(path, errors)
        if not text:
            continue
        if len(text) < minimum_chars:
            errors.append(
                f"Agent 注册定义疑似被压缩：.codex/agents/{filename} "
                f"仅 {len(text)} 字符，门禁下限 {minimum_chars} 字符"
            )
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            errors.append(f"Agent TOML 无法解析：.codex/agents/{filename}（{exc}）")
            continue
        allowed_keys = {"name", "description", "developer_instructions"}
        if set(data) != allowed_keys:
            errors.append(
                f"Agent TOML 字段未按已验证契约：{filename} 实际字段 {sorted(data)}"
            )
        if data.get("name") != expected_name:
            errors.append(
                f"Agent 名称错误：{filename} 期望 {expected_name!r}，实际 {data.get('name')!r}"
            )
        for key in allowed_keys:
            value = data.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"Agent TOML 缺少非空字符串字段：{filename} -> {key}")
        for token in required:
            if token not in text:
                errors.append(f"Agent 严格条款缺失：{filename} 未包含 {token!r}")

    config_path = ROOT / ".codex" / "config.toml"
    config_text = read_text(config_path, errors)
    if config_text:
        try:
            config = tomllib.loads(config_text)
        except tomllib.TOMLDecodeError as exc:
            errors.append(f".codex/config.toml 无法解析：{exc}")
        else:
            if config.get("features", {}).get("multi_agent") is not True:
                errors.append(".codex/config.toml 未启用 features.multi_agent")
            if config.get("agents", {}).get("max_depth", 0) < 1:
                errors.append(".codex/config.toml 的 agents.max_depth 必须至少为 1")


def check_fidelity(errors: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, str(SKILL_ROOT / "scripts" / "audit_fidelity.py"), "--quiet"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        errors.append(f"保真度审计失败：\n{detail}")


def check_cleanup_and_runtime_tokens(errors: list[str]) -> None:
    for managed_root in (SKILL_ROOT, ROOT / ".codex"):
        placeholders = sorted(
            path.relative_to(ROOT).as_posix() for path in managed_root.rglob(".gitkeep")
        )
        if placeholders:
            errors.append(f"受管目录禁止 .gitkeep：{placeholders}")

    for relative in REMOVED_COMPRESSED_FILES:
        if (SKILL_ROOT / relative).exists():
            errors.append(f"压缩版旧文件仍存在：{relative}")

    legacy_source = ROOT / "taichu"
    if legacy_source.exists():
        leftovers = sorted(
            path.relative_to(ROOT).as_posix()
            for path in legacy_source.rglob("*")
            if path.is_file()
        )
        if leftovers:
            errors.append(f"原始参考目录仍残留文件：{leftovers}")

    skill_parent = ROOT / ".agents" / "skills"
    for dirname in REMOVED_OLD_SKILLS:
        path = skill_parent / dirname
        leftovers = [item for item in path.rglob("*") if item.is_file()] if path.exists() else []
        if leftovers:
            errors.append(f"旧项目 SDD Skill 仍残留文件：{dirname}")

    runtime_files = [
        path
        for path in SKILL_ROOT.rglob("*")
        if path.is_file()
        and path.name
        not in {"migration-ledger.md", "validate_framework.py", "audit_fidelity.py"}
        and path.suffix.lower() in {".json", ".md", ".py", ".toml", ".yaml", ".yml"}
    ]
    runtime_files.extend((ROOT / ".codex").rglob("*.toml"))
    for path in runtime_files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"运行文件不是 UTF-8：{path.relative_to(ROOT).as_posix()}（{exc}）")
            continue
        for token in FORBIDDEN_RUNTIME_TOKENS:
            if token in text:
                errors.append(
                    f"运行文件含遗留或冲突机制词：{path.relative_to(ROOT).as_posix()} -> {token!r}"
                )


def main() -> int:
    errors: list[str] = []
    check_migrations(errors)
    check_required_content(errors)
    check_custom_agents(errors)
    check_fidelity(errors)
    check_cleanup_and_runtime_tokens(errors)

    if errors:
        print("Codex SDD 框架完整性校验：FAIL", file=sys.stderr)
        for index, error in enumerate(errors, start=1):
            print(f"{index}. {error}", file=sys.stderr)
        return 1

    category_summary = "、".join(
        f"{category}={len(items)}" for category, items in MIGRATIONS.items()
    )
    print("Codex SDD 框架完整性校验：PASS")
    print(f"一对一迁移：56 / 56（{category_summary}）")
    print(f"Codex 自定义 Agent：{len(TOML_AGENTS)} / 10")
    print("内容与格式保真度：PASS")
    print("遗留运行机制与压缩版文件：未发现")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
