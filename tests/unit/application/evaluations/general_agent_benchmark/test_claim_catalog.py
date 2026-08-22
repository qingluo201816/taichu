"""需求 2.3、2.4、3.2、3.3、10.3、10.8、11.5：独立 ClaimCatalog。"""

from __future__ import annotations

import builtins
import json
import socket
from pathlib import Path
from typing import Mapping

import pytest

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.claim_catalog import (
    DEFAULT_CLAIM_NORMALIZER_REGISTRY,
    ClaimCatalog,
    ClaimNormalizerRef,
    ClaimNormalizerRegistry,
    NormalizerDescriptor,
    NormalizerKind,
    NormalizerRegistration,
    OracleRuleSetIdentity,
    load_claim_catalog,
    validate_claim_references,
)

_ROOT = Path("tests/fixtures/evaluations/general_writing_agent_benchmark")
_CATALOG_PATH = _ROOT / "claim-catalog.json"
_MANIFEST_PATH = (
    _ROOT / "fixtures" / "core_novel" / "fixture-manifest.json"
)
_SUITE_PATH = _ROOT / "suite.json"


def _hidden_file_reader(value: str) -> str:
    return Path(value).read_text(encoding="utf-8")


_ALIASED_FILE_READER = _hidden_file_reader
_ALIASED_DYNAMIC_IMPORT = __import__


def _fixture_refs() -> frozenset[str]:
    payload = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return frozenset(item["asset_id"] for item in payload["scenario_assets"])


def _catalog_payload() -> dict[str, object]:
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


def _write_catalog(
    tmp_path: Path,
    payload: dict[str, object],
    *,
    refresh_hash: bool = True,
) -> Path:
    if refresh_hash:
        payload["content_hash"] = canonical_sha256(
            {
                key: value
                for key, value in payload.items()
                if key != "content_hash"
            }
        )
    path = tmp_path / "claim-catalog.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _load(
    path: Path = _CATALOG_PATH,
    *,
    registry: ClaimNormalizerRegistry = DEFAULT_CLAIM_NORMALIZER_REGISTRY,
    referenced_claim_ids: tuple[str, ...] = (),
) -> ClaimCatalog:
    return load_claim_catalog(
        path,
        registry=registry,
        known_fixture_refs=_fixture_refs(),
        referenced_claim_ids=referenced_claim_ids,
    )


def _descriptor(
    *,
    version: str = "1",
    description: str = "测试用纯文本 Claim 规范化器。",
) -> NormalizerDescriptor:
    return NormalizerDescriptor(
        normalizer_id="claim_text",
        version=version,
        kind=NormalizerKind.CLAIM_TEXT,
        description=description,
        operations=(
            "unicode_nfc",
            "whitespace",
            "punctuation",
            "finite_aliases",
        ),
    )


def _identity(
    catalog: ClaimCatalog,
    registry: ClaimNormalizerRegistry = DEFAULT_CLAIM_NORMALIZER_REGISTRY,
) -> OracleRuleSetIdentity:
    return OracleRuleSetIdentity.create(catalog=catalog, registry=registry)


def test_requirement_2_3_catalog_fixture_has_strict_typed_canonical_identity() -> None:
    catalog = _load()
    payload = _catalog_payload()

    assert catalog.schema_ == "taichu.general_agent_benchmark.claim_catalog@1"
    assert catalog.catalog_version == 1
    assert catalog.fixture_id == "core_novel"
    assert tuple(item.claim_id for item in catalog.claims) == tuple(
        sorted(item.claim_id for item in catalog.claims)
    )
    assert catalog.content_hash == canonical_sha256(
        {
            key: value
            for key, value in payload.items()
            if key != "content_hash"
        }
    )
    assert all(item.canonical_forms for item in catalog.claims)
    assert all(item.source_fixture_refs for item in catalog.claims)
    assert all(item.allowed_normalizers for item in catalog.claims)
    assert all(
        item.polarity.value in {"positive", "negative"}
        for item in catalog.claims
    )


@pytest.mark.parametrize(
    "mutation, expected_message",
    [
        (
            lambda payload: payload.update({"unexpected_field": True}),
            "额外",
        ),
        (
            lambda payload: payload["claims"].append(
                dict(payload["claims"][0])
            ),
            "claim_id",
        ),
        (
            lambda payload: payload["claims"][0]["source_fixture_refs"].append(
                "unknown_fixture_source"
            ),
            "夹具",
        ),
        (
            lambda payload: payload["claims"][0]["allowed_normalizers"].append(
                {
                    "normalizer_id": "claim_text",
                    "version": "999",
                }
            ),
            "normalizer",
        ),
    ],
)
def test_requirement_10_8_catalog_rejects_schema_duplicates_dangling_sources_and_rules(
    tmp_path: Path,
    mutation: object,
    expected_message: str,
) -> None:
    payload = _catalog_payload()
    mutation(payload)  # type: ignore[operator]

    with pytest.raises(ValueError, match=expected_message):
        _load(_write_catalog(tmp_path, payload))


def test_requirement_10_8_dangling_suite_claim_reference_is_rejected() -> None:
    catalog = _load()

    with pytest.raises(ValueError, match="missing_claim"):
        validate_claim_references(catalog, ("missing_claim",))

    with pytest.raises(ValueError, match="missing_claim"):
        _load(referenced_claim_ids=("missing_claim",))


def test_requirement_2_4_scripted_response_cannot_enter_expected_truth(
    tmp_path: Path,
) -> None:
    payload = _catalog_payload()
    payload["claims"][0]["scripted_response"] = {
        "content": "脚本预置答案不得成为真值。"
    }

    with pytest.raises(ValueError, match="脚本|额外"):
        _load(_write_catalog(tmp_path, payload))

    catalog = _load()
    identity = _identity(catalog)
    suite_payload = json.loads(_SUITE_PATH.read_text(encoding="utf-8"))
    suite_payload["cases"][0]["scripted_steps"][0]["response"] = {
        "content": "任意替换脚本响应"
    }

    assert _load().content_hash == catalog.content_hash
    assert _identity(_load()) == identity


def test_requirement_3_2_registry_is_static_pure_and_uses_only_finite_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = DEFAULT_CLAIM_NORMALIZER_REGISTRY
    normalizer = ClaimNormalizerRef(
        normalizer_id="claim_text",
        version="1",
    )

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("规范化器不得访问文件、网络或数据库。")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)

    normalized = registry.normalize(
        normalizer,
        "  潮灯\u3000会暂存共同记忆！  ",
        aliases={"潮灯": "归潮灯"},
    )

    assert normalized == "归潮灯 会暂存共同记忆!"
    assert not hasattr(registry, "register")
    with pytest.raises(AttributeError):
        setattr(registry, "registry_descriptor_sha256", "0" * 64)
    with pytest.raises(ValueError, match="未注册"):
        registry.resolve(
            ClaimNormalizerRef(
                normalizer_id="claim_text",
                version="999",
            )
        )


def test_requirement_3_2_registry_rejects_dynamic_import_and_io_callables() -> None:
    def reads_file(
        value: str,
        aliases: Mapping[str, str],
    ) -> str:
        del aliases
        return Path(value).read_text(encoding="utf-8")

    def imports_module(
        value: str,
        aliases: Mapping[str, str],
    ) -> str:
        del aliases
        return __import__(value).__name__

    def reads_file_through_alias(
        value: str,
        aliases: Mapping[str, str],
    ) -> str:
        del aliases
        return _ALIASED_FILE_READER(value)

    def imports_module_through_alias(
        value: str,
        aliases: Mapping[str, str],
    ) -> str:
        del aliases
        return _ALIASED_DYNAMIC_IMPORT(value).__name__

    for function in (
        reads_file,
        imports_module,
        reads_file_through_alias,
        imports_module_through_alias,
    ):
        with pytest.raises(ValueError, match="纯函数|禁止"):
            ClaimNormalizerRegistry(
                (
                    NormalizerRegistration(
                        descriptor=_descriptor(),
                        function=function,
                    ),
                )
            )


def test_requirement_2_3_rule_identity_changes_with_alias_descriptor_or_code(
    tmp_path: Path,
) -> None:
    catalog = _load()
    baseline = _identity(catalog)

    changed_payload = _catalog_payload()
    changed_payload["claims"][0]["aliases"].append(
        {
            "alias": "全新有限别名",
            "canonical": changed_payload["claims"][0]["canonical_forms"][0],
        }
    )
    changed_payload["claims"][0]["aliases"] = sorted(
        changed_payload["claims"][0]["aliases"],
        key=lambda item: (item["alias"], item["canonical"]),
    )
    changed_catalog = _load(_write_catalog(tmp_path, changed_payload))
    assert _identity(changed_catalog).oracle_rule_set_sha256 != (
        baseline.oracle_rule_set_sha256
    )

    def same_implementation(
        value: str,
        aliases: Mapping[str, str],
    ) -> str:
        del aliases
        return value

    descriptor_registry = ClaimNormalizerRegistry(
        (
            NormalizerRegistration(
                descriptor=_descriptor(description="描述符已变化。"),
                function=same_implementation,
            ),
        )
    )
    descriptor_identity = _identity(catalog, descriptor_registry)
    assert descriptor_identity.registry_descriptor_sha256 != (
        baseline.registry_descriptor_sha256
    )
    assert descriptor_identity.oracle_rule_set_sha256 != (
        baseline.oracle_rule_set_sha256
    )

    def changed_implementation(
        value: str,
        aliases: Mapping[str, str],
    ) -> str:
        del aliases
        return value.strip()

    implementation_registry = ClaimNormalizerRegistry(
        (
            NormalizerRegistration(
                descriptor=_descriptor(),
                function=changed_implementation,
            ),
        )
    )
    implementation_identity = _identity(catalog, implementation_registry)
    assert implementation_identity.normalizer_implementation_sha256 != (
        baseline.normalizer_implementation_sha256
    )
    assert implementation_identity.oracle_rule_set_sha256 != (
        baseline.oracle_rule_set_sha256
    )


def test_requirement_10_8_declared_content_identity_drift_is_rejected(
    tmp_path: Path,
) -> None:
    payload = _catalog_payload()
    payload["claims"][0]["object"] = "capability_changed"
    drifted = _write_catalog(tmp_path, payload, refresh_hash=False)

    with pytest.raises(ValueError, match="content_hash"):
        _load(drifted)
