from pathlib import Path

from taichu.application.evaluations.rag.dataset import load_golden_suite
from taichu.application.evaluations.rag.gates import select_pr_semantic_cases


def test_pr_semantic_selection_is_ten_cases_with_fixed_distribution() -> None:
    suite = load_golden_suite(
        Path("tests/fixtures/evaluations/rag_graph_core/suite.json")
    )

    selected = select_pr_semantic_cases(suite.cases)

    assert len(selected) == 10
    categories = [str(case.category) for case in selected]
    assert categories.count("single_fact") == 2
    assert categories.count("cross_source") == 2
    assert categories.count("graph_multi_hop") == 4
    assert categories.count("hard_negative") == 2
