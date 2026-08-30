"""运行通用 Agent 动态能力图的本地确定性长链路与恢复基准。"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from statistics import median
import tempfile
from time import perf_counter
from typing import Any
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from taichu.application.capabilities import CapabilityContext
from taichu.application.general_agent.executor import (
    DynamicDagExecutor,
    InjectedProcessTermination,
)
from taichu.application.general_agent.models import (
    GeneralAgentExecutionPlan,
    GeneralAgentNodeKind,
    GeneralAgentNodeStatus,
    GeneralAgentPlanNode,
    GeneralAgentRun,
    GeneralAgentRunStatus,
)
from taichu.application.invocations.models import now_iso
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
)
from taichu.application.services.outline_service import OutlineService
from taichu.application.subagents.registry import SubagentRegistry
from taichu.application.tools import get_novel_structure
from taichu.application.tools.contract import ToolPlugin
from taichu.application.tools.registry import ToolRegistry
from taichu.infrastructure.general_agent_runs import (
    JsonGeneralAgentEffectRepository,
    LangGraphGeneralAgentCapabilityResultRepository,
)
from taichu.infrastructure.storage.markdown_backend import ProjectAssetStorageBackend

NODE_COUNTS = (1, 3, 6, 12, 20, 40)
CONCURRENCY_LEVELS = (1, 3, 8)


class _InjectedProcessCrash(InjectedProcessTermination):
    """模拟能力节点执行期间进程被强制终止。"""


@dataclass(frozen=True)
class BenchmarkCaseResult:
    node_count: int
    concurrency: int
    fault: str
    repetition: int
    completed: bool
    recovered: bool
    duplicate_success_count: int
    elapsed_ms: int
    checkpoint_revision_count: int
    checkpoint_bytes: int
    error_type: str | None = None


async def run_case(
    *,
    node_count: int,
    concurrency: int,
    inject_crash: bool,
    repetition: int,
) -> BenchmarkCaseResult:
    with tempfile.TemporaryDirectory(prefix="taichu-recovery-benchmark-") as directory:
        root = Path(directory)
        policy = InvocationPolicyService()
        storage = ProjectAssetStorageBackend(root)
        outline_service = OutlineService(storage)
        chapter_service = ChapterService(storage)
        await outline_service.create_volume("基准卷")
        successful_calls: dict[str, int] = {}
        crash_index = max(0, node_count // 2)
        crash_node = f"read_{crash_index:02d}"
        crash_layer_start = (crash_index // concurrency) * concurrency
        crash_layer_members = {
            f"read_{index:02d}"
            for index in range(
                crash_layer_start,
                min(node_count, crash_layer_start + concurrency),
            )
        }
        crash_peers_finished: set[str] = set()
        crash_ready = asyncio.Event()
        if len(crash_layer_members) == 1:
            crash_ready.set()
        crash_pending = inject_crash

        async def measured_read(input_data, invocation, capabilities):
            nonlocal crash_pending
            node_id = invocation.phase.removeprefix("dag:")
            if crash_pending and node_id == crash_node:
                # 先让同一超步中的并发同伴完成，避免把协程取消噪声混入基准。
                await crash_ready.wait()
                crash_pending = False
                raise _InjectedProcessCrash()
            result = await get_novel_structure.run(
                input_data,
                invocation,
                capabilities,
            )
            successful_calls[node_id] = successful_calls.get(node_id, 0) + 1
            if node_id in crash_layer_members and node_id != crash_node:
                crash_peers_finished.add(node_id)
                if len(crash_peers_finished) == len(crash_layer_members) - 1:
                    crash_ready.set()
            return result

        registry = _registry(
            policy,
            outline_service,
            chapter_service,
            measured_read,
        )
        run = _run(node_count=node_count, concurrency=concurrency)
        graph_checkpointer = InMemorySaver()
        graph_store = InMemoryStore()
        timer = perf_counter()
        recovered = False
        error_type: str | None = None
        try:
            executor = _executor(
                root,
                registry,
                policy,
                graph_store=graph_store,
            )
            try:
                completed = await executor.execute(
                    run,
                    checkpoint=_checkpoint,
                    checkpointer=graph_checkpointer,
                )
            except _InjectedProcessCrash:
                # 让同一超步中已取消的并发任务完成 LangGraph 清理。
                await asyncio.sleep(0.01)
                recovered = True
                restarted_policy = InvocationPolicyService()
                restarted_registry = _registry(
                    restarted_policy,
                    outline_service,
                    chapter_service,
                    measured_read,
                )
                completed = await _executor(
                    root,
                    restarted_registry,
                    restarted_policy,
                    graph_store=graph_store,
                ).execute(
                    run,
                    checkpoint=_checkpoint,
                    checkpointer=graph_checkpointer,
                )
            completed_ok = all(
                item.status is GeneralAgentNodeStatus.SUCCESS
                for item in completed.node_runs
                if item.plan_revision == 1
            )
        except BaseException as error:  # noqa: BLE001
            completed_ok = False
            error_type = type(error).__name__
        checkpoint_config: RunnableConfig = {
            "configurable": {"thread_id": run.conversation_id}
        }
        revisions = [
            item async for item in graph_checkpointer.alist(checkpoint_config)
        ]
        checkpoint_bytes = sum(
            len(
                json.dumps(
                    item.checkpoint,
                    ensure_ascii=False,
                    default=str,
                ).encode("utf-8")
            )
            for item in revisions
        )
        duplicate_successes = sum(
            max(0, count - 1) for count in successful_calls.values()
        )
        return BenchmarkCaseResult(
            node_count=node_count,
            concurrency=concurrency,
            fault="process_interruption" if inject_crash else "none",
            repetition=repetition,
            completed=completed_ok,
            recovered=recovered and completed_ok,
            duplicate_success_count=duplicate_successes,
            elapsed_ms=max(0, round((perf_counter() - timer) * 1_000)),
            checkpoint_revision_count=len(revisions),
            checkpoint_bytes=checkpoint_bytes,
            error_type=error_type,
        )


async def run_matrix(repetitions: int) -> dict[str, Any]:
    cases: list[BenchmarkCaseResult] = []
    for node_count in NODE_COUNTS:
        for concurrency in CONCURRENCY_LEVELS:
            for inject_crash in (False, True):
                for repetition in range(1, repetitions + 1):
                    result = await run_case(
                        node_count=node_count,
                        concurrency=concurrency,
                        inject_crash=inject_crash,
                        repetition=repetition,
                    )
                    cases.append(result)
                    print(
                        f"节点 {node_count:>2} / 并发 {concurrency} / "
                        f"{'中断恢复' if inject_crash else '正常执行'}："
                        f"{'通过' if result.completed else '失败'}，"
                        f"{result.elapsed_ms} 毫秒"
                    )
    successful = [case for case in cases if case.completed]
    zero_duplicate = all(case.duplicate_success_count == 0 for case in cases)
    deterministic_nodes = max(
        (
            node_count
            for node_count in NODE_COUNTS
            if all(case.completed for case in cases if case.node_count == node_count)
        ),
        default=0,
    )
    deterministic_concurrency = max(
        (
            concurrency
            for concurrency in CONCURRENCY_LEVELS
            if all(case.completed for case in cases if case.concurrency == concurrency)
        ),
        default=0,
    )
    return {
        "format_version": 1,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "scope": {
            "capability": "真实本地只读工具：读取小说结构",
            "faults": ["无故障", "能力节点进程中断后恢复"],
            "real_model_included": False,
            "notes": "写入崩溃窗口由独立真实 Markdown 故障注入测试覆盖。",
        },
        "summary": {
            "case_count": len(cases),
            "completion_rate": len(successful) / len(cases),
            "recovery_success_rate": (
                sum(1 for case in cases if case.fault != "none" and case.recovered)
                / sum(1 for case in cases if case.fault != "none")
            ),
            "zero_duplicate_successes": zero_duplicate,
            "deterministic_max_plan_nodes": deterministic_nodes,
            "deterministic_max_concurrency": deterministic_concurrency,
            "recommended_max_plan_nodes": min(12, deterministic_nodes),
            "recommended_max_concurrency": min(3, deterministic_concurrency),
            "recommended_max_runtime_seconds": 900,
            "recommended_max_write_nodes_per_authorization": 1,
            "recommendation_reason": (
                "40 节点/并发 8 仅通过单轮本地确定性能力基准；"
                "真实模型三次重复与混合任务基准完成前，保留当前 12 节点/并发 3 默认值。"
            ),
            "median_elapsed_ms": int(median(case.elapsed_ms for case in cases)),
            "maximum_checkpoint_bytes": max(case.checkpoint_bytes for case in cases),
        },
        "cases": [asdict(case) for case in cases],
    }


def _registry(
    policy: InvocationPolicyService,
    outline_service: OutlineService,
    chapter_service: ChapterService,
    handler,
) -> ToolRegistry:
    registry = ToolRegistry(
        CapabilityContext(
            capabilities={
                "outline_service": outline_service,
                "chapter_service": chapter_service,
                "invocation_policy_service": policy,
            }
        )
    )
    registry.register(ToolPlugin(manifest=get_novel_structure.manifest, run=handler))
    return registry


def _executor(
    root: Path,
    registry: ToolRegistry,
    policy: InvocationPolicyService,
    *,
    graph_store: InMemoryStore,
) -> DynamicDagExecutor:
    return DynamicDagExecutor(
        tool_registry=registry,
        subagent_registry=SubagentRegistry(
            CapabilityContext(capabilities={"invocation_policy_service": policy})
        ),
        policy_service=policy,
        capability_result_repository=(
            LangGraphGeneralAgentCapabilityResultRepository(graph_store)
        ),
        capability_handler_identities={
            ("tool", "get_novel_structure"): "benchmark:get_novel_structure"
        },
        effect_repository=JsonGeneralAgentEffectRepository(root),
    )


def _run(*, node_count: int, concurrency: int) -> GeneralAgentRun:
    nodes = [
        GeneralAgentPlanNode(
            node_id=f"read_{index:02d}",
            kind=GeneralAgentNodeKind.TOOL,
            capability_name="get_novel_structure",
            objective=f"读取小说结构基准节点 {index + 1}。",
            input_data={},
            dependencies=(
                [f"read_{index - concurrency:02d}"] if index >= concurrency else []
            ),
        )
        for index in range(node_count)
    ]
    created_at = now_iso()
    return GeneralAgentRun(
        run_id=(
            f"general_run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_"
            f"{uuid4().hex[:6]}"
        ),
        task_id="general_recovery_benchmark",
        conversation_id="general_recovery_benchmark",
        request_index=1,
        user_goal="运行长链路恢复基准。",
        status=GeneralAgentRunStatus.EXECUTING,
        plan=GeneralAgentExecutionPlan(
            rationale="按指定节点数和并发度运行真实本地只读能力。",
            nodes=nodes,
        ),
        plan_revision=1,
        created_at=created_at,
        updated_at=created_at,
        started_at=created_at,
    )


async def _checkpoint(run: GeneralAgentRun, _event: str) -> GeneralAgentRun:
    return run


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "project_assets/derived/general_agent_recovery_benchmarks/latest.json"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.repetitions < 1:
        raise SystemExit("重复次数必须大于零。")
    report = asyncio.run(run_matrix(args.repetitions))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"基准报告已写入：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
