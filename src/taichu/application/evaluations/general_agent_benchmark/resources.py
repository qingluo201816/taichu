"""需求 7.4、7.8、9.4、9.5：终态案例、证据与套件工件查询。"""

from __future__ import annotations

from math import ceil

from pydantic import Field

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
)
from taichu.application.evaluations.general_agent_benchmark.run_models import (
    CaseResultRow,
    EvidenceBundle,
    SuiteArtifact,
)


class CaseResourcePage(BenchmarkModel):
    items: tuple[CaseResultRow, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    total_snapshot: str = Field(pattern=r"^[a-f0-9]{64}$")


class BenchmarkRunResourceService:
    """只读暴露已冻结 SuiteArtifact，不从显示字段反推结论。"""

    def __init__(self) -> None:
        self._artifacts: dict[str, SuiteArtifact] = {}

    def register(self, artifact: SuiteArtifact) -> SuiteArtifact:
        existing = self._artifacts.get(artifact.run_id)
        if existing is not None:
            if existing != artifact:
                raise ValueError("运行终态工件已经冻结，不能覆盖。")
            return existing
        self._artifacts[artifact.run_id] = artifact
        return artifact

    def list_cases(
        self,
        run_id: str,
        *,
        page: int,
        page_size: int,
    ) -> CaseResourcePage:
        if page < 1:
            raise ValueError("page 必须大于等于 1。")
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size 必须在 1 到 100 之间。")
        rows = self.get_artifact(run_id).case_rows
        total = len(rows)
        offset = (page - 1) * page_size
        return CaseResourcePage(
            items=rows[offset : offset + page_size],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=ceil(total / page_size) if total else 0,
            total_snapshot=canonical_sha256(rows),
        )

    def get_case(self, run_id: str, case_id: str) -> CaseResultRow:
        artifact = self.get_artifact(run_id)
        try:
            return next(
                item for item in artifact.case_rows if item.case_id == case_id
            )
        except StopIteration as error:
            raise KeyError(f"案例不存在：{case_id}") from error

    def get_evidence(self, run_id: str, case_id: str) -> EvidenceBundle:
        row = self.get_case(run_id, case_id)
        artifact = self.get_artifact(run_id)
        try:
            return next(
                item
                for item in artifact.evidence_bundles
                if item.identity.bundle_id == row.evidence_bundle_id
            )
        except StopIteration as error:
            raise KeyError(f"案例证据不存在：{case_id}") from error

    def get_artifact(self, run_id: str) -> SuiteArtifact:
        try:
            return self._artifacts[run_id]
        except KeyError as error:
            raise KeyError(f"运行终态工件不存在：{run_id}") from error
