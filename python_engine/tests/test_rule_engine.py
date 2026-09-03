from pathlib import Path

from landfinder.models.enums import RuleResultStatus
from landfinder.rules.engine import RuleEngine


def test_rule_engine_does_not_auto_apply_unverified_rules() -> None:
    path = Path(__file__).parents[1] / "rules" / "ds49" / "2026" / "adquisicion_terrenos.yaml"
    evaluations = RuleEngine().evaluate_ruleset(RuleEngine().load_ruleset(path), facts={})
    assert evaluations
    assert all(
        item.status in {RuleResultStatus.UNKNOWN, RuleResultStatus.MANUAL_REVIEW_REQUIRED}
        for item in evaluations
    )
    assert all(item.automatic is False for item in evaluations)
