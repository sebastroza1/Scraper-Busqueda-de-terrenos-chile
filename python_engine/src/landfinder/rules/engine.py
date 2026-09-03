from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from landfinder.models.enums import Program, RuleResultStatus
from landfinder.models.property import RuleEvaluation


@dataclass(frozen=True)
class RuleSet:
    path: Path
    payload: dict[str, Any]


class RuleEngine:
    """Small YAML-backed rule evaluator.

    The engine intentionally supports only simple operators. Unknown thresholds,
    missing values and manual rules produce `UNKNOWN` or `MANUAL_REVIEW_REQUIRED`
    instead of invented conclusions.
    """

    def load_ruleset(self, path: str | Path) -> RuleSet:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - depends on optional env setup.
            raise RuntimeError("PyYAML is required to load rule files") from exc

        rule_path = Path(path)
        payload = yaml.safe_load(rule_path.read_text(encoding="utf-8")) or {}
        return RuleSet(path=rule_path, payload=payload)

    def evaluate_rule(self, rule: dict[str, Any], facts: dict[str, Any]) -> RuleEvaluation:
        automatic = bool(rule.get("automatic", False))
        threshold = rule.get("threshold")
        operator = rule.get("operator")
        fact_key = rule.get("fact_key")
        value = facts.get(fact_key) if fact_key else None

        if not automatic or rule.get("manual_review_required"):
            status = RuleResultStatus.MANUAL_REVIEW_REQUIRED
        elif threshold in (None, "UNKNOWN") or value is None:
            status = RuleResultStatus.UNKNOWN
        else:
            status = self._apply_operator(operator, value, threshold)

        return RuleEvaluation(
            rule_id=rule["rule_id"],
            program=Program(rule["program"]),
            year=int(rule["year"]),
            call=rule.get("call"),
            status=status,
            severity=rule["severity"],
            description=rule["description"],
            legal_source=rule.get("legal_source"),
            effective_date=rule.get("effective_date"),
            automatic=automatic,
            notes=rule.get("notes"),
        )

    def evaluate_ruleset(self, ruleset: RuleSet, facts: dict[str, Any]) -> list[RuleEvaluation]:
        return [self.evaluate_rule(rule, facts) for rule in ruleset.payload.get("rules", [])]

    @staticmethod
    def _apply_operator(operator: str | None, value: Any, threshold: Any) -> RuleResultStatus:
        if operator == "exists":
            return (
                RuleResultStatus.PASSED if value not in (None, "", []) else RuleResultStatus.FAILED
            )
        if operator == "equals":
            return RuleResultStatus.PASSED if value == threshold else RuleResultStatus.FAILED
        if operator == "not_equals":
            return RuleResultStatus.PASSED if value != threshold else RuleResultStatus.FAILED
        if operator == "gte":
            return RuleResultStatus.PASSED if value >= threshold else RuleResultStatus.FAILED
        if operator == "lte":
            return RuleResultStatus.PASSED if value <= threshold else RuleResultStatus.FAILED
        if operator == "in":
            return RuleResultStatus.PASSED if value in threshold else RuleResultStatus.FAILED
        return RuleResultStatus.UNKNOWN
