"""通用写作助手 Agent 的高层编排运行时。"""

from typing import TYPE_CHECKING, Any

from taichu.application.general_agent.models import (
    GeneralAgentRun,
    GeneralAgentRunStatus,
)

if TYPE_CHECKING:
    from taichu.application.general_agent.service import GeneralAgentRuntimeService

__all__ = [
    "GeneralAgentRun",
    "GeneralAgentRunStatus",
    "GeneralAgentRuntimeService",
]


def __getattr__(name: str) -> Any:
    """延迟导出服务，避免 contracts→models→package 初始化形成循环导入。"""
    if name == "GeneralAgentRuntimeService":
        from taichu.application.general_agent.service import (
            GeneralAgentRuntimeService,
        )

        return GeneralAgentRuntimeService
    raise AttributeError(name)
