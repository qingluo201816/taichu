#!/usr/bin/env python3
"""Forward-test the codex-sdd state contract through downstream revalidation."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


STATE_SCRIPT = Path(__file__).with_name("state.py")
SPEC_ID = "1.0/状态机验证"


def run(root: Path, *arguments: str, expected: int = 0) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(STATE_SCRIPT), "--root", str(root), *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != expected:
        raise AssertionError(
            f"命令返回码异常：{arguments}\n"
            f"期望 {expected}，实际 {result.returncode}\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
    output = result.stdout if result.stdout.strip() else result.stderr
    return json.loads(output)


def write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-sdd-") as temporary:
        root = Path(temporary)
        initialized = run(
            root,
            "init",
            "--version",
            "1.0",
            "--module",
            "状态机验证",
            "--description",
            "验证规格初始化、需求和设计阶段能够连续推进并恢复。",
            "--target-phase",
            "design_validated",
        )
        spec_directory = Path(str(initialized["directory"]))
        assert spec_directory == root / ".sdd" / "specs" / "1.0" / "状态机验证"

        write(
            spec_directory / "requirements.md",
            "# 状态机验证需求规格\n\n"
            "## 需求 1：连续推进\n\n"
            "1.1 When 阶段产物有效, the 状态管理器 shall 原子记录下一阶段。\n",
        )
        run(
            root,
            "advance",
            "--spec",
            SPEC_ID,
            "--to",
            "requirements_ready",
            "--artifact",
            "requirements=requirements.md",
        )
        bypass = run(
            root,
            "advance",
            "--spec",
            SPEC_ID,
            "--to",
            "requirements_validated",
            expected=2,
        )
        assert "只能由 PASS 独立校验推进" in str(bypass["error"])

        write(spec_directory / "validation-discovery-requirements.md", "# 需求独立发现\n")
        write(
            spec_directory / "independent-validation-report-requirements.md",
            "# 需求独立校验报告\n\n结论：PASS\n\n"
            f"目标 SHA-256：`{sha256(spec_directory / 'requirements.md')}`\n\n证据完整。\n",
        )
        run(
            root,
            "validation",
            "--spec",
            SPEC_ID,
            "--mode",
            "requirements",
            "--status",
            "pass",
            "--report",
            "independent-validation-report-requirements.md",
        )

        original_requirements = (spec_directory / "requirements.md").read_text(encoding="utf-8")
        write(
            spec_directory / "requirements.md",
            original_requirements + "\n校验后按新反馈修订。\n",
        )
        write(
            spec_directory / "validation-discovery-requirements.md",
            "# 需求独立发现\n\n已在全新上下文中重新发现当前需求边界。\n",
        )
        write(
            spec_directory / "independent-validation-report-requirements.md",
            "# 需求独立校验报告\n\n结论：FAIL\n\n"
            f"目标 SHA-256：`{sha256(spec_directory / 'requirements.md')}`\n\n"
            "发现需要继续修正的主要问题。\n",
        )
        failed_revalidation = run(
            root,
            "validation",
            "--spec",
            SPEC_ID,
            "--mode",
            "requirements",
            "--status",
            "fail",
            "--report",
            "independent-validation-report-requirements.md",
        )
        assert failed_revalidation["spec"]["phase"] == "requirements_ready"
        assert failed_revalidation["validation"]["attempts"] == 2

        write(
            spec_directory / "validation-discovery-requirements.md",
            "# 需求独立发现\n\n已重新发现并核对修正后的当前需求边界。\n",
        )
        write(
            spec_directory / "independent-validation-report-requirements.md",
            "# 需求独立校验报告\n\n结论：PASS\n\n"
            f"目标 SHA-256：`{sha256(spec_directory / 'requirements.md')}`\n\n"
            "修正后的需求完整且可验证。\n",
        )
        passed_revalidation = run(
            root,
            "validation",
            "--spec",
            SPEC_ID,
            "--mode",
            "requirements",
            "--status",
            "pass",
            "--report",
            "independent-validation-report-requirements.md",
        )
        assert passed_revalidation["spec"]["phase"] == "requirements_validated"
        assert passed_revalidation["validation"]["attempts"] == 3

        write(spec_directory / "research.md", "# 设计调查\n\n已核对状态契约。\n")
        write(
            spec_directory / "design.md",
            "# 状态机验证技术设计\n\n"
            "## 需求追踪\n\n1.1 由原子 JSON 状态写入和验证命令覆盖。\n",
        )
        write(
            spec_directory / "design-review-report.md",
            "# 设计评审报告\n\n决策：GO\n\n边界与状态恢复路径明确。\n",
        )
        run(
            root,
            "advance",
            "--spec",
            SPEC_ID,
            "--to",
            "design_ready",
            "--artifact",
            "design=design.md",
            "--artifact",
            "research=research.md",
            "--artifact",
            "design_review=design-review-report.md",
        )
        write(spec_directory / "validation-discovery-design.md", "# 设计独立发现\n")
        write(
            spec_directory / "independent-validation-report-design.md",
            "# 设计独立校验报告\n\n结论：PASS\n\n"
            f"目标 SHA-256：`{sha256(spec_directory / 'design.md')}`\n\n设计可实施。\n",
        )
        run(
            root,
            "validation",
            "--spec",
            SPEC_ID,
            "--mode",
            "design",
            "--status",
            "pass",
            "--report",
            "independent-validation-report-design.md",
        )
        validation = run(root, "validate", "--spec", SPEC_ID)
        assert validation["ok"] is True, validation
        shown = run(root, "show", "--spec", SPEC_ID)
        assert shown["spec"]["phase"] == "design_validated"
        assert shown["spec"]["target_phase"] == "design_validated"
        assert len((spec_directory / "progress.log").read_text(encoding="utf-8").splitlines()) >= 5

        write(spec_directory / "tasks.md", "# 实现任务\n\n- [ ] 1.1 验证下游重验状态回退\n")
        run(
            root,
            "advance",
            "--spec",
            SPEC_ID,
            "--to",
            "tasks_ready",
            "--artifact",
            "tasks=tasks.md",
        )
        run(
            root,
            "task-set",
            "--spec",
            SPEC_ID,
            "--task-id",
            "1.1",
            "--status",
            "in_progress",
        )
        run(root, "advance", "--spec", SPEC_ID, "--to", "implementing")

        original_design = (spec_directory / "design.md").read_text(encoding="utf-8")
        write(spec_directory / "design.md", original_design + "\n校验后按新证据修订。\n")
        stale = run(root, "validate", "--spec", SPEC_ID, expected=1)
        assert any("PASS 后发生变化" in item for item in stale["errors"])

        write(
            spec_directory / "validation-discovery-design.md",
            "# 设计独立发现\n\n已在全新上下文中发现实施期间变更后的设计边界。\n",
        )
        write(
            spec_directory / "independent-validation-report-design.md",
            "# 设计独立校验报告\n\n结论：FAIL\n\n"
            f"目标 SHA-256：`{sha256(spec_directory / 'design.md')}`\n\n"
            "下游实施暴露出需要继续修正的设计问题。\n",
        )
        failed_downstream_revalidation = run(
            root,
            "validation",
            "--spec",
            SPEC_ID,
            "--mode",
            "design",
            "--status",
            "fail",
            "--report",
            "independent-validation-report-design.md",
        )
        assert failed_downstream_revalidation["spec"]["phase"] == "design_ready"
        assert failed_downstream_revalidation["spec"]["status"] == "active"

        task_state_before = json.loads(
            (spec_directory / "tasks-status.json").read_text(encoding="utf-8")
        )
        write(
            spec_directory / "validation-discovery-design.md",
            "# 设计独立发现\n\n已重新发现并核对修正后的当前设计边界。\n",
        )
        write(
            spec_directory / "independent-validation-report-design.md",
            "# 设计独立校验报告\n\n结论：PASS\n\n"
            f"目标 SHA-256：`{sha256(spec_directory / 'design.md')}`\n\n"
            "修正后的设计可以继续实施。\n",
        )
        passed_downstream_revalidation = run(
            root,
            "validation",
            "--spec",
            SPEC_ID,
            "--mode",
            "design",
            "--status",
            "pass",
            "--report",
            "independent-validation-report-design.md",
        )
        assert passed_downstream_revalidation["spec"]["phase"] == "design_validated"
        run(
            root,
            "advance",
            "--spec",
            SPEC_ID,
            "--to",
            "tasks_ready",
            "--artifact",
            "tasks=tasks.md",
        )
        task_state_after = json.loads(
            (spec_directory / "tasks-status.json").read_text(encoding="utf-8")
        )
        assert task_state_after == task_state_before
        run(root, "advance", "--spec", SPEC_ID, "--to", "implementing")
        assert run(root, "validate", "--spec", SPEC_ID)["ok"] is True

        write(root / ".sdd" / "state.json", "{损坏的索引")
        repaired = run(root, "repair-index", "--active-spec", SPEC_ID)
        assert repaired["active_spec"] == SPEC_ID
        assert repaired["spec_count"] == 1
        assert run(root, "show")["spec"]["id"] == SPEC_ID

        invalid = run(
            root,
            "init",
            "--version",
            "1.0",
            "--module",
            "../越界",
            "--description",
            "不应创建。",
            expected=2,
        )
        assert "不能包含 '..'" in str(invalid["error"])

    print("codex-sdd 状态机前向验证通过：spec-init -> spec-requirements -> spec-design")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
