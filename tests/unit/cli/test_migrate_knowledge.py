"""Guard tests for the one-time JSON-to-Mongo knowledge migration."""

import json
from pathlib import Path

import pytest

from taichu.cli.migrate_knowledge import (
    EXPECTED_ACTIVE_TYPE_COUNTS,
    KnowledgeMigrationError,
    canonical_card_hash,
    preflight,
)


def write_legacy_baseline(root: Path) -> tuple[Path, Path]:
    """Create the exact 88/58/30 baseline without using repository data."""
    source_dir = root / "knowledge"
    manifest_path = root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "chapters": [
                    {
                        "id": "chapter-1",
                        "title": "第一章",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    serial = 0
    for type_name, count in EXPECTED_ACTIVE_TYPE_COUNTS.items():
        for _ in range(count):
            serial += 1
            _write_card(source_dir, type_name, serial, "active")
    for _ in range(30):
        serial += 1
        _write_card(source_dir, "character", serial, "deprecated")
    return source_dir, manifest_path


def test_preflight_maps_only_active_cards_to_confirmed(tmp_path: Path) -> None:
    source_dir, manifest_path = write_legacy_baseline(tmp_path)

    inventory = preflight(source_dir, manifest_path)

    assert inventory.summary()["total"] == 88
    assert len(inventory.active_records) == 58
    assert {record.card.lifecycle.value for record in inventory.active_records} == {
        "confirmed"
    }
    assert all(record.card.model_dump().get("status") is None for record in inventory.records)
    assert all(len(canonical_card_hash(record.card)) == 64 for record in inventory.active_records)


def test_preflight_stops_when_baseline_changes(tmp_path: Path) -> None:
    source_dir, manifest_path = write_legacy_baseline(tmp_path)
    next(source_dir.rglob("*.json")).unlink()

    with pytest.raises(KnowledgeMigrationError, match="基线已变化"):
        preflight(source_dir, manifest_path)


def _write_card(
    source_dir: Path,
    type_name: str,
    serial: int,
    status: str,
) -> None:
    card_id = f"{type_name}-{serial:03d}"
    payload = {
        "id": card_id,
        "type": type_name,
        "name": f"{type_name}名称{serial}",
        "aliases": [f"别名{serial}"],
        "summary": f"摘要{serial}",
        "importance": "normal",
        "status": status,
        "source_origin": "agent_extract",
        "source_note": "第一章",
        "first_seen_chapter_id": "chapter-1" if type_name == "character" else None,
        "created_at": "2026-07-11T00:00:00.123456Z",
        "updated_at": "2026-07-11T00:00:00.123456Z",
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    target_dir = source_dir / type_name
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / f"{card_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
