#!/usr/bin/env python3
"""Persistent state manager for the project-level codex-sdd workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SPEC_SCHEMA = "codex-sdd/spec-state@1"
WORKSPACE_SCHEMA = "codex-sdd/workspace-state@1"
TASKS_SCHEMA = "codex-sdd/tasks-state@1"

PHASES = (
    "initialized",
    "requirements_ready",
    "requirements_validated",
    "design_ready",
    "design_validated",
    "tasks_ready",
    "implementing",
    "implementation_ready",
    "completed",
)
PHASE_INDEX = {phase: index for index, phase in enumerate(PHASES)}
NEXT_PHASE = dict(zip(PHASES, PHASES[1:], strict=False))

VALIDATION_CONFIG = {
    "requirements": {
        "from": "requirements_ready",
        "to": "requirements_validated",
        "artifact": "requirements_validation_report",
        "target_artifact": "requirements",
        "discovery_artifact": "requirements_validation_discovery",
        "discovery_file": "validation-discovery-requirements.md",
    },
    "design": {
        "from": "design_ready",
        "to": "design_validated",
        "artifact": "design_validation_report",
        "target_artifact": "design",
        "discovery_artifact": "design_validation_discovery",
        "discovery_file": "validation-discovery-design.md",
    },
    "implementation": {
        "from": "implementation_ready",
        "to": "completed",
        "artifact": "implementation_validation_report",
        "target_artifact": "implementation_report",
        "discovery_artifact": None,
        "discovery_file": None,
    },
}

ARTIFACT_KEYS = {
    "requirements",
    "research",
    "gap_analysis",
    "design",
    "design_review",
    "tasks",
    "implementation_report",
    "requirements_validation_report",
    "requirements_validation_discovery",
    "design_validation_report",
    "design_validation_discovery",
    "implementation_validation_report",
}

INVALID_SEGMENT_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
TASK_LINE = re.compile(
    r"^(?P<prefix>\s*-\s+\[)(?P<mark>[ xX])(?P<suffix>\]\s+\*{0,2}(?P<id>\d+(?:\.\d+)*)\*{0,2}(?:\s|[：:]).*)$",
    re.MULTILINE,
)


class StateError(RuntimeError):
    """A user-correctable state or input error."""


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def emit(payload: dict[str, Any], *, stream: Any = sys.stdout) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StateError(f"缺少{label}：{path}") from exc
    except json.JSONDecodeError as exc:
        raise StateError(f"{label}不是有效 JSON：{path}（{exc}）") from exc
    if not isinstance(value, dict):
        raise StateError(f"{label}根节点必须是对象：{path}")
    return value


def validate_segment(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise StateError(f"{label}不能为空")
    if normalized in {".", ".."} or ".." in normalized:
        raise StateError(f"{label}不能包含 '..'")
    if INVALID_SEGMENT_CHARS.search(normalized):
        raise StateError(f"{label}包含 Windows 路径非法字符：{value!r}")
    if normalized.endswith((" ", ".")):
        raise StateError(f"{label}不能以空格或句点结尾")
    if normalized.split(".", 1)[0].upper() in RESERVED_WINDOWS_NAMES:
        raise StateError(f"{label}不能使用 Windows 保留名称：{normalized}")
    if len(normalized) > 100:
        raise StateError(f"{label}不能超过 100 个字符")
    return normalized


def parse_spec_id(spec_id: str) -> tuple[str, str]:
    parts = spec_id.split("/")
    if len(parts) != 2:
        raise StateError("规格标识必须是 '{版本号}/{大需求模块名称}'")
    return validate_segment(parts[0], "版本号"), validate_segment(parts[1], "大需求模块名称")


def workspace_root(value: str | None) -> Path:
    root = Path(value or Path.cwd()).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise StateError(f"工作区不存在或不是目录：{root}")
    return root


def sdd_root(root: Path) -> Path:
    return root / ".sdd"


def workspace_state_path(root: Path) -> Path:
    return sdd_root(root) / "state.json"


def spec_dir(root: Path, spec_id: str) -> Path:
    version, module = parse_spec_id(spec_id)
    base = (sdd_root(root) / "specs").resolve()
    candidate = (base / version / module).resolve()
    if candidate != base and base not in candidate.parents:
        raise StateError("规格目录越出 .sdd/specs")
    return candidate


def spec_state_path(root: Path, spec_id: str) -> Path:
    return spec_dir(root, spec_id) / "spec.json"


def read_workspace_state(root: Path, *, allow_missing: bool = False) -> dict[str, Any]:
    path = workspace_state_path(root)
    if allow_missing and not path.exists():
        return {
            "schema": WORKSPACE_SCHEMA,
            "active_spec": None,
            "updated_at": now_iso(),
            "specs": {},
        }
    state = load_json(path, "工作区 SDD 状态")
    if state.get("schema") != WORKSPACE_SCHEMA:
        raise StateError(f"不支持的工作区状态 schema：{state.get('schema')!r}")
    if not isinstance(state.get("specs"), dict):
        raise StateError("工作区状态 specs 必须是对象")
    return state


def resolve_spec_id(root: Path, requested: str | None) -> str:
    if requested:
        version, module = parse_spec_id(requested)
        return f"{version}/{module}"
    state = read_workspace_state(root)
    active = state.get("active_spec")
    if not isinstance(active, str) or not active:
        raise StateError("没有活动规格，请提供 '{版本号}/{大需求模块名称}'")
    parse_spec_id(active)
    return active


def read_spec_state(root: Path, spec_id: str) -> dict[str, Any]:
    state = load_json(spec_state_path(root, spec_id), "规格状态")
    if state.get("schema") != SPEC_SCHEMA:
        raise StateError(f"不支持的规格状态 schema：{state.get('schema')!r}")
    if state.get("id") != spec_id:
        raise StateError(f"规格状态 id 与目录不一致：{state.get('id')!r} != {spec_id!r}")
    if state.get("phase") not in PHASES:
        raise StateError(f"未知阶段：{state.get('phase')!r}")
    if state.get("status") not in {"active", "blocked", "completed"}:
        raise StateError(f"未知规格状态：{state.get('status')!r}")
    return state


def write_workspace_index(root: Path, spec: dict[str, Any]) -> None:
    workspace = read_workspace_state(root, allow_missing=True)
    workspace["active_spec"] = spec["id"]
    workspace["updated_at"] = now_iso()
    workspace["specs"][spec["id"]] = {
        "phase": spec["phase"],
        "status": spec["status"],
        "target_phase": spec["target_phase"],
        "updated_at": spec["updated_at"],
    }
    atomic_json(workspace_state_path(root), workspace)


def save_spec_state(root: Path, spec: dict[str, Any]) -> None:
    spec["updated_at"] = now_iso()
    atomic_json(spec_state_path(root, spec["id"]), spec)
    write_workspace_index(root, spec)


def append_progress(root: Path, spec: dict[str, Any], event: str, message: str, level: str = "info") -> None:
    record = {
        "at": now_iso(),
        "level": level,
        "event": event,
        "phase": spec["phase"],
        "message": message,
    }
    path = spec_dir(root, spec["id"]) / "progress.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def safe_artifact(root: Path, spec_id: str, relative: str) -> tuple[str, Path]:
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts:
        raise StateError(f"产物路径必须位于规格目录内：{relative}")
    directory = spec_dir(root, spec_id)
    path = (directory / raw).resolve()
    if path != directory and directory not in path.parents:
        raise StateError(f"产物路径越出规格目录：{relative}")
    if not path.is_file():
        raise StateError(f"产物文件不存在：{path}")
    return path.relative_to(directory).as_posix(), path


def parse_artifacts(values: list[str], root: Path, spec_id: str) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for value in values:
        key, separator, relative = value.partition("=")
        if not separator or key not in ARTIFACT_KEYS or not relative:
            allowed = ", ".join(sorted(ARTIFACT_KEYS))
            raise StateError(f"产物参数必须是 key=path，允许 key：{allowed}")
        artifacts[key] = safe_artifact(root, spec_id, relative)[0]
    return artifacts


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_tasks(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    content = path.read_text(encoding="utf-8")
    return {
        match.group("id"): "completed" if match.group("mark").lower() == "x" else "pending"
        for match in TASK_LINE.finditer(content)
    }


def tasks_state_path(root: Path, spec_id: str) -> Path:
    return spec_dir(root, spec_id) / "tasks-status.json"


def initialize_tasks_state(root: Path, spec: dict[str, Any]) -> None:
    path = tasks_state_path(root, spec["id"])
    if path.exists():
        return
    tasks_file = spec_dir(root, spec["id"]) / spec["artifacts"]["tasks"]
    parsed = parse_tasks(tasks_file)
    timestamp = now_iso()
    payload = {
        "schema": TASKS_SCHEMA,
        "spec_id": spec["id"],
        "updated_at": timestamp,
        "tasks": {
            task_id: {"status": status, "note": None, "updated_at": timestamp}
            for task_id, status in parsed.items()
        },
    }
    atomic_json(path, payload)


def report_verdict(path: Path) -> str | None:
    content = path.read_text(encoding="utf-8")
    match = re.search(r"结论\s*[：:]\s*(PASS|FAIL)\b", content, re.IGNORECASE)
    return match.group(1).lower() if match else None


def report_mentions_hash(path: Path, expected: str) -> bool:
    compact = re.sub(r"[^0-9a-fA-F]", "", path.read_text(encoding="utf-8"))
    return expected.lower() in compact.lower()


def cmd_init(args: argparse.Namespace) -> dict[str, Any]:
    root = workspace_root(args.root)
    version = validate_segment(args.version, "版本号")
    module = validate_segment(args.module, "大需求模块名称")
    description = args.description.strip()
    if not description:
        raise StateError("需求描述不能为空")
    spec_id = f"{version}/{module}"
    directory = spec_dir(root, spec_id)
    if directory.exists():
        raise StateError(f"规格已存在，不会覆盖：{directory}")
    directory.mkdir(parents=True)
    timestamp = now_iso()
    title = (args.title or module).strip()
    spec = {
        "schema": SPEC_SCHEMA,
        "id": spec_id,
        "version": version,
        "module": module,
        "title": title,
        "description": description,
        "language": "zh-CN",
        "phase": "initialized",
        "status": "active",
        "target_phase": args.target_phase,
        "artifacts": {key: None for key in sorted(ARTIFACT_KEYS)},
        "validations": {
            mode: {"status": "pending", "attempts": 0, "report": None, "checked_at": None}
            for mode in VALIDATION_CONFIG
        },
        "blocker": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    initial_requirements = (
        f"# {title}需求规格\n\n"
        "> 状态：已初始化，等待需求阶段补全并通过独立校验。\n\n"
        "## 原始需求\n\n"
        f"{description}\n\n"
        "## 待完成\n\n"
        "- [ ] 明确范围与非目标\n"
        "- [ ] 编写可验证的 EARS 需求\n"
        "- [ ] 完成独立需求校验\n"
    )
    (directory / "requirements.md").write_text(initial_requirements, encoding="utf-8")
    save_spec_state(root, spec)
    append_progress(root, spec, "initialized", "规格已初始化")
    return {"ok": True, "spec": spec, "directory": str(directory)}


def cmd_show(args: argparse.Namespace) -> dict[str, Any]:
    root = workspace_root(args.root)
    spec_id = resolve_spec_id(root, args.spec)
    spec = read_spec_state(root, spec_id)
    return {"ok": True, "directory": str(spec_dir(root, spec_id)), "spec": spec}


def cmd_target(args: argparse.Namespace) -> dict[str, Any]:
    root = workspace_root(args.root)
    spec_id = resolve_spec_id(root, args.spec)
    spec = read_spec_state(root, spec_id)
    if PHASE_INDEX[args.phase] < PHASE_INDEX[spec["phase"]]:
        raise StateError("目标阶段不能早于当前阶段")
    spec["target_phase"] = args.phase
    save_spec_state(root, spec)
    append_progress(root, spec, "target_changed", f"目标阶段更新为 {args.phase}")
    return {"ok": True, "spec": spec}


def cmd_advance(args: argparse.Namespace) -> dict[str, Any]:
    root = workspace_root(args.root)
    spec_id = resolve_spec_id(root, args.spec)
    spec = read_spec_state(root, spec_id)
    if spec["status"] == "blocked":
        raise StateError("规格处于阻塞状态，请先解除阻塞")
    if spec["status"] == "completed":
        raise StateError("规格已经完成")
    current = spec["phase"]
    target = args.to
    if target != current and NEXT_PHASE.get(current) != target:
        raise StateError(f"非法阶段跃迁：{current} -> {target}")
    if target != current and target in {"requirements_validated", "design_validated", "completed"}:
        raise StateError(f"{target} 只能由 PASS 独立校验推进")
    artifacts = parse_artifacts(args.artifact, root, spec_id)
    spec["artifacts"].update(artifacts)

    required_artifacts = {
        "requirements_ready": ("requirements",),
        "design_ready": ("design", "design_review"),
        "tasks_ready": ("tasks",),
        "implementation_ready": ("implementation_report",),
    }.get(target, ())
    for required_artifact in required_artifacts:
        if not spec["artifacts"].get(required_artifact):
            raise StateError(f"进入 {target} 前必须登记产物 {required_artifact}")

    if target in {"implementing", "implementation_ready"}:
        task_state = load_json(tasks_state_path(root, spec_id), "任务状态")
        tasks = task_state.get("tasks")
        if not isinstance(tasks, dict) or not tasks:
            raise StateError(f"进入 {target} 前必须存在可识别任务")
        statuses = [item.get("status") for item in tasks.values() if isinstance(item, dict)]
        if target == "implementing" and not any(
            status in {"in_progress", "completed"} for status in statuses
        ):
            raise StateError("进入 implementing 前至少一个任务必须为 in_progress 或 completed")
        if target == "implementation_ready" and any(status != "completed" for status in statuses):
            raise StateError("进入 implementation_ready 前所有任务必须 completed")

    spec["phase"] = target
    save_spec_state(root, spec)
    if target == "tasks_ready":
        initialize_tasks_state(root, spec)
    append_progress(root, spec, "stage_changed", args.message or f"阶段更新为 {target}")
    return {"ok": True, "spec": spec}


def cmd_validation(args: argparse.Namespace) -> dict[str, Any]:
    root = workspace_root(args.root)
    spec_id = resolve_spec_id(root, args.spec)
    spec = read_spec_state(root, spec_id)
    if spec["status"] == "blocked":
        raise StateError("规格处于阻塞状态，请先解除阻塞")
    config = VALIDATION_CONFIG[args.mode]
    target_relative = spec["artifacts"].get(config["target_artifact"])
    if not target_relative:
        raise StateError(f"校验缺少目标产物登记：{config['target_artifact']}")
    target_relative, target_path = safe_artifact(root, spec_id, target_relative)
    target_sha256 = file_sha256(target_path)

    previous_validation = spec["validations"][args.mode]
    stale_pass_revalidation = (
        PHASE_INDEX[spec["phase"]] >= PHASE_INDEX[config["to"]]
        and previous_validation.get("status") == "pass"
        and (
            previous_validation.get("target") != target_relative
            or previous_validation.get("target_sha256") != target_sha256
        )
    )
    if spec["phase"] != config["from"] and not stale_pass_revalidation:
        raise StateError(f"{args.mode} 校验要求当前阶段为 {config['from']}，实际为 {spec['phase']}")

    relative, path = safe_artifact(root, spec_id, args.report)
    actual = report_verdict(path)
    if actual != args.status:
        raise StateError(f"报告结论 {actual!r} 与参数 {args.status!r} 不一致")
    if not report_mentions_hash(path, target_sha256):
        raise StateError("校验报告未包含当前目标产物的 SHA-256，无法证明报告新鲜度")

    discovery_relative: str | None = None
    discovery_sha256: str | None = None
    if config["discovery_file"]:
        discovery_relative, discovery_path = safe_artifact(
            root, spec_id, config["discovery_file"]
        )
        discovery_sha256 = file_sha256(discovery_path)
        spec["artifacts"][config["discovery_artifact"]] = discovery_relative

    validation = spec["validations"][args.mode]
    validation["status"] = args.status
    validation["attempts"] = int(validation.get("attempts", 0)) + 1
    validation["report"] = relative
    validation["checked_at"] = now_iso()
    validation["report_sha256"] = file_sha256(path)
    validation["target"] = target_relative
    validation["target_sha256"] = target_sha256
    validation["discovery"] = discovery_relative
    validation["discovery_sha256"] = discovery_sha256
    spec["artifacts"][config["artifact"]] = relative

    if args.status == "pass":
        spec["phase"] = config["to"]
        if config["to"] == "completed":
            spec["status"] = "completed"
    elif stale_pass_revalidation:
        spec["phase"] = config["from"]
        spec["status"] = "active"
    save_spec_state(root, spec)
    level = "info" if args.status == "pass" else "warning"
    append_progress(root, spec, "validation", f"{args.mode} 校验结论：{args.status.upper()}", level)
    return {"ok": True, "spec": spec, "validation": validation}


def cmd_task_set(args: argparse.Namespace) -> dict[str, Any]:
    root = workspace_root(args.root)
    spec_id = resolve_spec_id(root, args.spec)
    spec = read_spec_state(root, spec_id)
    if spec["status"] in {"blocked", "completed"}:
        raise StateError(f"规格状态为 {spec['status']}，不能更新任务")
    if PHASE_INDEX[spec["phase"]] < PHASE_INDEX["tasks_ready"]:
        raise StateError("任务状态只能在 tasks_ready 之后更新")
    path = tasks_state_path(root, spec_id)
    state = load_json(path, "任务状态")
    if state.get("schema") != TASKS_SCHEMA or state.get("spec_id") != spec_id:
        raise StateError("任务状态 schema 或 spec_id 不正确")
    tasks_file = spec_dir(root, spec_id) / (spec["artifacts"].get("tasks") or "tasks.md")
    parsed = parse_tasks(tasks_file)
    if args.task_id not in parsed:
        raise StateError(f"tasks.md 中不存在任务 {args.task_id}")
    timestamp = now_iso()
    state["tasks"].setdefault(args.task_id, {})
    state["tasks"][args.task_id].update(
        {"status": args.status, "note": args.note, "updated_at": timestamp}
    )
    state["updated_at"] = timestamp
    atomic_json(path, state)

    content = tasks_file.read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        if match.group("id") != args.task_id:
            return match.group(0)
        mark = "x" if args.status == "completed" else " "
        return f"{match.group('prefix')}{mark}{match.group('suffix')}"

    updated = TASK_LINE.sub(replace, content)
    tasks_file.write_text(updated, encoding="utf-8")
    append_progress(root, spec, "task_changed", f"任务 {args.task_id} -> {args.status}")
    return {"ok": True, "task_id": args.task_id, "status": args.status}


def cmd_block(args: argparse.Namespace) -> dict[str, Any]:
    root = workspace_root(args.root)
    spec_id = resolve_spec_id(root, args.spec)
    spec = read_spec_state(root, spec_id)
    if spec["status"] == "completed":
        raise StateError("已完成规格不能改为阻塞")
    reason = args.reason.strip()
    if not reason:
        raise StateError("阻塞原因不能为空")
    spec["status"] = "blocked"
    spec["blocker"] = {"reason": reason, "at": now_iso()}
    save_spec_state(root, spec)
    append_progress(root, spec, "blocked", reason, "error")
    return {"ok": True, "spec": spec}


def cmd_unblock(args: argparse.Namespace) -> dict[str, Any]:
    root = workspace_root(args.root)
    spec_id = resolve_spec_id(root, args.spec)
    spec = read_spec_state(root, spec_id)
    if spec["status"] != "blocked":
        raise StateError("规格当前并未阻塞")
    spec["status"] = "active"
    spec["blocker"] = None
    save_spec_state(root, spec)
    append_progress(root, spec, "unblocked", args.message or "阻塞条件已解除")
    return {"ok": True, "spec": spec}


def cmd_repair_index(args: argparse.Namespace) -> dict[str, Any]:
    root = workspace_root(args.root)
    specs_root = sdd_root(root) / "specs"
    entries: dict[str, dict[str, Any]] = {}
    states: dict[str, dict[str, Any]] = {}
    if specs_root.exists():
        for path in sorted(specs_root.glob("*/*/spec.json")):
            relative_parts = path.relative_to(specs_root).parts
            if len(relative_parts) != 3:
                continue
            spec_id = f"{relative_parts[0]}/{relative_parts[1]}"
            spec = read_spec_state(root, spec_id)
            states[spec_id] = spec
            entries[spec_id] = {
                "phase": spec["phase"],
                "status": spec["status"],
                "target_phase": spec["target_phase"],
                "updated_at": spec["updated_at"],
            }

    requested = args.active_spec
    if requested:
        active = resolve_spec_id_from_entries(requested, entries)
    else:
        active = None
        existing_path = workspace_state_path(root)
        if existing_path.exists():
            try:
                existing = json.loads(existing_path.read_text(encoding="utf-8"))
                candidate = existing.get("active_spec") if isinstance(existing, dict) else None
                if isinstance(candidate, str) and candidate in entries:
                    active = candidate
            except (json.JSONDecodeError, OSError):
                pass
        if active is None and states:
            active = max(states.values(), key=lambda item: item.get("updated_at", ""))["id"]

    payload = {
        "schema": WORKSPACE_SCHEMA,
        "active_spec": active,
        "updated_at": now_iso(),
        "specs": entries,
    }
    atomic_json(workspace_state_path(root), payload)
    return {"ok": True, "active_spec": active, "spec_count": len(entries)}


def resolve_spec_id_from_entries(requested: str, entries: dict[str, Any]) -> str:
    version, module = parse_spec_id(requested)
    normalized = f"{version}/{module}"
    if normalized not in entries:
        raise StateError(f"指定活动规格不存在：{normalized}")
    return normalized


def validate_spec(root: Path, spec_id: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        spec = read_spec_state(root, spec_id)
    except StateError as exc:
        return [str(exc)], warnings
    directory = spec_dir(root, spec_id)
    phase_index = PHASE_INDEX[spec["phase"]]

    if not (directory / "requirements.md").is_file():
        errors.append("缺少 requirements.md")
    if not (directory / "progress.log").is_file():
        errors.append("缺少 progress.log")

    artifact_requirements = {
        "requirements_ready": ("requirements",),
        "design_ready": ("design", "design_review"),
        "tasks_ready": ("tasks",),
        "implementation_ready": ("implementation_report",),
    }
    for phase, keys in artifact_requirements.items():
        if phase_index < PHASE_INDEX[phase]:
            continue
        for key in keys:
            relative = spec["artifacts"].get(key)
            if not relative:
                errors.append(f"阶段 {spec['phase']} 缺少产物登记：{key}")
                continue
            try:
                safe_artifact(root, spec_id, relative)
            except StateError as exc:
                errors.append(str(exc))

    if phase_index >= PHASE_INDEX["design_ready"]:
        review = spec["artifacts"].get("design_review")
        if review:
            try:
                _, review_path = safe_artifact(root, spec_id, review)
                review_text = review_path.read_text(encoding="utf-8")
                if not re.search(r"决策\s*[：:]\s*GO\b", review_text, re.IGNORECASE):
                    errors.append("设计评审报告不含明确的‘决策：GO’")
            except (OSError, UnicodeError) as exc:
                errors.append(f"无法读取设计评审报告：{exc}")

    for mode, config in VALIDATION_CONFIG.items():
        if phase_index < PHASE_INDEX[config["to"]]:
            continue
        validation = spec["validations"].get(mode, {})
        if validation.get("status") != "pass":
            errors.append(f"阶段 {spec['phase']} 缺少 {mode} PASS 状态")
            continue
        report = validation.get("report")
        if not report:
            errors.append(f"{mode} 校验缺少报告路径")
            continue
        try:
            _, path = safe_artifact(root, spec_id, report)
            if report_verdict(path) != "pass":
                errors.append(f"{mode} 校验报告不含 PASS 结论")
            report_sha256 = validation.get("report_sha256")
            if not report_sha256 or file_sha256(path) != report_sha256:
                errors.append(f"{mode} 校验报告在登记后发生变化")

            target = validation.get("target")
            target_sha256 = validation.get("target_sha256")
            if not target or not target_sha256:
                errors.append(f"{mode} 校验缺少目标产物双哈希登记")
            else:
                _, target_path = safe_artifact(root, spec_id, target)
                if file_sha256(target_path) != target_sha256:
                    errors.append(f"{mode} 校验目标在 PASS 后发生变化，必须重新校验")
                if not report_mentions_hash(path, target_sha256):
                    errors.append(f"{mode} 校验报告未引用登记的目标 SHA-256")

            if config["discovery_file"]:
                discovery = validation.get("discovery")
                discovery_sha256 = validation.get("discovery_sha256")
                if not discovery or not discovery_sha256:
                    errors.append(f"{mode} 校验缺少独立 discovery 登记")
                else:
                    _, discovery_path = safe_artifact(root, spec_id, discovery)
                    if file_sha256(discovery_path) != discovery_sha256:
                        errors.append(f"{mode} discovery 在登记后发生变化")
        except StateError as exc:
            errors.append(str(exc))

    if phase_index >= PHASE_INDEX["tasks_ready"]:
        task_path = tasks_state_path(root, spec_id)
        try:
            task_state = load_json(task_path, "任务状态")
            if task_state.get("schema") != TASKS_SCHEMA or task_state.get("spec_id") != spec_id:
                errors.append("tasks-status.json 的 schema 或 spec_id 不正确")
            tasks_file = directory / (spec["artifacts"].get("tasks") or "tasks.md")
            parsed = parse_tasks(tasks_file)
            if not parsed:
                errors.append("tasks.md 中没有可识别的编号任务")
            persisted = task_state.get("tasks")
            if not isinstance(persisted, dict):
                errors.append("tasks-status.json 的 tasks 必须是对象")
                persisted = {}
            for task_id, checkbox_status in parsed.items():
                item = persisted.get(task_id)
                if not isinstance(item, dict):
                    errors.append(f"tasks-status.json 缺少任务 {task_id}")
                    continue
                status = item.get("status")
                if status not in {"pending", "in_progress", "completed", "blocked"}:
                    errors.append(f"任务 {task_id} 状态非法：{status!r}")
                if (checkbox_status == "completed") != (status == "completed"):
                    errors.append(f"任务 {task_id} 的复选框与状态文件不一致")
            statuses = [item.get("status") for item in persisted.values() if isinstance(item, dict)]
            if phase_index >= PHASE_INDEX["implementing"] and not any(
                status in {"in_progress", "completed"} for status in statuses
            ):
                errors.append("implementing 阶段至少需要一个进行中或已完成任务")
            if phase_index >= PHASE_INDEX["implementation_ready"] and any(
                status != "completed" for status in statuses
            ):
                errors.append("implementation_ready 阶段仍有未完成任务")
        except StateError as exc:
            errors.append(str(exc))

    if spec["status"] == "completed" and spec["phase"] != "completed":
        errors.append("status=completed 但 phase 不是 completed")
    if spec["phase"] == "completed" and spec["status"] != "completed":
        errors.append("phase=completed 但 status 不是 completed")
    if spec["status"] == "blocked" and not spec.get("blocker"):
        errors.append("阻塞状态缺少 blocker")
    if spec["status"] != "blocked" and spec.get("blocker"):
        warnings.append("非阻塞状态仍保留 blocker")

    try:
        workspace = read_workspace_state(root)
        entry = workspace["specs"].get(spec_id)
        if not isinstance(entry, dict):
            errors.append("工作区状态索引缺少该规格")
        elif entry.get("phase") != spec["phase"] or entry.get("status") != spec["status"]:
            errors.append("工作区状态索引与 spec.json 不一致")
    except StateError as exc:
        errors.append(str(exc))
    return errors, warnings


def cmd_validate(args: argparse.Namespace) -> dict[str, Any]:
    root = workspace_root(args.root)
    spec_id = resolve_spec_id(root, args.spec)
    errors, warnings = validate_spec(root, spec_id)
    return {"ok": not errors, "spec_id": spec_id, "errors": errors, "warnings": warnings}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="管理 codex-sdd 持久化状态")
    parser.add_argument("--root", help="工作区根目录，默认使用当前目录")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="初始化规格")
    init_parser.add_argument("--version", required=True)
    init_parser.add_argument("--module", required=True)
    init_parser.add_argument("--description", required=True)
    init_parser.add_argument("--title")
    init_parser.add_argument("--target-phase", choices=PHASES, default="tasks_ready")
    init_parser.set_defaults(handler=cmd_init)

    show_parser = subparsers.add_parser("show", help="显示规格状态")
    show_parser.add_argument("--spec")
    show_parser.set_defaults(handler=cmd_show)

    target_parser = subparsers.add_parser("target", help="更新编排目标阶段")
    target_parser.add_argument("--spec")
    target_parser.add_argument("--phase", choices=PHASES, required=True)
    target_parser.set_defaults(handler=cmd_target)

    advance_parser = subparsers.add_parser("advance", help="推进一个相邻阶段")
    advance_parser.add_argument("--spec")
    advance_parser.add_argument("--to", choices=PHASES, required=True)
    advance_parser.add_argument("--artifact", action="append", default=[], metavar="KEY=PATH")
    advance_parser.add_argument("--message")
    advance_parser.set_defaults(handler=cmd_advance)

    validation_parser = subparsers.add_parser("validation", help="登记独立校验结论")
    validation_parser.add_argument("--spec")
    validation_parser.add_argument("--mode", choices=tuple(VALIDATION_CONFIG), required=True)
    validation_parser.add_argument("--status", choices=("pass", "fail"), required=True)
    validation_parser.add_argument("--report", required=True)
    validation_parser.set_defaults(handler=cmd_validation)

    task_parser = subparsers.add_parser("task-set", help="更新任务状态并同步复选框")
    task_parser.add_argument("--spec")
    task_parser.add_argument("--task-id", required=True)
    task_parser.add_argument(
        "--status",
        choices=("pending", "in_progress", "completed", "blocked"),
        required=True,
    )
    task_parser.add_argument("--note")
    task_parser.set_defaults(handler=cmd_task_set)

    block_parser = subparsers.add_parser("block", help="记录阻塞")
    block_parser.add_argument("--spec")
    block_parser.add_argument("--reason", required=True)
    block_parser.set_defaults(handler=cmd_block)

    unblock_parser = subparsers.add_parser("unblock", help="解除阻塞")
    unblock_parser.add_argument("--spec")
    unblock_parser.add_argument("--message")
    unblock_parser.set_defaults(handler=cmd_unblock)

    repair_parser = subparsers.add_parser("repair-index", help="根据 spec.json 重建工作区索引")
    repair_parser.add_argument("--active-spec")
    repair_parser.set_defaults(handler=cmd_repair_index)

    validate_parser = subparsers.add_parser("validate", help="核验状态与磁盘产物")
    validate_parser.add_argument("--spec")
    validate_parser.set_defaults(handler=cmd_validate)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = args.handler(args)
    except StateError as exc:
        emit({"ok": False, "error": str(exc)}, stream=sys.stderr)
        return 2
    emit(result)
    return 0 if result.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
