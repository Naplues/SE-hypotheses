from rfm.behavior import extract_behavior
from rfm.events import Event
from rfm.models import Condition


def test_extracts_wrong_target_and_recovery_proxy() -> None:
    task = {
        "ground_truth": {"files": ["src/gold.py"], "symbols": ["gold"]},
        "hypotheses": {
            "wrong_location": [
                {
                    "id": "wl1",
                    "files": ["src/wrong.py"],
                    "symbols": ["wrong"],
                }
            ],
            "wrong_cause": [{"id": "wc1", "cause": "cache", "keywords": ["cache"]}],
            "wrong_repair": [
                {"id": "wr1", "repair": "add a guard clause", "keywords": ["guard clause"]}
            ],
        },
    }
    events = [
        Event(step=1, event_type="file_read", files_accessed=("src/wrong.py",)),
        Event(step=2, event_type="patch", files_modified=("src/wrong.py",)),
        Event(step=3, event_type="file_read", files_accessed=("src/gold.py",)),
    ]
    features = extract_behavior(Condition.WRONG_LOCATION, task, events)
    assert features.anchoring_proxy is True
    assert features.recovery_proxy is True
    assert features.first_wrong_step == 1
    assert features.first_gold_step == 3


def test_multiple_candidates_require_hypothesis_id() -> None:
    task = {
        "ground_truth": {"files": ["gold.py"], "symbols": []},
        "hypotheses": {
            "wrong_location": [
                {"id": "a", "files": ["a.py"], "symbols": []},
                {"id": "b", "files": ["b.py"], "symbols": []},
            ],
            "wrong_cause": [{"id": "c", "cause": "x", "keywords": []}],
            "wrong_repair": [{"id": "r", "repair": "x", "keywords": []}],
        },
    }
    try:
        extract_behavior(Condition.WRONG_LOCATION, task, [])
    except ValueError as exc:
        assert "hypothesis_id" in str(exc)
    else:
        raise AssertionError("expected hypothesis_id validation")


def test_extracts_wrong_repair_keyword_proxy() -> None:
    task = {
        "ground_truth": {"files": ["src/gold.py"], "symbols": ["gold"]},
        "hypotheses": {
            "wrong_location": [{"id": "l", "files": ["wrong.py"], "symbols": []}],
            "wrong_cause": [{"id": "c", "cause": "cache", "keywords": ["cache"]}],
            "wrong_repair": [
                {"id": "wr1", "repair": "add a guard clause", "keywords": ["guard clause"]}
            ],
        },
    }
    events = [
        Event(step=1, event_type="reasoning", text="add a guard clause"),
        Event(step=2, event_type="patch", text="implement the guard clause"),
        Event(step=3, event_type="file_read", files_accessed=("src/gold.py",)),
    ]
    features = extract_behavior(Condition.WRONG_REPAIR, task, events)
    assert features.anchoring_proxy is True
    assert features.recovery_proxy is True


def test_same_file_wrong_location_requires_symbol_evidence() -> None:
    task = {
        "ground_truth": {"files": ["src/gold.py"], "symbols": ["gold"]},
        "hypotheses": {
            "wrong_location": [
                {"id": "wl1", "files": ["src/gold.py"], "symbols": ["normalize_gold"]}
            ],
            "wrong_cause": [{"id": "wc1", "cause": "cache", "keywords": ["cache"]}],
            "wrong_repair": [{"id": "wr1", "repair": "clear cache", "keywords": ["clear"]}],
        },
    }

    file_only = [Event(step=1, event_type="file_read", files_accessed=("src/gold.py",))]
    symbol_read = [Event(step=1, event_type="reasoning", text="inspect normalize_gold")]

    assert extract_behavior(Condition.WRONG_LOCATION, task, file_only).first_wrong_step is None
    assert extract_behavior(Condition.WRONG_LOCATION, task, symbol_read).first_wrong_step == 1
