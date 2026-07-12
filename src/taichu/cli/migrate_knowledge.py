"""One-time migration from legacy knowledge JSON files to MongoDB."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from pydantic import Field
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from taichu.config import settings
from taichu.domain.models.base import DomainModel
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeImportance,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeType,
)
from taichu.infrastructure.knowledge.mongo_repository import (
    DEFAULT_KNOWLEDGE_COLLECTION,
    bson_datetime_to_iso,
    card_to_document,
    document_to_card,
    ensure_knowledge_indexes,
    identity_keys,
    iso_to_bson_datetime,
    knowledge_collection_validator,
)

EXPECTED_TOTAL = 88
EXPECTED_ACTIVE = 58
EXPECTED_DEPRECATED = 30
EXPECTED_DRAFT = 0
EXPECTED_ACTIVE_TYPE_COUNTS: dict[str, int] = {
    "character": 18,
    "event": 10,
    "faction": 2,
    "item": 1,
    "location": 8,
    "realm": 4,
    "rule": 15,
    "technique": 0,
}
BACKUP_MANIFEST_NAME = "migration-manifest.json"
BACKUP_CARDS_DIR = "cards"
MIGRATION_MANIFEST_FORMAT = "taichu_knowledge_migration_v1"
STAGING_COLLECTION_PREFIX = "knowledge_cards_migration_"

_CHAPTER_REFERENCE_FIELDS = frozenset(
    {
        "death_chapter_id",
        "first_seen_chapter_id",
        "last_seen_chapter_id",
        "chapter_id",
    }
)
_KNOWLEDGE_REFERENCE_FIELDS = frozenset(
    {
        "owner_faction_id",
        "controlling_faction_id",
        "leader_id",
        "current_holder_id",
    }
)


class KnowledgeMigrationError(RuntimeError):
    """Raised when a migration guard or reconciliation check fails."""


class _LegacyKnowledgeCard(DomainModel):
    """Private parser for the pre-Mongo JSON shape; never used by the app."""

    id: str = Field(min_length=1)
    type: StructuredKnowledgeType
    name: str = ""
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""
    importance: StructuredKnowledgeImportance = StructuredKnowledgeImportance.NORMAL
    status: Literal["draft", "active", "deprecated"] = "draft"
    source_origin: StructuredKnowledgeSourceOrigin | None = None
    source_note: str = ""
    role_type: str | None = None
    identity: str | None = None
    relationship_summary: str | None = None
    death_chapter_id: str | None = None
    current_realm_text: str | None = None
    first_seen_chapter_id: str | None = None
    last_seen_chapter_id: str | None = None
    system: str | None = None
    level_order: float | None = None
    technique_type: str | None = None
    grade: str | None = None
    practice_condition: str | None = None
    owner_faction_id: str | None = None
    controlling_faction_id: str | None = None
    faction_type: str | None = None
    leader_id: str | None = None
    item_type: str | None = None
    current_holder_id: str | None = None
    exceptions: str | None = None
    chapter_id: str | None = None
    description: str | None = None
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)

    def to_current(self) -> StructuredKnowledgeCard:
        payload = self.model_dump(mode="json")
        legacy_status = payload.pop("status")
        payload["lifecycle"] = {
            "draft": StructuredKnowledgeLifecycle.DRAFT.value,
            "active": StructuredKnowledgeLifecycle.CONFIRMED.value,
            "deprecated": StructuredKnowledgeLifecycle.REJECTED.value,
        }[legacy_status]
        return StructuredKnowledgeCard.model_validate(payload)


@dataclass(frozen=True, slots=True)
class MigrationRecord:
    """One source file and its validated legacy/current representations."""

    source_path: Path
    relative_path: str
    sha256: str
    legacy: _LegacyKnowledgeCard
    card: StructuredKnowledgeCard


@dataclass(frozen=True, slots=True)
class MigrationInventory:
    """Fully validated source-disk snapshot used by apply and finalize."""

    source_dir: Path
    chapter_manifest_path: Path
    records: tuple[MigrationRecord, ...]

    @property
    def active_records(self) -> tuple[MigrationRecord, ...]:
        return tuple(record for record in self.records if record.legacy.status == "active")

    def summary(self) -> dict[str, Any]:
        statuses = Counter(record.legacy.status for record in self.records)
        type_counts = Counter(
            record.legacy.type.value for record in self.active_records
        )
        return {
            "total": len(self.records),
            "active": statuses["active"],
            "deprecated": statuses["deprecated"],
            "draft": statuses["draft"],
            "active_type_counts": {
                type_name: type_counts[type_name]
                for type_name in EXPECTED_ACTIVE_TYPE_COUNTS
            },
        }


@dataclass(frozen=True, slots=True)
class ApplyResult:
    """Result returned after backup, reconciliation, and collection switch."""

    backup_dir: Path
    collection_name: str
    imported: int
    skipped: int
    already_current: bool


def preflight(
    source_dir: Path,
    chapter_manifest_path: Path,
) -> MigrationInventory:
    """Scan the actual disk and reject anything outside the agreed baseline."""
    source_dir = source_dir.resolve()
    chapter_manifest_path = chapter_manifest_path.resolve()
    if not source_dir.is_dir():
        raise KnowledgeMigrationError(f"知识 JSON 目录不存在：{source_dir}")
    if not chapter_manifest_path.is_file():
        raise KnowledgeMigrationError(
            f"章节清单不存在：{chapter_manifest_path}"
        )

    chapter_ids = _read_chapter_ids(chapter_manifest_path)
    records: list[MigrationRecord] = []
    seen_ids: set[str] = set()
    for source_path in sorted(source_dir.rglob("*.json")):
        relative_path = source_path.relative_to(source_dir).as_posix()
        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
            legacy = _LegacyKnowledgeCard.model_validate(payload)
        except (OSError, ValueError) as error:
            raise KnowledgeMigrationError(
                f"知识卡文件无效：{relative_path}：{error}"
            ) from error
        if source_path.parent.name != legacy.type.value:
            raise KnowledgeMigrationError(
                f"知识卡类型与目录不一致：{relative_path}"
            )
        if source_path.stem != legacy.id:
            raise KnowledgeMigrationError(
                f"知识卡 ID 与文件名不一致：{relative_path}"
            )
        if legacy.id in seen_ids:
            raise KnowledgeMigrationError(f"知识卡 ID 重复：{legacy.id}")
        seen_ids.add(legacy.id)
        try:
            card = legacy.to_current()
            # BSON dates have millisecond precision; parsing here fails early.
            iso_to_bson_datetime(card.created_at)
            iso_to_bson_datetime(card.updated_at)
        except (ValueError, RuntimeError) as error:
            raise KnowledgeMigrationError(
                f"知识卡字段无效：{relative_path}：{error}"
            ) from error
        records.append(
            MigrationRecord(
                source_path=source_path,
                relative_path=relative_path,
                sha256=_sha256_file(source_path),
                legacy=legacy,
                card=card,
            )
        )

    inventory = MigrationInventory(
        source_dir=source_dir,
        chapter_manifest_path=chapter_manifest_path,
        records=tuple(records),
    )
    _validate_baseline(inventory)
    _validate_references(inventory, chapter_ids)
    _validate_active_identities(inventory)
    return inventory


async def apply(
    inventory: MigrationInventory,
    *,
    mongodb_uri: str,
    database_name: str,
    backup_root: Path,
    collection_name: str = DEFAULT_KNOWLEDGE_COLLECTION,
    client: Any | None = None,
    timestamp: datetime | None = None,
) -> ApplyResult:
    """Back up every JSON file, stage 58 cards, reconcile, then switch."""
    _validate_baseline(inventory)
    backup_dir = _create_backup(inventory, backup_root, timestamp=timestamp)
    stamp = (timestamp or datetime.now(UTC)).strftime("%Y%m%dT%H%M%S%fZ")
    staging_name = f"{STAGING_COLLECTION_PREFIX}{stamp}"
    owns_client = client is None
    mongo_client = client or AsyncMongoClient(
        mongodb_uri,
        tz_aware=True,
        serverSelectionTimeoutMS=5_000,
    )
    database = mongo_client[database_name]
    already_current = False
    try:
        await database.command("ping")
        names = await database.list_collection_names()
        if staging_name in names:
            raise KnowledgeMigrationError(
                f"迁移临时集合已存在，拒绝覆盖：{staging_name}"
            )
        await database.create_collection(
            staging_name,
            validator=knowledge_collection_validator(),
            validationLevel="strict",
            validationAction="error",
        )
        staging = database[staging_name]
        await ensure_knowledge_indexes(staging)
        documents = [
            card_to_document(record.card)
            for record in inventory.active_records
        ]
        await staging.insert_many(documents, ordered=True)
        expected_hashes = {
            record.card.id: canonical_card_hash(record.card)
            for record in inventory.active_records
        }
        await _reconcile_collection(staging, expected_hashes)

        names = await database.list_collection_names()
        if collection_name not in names:
            await staging.rename(collection_name)
        else:
            target = database[collection_name]
            target_count = await target.count_documents({})
            if target_count == 0:
                # Re-check immediately before the atomic drop-target rename.
                if await target.count_documents({}) != 0:
                    raise KnowledgeMigrationError(
                        "正式知识集合在切换前出现写入，迁移已停止。"
                    )
                await staging.rename(collection_name, dropTarget=True)
            else:
                try:
                    await _reconcile_collection(target, expected_hashes)
                except KnowledgeMigrationError as error:
                    raise KnowledgeMigrationError(
                        "正式知识集合非空且内容与迁移数据不一致，拒绝覆盖。"
                    ) from error
                already_current = True
                await database.drop_collection(staging_name)
        return ApplyResult(
            backup_dir=backup_dir,
            collection_name=collection_name,
            imported=EXPECTED_ACTIVE,
            skipped=EXPECTED_DEPRECATED,
            already_current=already_current,
        )
    except (PyMongoError, KnowledgeMigrationError) as error:
        await _drop_controlled_staging(database, staging_name)
        if isinstance(error, KnowledgeMigrationError):
            raise
        raise KnowledgeMigrationError(f"MongoDB 迁移失败：{error}") from error
    finally:
        if owns_client:
            await mongo_client.close()


async def finalize(
    backup_dir: Path,
    *,
    mongodb_uri: str,
    database_name: str,
    collection_name: str = DEFAULT_KNOWLEDGE_COLLECTION,
    client: Any | None = None,
) -> None:
    """Delete source JSON only after backup, source, and Mongo all reconcile."""
    backup_dir = backup_dir.resolve()
    manifest = _read_backup_manifest(backup_dir)
    source_dir = Path(str(manifest["source_dir"])).resolve()
    chapter_manifest_path = Path(str(manifest["chapter_manifest_path"])).resolve()
    inventory = preflight(source_dir, chapter_manifest_path)
    manifest_records = _manifest_records_by_id(manifest)
    if len(manifest_records) != EXPECTED_TOTAL:
        raise KnowledgeMigrationError("迁移清单记录数不是 88，禁止清理源数据。")
    for record in inventory.records:
        manifest_record = manifest_records.get(record.card.id)
        if manifest_record is None:
            raise KnowledgeMigrationError(
                f"迁移清单缺少知识卡：{record.card.id}"
            )
        if manifest_record.get("sha256") != record.sha256:
            raise KnowledgeMigrationError(
                f"源知识卡在迁移后发生变化：{record.relative_path}"
            )
        backup_file = _safe_backup_card_path(
            backup_dir,
            str(manifest_record["relative_path"]),
        )
        if not backup_file.is_file() or _sha256_file(backup_file) != record.sha256:
            raise KnowledgeMigrationError(
                f"知识卡备份缺失或哈希不一致：{record.relative_path}"
            )

    expected_hashes = {
        record.card.id: canonical_card_hash(record.card)
        for record in inventory.active_records
    }
    owns_client = client is None
    mongo_client = client or AsyncMongoClient(
        mongodb_uri,
        tz_aware=True,
        serverSelectionTimeoutMS=5_000,
    )
    try:
        database = mongo_client[database_name]
        await database.command("ping")
        if collection_name not in await database.list_collection_names():
            raise KnowledgeMigrationError("正式知识集合不存在，禁止清理源数据。")
        await _reconcile_collection(database[collection_name], expected_hashes)
    except PyMongoError as error:
        raise KnowledgeMigrationError(f"MongoDB 最终核验失败：{error}") from error
    finally:
        if owns_client:
            await mongo_client.close()

    shutil.rmtree(source_dir)
    if source_dir.exists():
        raise KnowledgeMigrationError("源知识目录删除未完成，请人工检查。")


def canonical_card_hash(card: StructuredKnowledgeCard) -> str:
    """Hash public card data after normalizing BSON datetime precision."""
    payload = card.model_dump(mode="json", exclude_none=False)
    for field_name in ("created_at", "updated_at"):
        parsed = iso_to_bson_datetime(str(payload[field_name]))
        parsed = parsed.replace(microsecond=(parsed.microsecond // 1000) * 1000)
        payload[field_name] = bson_datetime_to_iso(parsed)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_baseline(inventory: MigrationInventory) -> None:
    summary = inventory.summary()
    expected = {
        "total": EXPECTED_TOTAL,
        "active": EXPECTED_ACTIVE,
        "deprecated": EXPECTED_DEPRECATED,
        "draft": EXPECTED_DRAFT,
        "active_type_counts": EXPECTED_ACTIVE_TYPE_COUNTS,
    }
    if summary != expected:
        raise KnowledgeMigrationError(
            "知识卡基线已变化，迁移停止。"
            f"期望 {json.dumps(expected, ensure_ascii=False, sort_keys=True)}；"
            f"实际 {json.dumps(summary, ensure_ascii=False, sort_keys=True)}。"
        )


def _validate_references(
    inventory: MigrationInventory,
    chapter_ids: set[str],
) -> None:
    all_ids = {record.card.id for record in inventory.records}
    active_ids = {record.card.id for record in inventory.active_records}
    for record in inventory.records:
        payload = record.legacy.model_dump(mode="python")
        for field_name in _CHAPTER_REFERENCE_FIELDS:
            reference = payload.get(field_name)
            if reference and reference not in chapter_ids:
                raise KnowledgeMigrationError(
                    f"章节引用不存在：{record.relative_path} -> {reference}"
                )
        for field_name in _KNOWLEDGE_REFERENCE_FIELDS:
            reference = payload.get(field_name)
            if not reference:
                continue
            if reference not in all_ids:
                raise KnowledgeMigrationError(
                    f"知识引用不存在：{record.relative_path} -> {reference}"
                )
            if record.legacy.status == "active" and reference not in active_ids:
                raise KnowledgeMigrationError(
                    f"有效知识卡引用了不迁移的知识卡："
                    f"{record.relative_path} -> {reference}"
                )


def _validate_active_identities(inventory: MigrationInventory) -> None:
    owners: dict[tuple[str, str], str] = {}
    for record in inventory.active_records:
        if not record.card.name.strip():
            raise KnowledgeMigrationError(
                f"有效知识卡名称为空：{record.relative_path}"
            )
        for identity_key in identity_keys(record.card.name, record.card.aliases):
            key = (record.card.type.value, identity_key)
            existing = owners.get(key)
            if existing is not None and existing != record.card.id:
                raise KnowledgeMigrationError(
                    "有效知识卡名称或别名冲突："
                    f"{existing} 与 {record.card.id}"
                )
            owners[key] = record.card.id


def _read_chapter_ids(chapter_manifest_path: Path) -> set[str]:
    try:
        manifest = json.loads(chapter_manifest_path.read_text(encoding="utf-8"))
        chapters = manifest["chapters"]
        chapter_ids = {
            str(chapter["id"])
            for chapter in chapters
            if isinstance(chapter, Mapping) and chapter.get("id")
        }
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise KnowledgeMigrationError(f"章节清单无法读取：{error}") from error
    if not chapter_ids:
        raise KnowledgeMigrationError("章节清单不包含任何章节 ID。")
    return chapter_ids


def _create_backup(
    inventory: MigrationInventory,
    backup_root: Path,
    *,
    timestamp: datetime | None,
) -> Path:
    backup_root = backup_root.resolve()
    if backup_root.is_relative_to(inventory.source_dir):
        raise KnowledgeMigrationError("迁移备份目录不能位于源知识目录内。")
    backup_stamp = (timestamp or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    backup_dir = backup_root / f"知识库-{backup_stamp}"
    if backup_dir.exists():
        raise KnowledgeMigrationError(f"迁移备份目录已存在：{backup_dir}")
    cards_root = backup_dir / BACKUP_CARDS_DIR
    cards_root.mkdir(parents=True)
    manifest_records: list[dict[str, Any]] = []
    for record in inventory.records:
        target = _safe_backup_card_path(backup_dir, record.relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(record.source_path, target)
        copied_hash = _sha256_file(target)
        if copied_hash != record.sha256:
            raise KnowledgeMigrationError(
                f"知识卡备份哈希不一致：{record.relative_path}"
            )
        imported = record.legacy.status == "active"
        manifest_records.append(
            {
                "id": record.card.id,
                "relative_path": record.relative_path,
                "sha256": record.sha256,
                "normalized_hash": (
                    canonical_card_hash(record.card) if imported else None
                ),
                "type": record.card.type.value,
                "legacy_status": record.legacy.status,
                "action": "imported" if imported else "skipped",
                "reason": (
                    "有效知识卡迁移为 confirmed"
                    if imported
                    else "已弃用重复卡只保留备份"
                ),
            }
        )
    manifest = {
        "format": MIGRATION_MANIFEST_FORMAT,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_dir": str(inventory.source_dir),
        "chapter_manifest_path": str(inventory.chapter_manifest_path),
        "totals": inventory.summary(),
        "records": manifest_records,
    }
    (backup_dir / BACKUP_MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return backup_dir


async def _reconcile_collection(
    collection: Any,
    expected_hashes: Mapping[str, str],
) -> None:
    documents = await collection.find({}).to_list(length=None)
    if len(documents) != EXPECTED_ACTIVE:
        raise KnowledgeMigrationError(
            f"MongoDB 知识卡数量不是 {EXPECTED_ACTIVE}：{len(documents)}"
        )
    type_counts: Counter[str] = Counter()
    actual_hashes: dict[str, str] = {}
    for document in documents:
        if "status" in document:
            raise KnowledgeMigrationError("MongoDB 知识卡仍包含旧 status 字段。")
        if document.get("lifecycle") != StructuredKnowledgeLifecycle.CONFIRMED.value:
            raise KnowledgeMigrationError("MongoDB 中存在未确认的迁移知识卡。")
        try:
            card = document_to_card(document)
        except ValueError as error:
            raise KnowledgeMigrationError(
                "MongoDB 知识卡字段无法按当前模型解析。"
            ) from error
        type_counts[card.type.value] += 1
        actual_hashes[card.id] = canonical_card_hash(card)
    actual_type_counts = {
        type_name: type_counts[type_name]
        for type_name in EXPECTED_ACTIVE_TYPE_COUNTS
    }
    if actual_type_counts != EXPECTED_ACTIVE_TYPE_COUNTS:
        raise KnowledgeMigrationError(
            f"MongoDB 类型统计不一致：{actual_type_counts}"
        )
    if dict(expected_hashes) != actual_hashes:
        raise KnowledgeMigrationError("MongoDB 逐卡内容哈希对账失败。")


async def _drop_controlled_staging(database: Any, name: str) -> None:
    if not name.startswith(STAGING_COLLECTION_PREFIX):
        return
    try:
        if name in await database.list_collection_names():
            await database.drop_collection(name)
    except PyMongoError:
        # Preserve the original error; controlled staging is safe to inspect later.
        return


def _read_backup_manifest(backup_dir: Path) -> dict[str, Any]:
    manifest_path = backup_dir / BACKUP_MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise KnowledgeMigrationError(f"迁移清单无法读取：{error}") from error
    if manifest.get("format") != MIGRATION_MANIFEST_FORMAT:
        raise KnowledgeMigrationError("迁移清单格式不受支持。")
    if manifest.get("totals") != {
        "total": EXPECTED_TOTAL,
        "active": EXPECTED_ACTIVE,
        "deprecated": EXPECTED_DEPRECATED,
        "draft": EXPECTED_DRAFT,
        "active_type_counts": EXPECTED_ACTIVE_TYPE_COUNTS,
    }:
        raise KnowledgeMigrationError("迁移清单基线统计不一致。")
    return manifest


def _manifest_records_by_id(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    records = manifest.get("records")
    if not isinstance(records, list):
        raise KnowledgeMigrationError("迁移清单 records 字段无效。")
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise KnowledgeMigrationError("迁移清单包含无效记录。")
        if record["id"] in result:
            raise KnowledgeMigrationError("迁移清单包含重复知识卡 ID。")
        result[record["id"]] = record
    return result


def _safe_backup_card_path(backup_dir: Path, relative_path: str) -> Path:
    cards_root = (backup_dir / BACKUP_CARDS_DIR).resolve()
    candidate = (cards_root / Path(relative_path)).resolve()
    if not candidate.is_relative_to(cards_root):
        raise KnowledgeMigrationError("迁移清单包含越界文件路径。")
    return candidate


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="将太初旧知识 JSON 一次性迁移到 MongoDB。"
    )
    parser.add_argument(
        "command",
        choices=("preflight", "apply", "finalize"),
        help="预检、执行迁移或最终删除源 JSON。",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=settings.project_assets_dir / "source" / "knowledge",
    )
    parser.add_argument(
        "--chapter-manifest",
        type=Path,
        default=settings.project_assets_dir / "source" / "manuscripts" / "manifest.json",
    )
    parser.add_argument("--mongodb-uri", default=settings.mongodb_uri)
    parser.add_argument("--database", default=settings.mongodb_database)
    parser.add_argument("--collection", default=DEFAULT_KNOWLEDGE_COLLECTION)
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=Path(r"E:\Taichu\迁移备份"),
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        help="finalize 必须显式指定 apply 输出的备份目录。",
    )
    return parser


async def _run_cli(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "preflight":
        inventory = preflight(args.source_dir, args.chapter_manifest)
        return {"结果": "预检通过", **inventory.summary()}
    if args.command == "apply":
        inventory = preflight(args.source_dir, args.chapter_manifest)
        result = await apply(
            inventory,
            mongodb_uri=args.mongodb_uri,
            database_name=args.database,
            backup_root=args.backup_root,
            collection_name=args.collection,
        )
        return {
            "结果": "迁移完成",
            "备份目录": str(result.backup_dir),
            "集合": result.collection_name,
            "导入": result.imported,
            "跳过": result.skipped,
            "正式集合原本已一致": result.already_current,
        }
    if args.backup_dir is None:
        raise KnowledgeMigrationError("finalize 必须提供 --backup-dir。")
    await finalize(
        args.backup_dir,
        mongodb_uri=args.mongodb_uri,
        database_name=args.database,
        collection_name=args.collection,
    )
    return {"结果": "最终核验通过，源知识 JSON 已删除"}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the guarded migration CLI and return a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(_run_cli(args))
    except KnowledgeMigrationError as error:
        parser.exit(1, f"迁移失败：{error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
