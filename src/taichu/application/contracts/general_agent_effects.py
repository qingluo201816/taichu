"""通用写作助手副作用日志仓储契约。"""

from typing import Protocol, runtime_checkable

from taichu.application.general_agent.recovery import EffectRecord


@runtime_checkable
class GeneralAgentEffectRepository(Protocol):
    async def append(self, record: EffectRecord) -> None: ...

    async def latest(self, effect_id: str) -> EffectRecord | None: ...

    async def list_effects(self, run_id: str) -> list[EffectRecord]: ...

    async def delete_run(self, run_id: str) -> bool: ...
