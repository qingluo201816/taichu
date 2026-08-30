import json

import pytest
from pydantic import ValidationError

from taichu.application.evaluations.rag.dataset import (
    load_golden_suite,
    validate_core_golden_suite,
)
from taichu.application.evaluations.rag.models import (
    RAGExpectedRelation,
    stable_relation_id,
)


def test_relation_identity_is_stable_across_spacing_and_unicode_width() -> None:
    assert stable_relation_id("秦浩轩  修炼 道心种魔大法") == stable_relation_id(
        "秦浩轩\u3000修炼\u3000道心种魔大法"
    )
    relation = RAGExpectedRelation(
        subject="秦浩轩 ", predicate=" 修炼", object="道心种魔大法"
    )
    assert relation.relation_id == stable_relation_id("秦浩轩 修炼 道心种魔大法")


def test_suite_rejects_duplicate_case_ids(tmp_path) -> None:
    case = {
        "case_id": "single-001",
        "query": "问题",
        "category": "single_fact",
        "expected_source_ids": ["source-a"],
        "expected_claims": ["事实"],
        "reference_answer": "答案",
    }
    path = tmp_path / "suite.json"
    path.write_text(
        json.dumps({"suite_id": "suite", "cases": [case, case]}),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="case_id"):
        load_golden_suite(path)


def test_core_golden_suite_has_fixed_layer_distribution() -> None:
    suite = load_golden_suite(
        __import__("pathlib").Path(
            "tests/fixtures/evaluations/rag_graph_core/suite.json"
        )
    )

    validate_core_golden_suite(suite)
    assert len(suite.cases) == 30


def test_graph_cases_do_not_reveal_their_bridge_entity() -> None:
    suite = load_golden_suite(
        __import__("pathlib").Path(
            "tests/fixtures/evaluations/rag_graph_core/suite.json"
        )
    )
    cases = {case.case_id: case for case in suite.cases}
    hidden_bridges = {
        "graph-001": "道心种魔大法",
        "graph-002": "驭兽术",
        "graph-003": "耶律齐",
        "graph-004": "绝仙毒谷",
        "graph-005": "无形剑",
        "graph-006": "徐羽",
        "graph-007": "小金",
        "graph-008": "袁山象",
        "graph-009": "古云子",
        "graph-010": "一叶金莲",
        "graph-011": "蒲汉忠",
        "graph-012": "慕容超",
        "graph-013": "璇玑子",
        "graph-014": "大田镇",
    }

    for case_id, bridge_entity in hidden_bridges.items():
        assert bridge_entity not in cases[case_id].query


def test_cross_002_answers_the_requested_cause_instead_of_rephrasing_targeting() -> None:
    suite = load_golden_suite(
        __import__("pathlib").Path(
            "tests/fixtures/evaluations/rag_graph_core/suite.json"
        )
    )
    case = next(case for case in suite.cases if case.case_id == "cross-002")

    assert case.expected_claims[0] == (
        "秦浩轩拒绝归附并妨碍李靖拉拢徐羽，李靖因而把不断壮大的秦浩轩视为威胁"
    )
    assert "张狂并非保护秦浩轩" in case.reference_answer
