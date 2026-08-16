"""第一版能力目录与独立评测 Profile 一致性测试。"""

from taichu.application.evaluations.capability_profiles import (
    all_capability_evaluation_profiles,
    capability_evaluation_profile,
)
from taichu.infrastructure.plugin_discovery import (
    discover_subagents,
    discover_tools,
)


def test_every_production_capability_has_one_independent_profile() -> None:
    profiles = all_capability_evaluation_profiles()
    keys = {(item.capability_type, item.capability_name) for item in profiles}
    expected = {
        ("tool", plugin.manifest.name)
        for plugin in discover_tools("taichu.application.tools")
    } | {
        ("subagent", plugin.manifest.name)
        for plugin in discover_subagents("taichu.application.subagents")
    }

    assert len(profiles) == 30
    assert keys == expected


def test_confirmed_split_capabilities_keep_different_metrics() -> None:
    drafting = capability_evaluation_profile("subagent", "drafting")
    revision = capability_evaluation_profile("subagent", "revision")
    story = capability_evaluation_profile("subagent", "story_architecture")
    scene = capability_evaluation_profile("subagent", "scene_planning")

    assert drafting.metrics != revision.metrics
    assert story.metrics != scene.metrics


def test_consistency_review_keeps_one_contract_with_six_dimensions() -> None:
    profile = capability_evaluation_profile("subagent", "consistency_reviewer")

    assert {metric.dimension for metric in profile.metrics} == {
        "world_rules",
        "character",
        "timeline",
        "causality",
        "state_continuity",
        "foreshadowing",
    }
