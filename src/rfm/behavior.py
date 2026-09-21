"""Extract compact trajectory features used by the RQ analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from rfm.events import Event
from rfm.models import MISLEADING_CONDITIONS, Condition, normalize_path


@dataclass(frozen=True)
class BehaviorFeatures:
    first_wrong_step: int | None
    first_gold_step: int | None
    wrong_visit_count: int
    wrong_edit_count: int
    gold_visit_count: int
    gold_edit_count: int
    anchoring_proxy: bool
    recovery_proxy: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_behavior(
    condition: Condition,
    task: dict[str, Any],
    events: list[Event],
    *,
    hypothesis_id: str | None = None,
    early_step_limit: int = 10,
) -> BehaviorFeatures:
    wrong = _wrong_target(task, condition, hypothesis_id)
    gold = task["ground_truth"]
    wrong_steps = [event.step for event in events if wrong and _hits(event, wrong)]
    wrong_edits = [event.step for event in events if wrong and _edits(event, wrong)]
    gold_steps = [event.step for event in events if _hits(event, gold)]
    gold_edits = [event.step for event in events if _edits(event, gold)]
    first_wrong = min(wrong_steps, default=None)
    anchoring = bool(
        condition in MISLEADING_CONDITIONS
        and first_wrong is not None
        and first_wrong <= early_step_limit
        and (len(wrong_steps) >= 2 or wrong_edits)
    )
    recovery = bool(
        anchoring and first_wrong is not None and any(step > first_wrong for step in gold_steps)
    )
    return BehaviorFeatures(
        first_wrong_step=first_wrong,
        first_gold_step=min(gold_steps, default=None),
        wrong_visit_count=len(wrong_steps),
        wrong_edit_count=len(wrong_edits),
        gold_visit_count=len(gold_steps),
        gold_edit_count=len(gold_edits),
        anchoring_proxy=anchoring,
        recovery_proxy=recovery,
    )


def _wrong_target(
    task: dict[str, Any], condition: Condition, hypothesis_id: str | None
) -> dict[str, Any] | None:
    if condition not in MISLEADING_CONDITIONS:
        return None
    candidates = task["hypotheses"][condition.value]
    if hypothesis_id:
        matches = [item for item in candidates if item.get("id") == hypothesis_id]
        if len(matches) != 1:
            raise ValueError(f"Unknown hypothesis_id {hypothesis_id!r} for {condition.value}")
        return matches[0]
    if len(candidates) != 1:
        raise ValueError(
            f"run.json requires hypothesis_id when {condition.value} has multiple candidates"
        )
    return candidates[0]


def _hits(event: Event, target: dict[str, Any]) -> bool:
    files = target.get("files", [])
    if any(
        _path_matches(candidate, expected)
        for candidate in (*event.files_accessed, *event.files_modified)
        for expected in files
    ):
        return True
    blob = _event_blob(event)
    terms = [*target.get("symbols", []), *target.get("keywords", [])]
    return any(str(value).casefold() in blob for value in terms if value)


def _edits(event: Event, target: dict[str, Any]) -> bool:
    if any(
        _path_matches(candidate, expected)
        for candidate in event.files_modified
        for expected in target.get("files", [])
    ):
        return True
    return event.event_type in {"file_write", "patch"} and _hits(event, target)


def _event_blob(event: Event) -> str:
    return "\n".join(
        [
            event.text or "",
            event.tool_name or "",
            event.tool_output or "",
            event.command or "",
            " ".join(event.files_accessed),
            " ".join(event.files_modified),
            str(event.tool_arguments),
        ]
    ).casefold()


def _path_matches(candidate: str, target: str) -> bool:
    left = normalize_path(candidate)
    right = normalize_path(target)
    return left == right or left.endswith("/" + right) or right.endswith("/" + left)
