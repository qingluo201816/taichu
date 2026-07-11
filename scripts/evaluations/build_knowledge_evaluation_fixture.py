"""Compile the curated first-five-chapter fixture into runtime evaluation files."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATASET_ROOT = (
    REPOSITORY_ROOT
    / "tests"
    / "fixtures"
    / "evaluations"
    / "taichu_knowledge_eval_first5_three_experts"
)
SOURCE_ROOT = REPOSITORY_ROOT / "project_assets" / "source"
EXPERTS = ("character_expert", "entity_expert", "worldview_expert")
SEMANTIC_FIELDS = (
    "summary",
    "source_note",
    "identity",
    "relationship_summary",
    "current_realm_text",
    "system",
    "practice_condition",
    "exceptions",
    "description",
)
EXACT_FIELDS = ("type", "status", "importance", "source_origin")
COMMON_TERMS = {
    "事件",
    "规则",
    "开始",
    "获得",
    "体系",
    "相关",
    "一个",
    "一种",
    "进行",
    "太初",
}


@dataclass(frozen=True)
class ChapterSource:
    chapter_id: str
    path: Path
    markdown: str
    content_hash: str


@dataclass(frozen=True)
class QuoteWindow:
    chapter_id: str
    text: str
    start_offset: int
    end_offset: int
    source_hash: str
    score: int


def main() -> None:
    legacy_manifest = _load_json(DATASET_ROOT / "manifest.json")
    legacy_path = DATASET_ROOT / "_metadata" / "legacy_manifest.json"
    if "cases" not in legacy_manifest and not legacy_path.exists():
        _write_json(legacy_path, legacy_manifest)
    if legacy_path.exists():
        legacy_manifest = _load_json(legacy_path)

    chapter_index = _load_json(DATASET_ROOT / "_metadata" / "chapter_index.json")
    chapters = {int(item["chapter_no"]): _load_chapter(item) for item in chapter_index}
    cases: list[dict[str, Any]] = []

    for chapter_no in range(1, 6):
        case_id = f"chapter_{chapter_no:03d}"
        case_dir = DATASET_ROOT / "single_chapter" / case_id
        cases.append(
            _compile_case(
                case_id=case_id,
                scope_type="chapter",
                case_dir=case_dir,
                chapters=[chapters[chapter_no]],
            )
        )

    cases.append(
        _compile_case(
            case_id="batch_001_005",
            scope_type="chapter_batch",
            case_dir=DATASET_ROOT / "batch_001_005",
            chapters=[chapters[number] for number in range(1, 6)],
        )
    )

    manifest = {
        "dataset_id": "taichu_knowledge_eval_first5_three_experts",
        "label": "太初前五章知识抽取评测集",
        "lifecycle": "confirmed",
        "agent_name": "knowledge_extraction",
        "schema_snapshot_path": "_metadata/schema_snapshot.json",
        "checksum_manifest_path": "_metadata/checksums.sha256.json",
        "cases": cases,
    }
    _write_json(DATASET_ROOT / "manifest.json", manifest)
    _write_checksums()
    counts = [
        len(_load_json(DATASET_ROOT / case["expected_cards_path"])) for case in cases
    ]
    print(f"评测集已生成，六个 case 的期望卡数量：{counts}")


def _load_chapter(item: dict[str, Any]) -> ChapterSource:
    path = SOURCE_ROOT / str(item["markdown_path"])
    markdown = path.read_text(encoding="utf-8")
    return ChapterSource(
        chapter_id=str(item["chapter_id"]),
        path=path,
        markdown=markdown,
        content_hash=_hash_text(markdown),
    )


def _compile_case(
    *,
    case_id: str,
    scope_type: str,
    case_dir: Path,
    chapters: list[ChapterSource],
) -> dict[str, Any]:
    cards = _load_case_cards(case_dir)
    quote_records: dict[str, dict[str, Any]] = {}
    expected_cards: list[dict[str, Any]] = []

    for card in cards:
        expected_card_id = str(card["id"])
        aliases = [
            str(value).strip()
            for value in card.get("aliases", [])
            if str(value).strip()
        ]
        accepted_names = _unique([str(card["name"]).strip(), *aliases])
        windows = _find_quote_windows(card, chapters)
        quote_ids: list[str] = []
        for index, window in enumerate(windows, start=1):
            quote_id = f"quote_{expected_card_id}_{index:02d}"
            quote_ids.append(quote_id)
            quote_records[quote_id] = {
                "quote_id": quote_id,
                "chapter_id": window.chapter_id,
                "text": window.text,
                "start_offset": window.start_offset,
                "end_offset": window.end_offset,
                "source_hash": window.source_hash,
            }

        projected_card = {
            key: value
            for key, value in card.items()
            if key not in {"id", "created_at", "updated_at"}
        }
        semantic_fields = [
            field
            for field in SEMANTIC_FIELDS
            if _has_content(projected_card.get(field))
        ]
        expected_claims = []
        summary = projected_card.get("summary")
        if isinstance(summary, str) and summary.strip():
            expected_claims.append(
                {
                    "claim_id": f"claim_{expected_card_id}_summary",
                    "field": "summary",
                    "importance": "major",
                    "description": summary.strip(),
                    "source_quote_ids": quote_ids,
                }
            )
        expected_cards.append(
            {
                "expected_card_id": expected_card_id,
                "knowledge_type": str(card["type"]),
                "card": projected_card,
                "accepted_names": accepted_names,
                "exact_fields": [
                    field for field in EXACT_FIELDS if field in projected_card
                ],
                "set_fields": ["aliases"],
                "semantic_fields": semantic_fields,
                "expected_claims": expected_claims,
                "source_quote_ids": quote_ids,
            }
        )

    negative_cases = _compile_negative_cases(
        case_id=case_id,
        case_dir=case_dir,
        chapters=chapters,
        quote_records=quote_records,
    )
    expected_path = case_dir / "expected_cards.json"
    rules_path = case_dir / "evaluation_rules.json"
    evidence_path = case_dir / "source_evidence.json"
    negatives_path = case_dir / "negative_cases.json"
    _write_json(expected_path, expected_cards)
    _write_json(
        rules_path,
        {
            "field_weights": {
                "type": 2.0,
                "status": 1.0,
                "importance": 1.0,
                "source_origin": 1.0,
                "aliases": 1.0,
            },
            "reference_identity_map": {},
            "reference_fields": [
                "owner_faction_id",
                "controlling_faction_id",
                "leader_id",
                "current_holder_id",
            ],
        },
    )
    _write_json(
        evidence_path,
        [quote_records[key] for key in sorted(quote_records)],
    )
    _write_json(negatives_path, negative_cases)
    return {
        "case_id": case_id,
        "scope_type": scope_type,
        "chapter_ids": [chapter.chapter_id for chapter in chapters],
        "source_chapter_hashes": {
            chapter.chapter_id: chapter.content_hash for chapter in chapters
        },
        "expected_cards_path": _relative(expected_path),
        "evaluation_rules_path": _relative(rules_path),
        "source_evidence_path": _relative(evidence_path),
        "negative_cases_path": _relative(negatives_path),
    }


def _load_case_cards(case_dir: Path) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for expert in EXPERTS:
        path = case_dir / expert / "cards.json"
        for card in _load_json(path):
            card_id = str(card["id"])
            if card_id in seen_ids:
                raise ValueError(f"期望卡重复：{card_id}")
            seen_ids.add(card_id)
            cards.append(card)
    return sorted(cards, key=lambda item: (str(item["type"]), str(item["id"])))


def _find_quote_windows(
    card: dict[str, Any],
    chapters: list[ChapterSource],
) -> list[QuoteWindow]:
    terms = _search_terms(card)
    candidates: list[QuoteWindow] = []
    for chapter in chapters:
        for start, end, paragraph in _paragraphs(chapter.markdown):
            score = _paragraph_score(paragraph, terms)
            if score <= 0:
                continue
            window_start, window_end = _bounded_window(
                chapter.markdown,
                start,
                end,
                terms,
            )
            candidates.append(
                QuoteWindow(
                    chapter_id=chapter.chapter_id,
                    text=chapter.markdown[window_start:window_end],
                    start_offset=window_start,
                    end_offset=window_end,
                    source_hash=chapter.content_hash,
                    score=score,
                )
            )
    if not candidates:
        chapter = chapters[0]
        end = min(len(chapter.markdown), 900)
        candidates.append(
            QuoteWindow(
                chapter_id=chapter.chapter_id,
                text=chapter.markdown[:end],
                start_offset=0,
                end_offset=end,
                source_hash=chapter.content_hash,
                score=0,
            )
        )
    ordered = sorted(
        candidates,
        key=lambda item: (-item.score, item.chapter_id, item.start_offset),
    )
    selected: list[QuoteWindow] = []
    seen: set[tuple[str, int, int]] = set()
    for item in ordered:
        key = (item.chapter_id, item.start_offset, item.end_offset)
        if key in seen:
            continue
        seen.add(key)
        selected.append(item)
        if len(selected) == 4:
            break
    return selected


def _search_terms(card: dict[str, Any]) -> list[str]:
    direct = [str(card.get("name") or "")]
    direct.extend(str(value) for value in card.get("aliases", []))
    terms = [term.strip() for term in direct if len(term.strip()) >= 2]
    seed = "".join(
        [
            str(card.get("name") or ""),
            str(card.get("summary") or ""),
        ]
    )
    for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", seed):
        for width in (4, 3, 2):
            for index in range(0, max(0, len(sequence) - width + 1)):
                term = sequence[index : index + width]
                if term not in COMMON_TERMS:
                    terms.append(term)
    return _unique(terms)[:80]


def _paragraphs(markdown: str) -> list[tuple[int, int, str]]:
    matches = re.finditer(r"\S(?:.|\n)*?(?=\n\s*\n|\Z)", markdown)
    return [
        (match.start(), match.end(), match.group(0))
        for match in matches
        if match.group(0).strip()
    ]


def _paragraph_score(paragraph: str, terms: list[str]) -> int:
    return sum(len(term) ** 2 for term in terms if term in paragraph)


def _bounded_window(
    markdown: str,
    paragraph_start: int,
    paragraph_end: int,
    terms: list[str],
) -> tuple[int, int]:
    if paragraph_end - paragraph_start <= 1000:
        return paragraph_start, paragraph_end
    paragraph = markdown[paragraph_start:paragraph_end]
    hits = [paragraph.find(term) for term in terms if term in paragraph]
    anchor = min((hit for hit in hits if hit >= 0), default=0)
    start = max(paragraph_start, paragraph_start + anchor - 320)
    end = min(paragraph_end, start + 1000)
    start = max(paragraph_start, end - 1000)
    return start, end


def _compile_negative_cases(
    *,
    case_id: str,
    case_dir: Path,
    chapters: list[ChapterSource],
    quote_records: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    path = case_dir / "ignored_candidates.json"
    if not path.exists():
        return []
    results: list[dict[str, Any]] = []
    for index, raw in enumerate(_load_json(path), start=1):
        accepted_names = _unique(
            [part.strip() for part in re.split(r"[/／、]", str(raw["text"]))]
        )
        card = {
            "name": accepted_names[0],
            "aliases": accepted_names[1:],
            "summary": str(raw.get("reason") or ""),
        }
        window = _find_quote_windows(card, chapters)[0]
        quote_id = f"quote_negative_{case_id}_{index:02d}"
        quote_records[quote_id] = {
            "quote_id": quote_id,
            "chapter_id": window.chapter_id,
            "text": window.text,
            "start_offset": window.start_offset,
            "end_offset": window.end_offset,
            "source_hash": window.source_hash,
        }
        results.append(
            {
                "negative_case_id": f"negative_{case_id}_{index:02d}",
                "knowledge_type": _infer_negative_type(accepted_names),
                "accepted_names": accepted_names,
                "reason": str(raw["reason"]),
                "source_quote_ids": [quote_id],
            }
        )
    return results


def _infer_negative_type(names: list[str]) -> str:
    joined = "".join(names)
    if any(token in joined for token in ("山", "谷", "洞", "亭", "地点")):
        return "location"
    if any(token in joined for token in ("剑", "花", "草", "药", "物品")):
        return "item"
    return "character"


def _write_checksums() -> None:
    checksum_path = DATASET_ROOT / "_metadata" / "checksums.sha256.json"
    records: dict[str, str] = {}
    for path in sorted(DATASET_ROOT.rglob("*")):
        if not path.is_file() or path == checksum_path:
            continue
        records[_relative(path)] = sha256(path.read_bytes()).hexdigest()
    _write_json(checksum_path, records)


def _relative(path: Path) -> str:
    return path.relative_to(DATASET_ROOT).as_posix()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return
    path.write_text(rendered, encoding="utf-8")


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _has_content(value: Any) -> bool:
    return value not in (None, "", [], {})


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


if __name__ == "__main__":
    main()
