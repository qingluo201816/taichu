#!/usr/bin/env python3
"""验证任务包结构、JSON 和阶段文件。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

REQUIRED_ROOT = (
    "README.md",
    "仓库事实快照.md",
    "修正后的推进路线图.md",
    "任务执行总规约.md",
    "任务索引.json",
    "prompts/连续执行总提示词.md",
    "prompts/单阶段执行提示词模板.md",
    "templates/阶段验收记录模板.md",
    "templates/评测报告模板.md",
    "templates/架构决策记录模板.md",
    "templates/故障注入结果模板.md",
    "scripts/check_repository_baseline.py",
)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    missing = [path for path in REQUIRED_ROOT if not (root / path).is_file()]
    if missing:
        print("任务包缺少文件：", file=sys.stderr)
        for path in missing:
            print(f"- {path}", file=sys.stderr)
        return 2

    manifest = json.loads((root / "任务索引.json").read_text(encoding="utf-8"))
    phases = manifest.get("phases")
    if not isinstance(phases, list) or not phases:
        print("任务索引没有有效 phases。", file=sys.stderr)
        return 3

    ids: set[str] = set()
    task_ids: set[str] = set()
    for phase in phases:
        phase_id = phase.get("id")
        path = phase.get("file")
        tasks = phase.get("tasks")
        if not isinstance(phase_id, str) or phase_id in ids:
            print(f"阶段 ID 无效或重复：{phase_id}", file=sys.stderr)
            return 4
        ids.add(phase_id)
        if not isinstance(path, str) or not (root / path).is_file():
            print(f"阶段文件不存在：{path}", file=sys.stderr)
            return 5
        text = (root / path).read_text(encoding="utf-8")
        if not isinstance(tasks, list) or not tasks:
            print(f"阶段 {phase_id} 没有任务。", file=sys.stderr)
            return 6
        for task_id in tasks:
            if task_id in task_ids:
                print(f"任务 ID 重复：{task_id}", file=sys.stderr)
                return 7
            task_ids.add(task_id)
            if f"`{task_id}`" not in text:
                print(f"阶段文件没有任务标题：{task_id}", file=sys.stderr)
                return 8

    gitkeep = list(root.rglob(".gitkeep"))
    if gitkeep:
        print("任务包中禁止包含 .gitkeep。", file=sys.stderr)
        return 9

    print(f"任务包验证通过：{len(phases)} 个阶段，{len(task_ids)} 个任务。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
