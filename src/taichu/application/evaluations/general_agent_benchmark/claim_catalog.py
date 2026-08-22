"""独立 ClaimCatalog、静态文本规范化注册表与 Oracle 规则身份。"""

from __future__ import annotations

import builtins
import dis
import hashlib
import json
import types
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from taichu.application.evaluations.general_agent_benchmark.canonical import (
    canonical_sha256,
)
from taichu.application.evaluations.general_agent_benchmark.models import (
    BenchmarkModel,
    Sha256,
    StableId,
)

NormalizerVersion: TypeAlias = Annotated[
    str,
    StringConstraints(pattern=r"^[1-9][0-9]{0,3}$"),
]
ClaimNormalizerFunction: TypeAlias = Callable[[str, Mapping[str, str]], str]

_CATALOG_SCHEMA = "taichu.general_agent_benchmark.claim_catalog@1"
_RULE_SET_SCHEMA = "taichu.general_agent_benchmark.oracle_rule_set@1"
_REGISTRY_DESCRIPTOR_SCHEMA = (
    "taichu.general_agent_benchmark.normalizer_registry@1"
)
_REGISTRY_IMPLEMENTATION_SCHEMA = (
    "taichu.general_agent_benchmark.normalizer_implementation@1"
)
_FORBIDDEN_TRUTH_FIELDS = frozenset(
    {
        "model_response",
        "response",
        "scripted_response",
        "scripted_steps",
    }
)
_FORBIDDEN_NORMALIZER_NAMES = frozenset(
    {
        "MongoClient",
        "Path",
        "__import__",
        "compile",
        "connect",
        "eval",
        "exec",
        "httpx",
        "import_module",
        "open",
        "os",
        "pymongo",
        "requests",
        "socket",
        "sqlite3",
        "subprocess",
        "urlopen",
    }
)
_ALLOWED_NORMALIZER_GLOBALS = MappingProxyType(
    {
        "len": builtins.len,
        "sorted": builtins.sorted,
        "str": builtins.str,
        "unicodedata": unicodedata,
    }
)
_MAX_ALIAS_COUNT = 256
_MAX_ALIAS_CHARS = 32_000


class ClaimPolarity(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class NormalizerKind(StrEnum):
    CLAIM_TEXT = "claim_text"


class NormalizerOperation(StrEnum):
    UNICODE_NFC = "unicode_nfc"
    WHITESPACE = "whitespace"
    PUNCTUATION = "punctuation"
    FINITE_ALIASES = "finite_aliases"


class ClaimNormalizerRef(BenchmarkModel):
    normalizer_id: StableId
    version: NormalizerVersion


class ClaimAliasSpec(BenchmarkModel):
    alias: str = Field(min_length=1, max_length=500)
    canonical: str = Field(min_length=1, max_length=500)

    @field_validator("alias", "canonical")
    @classmethod
    def _text_is_already_canonical(cls, value: str) -> str:
        return _require_canonical_text(value, field_name="claim alias")


class ExpectedClaimSpec(BenchmarkModel):
    claim_id: StableId
    subject: StableId
    predicate: StableId
    object: StableId
    polarity: ClaimPolarity
    canonical_forms: tuple[str, ...] = Field(min_length=1)
    aliases: tuple[ClaimAliasSpec, ...]
    source_fixture_refs: tuple[StableId, ...] = Field(min_length=1)
    allowed_normalizers: tuple[ClaimNormalizerRef, ...] = Field(min_length=1)

    @field_validator("canonical_forms")
    @classmethod
    def _canonical_forms_are_sorted_and_unique(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized = tuple(
            _require_canonical_text(item, field_name="canonical form")
            for item in value
        )
        if normalized != tuple(sorted(normalized)) or len(normalized) != len(
            set(normalized)
        ):
            raise ValueError("canonical_forms 必须排序且不得重复。")
        return normalized

    @field_validator("source_fixture_refs")
    @classmethod
    def _source_refs_are_sorted_and_unique(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if value != tuple(sorted(value)) or len(value) != len(set(value)):
            raise ValueError("source_fixture_refs 必须排序且不得重复。")
        return value

    @field_validator("allowed_normalizers")
    @classmethod
    def _normalizers_are_sorted_and_unique(
        cls,
        value: tuple[ClaimNormalizerRef, ...],
    ) -> tuple[ClaimNormalizerRef, ...]:
        keys = tuple((item.normalizer_id, item.version) for item in value)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValueError("allowed_normalizers 必须排序且不得重复。")
        return value

    @model_validator(mode="after")
    def _aliases_are_finite_and_unambiguous(self) -> ExpectedClaimSpec:
        keys = tuple((item.alias, item.canonical) for item in self.aliases)
        if keys != tuple(sorted(keys)):
            raise ValueError("aliases 必须按 alias/canonical 排序。")
        aliases = [item.alias for item in self.aliases]
        if len(aliases) != len(set(aliases)):
            raise ValueError("同一 claim 的 alias 不得重复或映射多个词形。")
        canonical_forms = set(self.canonical_forms)
        for item in self.aliases:
            if item.canonical not in canonical_forms:
                raise ValueError("alias.canonical 必须引用 canonical_forms。")
            if item.alias in canonical_forms:
                raise ValueError("alias 不得与 canonical_forms 重复。")
        return self

    @property
    def alias_map(self) -> Mapping[str, str]:
        return MappingProxyType(
            {item.alias: item.canonical for item in self.aliases}
        )


class ClaimCatalog(BenchmarkModel):
    schema_: Literal[
        "taichu.general_agent_benchmark.claim_catalog@1"
    ] = Field(alias="schema")
    catalog_version: Literal[1]
    fixture_id: StableId
    claims: tuple[ExpectedClaimSpec, ...] = Field(min_length=1)
    content_hash: Sha256

    @model_validator(mode="after")
    def _claims_and_identity_are_valid(self) -> ClaimCatalog:
        claim_ids = tuple(item.claim_id for item in self.claims)
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("ClaimCatalog 的 claim_id 不得重复。")
        if claim_ids != tuple(sorted(claim_ids)):
            raise ValueError("claims 必须按 claim_id 排序。")
        calculated_hash = canonical_sha256(
            self.model_dump(
                mode="json",
                by_alias=True,
                exclude={"content_hash"},
            )
        )
        if self.content_hash != calculated_hash:
            raise ValueError("ClaimCatalog content_hash 与规范化内容不一致。")
        return self

    def claim(self, claim_id: str) -> ExpectedClaimSpec:
        for claim in self.claims:
            if claim.claim_id == claim_id:
                return claim
        raise ValueError(f"ClaimCatalog 引用了未知 claim_id：{claim_id}。")


class NormalizerDescriptor(BenchmarkModel):
    normalizer_id: StableId
    version: NormalizerVersion
    kind: NormalizerKind
    description: str = Field(min_length=1, max_length=1_000)
    operations: tuple[NormalizerOperation, ...] = Field(min_length=1)

    @field_validator("description")
    @classmethod
    def _description_is_canonical(cls, value: str) -> str:
        return _require_canonical_text(value, field_name="normalizer description")

    @field_validator("operations")
    @classmethod
    def _operations_are_unique(
        cls,
        value: tuple[NormalizerOperation, ...],
    ) -> tuple[NormalizerOperation, ...]:
        if len(value) != len(set(value)):
            raise ValueError("normalizer operations 不得重复。")
        return value

    @property
    def reference(self) -> ClaimNormalizerRef:
        return ClaimNormalizerRef(
            normalizer_id=self.normalizer_id,
            version=self.version,
        )


@dataclass(frozen=True, slots=True)
class NormalizerRegistration:
    descriptor: NormalizerDescriptor
    function: ClaimNormalizerFunction = field(repr=False)
    implementation_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_normalizer_function(self.function)
        object.__setattr__(
            self,
            "implementation_sha256",
            _normalizer_implementation_sha256(self.function),
        )


class ClaimNormalizerRegistry:
    """构造后不可注册或扫描模块的显式 normalizer 映射。"""

    __slots__ = (
        "_entries",
        "_normalizer_implementation_sha256",
        "_registrations",
        "_registry_descriptor_sha256",
    )

    def __init__(
        self,
        registrations: tuple[NormalizerRegistration, ...],
    ) -> None:
        if not registrations:
            raise ValueError("ClaimNormalizerRegistry 至少需要一个静态注册项。")
        ordered = tuple(
            sorted(
                registrations,
                key=lambda item: (
                    item.descriptor.normalizer_id,
                    item.descriptor.version,
                ),
            )
        )
        entries: dict[tuple[str, str], NormalizerRegistration] = {}
        for registration in ordered:
            key = (
                registration.descriptor.normalizer_id,
                registration.descriptor.version,
            )
            if key in entries:
                raise ValueError(
                    "ClaimNormalizerRegistry normalizer ID/version 不得重复。"
                )
            entries[key] = registration
        self._registrations = ordered
        self._entries = MappingProxyType(entries)
        self._registry_descriptor_sha256 = canonical_sha256(
            {
                "schema": _REGISTRY_DESCRIPTOR_SCHEMA,
                "descriptors": tuple(
                    item.descriptor for item in self._registrations
                ),
            }
        )
        self._normalizer_implementation_sha256 = canonical_sha256(
            {
                "schema": _REGISTRY_IMPLEMENTATION_SCHEMA,
                "implementations": tuple(
                    {
                        "normalizer_id": item.descriptor.normalizer_id,
                        "version": item.descriptor.version,
                        "implementation_sha256": item.implementation_sha256,
                    }
                    for item in self._registrations
                ),
            }
        )

    @property
    def descriptors(self) -> tuple[NormalizerDescriptor, ...]:
        return tuple(item.descriptor for item in self._registrations)

    @property
    def registry_descriptor_sha256(self) -> str:
        return self._registry_descriptor_sha256

    @property
    def normalizer_implementation_sha256(self) -> str:
        return self._normalizer_implementation_sha256

    def resolve(
        self,
        reference: ClaimNormalizerRef,
    ) -> NormalizerRegistration:
        key = (reference.normalizer_id, reference.version)
        registration = self._entries.get(key)
        if registration is None:
            raise ValueError(
                "Claim normalizer 未注册："
                f"{reference.normalizer_id}@{reference.version}。"
            )
        return registration

    def normalize(
        self,
        reference: ClaimNormalizerRef,
        value: str,
        *,
        aliases: Mapping[str, str],
    ) -> str:
        registration = self.resolve(reference)
        normalized_aliases = _validate_finite_aliases(aliases)
        result = registration.function(
            value,
            MappingProxyType(normalized_aliases),
        )
        if not isinstance(result, str):
            raise ValueError("Claim normalizer 必须返回字符串。")
        return result

    def validate_catalog(self, catalog: ClaimCatalog) -> None:
        for claim in catalog.claims:
            for reference in claim.allowed_normalizers:
                self.resolve(reference)


class OracleRuleSetIdentity(BenchmarkModel):
    schema_: Literal[
        "taichu.general_agent_benchmark.oracle_rule_set@1"
    ] = Field(alias="schema")
    catalog_schema: Literal[
        "taichu.general_agent_benchmark.claim_catalog@1"
    ]
    catalog_version: Literal[1]
    catalog_sha256: Sha256
    registry_descriptor_sha256: Sha256
    normalizer_implementation_sha256: Sha256
    oracle_rule_set_sha256: Sha256

    @model_validator(mode="after")
    def _identity_matches_components(self) -> OracleRuleSetIdentity:
        calculated_hash = canonical_sha256(
            self.model_dump(
                mode="json",
                by_alias=True,
                exclude={"oracle_rule_set_sha256"},
            )
        )
        if self.oracle_rule_set_sha256 != calculated_hash:
            raise ValueError(
                "OracleRuleSetIdentity 与 catalog/registry 内容身份不一致。"
            )
        return self

    @classmethod
    def create(
        cls,
        *,
        catalog: ClaimCatalog,
        registry: ClaimNormalizerRegistry,
    ) -> OracleRuleSetIdentity:
        payload = {
            "schema": _RULE_SET_SCHEMA,
            "catalog_schema": catalog.schema_,
            "catalog_version": catalog.catalog_version,
            "catalog_sha256": catalog.content_hash,
            "registry_descriptor_sha256": (
                registry.registry_descriptor_sha256
            ),
            "normalizer_implementation_sha256": (
                registry.normalizer_implementation_sha256
            ),
        }
        return cls(
            **payload,
            oracle_rule_set_sha256=canonical_sha256(payload),
        )


def load_claim_catalog(
    path: Path,
    *,
    registry: ClaimNormalizerRegistry,
    known_fixture_refs: Iterable[str],
    referenced_claim_ids: Iterable[str] = (),
) -> ClaimCatalog:
    """严格读取独立预期真值，并在 Oracle 执行前完成全部引用校验。"""

    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_strict_json_object,
    )
    if not isinstance(payload, dict):
        raise ValueError("claim-catalog.json 根节点必须是对象。")
    unexpected_fields = sorted(
        set(payload)
        - {"schema", "catalog_version", "fixture_id", "claims", "content_hash"}
    )
    if unexpected_fields:
        raise ValueError(f"ClaimCatalog 包含额外字段：{unexpected_fields}。")
    _reject_script_truth_fields(payload)
    catalog = ClaimCatalog.model_validate(payload)
    registry.validate_catalog(catalog)

    known_sources = frozenset(known_fixture_refs)
    missing_sources = sorted(
        {
            source
            for claim in catalog.claims
            for source in claim.source_fixture_refs
            if source not in known_sources
        }
    )
    if missing_sources:
        raise ValueError(
            "ClaimCatalog 引用了未知夹具来源："
            + ", ".join(missing_sources)
            + "。"
        )
    validate_claim_references(catalog, referenced_claim_ids)
    return catalog


def validate_claim_references(
    catalog: ClaimCatalog,
    referenced_claim_ids: Iterable[str],
) -> tuple[ExpectedClaimSpec, ...]:
    references = tuple(referenced_claim_ids)
    if len(references) != len(set(references)):
        raise ValueError("Suite claim 引用不得重复。")
    known = {claim.claim_id for claim in catalog.claims}
    missing = sorted(set(references) - known)
    if missing:
        raise ValueError(
            "Suite 引用了未知 ClaimCatalog claim_id："
            + ", ".join(missing)
            + "。"
        )
    return tuple(catalog.claim(claim_id) for claim_id in references)


def _claim_text_normalizer_v1(
    value: str,
    aliases: Mapping[str, str],
) -> str:
    normalized = unicodedata.normalize("NFC", value)
    normalized = normalized.translate(
        str.maketrans(
            {
                "！": "!",
                "，": ",",
                "。": ".",
                "：": ":",
                "；": ";",
                "？": "?",
                "（": "(",
                "）": ")",
                "\u3000": " ",
            }
        )
    )
    normalized = " ".join(normalized.split())
    for alias in sorted(aliases, key=lambda item: (-len(item), item)):
        canonical = aliases[alias]
        normalized = normalized.replace(
            unicodedata.normalize("NFC", alias),
            unicodedata.normalize("NFC", canonical),
        )
    return normalized


def _require_canonical_text(value: str, *, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} 不得为空白。")
    if value != value.strip():
        raise ValueError(f"{field_name} 不得包含首尾空白。")
    if value != unicodedata.normalize("NFC", value):
        raise ValueError(f"{field_name} 必须已规范化为 Unicode NFC。")
    return value


def _validate_finite_aliases(
    aliases: Mapping[str, str],
) -> dict[str, str]:
    if len(aliases) > _MAX_ALIAS_COUNT:
        raise ValueError("Claim alias 数量超出静态有限上限。")
    normalized: dict[str, str] = {}
    total_chars = 0
    for alias, canonical in sorted(aliases.items()):
        checked_alias = _require_canonical_text(alias, field_name="claim alias")
        checked_canonical = _require_canonical_text(
            canonical,
            field_name="canonical form",
        )
        if checked_alias == checked_canonical:
            raise ValueError("Claim alias 不得等于 canonical form。")
        total_chars += len(checked_alias) + len(checked_canonical)
        normalized[checked_alias] = checked_canonical
    if total_chars > _MAX_ALIAS_CHARS:
        raise ValueError("Claim alias 总长度超出静态有限上限。")
    return normalized


def _validate_normalizer_function(function: ClaimNormalizerFunction) -> None:
    if not isinstance(function, types.FunctionType):
        raise ValueError("Claim normalizer 必须是显式静态纯函数。")
    if function.__closure__:
        raise ValueError("Claim normalizer 纯函数不得捕获闭包可变状态。")
    if function.__defaults__ or function.__kwdefaults__:
        raise ValueError("Claim normalizer 纯函数不得隐藏默认依赖。")

    code_objects = tuple(_walk_code_objects(function.__code__))
    loaded_global_names = {
        instruction.argval
        for code in code_objects
        for instruction in dis.get_instructions(code)
        if instruction.opname in {"LOAD_GLOBAL", "LOAD_NAME"}
        and isinstance(instruction.argval, str)
    }
    forbidden_names = sorted(
        {
            name
            for code in code_objects
            for name in code.co_names
            if name in _FORBIDDEN_NORMALIZER_NAMES
        }
    )
    unapproved_globals = sorted(
        loaded_global_names - _ALLOWED_NORMALIZER_GLOBALS.keys()
    )
    shadowed_globals = sorted(
        name
        for name in loaded_global_names.intersection(
            _ALLOWED_NORMALIZER_GLOBALS
        )
        if function.__globals__.get(
            name,
            getattr(builtins, name, None),
        )
        is not _ALLOWED_NORMALIZER_GLOBALS[name]
    )
    import_opcodes = [
        instruction.opname
        for code in code_objects
        for instruction in dis.get_instructions(code)
        if instruction.opname in {"IMPORT_FROM", "IMPORT_NAME", "IMPORT_STAR"}
    ]
    if (
        forbidden_names
        or import_opcodes
        or unapproved_globals
        or shadowed_globals
    ):
        details = ", ".join(
            (
                *forbidden_names,
                *import_opcodes,
                *(f"未批准全局依赖:{name}" for name in unapproved_globals),
                *(f"被替换全局依赖:{name}" for name in shadowed_globals),
            )
        )
        raise ValueError(
            "Claim normalizer 纯函数包含禁止的动态导入、文件、网络或"
            f"数据库能力：{details}。"
        )


def _normalizer_implementation_sha256(
    function: ClaimNormalizerFunction,
) -> str:
    payload = {
        "schema": _REGISTRY_IMPLEMENTATION_SCHEMA,
        "function": function.__qualname__,
        "code": _code_snapshot(function.__code__),
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _walk_code_objects(code: types.CodeType) -> Iterable[types.CodeType]:
    yield code
    for constant in code.co_consts:
        if isinstance(constant, types.CodeType):
            yield from _walk_code_objects(constant)


def _code_snapshot(code: types.CodeType) -> dict[str, object]:
    return {
        "argcount": code.co_argcount,
        "posonlyargcount": code.co_posonlyargcount,
        "kwonlyargcount": code.co_kwonlyargcount,
        "flags": code.co_flags,
        "code": code.co_code.hex(),
        "constants": tuple(_constant_snapshot(item) for item in code.co_consts),
        "names": code.co_names,
        "varnames": code.co_varnames,
        "freevars": code.co_freevars,
        "cellvars": code.co_cellvars,
    }


def _constant_snapshot(value: object) -> object:
    if isinstance(value, types.CodeType):
        return {"code_object": _code_snapshot(value)}
    if isinstance(value, bytes):
        return {"bytes": value.hex()}
    if isinstance(value, tuple):
        return tuple(_constant_snapshot(item) for item in value)
    if isinstance(value, frozenset):
        return tuple(
            sorted(
                (_constant_snapshot(item) for item in value),
                key=lambda item: json.dumps(
                    item,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise ValueError(
        "Claim normalizer 包含无法形成静态代码快照的常量："
        f"{type(value).__name__}。"
    )


def _strict_json_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"claim-catalog.json 包含重复字段：{key}。")
        result[key] = value
    return result


def _reject_script_truth_fields(value: object, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        forbidden = sorted(_FORBIDDEN_TRUTH_FIELDS.intersection(value))
        if forbidden:
            raise ValueError(
                "ClaimCatalog 禁止混入脚本响应真值字段："
                + ", ".join(f"{path}.{name}" for name in forbidden)
                + "。"
            )
        for key, item in value.items():
            _reject_script_truth_fields(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_script_truth_fields(item, path=f"{path}[{index}]")


DEFAULT_CLAIM_NORMALIZER_REGISTRY = ClaimNormalizerRegistry(
    (
        NormalizerRegistration(
            descriptor=NormalizerDescriptor(
                normalizer_id="claim_text",
                version="1",
                kind=NormalizerKind.CLAIM_TEXT,
                description="固定执行 NFC、空白、标点与有限别名替换。",
                operations=(
                    NormalizerOperation.UNICODE_NFC,
                    NormalizerOperation.WHITESPACE,
                    NormalizerOperation.PUNCTUATION,
                    NormalizerOperation.FINITE_ALIASES,
                ),
            ),
            function=_claim_text_normalizer_v1,
        ),
    )
)
