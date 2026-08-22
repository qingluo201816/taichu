"""CapabilityResult 应用层合同的稳定身份与 owner 边界测试。"""

from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError

from taichu.application.contracts.general_agent_capability_results import (
    CAPABILITY_RESULT_ID_TAG,
    CapabilityResultOwner,
    CapabilityResultRecord,
    DeleteRunOutcome,
    GeneralAgentCapabilityResultRepository,
    ResultIdentityPayload,
    build_capability_result_record,
    capability_result_id,
)


def _owner(
    *,
    conversation_id: str = "conversation_001",
    run_id: str = "general_run_20260730_120000_abc123",
) -> CapabilityResultOwner:
    return CapabilityResultOwner(
        conversation_id=conversation_id,
        run_id=run_id,
    )


def _identity(
    *,
    owner: CapabilityResultOwner | None = None,
) -> ResultIdentityPayload:
    return ResultIdentityPayload(
        owner=owner or _owner(),
        plan_revision=2,
        node_id="retrieve_canon",
        attempt_id="attempt_0123456789abcdef0123456789abcdef",
        capability_kind="tool",
        capability_name="search_manuscript",
        input_sha256="1" * 64,
        handler_identity_sha256="2" * 64,
        input_schema_sha256="3" * 64,
        output_schema_sha256="4" * 64,
    )


@pytest.mark.parametrize(
    "invalid_id",
    [
        "",
        ".",
        "..",
        "../run",
        "conversation/run",
        r"conversation\run",
        "C:run",
        "run\x00id",
        "é",
        " run",
        "run ",
        "a" * 129,
    ],
)
def test_owner_rejects_noncanonical_or_path_escaping_ids(
    invalid_id: str,
) -> None:
    with pytest.raises(ValidationError):
        CapabilityResultOwner(
            conversation_id=invalid_id,
            run_id="general_run_20260730_120000_abc123",
        )


def test_owner_is_mandatory_and_run_id_alone_is_not_a_lookup_key() -> None:
    with pytest.raises(ValidationError):
        ResultIdentityPayload.model_validate(
            {
                "plan_revision": 2,
                "node_id": "retrieve_canon",
                "attempt_id": "attempt_0123456789abcdef0123456789abcdef",
                "capability_kind": "tool",
                "capability_name": "search_manuscript",
                "input_sha256": "1" * 64,
                "handler_identity_sha256": "2" * 64,
                "input_schema_sha256": "3" * 64,
                "output_schema_sha256": "4" * 64,
            }
        )


def test_result_id_is_stable_canonical_hash_with_machine_tag() -> None:
    identity = _identity()
    payload = identity.model_dump(mode="json")
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    expected = "cr_" + hashlib.sha256(
        CAPABILITY_RESULT_ID_TAG.encode("utf-8") + b"\0" + canonical
    ).hexdigest()

    assert capability_result_id(identity) == expected
    assert capability_result_id(
        ResultIdentityPayload.model_validate(payload)
    ) == expected


def test_same_run_id_in_different_conversations_has_different_identity() -> None:
    first = _identity(owner=_owner(conversation_id="conversation_a"))
    second = _identity(owner=_owner(conversation_id="conversation_b"))

    assert first.owner.run_id == second.owner.run_id
    assert capability_result_id(first) != capability_result_id(second)


def test_identity_rejects_float_coercion_and_missing_canonical_keys() -> None:
    payload = _identity().model_dump(mode="json")
    payload["plan_revision"] = 2.0
    with pytest.raises(ValidationError):
        ResultIdentityPayload.model_validate(payload)

    payload = _identity().model_dump(mode="json")
    payload.pop("output_schema_sha256")
    with pytest.raises(ValidationError):
        ResultIdentityPayload.model_validate(payload)


def test_completed_record_rejects_noncanonical_result_id() -> None:
    record = build_capability_result_record(
        identity=_identity(),
        output={"answer": "海雾来自已确认正文。"},
        source_refs=("chapter_001",),
        artifact_refs=("artifact_001",),
        trace_id="trace_001",
        committed_at="2026-07-30T12:00:00Z",
    )
    payload = record.model_dump(mode="json")
    payload["result_id"] = "cr_" + "f" * 64

    with pytest.raises(ValidationError, match="结果标识"):
        CapabilityResultRecord.model_validate(payload)


def test_completed_record_rejects_cross_owner_forgery() -> None:
    record = build_capability_result_record(
        identity=_identity(),
        output={"answer": "已完成。"},
        committed_at="2026-07-30T12:00:00Z",
    )
    payload = record.model_dump(mode="json")
    payload["owner"] = _owner(conversation_id="conversation_other").model_dump(
        mode="json"
    )

    with pytest.raises(ValidationError, match="所有者"):
        CapabilityResultRecord.model_validate(payload)


def test_completed_record_detects_content_tampering() -> None:
    record = build_capability_result_record(
        identity=_identity(),
        output={"answer": "原始结果"},
        committed_at="2026-07-30T12:00:00Z",
    )
    payload = record.model_dump(mode="json")
    payload["output"] = {"answer": "被篡改结果"}

    with pytest.raises(ValidationError, match="内容校验"):
        CapabilityResultRecord.model_validate(payload)


def test_repository_protocol_and_unknown_delete_outcome_are_explicit() -> None:
    assert GeneralAgentCapabilityResultRepository
    assert DeleteRunOutcome.NOT_FOUND == "not_found"
    assert DeleteRunOutcome.DELETED == "deleted"
