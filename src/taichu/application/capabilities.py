"""向应用编排提供由组合入口注入的运行能力。"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class CapabilityContext:
    """保存 Agent 和 Tool 可按名称取得的运行能力。"""

    capabilities: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "capabilities",
            MappingProxyType(dict(self.capabilities)),
        )

    def require(self, name: str, expected_type: type[T]) -> T:
        """取得并校验已声明的能力。"""
        if name not in self.capabilities:
            raise MissingCapabilityError(name)

        capability = self.capabilities[name]
        if not isinstance(capability, expected_type):
            raise CapabilityTypeError(
                name=name,
                expected=expected_type,
                actual=type(capability),
            )
        return capability


class MissingCapabilityError(RuntimeError):
    """应用编排所需能力未被组合入口注入。"""

    def __init__(self, name: str) -> None:
        super().__init__(f"Required capability '{name}' is unavailable")


class CapabilityTypeError(TypeError):
    """注入能力与调用方期待的类型不一致。"""

    def __init__(
        self,
        *,
        name: str,
        expected: type[object],
        actual: type[object],
    ) -> None:
        super().__init__(
            f"Capability '{name}' must be {expected.__name__}, "
            f"got {actual.__name__}"
        )
