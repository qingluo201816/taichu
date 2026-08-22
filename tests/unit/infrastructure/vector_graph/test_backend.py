"""Milvus Vector Graph RAG 来源封装测试。"""

import asyncio
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from taichu.application.vector_graph.corpus import (
    build_source_index_state,
    corpus_snapshot_sha256,
    source_documents_sha256,
)

from taichu.application.vector_graph.models import (
    VectorGraphBuildPlan,
    VectorGraphBuildProgress,
    VectorGraphBuildResult,
    VectorGraphBuildStage,
    VectorGraphIndexState,
    VectorGraphSourceDocument,
    VectorGraphSourceIndexManifest,
    VectorGraphSourceIndexState,
    VectorGraphSourceType,
)
from taichu.infrastructure.vector_graph.backend import (
    MilvusVectorGraphBackend,
    _parse_passage,
)


def test_passage_header_round_trips_traceable_source(tmp_path: Path) -> None:
    content = "秦浩轩通过小蛇发现了隐藏灵药。"
    source = VectorGraphSourceDocument(
        source_type=VectorGraphSourceType.MANUSCRIPT_CHUNK,
        source_id="chapter-1",
        source_ref="manuscript:chapter-1:10-26",
        title="第一章",
        content=content,
        content_sha256=hashlib.sha256(content.encode()).hexdigest(),
        updated_at="2026-08-15T00:00:00Z",
        start_char=10,
        end_char=26,
    )
    backend = MilvusVectorGraphBackend(
        milvus_uri="http://127.0.0.1:19530",
        milvus_token="",
        collection_prefix="test_story",
        llm=Mock(),
        llm_model="test-model",
        embedding_base_url="http://127.0.0.1:8011/v1",
        embedding_model="test-embedding",
        embedding_dimensions=2,
        manifest_path=tmp_path / "manifest.json",
    )

    assert backend._settings.milvus_index_type == "HNSW"
    assert backend._settings.milvus_index_params == {
        "M": 24,
        "efConstruction": 300,
    }
    assert backend._hnsw_ef_search == 150
    assert backend._settings.batch_size == 4
    assert backend._settings.relation_number_threshold == 60

    document = backend._to_document(source)
    parsed = _parse_passage(document.page_content)

    assert parsed is not None
    metadata, restored_content = parsed
    assert restored_content == content
    assert metadata["source_ref"] == source.source_ref
    assert metadata["source_type"] == "manuscript_chunk"


def test_status_reports_not_built_when_all_collections_are_absent(
    tmp_path: Path,
) -> None:
    backend = MilvusVectorGraphBackend(
        milvus_uri="http://127.0.0.1:19530",
        milvus_token="",
        collection_prefix="test_story",
        llm=Mock(),
        llm_model="test-model",
        embedding_base_url="http://127.0.0.1:8011/v1",
        embedding_model="test-embedding",
        embedding_dimensions=2,
        manifest_path=tmp_path / "active_manifest.json",
    )
    client = Mock()
    client.has_collection.return_value = False
    plan = VectorGraphBuildPlan(
        snapshot_sha256="a" * 64,
        manuscript_count=100,
        manuscript_chunk_count=1753,
        knowledge_card_count=305,
        document_count=2058,
        total_content_chars=570546,
    )

    with patch(
        "taichu.infrastructure.vector_graph.backend.MilvusClient",
        return_value=client,
    ):
        status = backend._inspect_sync(plan)

    assert status.state is VectorGraphIndexState.NOT_BUILT
    assert status.is_current is False
    assert len(status.collections) == 3
    assert all(not item.exists for item in status.collections)


def test_status_reports_build_progress_from_shared_generated_file(
    tmp_path: Path,
) -> None:
    backend = MilvusVectorGraphBackend(
        milvus_uri="http://127.0.0.1:19530",
        milvus_token="",
        collection_prefix="test_story",
        llm=Mock(),
        llm_model="test-model",
        embedding_base_url="http://127.0.0.1:8011/v1",
        embedding_model="test-embedding",
        embedding_dimensions=2,
        manifest_path=tmp_path / "active_manifest.json",
    )
    client = Mock()
    client.has_collection.return_value = False
    plan = VectorGraphBuildPlan(
        snapshot_sha256="b" * 64,
        manuscript_count=100,
        manuscript_chunk_count=1753,
        knowledge_card_count=305,
        document_count=2058,
        total_content_chars=570546,
    )
    backend._write_progress(
        VectorGraphBuildProgress(
            stage=VectorGraphBuildStage.EXTRACTING,
            snapshot_sha256=plan.snapshot_sha256,
            processed_documents=321,
            total_documents=2058,
            started_at="2026-08-15T00:00:00+00:00",
            updated_at="2026-08-15T00:05:00+00:00",
        )
    )

    with patch(
        "taichu.infrastructure.vector_graph.backend.MilvusClient",
        return_value=client,
    ):
        status = backend._inspect_sync(plan)

    assert status.state is VectorGraphIndexState.BUILDING
    assert status.progress is not None
    assert status.progress.processed_documents == 321


def test_status_requires_source_manifest_before_reporting_current(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    documents = [_source_document(source_id="chapter-1")]
    plan = _plan(documents)
    backend._write_manifest(
        VectorGraphBuildResult(
            status="completed",
            plan=plan,
            entity_count=1,
            relation_count=1,
            passage_count=1,
        )
    )
    client = Mock()
    client.has_collection.return_value = True
    client.get_collection_stats.return_value = {"row_count": 1}

    with (
        patch(
            "taichu.infrastructure.vector_graph.backend.MilvusClient",
            return_value=client,
        ),
        patch(
            "taichu.infrastructure.vector_graph.backend._count_collection_records",
            return_value=1,
        ),
    ):
        status = backend._inspect_sync(plan)

    assert status.state is VectorGraphIndexState.STALE
    assert status.is_current is False
    assert "来源状态尚未接管" in status.message


def test_update_only_replaces_changed_sources_and_deletes_disappeared_sources(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    unchanged = _source_document(source_id="chapter-1", content="未变化正文")
    old_changed = _source_document(source_id="chapter-2", content="旧正文")
    changed = _source_document(source_id="chapter-2", content="新正文")
    added = _source_document(
        source_type=VectorGraphSourceType.KNOWLEDGE_CARD,
        source_id="card-1",
        content="新增知识卡",
    )
    disappeared = _source_document(source_id="chapter-deleted", content="已删除正文")
    documents = [changed, unchanged, added]
    backend._write_source_manifest(
        [
            _source_state(backend, [unchanged]),
            _source_state(backend, [old_changed]),
            _source_state(backend, [disappeared]),
        ]
    )
    backend._llm.extract_triplets = AsyncMock(return_value=[["主语", "关系", "宾语"]])

    with (
        patch.object(
            backend,
            "_passage_source_counts_sync",
            side_effect=[
                {
                    "manuscript_chunk:chapter-1": 1,
                    "manuscript_chunk:chapter-2": 1,
                    "manuscript_chunk:chapter-deleted": 1,
                },
                {
                    "knowledge_card:card-1": 1,
                    "manuscript_chunk:chapter-1": 1,
                    "manuscript_chunk:chapter-2": 1,
                },
            ],
        ),
        patch.object(
            backend,
            "_delete_source_sync",
            return_value=True,
        ) as delete_source,
        patch.object(backend, "_upsert_source_sync") as upsert_source,
        patch.object(
            backend,
            "_collection_counts_sync",
            return_value=(7, 8, 3),
        ),
    ):
        result = asyncio.run(backend.update(documents, plan=_plan(documents)))

    delete_source.assert_called_once_with("manuscript_chunk:chapter-deleted")
    assert [item.args[0] for item in upsert_source.call_args_list] == [
        "knowledge_card:card-1",
        "manuscript_chunk:chapter-2",
    ]
    assert backend._llm.extract_triplets.await_count == 2
    assert result.updated_source_count == 2
    assert result.deleted_source_count == 1
    assert result.unchanged_source_count == 1
    assert (result.entity_count, result.relation_count, result.passage_count) == (
        7,
        8,
        3,
    )
    assert result.index_configuration_sha256 == backend._index_configuration_sha256

    manifest = VectorGraphSourceIndexManifest.model_validate_json(
        backend._source_manifest_path.read_text(encoding="utf-8")
    )
    assert [item.source_key for item in manifest.sources] == [
        "knowledge_card:card-1",
        "manuscript_chunk:chapter-1",
        "manuscript_chunk:chapter-2",
    ]
    states = {item.source_key: item for item in manifest.sources}
    assert states["manuscript_chunk:chapter-1"].source_sha256 == _source_sha256(
        backend, [unchanged]
    )
    assert states["manuscript_chunk:chapter-2"].source_sha256 == _source_sha256(
        backend, [changed]
    )
    assert states["knowledge_card:card-1"].source_sha256 == _source_sha256(
        backend, [added]
    )


def test_update_uses_supplied_triplets_without_calling_llm(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    document = _source_document(source_id="chapter-1", content="第一章正文")
    backend._llm.extract_triplets = AsyncMock(
        side_effect=AssertionError("离线导入不得调用 LLM")
    )
    supplied = {
        (
            document.source_ref,
            document.chunk_index,
            document.content_sha256,
        ): (("秦浩轩", "位于", "大田镇"),)
    }

    with (
        patch.object(
            backend,
            "_passage_source_counts_sync",
            side_effect=[{}, {"manuscript_chunk:chapter-1": 1}],
        ),
        patch.object(backend, "_collection_counts_sync", return_value=(2, 1, 1)),
        patch.object(backend, "_upsert_source_sync") as upsert_source,
    ):
        result = asyncio.run(
            backend.update(
                [document],
                plan=_plan([document]),
                extracted_triplets=supplied,
            )
        )

    backend._llm.extract_triplets.assert_not_awaited()
    indexed_document = upsert_source.call_args.args[1][0]
    assert indexed_document.metadata["triplets"] == [
        ["秦浩轩", "位于", "大田镇"]
    ]
    assert result.passage_count == 1


def test_update_rejects_incomplete_supplied_triplets_before_writing(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    document = _source_document(source_id="chapter-1", content="第一章正文")

    with pytest.raises(ValueError, match="缺少 1 条"):
        asyncio.run(
            backend.update(
                [document],
                plan=_plan([document]),
                extracted_triplets={},
            )
        )


def test_failed_source_is_not_committed_and_next_update_only_retries_that_source(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    chapter_1 = _source_document(source_id="chapter-1", content="第一章正文")
    chapter_2 = _source_document(source_id="chapter-2", content="第二章正文")
    documents = [chapter_1, chapter_2]
    backend._llm.extract_triplets = AsyncMock(return_value=[])

    with (
        patch.object(backend, "_passage_source_counts_sync", return_value={}),
        patch.object(
            backend,
            "_upsert_source_sync",
            side_effect=[None, RuntimeError("第二章写入失败")],
        ) as first_upsert,
        patch.object(backend, "_collection_counts_sync", return_value=(0, 0, 0)),
    ):
        with pytest.raises(RuntimeError, match="第二章写入失败"):
            asyncio.run(backend.update(documents, plan=_plan(documents)))

    assert [item.args[0] for item in first_upsert.call_args_list] == [
        "manuscript_chunk:chapter-1",
        "manuscript_chunk:chapter-2",
    ]
    failed_manifest = VectorGraphSourceIndexManifest.model_validate_json(
        backend._source_manifest_path.read_text(encoding="utf-8")
    )
    assert [item.source_key for item in failed_manifest.sources] == [
        "manuscript_chunk:chapter-1"
    ]

    backend._llm.extract_triplets.reset_mock()
    with (
        patch.object(
            backend,
            "_passage_source_counts_sync",
            side_effect=[
                {"manuscript_chunk:chapter-1": 1},
                {
                    "manuscript_chunk:chapter-1": 1,
                    "manuscript_chunk:chapter-2": 1,
                },
            ],
        ),
        patch.object(backend, "_upsert_source_sync") as retry_upsert,
        patch.object(backend, "_collection_counts_sync", return_value=(1, 1, 2)),
    ):
        result = asyncio.run(backend.update(documents, plan=_plan(documents)))

    retry_upsert.assert_called_once()
    assert retry_upsert.call_args.args[0] == "manuscript_chunk:chapter-2"
    backend._llm.extract_triplets.assert_awaited_once_with("第二章正文")
    assert result.updated_source_count == 1
    assert result.unchanged_source_count == 1
    recovered_manifest = VectorGraphSourceIndexManifest.model_validate_json(
        backend._source_manifest_path.read_text(encoding="utf-8")
    )
    assert [item.source_key for item in recovered_manifest.sources] == [
        "manuscript_chunk:chapter-1",
        "manuscript_chunk:chapter-2",
    ]


def test_source_with_wrong_actual_passage_count_is_replaced_even_when_hash_matches(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    document = _source_document(source_id="chapter-1", content="第一章正文")
    backend._write_source_manifest([_source_state(backend, [document])])
    backend._llm.extract_triplets = AsyncMock(return_value=[])

    with (
        patch.object(
            backend,
            "_passage_source_counts_sync",
            side_effect=[
                {"manuscript_chunk:chapter-1": 2},
                {"manuscript_chunk:chapter-1": 1},
            ],
        ),
        patch.object(backend, "_collection_counts_sync", return_value=(1, 1, 1)),
        patch.object(backend, "_upsert_source_sync") as upsert_source,
    ):
        result = asyncio.run(backend.update([document], plan=_plan([document])))

    upsert_source.assert_called_once()
    backend._llm.extract_triplets.assert_awaited_once_with("第一章正文")
    assert result.updated_source_count == 1
    assert result.unchanged_source_count == 0


def test_source_with_old_configuration_is_replaced_even_when_content_is_unchanged(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    document = _source_document(source_id="chapter-1", content="第一章正文")
    old_state = _source_state(backend, [document]).model_copy(
        update={"index_configuration_sha256": "f" * 64}
    )
    backend._write_source_manifest([old_state])
    backend._llm.extract_triplets = AsyncMock(return_value=[])

    with (
        patch.object(
            backend,
            "_passage_source_counts_sync",
            side_effect=[
                {"manuscript_chunk:chapter-1": 1},
                {"manuscript_chunk:chapter-1": 1},
            ],
        ),
        patch.object(backend, "_collection_counts_sync", return_value=(1, 1, 1)),
        patch.object(backend, "_upsert_source_sync") as upsert_source,
    ):
        result = asyncio.run(backend.update([document], plan=_plan([document])))

    upsert_source.assert_called_once()
    backend._llm.extract_triplets.assert_awaited_once_with("第一章正文")
    assert result.updated_source_count == 1
    manifest = VectorGraphSourceIndexManifest.model_validate_json(
        backend._source_manifest_path.read_text(encoding="utf-8")
    )
    assert (
        manifest.sources[0].index_configuration_sha256
        == backend._index_configuration_sha256
    )


def test_source_with_passage_is_removed_only_after_delete_returns_true(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    removed = _source_document(source_id="chapter-removed")
    backend._write_source_manifest([_source_state(backend, [removed])])

    with (
        patch.object(
            backend,
            "_passage_source_counts_sync",
            side_effect=[{"manuscript_chunk:chapter-removed": 1}, {}],
        ),
        patch.object(backend, "_collection_counts_sync", return_value=(0, 0, 0)),
        patch.object(
            backend,
            "_delete_source_sync",
            return_value=True,
        ) as delete_source,
    ):
        result = asyncio.run(backend.update([], plan=_plan([])))

    delete_source.assert_called_once_with("manuscript_chunk:chapter-removed")
    assert result.deleted_source_count == 1
    manifest = VectorGraphSourceIndexManifest.model_validate_json(
        backend._source_manifest_path.read_text(encoding="utf-8")
    )
    assert manifest.sources == []


def test_source_delete_false_fails_without_removing_source_manifest(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    removed = _source_document(source_id="chapter-removed")
    backend._write_source_manifest([_source_state(backend, [removed])])

    with (
        patch.object(
            backend,
            "_passage_source_counts_sync",
            return_value={"manuscript_chunk:chapter-removed": 1},
        ),
        patch.object(backend, "_collection_counts_sync", return_value=(1, 1, 1)),
        patch.object(backend, "_delete_source_sync", return_value=False),
    ):
        with pytest.raises(RuntimeError, match="未确认.*删除成功"):
            asyncio.run(backend.update([], plan=_plan([])))

    manifest = VectorGraphSourceIndexManifest.model_validate_json(
        backend._source_manifest_path.read_text(encoding="utf-8")
    )
    assert [item.source_key for item in manifest.sources] == [
        "manuscript_chunk:chapter-removed"
    ]


def test_source_delete_exception_fails_without_removing_source_manifest(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    removed = _source_document(source_id="chapter-removed")
    backend._write_source_manifest([_source_state(backend, [removed])])

    with (
        patch.object(
            backend,
            "_passage_source_counts_sync",
            return_value={"manuscript_chunk:chapter-removed": 1},
        ),
        patch.object(backend, "_collection_counts_sync", return_value=(1, 1, 1)),
        patch.object(
            backend,
            "_delete_source_sync",
            side_effect=RuntimeError("连接中断"),
        ),
    ):
        with pytest.raises(RuntimeError, match="删除来源.*失败"):
            asyncio.run(backend.update([], plan=_plan([])))

    manifest = VectorGraphSourceIndexManifest.model_validate_json(
        backend._source_manifest_path.read_text(encoding="utf-8")
    )
    assert [item.source_key for item in manifest.sources] == [
        "manuscript_chunk:chapter-removed"
    ]


def test_stored_delete_source_without_passage_blocks_before_manifest_rewrite(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    removed = _source_document(source_id="chapter-removed")
    backend._write_source_manifest([_source_state(backend, [removed])])

    with (
        patch.object(backend, "_passage_source_counts_sync", return_value={}),
        patch.object(backend, "_collection_counts_sync", return_value=(1, 1, 0)),
        patch.object(backend, "_delete_source_sync") as delete_source,
    ):
        with pytest.raises(RuntimeError, match="段落记录.*已为 0"):
            asyncio.run(backend.update([], plan=_plan([])))

    delete_source.assert_not_called()
    manifest = VectorGraphSourceIndexManifest.model_validate_json(
        backend._source_manifest_path.read_text(encoding="utf-8")
    )
    assert [item.source_key for item in manifest.sources] == [
        "manuscript_chunk:chapter-removed"
    ]
    assert not backend._manifest_path.exists()


def test_failed_upsert_from_older_snapshot_cannot_finalize_as_completed_delete(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    removed = _source_document(source_id="chapter-removed")
    previous_plan = _plan([removed])
    current_plan = _plan([])
    backend._write_source_manifest([_source_state(backend, [removed])])
    backend._write_progress(
        VectorGraphBuildProgress(
            stage=VectorGraphBuildStage.FAILED,
            snapshot_sha256=previous_plan.snapshot_sha256,
            total_sources=1,
            current_source_key="manuscript_chunk:chapter-removed",
            started_at="2026-08-16T00:00:00Z",
            updated_at="2026-08-16T00:01:00Z",
            error_message="来源更新写入失败",
        )
    )

    with (
        patch.object(backend, "_passage_source_counts_sync", return_value={}),
        patch.object(backend, "_collection_counts_sync", return_value=(1, 1, 0)),
        patch.object(backend, "_delete_source_sync") as delete_source,
    ):
        with pytest.raises(RuntimeError, match="段落记录.*已为 0"):
            asyncio.run(backend.update([], plan=current_plan))

    delete_source.assert_not_called()
    manifest = VectorGraphSourceIndexManifest.model_validate_json(
        backend._source_manifest_path.read_text(encoding="utf-8")
    )
    assert [item.source_key for item in manifest.sources] == [
        "manuscript_chunk:chapter-removed"
    ]


def test_failed_delete_with_zero_passage_still_blocks_orphan_graph_rows(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    removed = _source_document(source_id="chapter-removed")
    previous_plan = _plan([removed])
    current_plan = _plan([])
    backend._write_manifest(
        VectorGraphBuildResult(
            status="completed",
            plan=previous_plan,
            index_configuration_sha256=backend._index_configuration_sha256,
            entity_count=2,
            relation_count=3,
            passage_count=1,
        )
    )
    backend._write_source_manifest([_source_state(backend, [removed])])
    backend._write_progress(
        VectorGraphBuildProgress(
            stage=VectorGraphBuildStage.FAILED,
            snapshot_sha256=current_plan.snapshot_sha256,
            total_sources=1,
            current_source_key="manuscript_chunk:chapter-removed",
            started_at="2026-08-16T00:00:00Z",
            updated_at="2026-08-16T00:01:00Z",
            error_message="删除响应中断",
        )
    )

    with (
        patch.object(backend, "_passage_source_counts_sync", return_value={}),
        patch.object(backend, "_collection_counts_sync", return_value=(2, 3, 0)),
        patch.object(backend, "_delete_source_sync") as delete_source,
    ):
        with pytest.raises(RuntimeError, match="段落记录.*已为 0"):
            asyncio.run(backend.update([], plan=current_plan))

    delete_source.assert_not_called()
    source_manifest = VectorGraphSourceIndexManifest.model_validate_json(
        backend._source_manifest_path.read_text(encoding="utf-8")
    )
    assert [item.source_key for item in source_manifest.sources] == [
        "manuscript_chunk:chapter-removed"
    ]
    active_manifest = VectorGraphBuildResult.model_validate_json(
        backend._manifest_path.read_text(encoding="utf-8")
    )
    assert active_manifest.plan == previous_plan
    assert (
        active_manifest.entity_count,
        active_manifest.relation_count,
        active_manifest.passage_count,
    ) == (2, 3, 1)


def test_status_is_incomplete_when_actual_collection_rows_differ_from_manifest(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    document = _source_document(source_id="chapter-1")
    plan = _plan([document])
    backend._write_manifest(
        VectorGraphBuildResult(
            status="completed",
            plan=plan,
            index_configuration_sha256=backend._index_configuration_sha256,
            entity_count=1,
            relation_count=1,
            passage_count=1,
        )
    )
    backend._write_source_manifest([_source_state(backend, [document])])
    client = Mock()
    client.has_collection.return_value = True
    client.get_collection_stats.side_effect = lambda name: {
        "row_count": 2 if name.endswith("_passages") else 1
    }

    with (
        patch(
            "taichu.infrastructure.vector_graph.backend.MilvusClient",
            return_value=client,
        ),
        patch(
            "taichu.infrastructure.vector_graph.backend._count_collection_records",
            side_effect=lambda _client, name: (
                2 if name.endswith("_passages") else 1
            ),
        ),
    ):
        status = backend._inspect_sync(plan)

    assert status.state is VectorGraphIndexState.INCOMPLETE
    assert status.is_current is False
    assert "实际行数" in status.message


def test_non_failed_update_blocks_entity_relation_baseline_mismatch_before_writes(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    document = _source_document(source_id="chapter-1")
    plan = _plan([document])
    backend._write_manifest(
        VectorGraphBuildResult(
            status="completed",
            plan=plan,
            index_configuration_sha256=backend._index_configuration_sha256,
            entity_count=1,
            relation_count=1,
            passage_count=1,
        )
    )
    backend._write_source_manifest([_source_state(backend, [document])])
    backend._llm.extract_triplets = AsyncMock(return_value=[])

    with (
        patch.object(
            backend,
            "_passage_source_counts_sync",
            return_value={"manuscript_chunk:chapter-1": 1},
        ),
        patch.object(backend, "_collection_counts_sync", return_value=(9, 1, 1)),
        patch.object(backend, "_upsert_source_sync") as upsert_source,
        patch.object(
            backend,
            "_delete_source_sync",
            return_value=True,
        ) as delete_source,
    ):
        with pytest.raises(RuntimeError, match="完成清单不一致"):
            asyncio.run(backend.update([document], plan=plan))

    upsert_source.assert_not_called()
    delete_source.assert_not_called()
    backend._llm.extract_triplets.assert_not_awaited()


def test_failed_resume_only_retries_unfinished_source_when_graph_totals_changed(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    documents = [
        _source_document(source_id="chapter-1"),
        _source_document(source_id="chapter-2"),
    ]
    plan = _plan(documents)
    backend._write_manifest(
        VectorGraphBuildResult(
            status="completed",
            plan=plan,
            index_configuration_sha256=backend._index_configuration_sha256,
            entity_count=1,
            relation_count=1,
            passage_count=2,
        )
    )
    backend._write_source_manifest([_source_state(backend, [documents[0]])])
    backend._write_progress(
        VectorGraphBuildProgress(
            stage=VectorGraphBuildStage.FAILED,
            snapshot_sha256=plan.snapshot_sha256,
            processed_documents=1,
            total_documents=2,
            processed_sources=1,
            total_sources=2,
            current_source_key="manuscript_chunk:chapter-2",
            started_at="2026-08-16T00:00:00Z",
            updated_at="2026-08-16T00:01:00Z",
            error_message="来源写入中断",
        )
    )
    backend._llm.extract_triplets = AsyncMock(return_value=[])
    actual_sources = {
        "manuscript_chunk:chapter-1": 1,
    }

    with (
        patch.object(
            backend,
            "_passage_source_counts_sync",
            side_effect=[
                actual_sources,
                {
                    "manuscript_chunk:chapter-1": 1,
                    "manuscript_chunk:chapter-2": 1,
                },
            ],
        ),
        patch.object(
            backend,
            "_collection_counts_sync",
            side_effect=[(2, 3, 1), (4, 5, 2)],
        ),
        patch.object(backend, "_upsert_source_sync") as upsert_source,
    ):
        result = asyncio.run(backend.update(documents, plan=plan))

    upsert_source.assert_called_once()
    assert upsert_source.call_args.args[0] == "manuscript_chunk:chapter-2"
    backend._llm.extract_triplets.assert_awaited_once_with(documents[1].content)
    assert result.updated_source_count == 1
    assert result.unchanged_source_count == 1
    assert (result.entity_count, result.relation_count, result.passage_count) == (
        4,
        5,
        2,
    )
    completed = VectorGraphBuildResult.model_validate_json(
        backend._manifest_path.read_text(encoding="utf-8")
    )
    assert (completed.entity_count, completed.relation_count) == (4, 5)


def test_first_incremental_update_adopts_current_fingerprinted_snapshot_without_llm(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    documents = [_source_document(source_id="chapter-1", content="第一章正文")]
    current_plan = _plan(documents)
    backend._write_manifest(
        VectorGraphBuildResult(
            status="completed",
            plan=current_plan,
            index_configuration_sha256=backend._index_configuration_sha256,
            entity_count=3,
            relation_count=4,
            passage_count=1,
        )
    )
    backend._llm.extract_triplets = AsyncMock(return_value=[])

    with (
        patch.object(backend, "_can_adopt_existing_index_sync", return_value=True),
        patch.object(backend, "_passage_source_counts_sync") as source_counts,
        patch.object(backend, "_upsert_source_sync") as upsert_source,
    ):
        result = asyncio.run(backend.update(documents, plan=current_plan))

    assert result.plan == current_plan
    assert result.updated_source_count == 0
    assert result.unchanged_source_count == 1
    assert result.index_configuration_sha256 == backend._index_configuration_sha256
    backend._llm.extract_triplets.assert_not_awaited()
    source_counts.assert_not_called()
    upsert_source.assert_not_called()
    manifest = VectorGraphSourceIndexManifest.model_validate_json(
        backend._source_manifest_path.read_text(encoding="utf-8")
    )
    assert [item.source_key for item in manifest.sources] == [
        "manuscript_chunk:chapter-1"
    ]


def test_same_passage_total_with_wrong_source_distribution_is_not_adopted(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    documents = [_source_document(source_id="chapter-1", content="第一章正文")]
    current_plan = _plan(documents)
    active_build = VectorGraphBuildResult(
        status="completed",
        plan=current_plan,
        index_configuration_sha256=backend._index_configuration_sha256,
        entity_count=3,
        relation_count=4,
        passage_count=1,
    )
    backend._write_manifest(active_build)
    backend._llm.extract_triplets = AsyncMock(return_value=[])
    collection_client = Mock()
    collection_client.has_collection.return_value = True
    collection_client.get_collection_stats.side_effect = lambda name: {
        "row_count": (
            3 if name.endswith("_entities") else 4 if name.endswith("_relations") else 1
        )
    }
    prepared_store = Mock()
    prepared_store.passage_source_counts.return_value = {
        "manuscript_chunk:another-chapter": 1
    }

    with (
        patch(
            "taichu.infrastructure.vector_graph.backend.MilvusClient",
            return_value=collection_client,
        ),
        patch(
            "taichu.infrastructure.vector_graph.backend._count_collection_records",
            side_effect=lambda _client, name: (
                3
                if name.endswith("_entities")
                else 4
                if name.endswith("_relations")
                else 1
            ),
        ),
        patch(
            "taichu.infrastructure.vector_graph.backend.TaichuHNSWMilvusStore",
            return_value=prepared_store,
        ),
        patch.object(
            backend,
            "_passage_source_counts_sync",
            side_effect=[
                {"manuscript_chunk:another-chapter": 1},
                {"manuscript_chunk:chapter-1": 1},
            ],
        ),
        patch.object(backend, "_collection_counts_sync", return_value=(3, 4, 1)),
        patch.object(backend, "_upsert_source_sync") as upsert_source,
        patch.object(
            backend,
            "_delete_source_sync",
            return_value=True,
        ) as delete_source,
    ):
        result = asyncio.run(backend.update(documents, plan=current_plan))

    prepared_store.ensure_incremental_collections.assert_called_once_with()
    prepared_store.passage_source_counts.assert_called_once_with()
    delete_source.assert_called_once_with("manuscript_chunk:another-chapter")
    upsert_source.assert_called_once()
    assert upsert_source.call_args.args[0] == "manuscript_chunk:chapter-1"
    backend._llm.extract_triplets.assert_awaited_once_with("第一章正文")
    assert result.updated_source_count == 1
    assert result.deleted_source_count == 1


@pytest.mark.parametrize(
    ("snapshot_matches", "has_current_fingerprint"),
    [(True, False), (False, True)],
)
def test_old_or_legacy_active_manifest_is_not_adopted(
    tmp_path: Path,
    snapshot_matches: bool,
    has_current_fingerprint: bool,
) -> None:
    backend = _backend(tmp_path)
    documents = [_source_document(source_id="chapter-1", content="第一章正文")]
    current_plan = _plan(documents)
    old_plan = (
        current_plan
        if snapshot_matches
        else current_plan.model_copy(update={"snapshot_sha256": "f" * 64})
    )
    backend._write_manifest(
        VectorGraphBuildResult(
            status="completed",
            plan=old_plan,
            index_configuration_sha256=(
                backend._index_configuration_sha256 if has_current_fingerprint else None
            ),
            entity_count=3,
            relation_count=4,
            passage_count=1,
        )
    )
    backend._llm.extract_triplets = AsyncMock(return_value=[])

    with (
        patch.object(backend, "_can_adopt_existing_index_sync") as can_adopt,
        patch.object(
            backend,
            "_passage_source_counts_sync",
            side_effect=[
                {"manuscript_chunk:chapter-1": 1},
                {"manuscript_chunk:chapter-1": 1},
            ],
        ),
        patch.object(backend, "_collection_counts_sync", return_value=(3, 4, 1)),
        patch.object(backend, "_upsert_source_sync") as upsert_source,
    ):
        result = asyncio.run(backend.update(documents, plan=current_plan))

    can_adopt.assert_not_called()
    upsert_source.assert_called_once()
    backend._llm.extract_triplets.assert_awaited_once_with("第一章正文")
    assert result.updated_source_count == 1
    assert result.index_configuration_sha256 == backend._index_configuration_sha256


def test_source_writes_use_upstream_source_replacement_api(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    source = _source_document(source_id="chapter-1")
    document = backend._to_document(source)
    rag = Mock()
    rag.delete_documents_by_source.return_value = True

    with patch.object(backend, "_get_rag", return_value=rag):
        backend._upsert_source_sync("manuscript_chunk:chapter-1", [document])
        deleted = backend._delete_source_sync("manuscript_chunk:chapter-1")

    rag.upsert_documents_by_source.assert_called_once_with(
        [document],
        source="manuscript_chunk:chapter-1",
        extract_triplets=False,
        show_progress=False,
    )
    rag.delete_documents_by_source.assert_called_once_with("manuscript_chunk:chapter-1")
    assert deleted is True


def _backend(tmp_path: Path) -> MilvusVectorGraphBackend:
    return MilvusVectorGraphBackend(
        milvus_uri="http://127.0.0.1:19530",
        milvus_token="",
        collection_prefix="test_story",
        llm=Mock(),
        llm_model="test-model",
        embedding_base_url="http://127.0.0.1:8011/v1",
        embedding_model="test-embedding",
        embedding_dimensions=2,
        manifest_path=tmp_path / "active_manifest.json",
    )


def _source_document(
    *,
    source_id: str,
    content: str = "正文",
    source_type: VectorGraphSourceType = VectorGraphSourceType.MANUSCRIPT_CHUNK,
) -> VectorGraphSourceDocument:
    source_prefix = (
        "manuscript"
        if source_type is VectorGraphSourceType.MANUSCRIPT_CHUNK
        else "knowledge"
    )
    return VectorGraphSourceDocument(
        source_type=source_type,
        source_id=source_id,
        source_ref=f"{source_prefix}:{source_id}",
        title=source_id,
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        updated_at="2026-08-16T00:00:00Z",
    )


def _plan(documents: list[VectorGraphSourceDocument]) -> VectorGraphBuildPlan:
    return VectorGraphBuildPlan(
        snapshot_sha256=corpus_snapshot_sha256(documents),
        manuscript_count=len(
            {
                document.source_id
                for document in documents
                if document.source_type is VectorGraphSourceType.MANUSCRIPT_CHUNK
            }
        ),
        manuscript_chunk_count=sum(
            document.source_type is VectorGraphSourceType.MANUSCRIPT_CHUNK
            for document in documents
        ),
        knowledge_card_count=sum(
            document.source_type is VectorGraphSourceType.KNOWLEDGE_CARD
            for document in documents
        ),
        document_count=len(documents),
        total_content_chars=sum(len(document.content) for document in documents),
    )


def _source_state(
    backend: MilvusVectorGraphBackend,
    documents: list[VectorGraphSourceDocument],
) -> VectorGraphSourceIndexState:
    return build_source_index_state(
        documents,
        indexed_at="2026-08-16T00:00:00Z",
        index_configuration_sha256=backend._index_configuration_sha256,
    )


def _source_sha256(
    backend: MilvusVectorGraphBackend,
    documents: list[VectorGraphSourceDocument],
) -> str:
    return source_documents_sha256(
        documents,
        index_configuration_sha256=backend._index_configuration_sha256,
    )
