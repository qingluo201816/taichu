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
    # 离线索引维护服务从 MongoDB 事实源生成可删除的 Milvus 派生索引；
    # 查询侧只通过独立的 Vector Graph RAG 能力返回带来源的证据。
    _APPLICATION / "vector_graph" / "service.py",
}
_ALLOWED_DIRECT_READS = {
    # 写 Tool 的副作用对账必须核对 MongoDB 权威状态，不能使用带排名、
    # 截断和回退的 AI 召回结果证明一次写入是否已经生效。
    _APPLICATION / "tools" / "create_confirmed_knowledge.py": {
        "reconcile": {"search_confirmed_identity"},
    },
}


def test_ai_consumers_do_not_bypass_unified_retrieval() -> None:
    violations: list[str] = []
    for path in _consumer_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        allowed_direct_reads = _allowed_direct_read_node_ids(path, tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and _called_name(node.func) in _FORBIDDEN_CALLS
                and id(node) not in allowed_direct_reads
            ):
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


def _allowed_direct_read_node_ids(path: Path, tree: ast.Module) -> set[int]:
    allowed_by_function = _ALLOWED_DIRECT_READS.get(path, {})
    allowed: set[int] = set()
    for statement in tree.body:
        if not isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        allowed_calls = allowed_by_function.get(statement.name, set())
        for node in ast.walk(statement):
            if isinstance(node, ast.Call) and _called_name(node.func) in allowed_calls:
                allowed.add(id(node))
    return allowed
