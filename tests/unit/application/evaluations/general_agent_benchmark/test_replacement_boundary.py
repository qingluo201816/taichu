from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]

OLD_PATHS = (
    "src/taichu/application/evaluations/general_agent",
    "src/taichu/application/contracts/general_agent_evaluation.py",
    "src/taichu/infrastructure/evaluations/general_agent_repository.py",
    "src/taichu/api/schemas/general_agent_evaluations.py",
    "src/taichu/api/routes/general_agent_evaluations.py",
    "tests/fixtures/evaluations/general_writing_assistant_core/manifest.json",
    "tests/integration/api/test_general_agent_evaluations_api.py",
    "web/src/lib/api/general-agent-evaluation.ts",
    "web/src/lib/types/general-agent-evaluation.ts",
    "web/src/lib/general-agent-evaluation-view.ts",
)

EXPECTED_PENDING_OLD_ASSETS = (
)

PRESERVED_ASSETS = (
    "src/taichu/application/general_agent",
    "src/taichu/application/evaluations/knowledge_extraction",
    "scripts/benchmark_general_agent_recovery.py",
    "docs/旧历史",
)

FORBIDDEN_ACTIVE_TEXT = (
    "/api/agent-evaluations/general-agent",
    "GeneralAgentEvaluationDimension",
    "overall_score",
    "general-agent-evaluation-view",
    "@/lib/api/general-agent-evaluation",
    "@/lib/types/general-agent-evaluation",
    "general_eval_",
)


def _present_old_assets() -> tuple[str, ...]:
    present = []
    for path in OLD_PATHS:
        candidate = ROOT / path
        if candidate.is_dir():
            if any(
                item.is_file() and "__pycache__" not in item.parts
                for item in candidate.rglob("*")
            ):
                present.append(path)
        elif candidate.exists():
            present.append(path)
    present.extend(
        item.relative_to(ROOT).as_posix()
        for item in sorted(
            (
                ROOT
                / "project_assets/derived/agent_evaluations/general_agent"
            ).glob("general_eval_*.json")
        )
    )

    return tuple(present)


def test_atomic_replacement_has_no_old_assets() -> None:
    assert _present_old_assets() == EXPECTED_PENDING_OLD_ASSETS


def test_active_code_has_no_old_contract_or_result_reader() -> None:
    candidates = [
        *list((ROOT / "src/taichu").rglob("*.py")),
        *list((ROOT / "web/src").rglob("*.ts")),
        *list((ROOT / "web/src").rglob("*.tsx")),
    ]
    violations = {
        path.relative_to(ROOT).as_posix(): [
            token
            for token in FORBIDDEN_ACTIVE_TEXT
            if token in path.read_text(encoding="utf-8")
        ]
        for path in candidates
    }

    assert {path: tokens for path, tokens in violations.items() if tokens} == {}


def test_new_route_and_frontend_own_the_active_entry() -> None:
    router_source = (ROOT / "src/taichu/api/router.py").read_text(
        encoding="utf-8"
    )
    shell_source = (
        ROOT
        / "web/src/components/agent-task-monitor/general-agent-evaluation-shell.tsx"
    ).read_text(encoding="utf-8")

    assert "general_agent_benchmarks" in router_source
    assert "general_agent_evaluations" not in router_source
    assert "/api/general-agent-benchmarks" not in shell_source
    assert "@/lib/api/general-agent-benchmark" in shell_source
    assert "GeneralAgentEvaluationShell" in shell_source


def test_preserved_runtime_and_adjacent_evaluations_still_exist() -> None:
    missing = [path for path in PRESERVED_ASSETS if not (ROOT / path).exists()]
    assert missing == []


def test_protected_runtime_baseline_has_not_changed() -> None:
    baseline_path = (
        ROOT
        / "tests/fixtures/evaluations/general_agent_benchmark"
        / "protected_runtime_baseline.json"
    )
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    expected = baseline["sha256"]
    actual = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in expected
    }

    assert actual == expected


def test_current_documentation_points_to_the_new_benchmark_only() -> None:
    repository_map = (ROOT / "README.md").read_text(encoding="utf-8")
    assets_map = (ROOT / "project_assets/readme.md").read_text(encoding="utf-8")
    decision = (
        ROOT
        / "docs/已讨论功能/7-13通用写作助手智能体架构与能力演进决策.md"
    ).read_text(encoding="utf-8")
    runtime_map = (
        ROOT
        / "docs/学习资料/7-20通用Agent运行链路上下文与能力调用排查地图.md"
    ).read_text(encoding="utf-8")

    assert "general_writing_agent_benchmark/suite.json" in repository_map
    assert "general_agent_benchmarks/" in assets_map
    assert "agent_evaluations/general_agent/" not in assets_map
    assert "general_writing_assistant_core" not in assets_map
    assert "/api/general-agent-benchmarks" in decision
    assert "general_writing_agent_benchmark" in decision
    assert "五维确定性指标权重" not in decision
    assert "evaluations/general_agent/" not in runtime_map
    assert "general_agent_evaluations.py" not in runtime_map
    assert "general_writing_assistant_core" not in runtime_map
    assert "general_agent_benchmark" in runtime_map
