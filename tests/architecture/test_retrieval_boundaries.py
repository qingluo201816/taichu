"""防止 AI 消费者绕过统一召回直读知识仓储。"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_APPLICATION = _ROOT / "src" / "taichu" / "application"
_FORBIDDEN_CALLS = {"list_confirmed_cards", "search_confirmed_identity"}
_FORBIDDEN_IMPORT_PREFIXES = (
    "taichu.infrastructure.knowledge",
    "taichu.infrastructure.retrieval.mongo_lexical_backend",
)
_ALLOWED_APPLICATION_EXCEPTIONS = {
    _APPLICATION / "services" / "knowledge_service.py",
}


def test_ai_consumers_do_not_bypass_unified_retrieval() -> None:
    violations: list[str] = []
    for path in _consumer_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _called_name(node.func) in _FORBIDDEN_CALLS:
                violations.append(
                    f"{path.relative_to(_ROOT)}:{node.lineno} 直接调用知识仓储读取"
                )
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith(_FORBIDDEN_IMPORT_PREFIXES):
                    violations.append(
                        f"{path.relative_to(_ROOT)}:{node.lineno} 直接依赖知识基础设施"
                    )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(_FORBIDDEN_IMPORT_PREFIXES):
                        violations.append(
                            f"{path.relative_to(_ROOT)}:{node.lineno} 直接依赖知识基础设施"
                        )
    assert not violations, "发现绕过统一召回的 AI 消费者：\n" + "\n".join(violations)


def _consumer_files() -> list[Path]:
    roots = [
        _APPLICATION / "agents",
        _APPLICATION / "subagents",
        _APPLICATION / "general_agent",
        _APPLICATION / "tools",
        _APPLICATION / "services",
        _APPLICATION / "workflows",
    ]
    files = {path for root in roots for path in root.rglob("*.py")}
    return sorted(files - _ALLOWED_APPLICATION_EXCEPTIONS)


def _called_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None
