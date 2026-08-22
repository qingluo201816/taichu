"""评测运行的可恢复状态机与逐案例 Runner。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

from taichu.application.evaluations.general_agent_benchmark.models import (
    TrackKind,
)
from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    ProviderExecutionState,
    SuiteConclusion,
    SuiteRun,
    SuiteRunLifecycle,
)


class SuiteRunRevisionConflict(RuntimeError):
    """运行 revision 与调用方预期不一致。"""


class SuiteRunStateError(RuntimeError):
    """运行生命周期不允许当前动作。"""


class SuiteRunStore(Protocol):
    async def create(self, run: SuiteRun) -> SuiteRun: ...

    async def get(self, run_id: str) -> SuiteRun: ...

    async def save(
        self,
        run: SuiteRun,
        *,
        expected_revision: int,
    ) -> SuiteRun: ...

    async def list_snapshot(
        self,
        total_snapshot: str | None = None,
    ) -> tuple[tuple[SuiteRun, ...], int, str]: ...


class InMemorySuiteRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, SuiteRun] = {}
        self._lock = asyncio.Lock()
        self._index_revision = 0
        self._snapshots: dict[str, tuple[tuple[SuiteRun, ...], int]] = {}

    async def create(self, run: SuiteRun) -> SuiteRun:
        async with self._lock:
            if run.run_id in self._runs:
                raise SuiteRunRevisionConflict("评测运行已存在。")
            self._runs[run.run_id] = run
            self._record_snapshot()
            return run

    def restore_frozen(self, run: SuiteRun) -> None:
        """把已校验冻结视图装入全新的查询存储，不改写源工件。"""

        existing = self._runs.get(run.run_id)
        if existing is not None and existing != run:
            raise SuiteRunRevisionConflict("冻结评测运行恢复冲突。")
        if existing is None:
            self._runs[run.run_id] = run
            self._record_snapshot()

    async def get(self, run_id: str) -> SuiteRun:
        async with self._lock:
            try:
                return self._runs[run_id]
            except KeyError as error:
                raise KeyError(f"评测运行不存在：{run_id}") from error

    async def save(
        self,
        run: SuiteRun,
        *,
        expected_revision: int,
    ) -> SuiteRun:
        async with self._lock:
            current = self._runs.get(run.run_id)
            if current is None:
                raise KeyError(f"评测运行不存在：{run.run_id}")
            if current.revision != expected_revision:
                raise SuiteRunRevisionConflict(
                    f"评测运行 revision 冲突：当前 {current.revision}，"
                    f"期望 {expected_revision}。"
                )
            if run.revision != expected_revision + 1:
                raise SuiteRunRevisionConflict("新 revision 必须严格递增一。")
            self._runs[run.run_id] = run
            self._record_snapshot()
            return run

    async def list_snapshot(
        self,
        total_snapshot: str | None = None,
    ) -> tuple[tuple[SuiteRun, ...], int, str]:
        async with self._lock:
            if total_snapshot is not None:
                try:
                    runs, revision = self._snapshots[total_snapshot]
                except KeyError as error:
                    raise KeyError("分页快照不存在或已经失效。") from error
                return runs, revision, total_snapshot
            if not self._snapshots:
                self._record_snapshot()
            token, (runs, revision) = next(
                reversed(self._snapshots.items())
            )
            return runs, revision, token

    def _record_snapshot(self) -> None:
        self._index_revision += 1
        # run_id 的哈希尾缀不表达新鲜度；恢复或创建顺序才是权威顺序。
        runs = tuple(reversed(self._runs.values()))
        token = canonical_sha256(
            {
                "index_revision": self._index_revision,
                "runs": [
                    {
                        "run_id": item.run_id,
                        "revision": item.revision,
                    }
                    for item in runs
                ],
            }
        )
        self._snapshots[token] = (runs, self._index_revision)


class BenchmarkLifecycleService:
    def __init__(self, store: SuiteRunStore) -> None:
        self._store = store

    async def create(
        self,
        *,
        run_id: str,
        suite_content_hash: str,
        selected_case_ids: tuple[str, ...],
        track: TrackKind,
    ) -> SuiteRun:
        track = TrackKind(track)
        provider_state = (
            ProviderExecutionState.NOT_APPLICABLE
            if track is TrackKind.SYNTHETIC
            else ProviderExecutionState.PENDING
        )
        return await self._store.create(
            SuiteRun(
                run_id=run_id,
                revision=0,
                lifecycle=SuiteRunLifecycle.QUEUED,
                conclusion=None,
                suite_content_hash=suite_content_hash,
                selected_case_ids=selected_case_ids,
                track=track,
                provider_state=provider_state,
                case_row_refs=(),
                pending_case_ids=selected_case_ids,
                terminal_artifact_ref=None,
            )
        )

    async def get(self, run_id: str) -> SuiteRun:
        return await self._store.get(run_id)

    async def start(
        self,
        run_id: str,
        *,
        expected_revision: int,
    ) -> SuiteRun:
        return await self._change_lifecycle(
            run_id,
            expected_revision=expected_revision,
            allowed=frozenset({SuiteRunLifecycle.QUEUED}),
            target=SuiteRunLifecycle.RUNNING,
        )

    async def request_cancel(
        self,
        run_id: str,
        *,
        expected_revision: int,
    ) -> SuiteRun:
        return await self._change_lifecycle(
            run_id,
            expected_revision=expected_revision,
            allowed=frozenset({SuiteRunLifecycle.RUNNING}),
            target=SuiteRunLifecycle.CANCELLING,
        )

    async def finish_cancel(
        self,
        run_id: str,
        *,
        expected_revision: int,
    ) -> SuiteRun:
        return await self._change_lifecycle(
            run_id,
            expected_revision=expected_revision,
            allowed=frozenset({SuiteRunLifecycle.CANCELLING}),
            target=SuiteRunLifecycle.CANCELLED,
        )

    async def record_case(
        self,
        run_id: str,
        *,
        case_id: str,
        case_row_ref: str,
        expected_revision: int,
    ) -> SuiteRun:
        current = await self._expected(run_id, expected_revision)
        if current.lifecycle not in {
            SuiteRunLifecycle.RUNNING,
            SuiteRunLifecycle.CANCELLING,
        }:
            raise SuiteRunStateError("当前生命周期不能记录案例结果。")
        if case_id not in current.pending_case_ids:
            return current
        pending = tuple(
            item for item in current.pending_case_ids if item != case_id
        )
        updated = current.model_copy(
            update={
                "revision": current.revision + 1,
                "case_row_refs": (*current.case_row_refs, case_row_ref),
                "pending_case_ids": pending,
            }
        )
        return await self._store.save(
            updated,
            expected_revision=expected_revision,
        )

    async def begin_finalizing(
        self,
        run_id: str,
        *,
        expected_revision: int,
    ) -> SuiteRun:
        current = await self._expected(run_id, expected_revision)
        if current.lifecycle is not SuiteRunLifecycle.RUNNING:
            raise SuiteRunStateError("只有 running 运行可以进入 finalizing。")
        if current.pending_case_ids:
            raise SuiteRunStateError("仍有待执行案例，不能开始最终化。")
        return await self._save_lifecycle(
            current,
            target=SuiteRunLifecycle.FINALIZING,
        )

    async def complete(
        self,
        run_id: str,
        *,
        conclusion: SuiteConclusion,
        terminal_artifact_ref: str,
        expected_revision: int,
    ) -> SuiteRun:
        current = await self._expected(run_id, expected_revision)
        if current.lifecycle is not SuiteRunLifecycle.FINALIZING:
            raise SuiteRunStateError("只有 finalizing 运行可以完成。")
        updated = current.model_copy(
            update={
                "revision": current.revision + 1,
                "lifecycle": SuiteRunLifecycle.COMPLETED,
                "conclusion": conclusion,
                "terminal_artifact_ref": terminal_artifact_ref,
            }
        )
        return await self._store.save(
            updated,
            expected_revision=expected_revision,
        )

    async def interrupt(
        self,
        run_id: str,
        *,
        expected_revision: int,
    ) -> SuiteRun:
        return await self._change_lifecycle(
            run_id,
            expected_revision=expected_revision,
            allowed=frozenset(
                {
                    SuiteRunLifecycle.RUNNING,
                    SuiteRunLifecycle.CANCELLING,
                    SuiteRunLifecycle.FINALIZING,
                }
            ),
            target=SuiteRunLifecycle.UNFINISHED,
        )

    async def resume(
        self,
        run_id: str,
        *,
        expected_revision: int,
    ) -> SuiteRun:
        current = await self._expected(run_id, expected_revision)
        if current.lifecycle is SuiteRunLifecycle.RUNNING:
            return current
        if current.lifecycle is not SuiteRunLifecycle.UNFINISHED:
            raise SuiteRunStateError("只有 unfinished 运行可以恢复。")
        return await self._save_lifecycle(
            current,
            target=SuiteRunLifecycle.RUNNING,
        )

    async def _change_lifecycle(
        self,
        run_id: str,
        *,
        expected_revision: int,
        allowed: frozenset[SuiteRunLifecycle],
        target: SuiteRunLifecycle,
    ) -> SuiteRun:
        current = await self._expected(run_id, expected_revision)
        if current.lifecycle not in allowed:
            raise SuiteRunStateError(
                f"不允许从 {current.lifecycle.value} 转为 {target.value}。"
            )
        return await self._save_lifecycle(current, target=target)

    async def _save_lifecycle(
        self,
        current: SuiteRun,
        *,
        target: SuiteRunLifecycle,
    ) -> SuiteRun:
        updated = current.model_copy(
            update={
                "revision": current.revision + 1,
                "lifecycle": target,
            }
        )
        return await self._store.save(
            updated,
            expected_revision=current.revision,
        )

    async def _expected(
        self,
        run_id: str,
        expected_revision: int,
    ) -> SuiteRun:
        current = await self._store.get(run_id)
        if current.revision != expected_revision:
            raise SuiteRunRevisionConflict(
                f"评测运行 revision 冲突：当前 {current.revision}，"
                f"期望 {expected_revision}。"
            )
        return current


CaseExecutor = Callable[[SuiteRun, str], Awaitable[str]]
SuiteFinalizer = Callable[
    [SuiteRun],
    Awaitable[tuple[SuiteConclusion, str]],
]


class BenchmarkRunner:
    def __init__(
        self,
        *,
        lifecycle: BenchmarkLifecycleService,
        execute_case: CaseExecutor,
        finalize: SuiteFinalizer,
    ) -> None:
        self._lifecycle = lifecycle
        self._execute_case = execute_case
        self._finalize = finalize

    async def run(self, run_id: str) -> SuiteRun:
        current = await self._lifecycle.get(run_id)
        if current.lifecycle is SuiteRunLifecycle.QUEUED:
            current = await self._lifecycle.start(
                run_id,
                expected_revision=current.revision,
            )
        elif current.lifecycle is SuiteRunLifecycle.UNFINISHED:
            current = await self._lifecycle.resume(
                run_id,
                expected_revision=current.revision,
            )
        elif current.lifecycle in {
            SuiteRunLifecycle.COMPLETED,
            SuiteRunLifecycle.CANCELLED,
        }:
            return current

        for case_id in tuple(current.pending_case_ids):
            current = await self._lifecycle.get(run_id)
            if current.lifecycle is SuiteRunLifecycle.CANCELLING:
                return await self._lifecycle.finish_cancel(
                    run_id,
                    expected_revision=current.revision,
                )
            try:
                case_row_ref = await self._execute_case(current, case_id)
            except Exception:
                return await self._lifecycle.interrupt(
                    run_id,
                    expected_revision=current.revision,
                )
            current = await self._lifecycle.record_case(
                run_id,
                case_id=case_id,
                case_row_ref=case_row_ref,
                expected_revision=current.revision,
            )
        try:
            current = await self._lifecycle.begin_finalizing(
                run_id,
                expected_revision=current.revision,
            )
            conclusion, artifact_ref = await self._finalize(current)
            return await self._lifecycle.complete(
                run_id,
                conclusion=conclusion,
                terminal_artifact_ref=artifact_ref,
                expected_revision=current.revision,
            )
        except Exception:
            latest = await self._lifecycle.get(run_id)
            if latest.lifecycle in {
                SuiteRunLifecycle.RUNNING,
                SuiteRunLifecycle.CANCELLING,
                SuiteRunLifecycle.FINALIZING,
            }:
                return await self._lifecycle.interrupt(
                    run_id,
                    expected_revision=latest.revision,
                )
            raise
