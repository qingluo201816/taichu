#!/usr/bin/env python3
"""检查太初任务包基线和关键架构路径。"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

EXPECTED_REPOSITORY = "qingluo201816/taichu"
EXPECTED_BRANCH = "master"
EXPECTED_SHA = "7ad671f1f2558c39558c004e17b6d004b1a6b083"

REQUIRED_PATHS = (
    "AGENTS.md",
    "DESIGN.md",
    "docs/rule.md",
    "project_assets/readme.md",
    "pyproject.toml",
    "start.bat",
    "src/taichu/application/contracts/retrieval.py",
    "src/taichu/application/retrieval/models.py",
    "src/taichu/application/services/retrieval_service.py",
    "src/taichu/infrastructure/retrieval/mongo_lexical_backend.py",
    "src/taichu/application/services/model_role_router.py",
    "src/taichu/application/general_agent/models.py",
    "src/taichu/application/general_agent/orchestrator.py",
    "src/taichu/application/general_agent/executor.py",
    "src/taichu/application/general_agent/service.py",
    "src/taichu/infrastructure/general_agent_runs/json_repository.py",
    "src/taichu/application/evaluations/general_agent/service.py",
    "web/package.json",
)

FORBIDDEN_PATHS = (
    "project_assets/source/knowledge",
)


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--acknowledge-drift",
        action="store_true",
        help="已人工阅读基线之后的提交，并接受按当前代码重新审计。",
    )
    args = parser.parse_args()

    root = Path.cwd()
    try:
        sha = git("rev-parse", "HEAD")
        branch = git("branch", "--show-current")
        remote = git("remote", "get-url", "origin")
        status = git("status", "--short")
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        print(f"错误：当前目录不是可用的 Git 仓库：{error}", file=sys.stderr)
        return 2

    print(f"仓库：{remote}")
    print(f"分支：{branch}")
    print(f"HEAD：{sha}")
    print("工作树：" + ("干净" if not status else "\n" + status))

    missing = [path for path in REQUIRED_PATHS if not (root / path).exists()]
    forbidden = [path for path in FORBIDDEN_PATHS if (root / path).exists()]
    gitkeep = list(root.rglob(".gitkeep"))

    if missing:
        print("\n缺少关键路径：")
        for path in missing:
            print(f"- {path}")
    if forbidden:
        print("\n发现禁止路径：")
        for path in forbidden:
            print(f"- {path}")
    if gitkeep:
        print("\n发现禁止的 .gitkeep：")
        for path in gitkeep:
            print(f"- {path.relative_to(root)}")

    drift = sha != EXPECTED_SHA or branch != EXPECTED_BRANCH
    if drift:
        print(
            "\n基线漂移：任务包基线为 "
            f"{EXPECTED_BRANCH}@{EXPECTED_SHA}，当前为 {branch}@{sha}。"
        )
        print("先执行阶段 00，阅读新增提交并更新事实快照。")
        if not args.acknowledge_drift:
            print("人工确认后可使用 --acknowledge-drift 继续检查。")
            return 3

    if missing or forbidden or gitkeep:
        return 4

    print("\n关键路径检查通过。")
    if drift:
        print("已确认基线漂移；后续任务必须以当前代码为准。")
    else:
        print("当前 HEAD 与任务包基线一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
