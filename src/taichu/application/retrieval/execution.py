"""统一召回策略解析后的稳定执行计划。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetrievalExecutionPlan:
    """把消费者策略冻结为一次可观测、可执行的召回计划。"""

    policy_name: str
    top_k: int
    max_content_chars: int
    timeout_ms: int
    requested_strategy: str
    fallback_strategy: str | None

    def snapshot(self) -> dict[str, str | int | None]:
        """返回不含查询正文的策略快照。"""
        return {
            "policy_name": self.policy_name,
            "top_k": self.top_k,
            "max_content_chars": self.max_content_chars,
            "timeout_ms": self.timeout_ms,
            "requested_strategy": self.requested_strategy,
            "fallback_strategy": self.fallback_strategy,
        }
