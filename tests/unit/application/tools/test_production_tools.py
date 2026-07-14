"""第一版真实正文、卷章和知识 Tool 的集成式单元测试。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from pathlib import Path
from types import ModuleType
from typing import Any

from taichu.application.capabilities import CapabilityContext
from taichu.application.invocations.models import InvocationContext
from taichu.application.services.chapter_service import ChapterService
from taichu.application.services.invocation_policy_service import (
    InvocationPolicyService,
)
from taichu.application.services.knowledge_service import KnowledgeService
from taichu.application.services.outline_service import OutlineService
from taichu.application.services.retrieval_service import RetrievalService
from taichu.application.tools import (
    apply_manuscript_patch,
    create_confirmed_knowledge,
    create_novel_structure_items,
    delete_novel_structure_items,
    get_novel_structure,
    list_knowledge_catalog,
    preview_manuscript_patch,
    read_knowledge_cards,
    read_manuscript,
    resolve_knowledge_identity,
    search_manuscript,
    update_confirmed_knowledge,
    update_novel_structure,
)
from taichu.application.tools.contract import ToolPlugin
from taichu.application.tools.knowledge_retrieval import tool as retrieve_knowledge
from taichu.application.tools.registry import ToolRegistry
from taichu.infrastructure.retrieval import (
    JsonlRetrievalTraceRepository,
    MongoLexicalRetrievalBackend,
)
from taichu.infrastructure.storage.markdown_backend import ProjectAssetStorageBackend
from tests.fakes import InMemoryKnowledgeRepository


def _async_test(
    test: Callable[..., Coroutine[Any, Any, None]],
) -> Callable[..., None]:
    @wraps(test)
    def run(*args: Any, **kwargs: Any) -> None:
        asyncio.run(test(*args, **kwargs))

    return run


@_async_test
async def test_manuscript_patch_and_structure_writes_are_real_and_guarded(
    tmp_path: Path,
) -> None:
    storage = ProjectAssetStorageBackend(tmp_path)
    chapter_service = ChapterService(storage)
    outline_service = OutlineService(storage)
    initial_outline = await outline_service.create_volume("第一卷")
    volume_id = initial_outline.volumes[0].volume_id
    initial_outline = await outline_service.create_chapter(volume_id, "开端")
    chapter_id = initial_outline.current_chapter_id
    assert chapter_id is not None
    await chapter_service.save_chapter(chapter_id, "旧内容。秦阳走入山门。")

    policy = InvocationPolicyService()
    context = CapabilityContext(
        capabilities={
            "chapter_service": chapter_service,
            "outline_service": outline_service,
            "invocation_policy_service": policy,
        }
    )
    registry = ToolRegistry(context)
    _register_modules(
        registry,
        [
            get_novel_structure,
            read_manuscript,
            search_manuscript,
            preview_manuscript_patch,
            apply_manuscript_patch,
            create_novel_structure_items,
            update_novel_structure,
            delete_novel_structure_items,
        ],
    )
    invocation = _invocation()

    read = await registry.invoke(
        "read_manuscript",
        {"chapter_ids": [chapter_id]},
        invocation,
    )
    base_hash = _output(read).chunks[0].content_sha256
    search = await registry.invoke(
        "search_manuscript",
        {"query": "秦阳", "max_hits": 5},
        invocation,
    )
    assert _output(search).hits[0].chapter_id == chapter_id

    preview = await registry.invoke(
        "preview_manuscript_patch",
        {
            "chapter_id": chapter_id,
            "base_content_sha256": base_hash,
            "operations": [
                {
                    "operation": "replace_span",
                    "start_char": 0,
                    "end_char": 3,
                    "text": "新内容",
                }
            ],
        },
        invocation,
    )
    apply_payload = {
        "patch_id": _output(preview).patch_id,
        "chapter_id": chapter_id,
        "base_content_sha256": base_hash,
        "expected_content_sha256": _output(preview).expected_content_sha256,
        "operations": _output(preview).normalized_operations,
        "idempotency_key": "patch-idem-0001",
    }
    grant = await policy.issue_author_write(
        task_id=invocation.task_id,
        tool_name="apply_manuscript_patch",
        input_payload=apply_payload,
        resource_scopes=(f"chapter:{chapter_id}",),
    )
    authorized_patch = {**apply_payload, "author_grant_id": grant.grant_id}
    first_apply = await registry.invoke(
        "apply_manuscript_patch", authorized_patch, invocation
    )
    second_apply = await registry.invoke(
        "apply_manuscript_patch", authorized_patch, invocation
    )
    assert _output(first_apply).content_sha256 == _output(second_apply).content_sha256
    assert (await chapter_service.read_chapter(chapter_id)).markdown.startswith(
        "新内容"
    )

    structure = await registry.invoke("get_novel_structure", {}, invocation)
    create_payload = {
        "expected_structure_version": _output(structure).structure_version,
        "items": [{"kind": "chapter", "title": "第二幕", "volume_id": volume_id}],
        "idempotency_key": "structure-create-0001",
    }
    create_grant = await policy.issue_author_write(
        task_id=invocation.task_id,
        tool_name="create_novel_structure_items",
        input_payload=create_payload,
        resource_scopes=(f"volume:{volume_id}",),
    )
    created = await registry.invoke(
        "create_novel_structure_items",
        {**create_payload, "author_grant_id": create_grant.grant_id},
        invocation,
    )
    created_chapter_id = _output(created).changes[0].item_id

    update_payload = {
        "expected_structure_version": _output(created).structure_version,
        "operations": [
            {
                "operation": "rename_chapter",
                "target_id": created_chapter_id,
                "title": "改名后的第二幕",
            }
        ],
        "idempotency_key": "structure-update-0001",
    }
    update_grant = await policy.issue_author_write(
        task_id=invocation.task_id,
        tool_name="update_novel_structure",
        input_payload=update_payload,
        resource_scopes=(f"chapter:{created_chapter_id}",),
    )
    updated = await registry.invoke(
        "update_novel_structure",
        {**update_payload, "author_grant_id": update_grant.grant_id},
        invocation,
    )
    assert "改名后的第二幕" in _output(updated).changes[0].title

    delete_payload = {
        "expected_structure_version": _output(updated).structure_version,
        "targets": [{"kind": "chapter", "target_id": created_chapter_id}],
        "impact_acknowledgement": "确认归档该章节正文",
        "idempotency_key": "structure-delete-0001",
    }
    delete_grant = await policy.issue_author_write(
        task_id=invocation.task_id,
        tool_name="delete_novel_structure_items",
        input_payload=delete_payload,
        resource_scopes=(f"chapter:{created_chapter_id}",),
        second_confirmation=True,
    )
    deleted = await registry.invoke(
        "delete_novel_structure_items",
        {**delete_payload, "author_grant_id": delete_grant.grant_id},
        invocation,
    )
    assert _output(deleted).changes[0].action == "archived"
    assert all(
        item.id != created_chapter_id for item in await chapter_service.list_chapters()
    )


@_async_test
async def test_four_knowledge_reads_and_confirmed_writes_share_real_services(
    tmp_path: Path,
) -> None:
    repository = InMemoryKnowledgeRepository()
    knowledge_service = KnowledgeService(repository)
    retrieval_service = RetrievalService(
        MongoLexicalRetrievalBackend(repository),
        JsonlRetrievalTraceRepository(tmp_path),
    )
    policy = InvocationPolicyService()
    context = CapabilityContext(
        capabilities={
            "knowledge_service": knowledge_service,
            "retrieval_service": retrieval_service,
            "invocation_policy_service": policy,
        }
    )
    registry = ToolRegistry(context)
    _register_modules(
        registry,
        [
            retrieve_knowledge,
            resolve_knowledge_identity,
            list_knowledge_catalog,
            read_knowledge_cards,
            create_confirmed_knowledge,
            update_confirmed_knowledge,
        ],
    )
    invocation = _invocation()
    create_payload = {
        "knowledge_type": "character",
        "card": {
            "name": "秦阳",
            "aliases": ["秦师兄"],
            "summary": "太初教弟子。",
            "source_origin": "manual",
            "source_note": "作者确认。",
            "role_type": "protagonist",
        },
        "source_refs": ["manuscript:chapter-1:0-20"],
        "idempotency_key": "knowledge-create-0001",
    }
    grant = await policy.issue_author_write(
        task_id=invocation.task_id,
        tool_name="create_confirmed_knowledge",
        input_payload=create_payload,
        resource_scopes=("knowledge:character:秦阳",),
    )
    created = await registry.invoke(
        "create_confirmed_knowledge",
        {**create_payload, "author_grant_id": grant.grant_id},
        invocation,
    )
    card = _output(created).card

    relevance = await registry.invoke(
        "retrieve_knowledge",
        {"query_text": "秦阳是谁"},
        invocation,
    )
    identity = await registry.invoke(
        "resolve_knowledge_identity",
        {"knowledge_type": "character", "name": "秦师兄"},
        invocation,
    )
    catalog = await registry.invoke(
        "list_knowledge_catalog",
        {"knowledge_types": ["character"], "limit": 10},
        invocation,
    )
    directed = await registry.invoke(
        "read_knowledge_cards",
        {"card_ids": [card.id, "missing-card"]},
        invocation,
    )
    assert _output(relevance).items[0].source_id == card.id
    assert _output(identity).resolution == "unique"
    assert _output(catalog).items[0].card_id == card.id
    assert _output(directed).cards[0].id == card.id
    assert _output(directed).missing_card_ids == ["missing-card"]

    update_payload = {
        "card_id": card.id,
        "expected_updated_at": card.updated_at,
        "updates": {"summary": "太初教弟子，也是本书主角。"},
        "merge_mode": "overwrite",
        "source_refs": ["author:confirmation-1"],
        "idempotency_key": "knowledge-update-0001",
    }
    update_grant = await policy.issue_author_write(
        task_id=invocation.task_id,
        tool_name="update_confirmed_knowledge",
        input_payload=update_payload,
        resource_scopes=(f"knowledge:{card.id}",),
    )
    updated = await registry.invoke(
        "update_confirmed_knowledge",
        {**update_payload, "author_grant_id": update_grant.grant_id},
        invocation,
    )
    assert _output(updated).card.summary.endswith("本书主角。")
    assert _output(updated).changed_fields == ["summary"]


def _register_modules(registry: ToolRegistry, modules: list[ModuleType]) -> None:
    for module in modules:
        registry.register(ToolPlugin(manifest=module.manifest, run=module.run))


def _output(envelope: object) -> Any:
    return getattr(envelope, "output")


def _invocation() -> InvocationContext:
    return InvocationContext(
        task_id="task-production-tools",
        run_id="run-production-tools",
        caller_type="orchestrator",
        caller_name="orchestrator",
    )
