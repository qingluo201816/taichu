"""通用写作助手的专业子 Agent 能力层。"""

from taichu.application.subagents.contract import (
    SubagentManifest,
    SubagentPlugin,
)
from taichu.application.subagents.registry import SubagentRegistry

__all__ = ["SubagentManifest", "SubagentPlugin", "SubagentRegistry"]
