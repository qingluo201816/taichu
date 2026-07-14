"""能力调用技术记录仓储契约。"""

from typing import Protocol, runtime_checkable

from taichu.application.invocations.models import InvocationTraceRecord


@runtime_checkable
class InvocationTraceRepository(Protocol):
    """追加保存可脱敏回放的能力调用技术记录。"""

    async def append(self, record: InvocationTraceRecord) -> None:
        ...


@runtime_checkable
class InvocationTraceReader(Protocol):
    """按业务运行读取脱敏调用记录，不承担业务状态判断。"""

    async def list_for_run(
        self,
        run_id: str,
        *,
        limit: int = 500,
    ) -> tuple[list[InvocationTraceRecord], int]:
        ...
