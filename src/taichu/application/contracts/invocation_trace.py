"""能力调用技术记录仓储契约。"""

from typing import Protocol, runtime_checkable

from taichu.application.invocations.models import InvocationTraceRecord


@runtime_checkable
class InvocationTraceRepository(Protocol):
    """追加保存可脱敏回放的能力调用技术记录。"""

    async def append(self, record: InvocationTraceRecord) -> None:
        ...
