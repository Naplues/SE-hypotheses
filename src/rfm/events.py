from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rfm.io import read_jsonl

ALLOWED_EVENT_TYPES = {
    "message",
    "reasoning",
    "tool_call",
    "tool_result",
    "file_read",
    "file_write",
    "shell",
    "test",
    "patch",
    "final",
    "other",
}


@dataclass(frozen=True)
class Event:
    step: int
    event_type: str
    timestamp: float | None = None
    text: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    tool_output: str | None = None
    command: str | None = None
    files_accessed: tuple[str, ...] = ()
    files_modified: tuple[str, ...] = ()
    tokens_input: int | None = None
    tokens_output: int | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any], line_number: int) -> Event:
        try:
            step = int(raw["step"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"trajectory line {line_number} requires an integer step") from exc
        event_type = str(raw.get("event_type", "")).strip()
        if event_type not in ALLOWED_EVENT_TYPES:
            raise ValueError(
                f"trajectory line {line_number} has invalid event_type {event_type!r}; "
                f"expected one of {sorted(ALLOWED_EVENT_TYPES)}"
            )
        tool_arguments = raw.get("tool_arguments", {}) or {}
        if not isinstance(tool_arguments, dict):
            raise ValueError(f"trajectory line {line_number}.tool_arguments must be an object")
        return cls(
            step=step,
            event_type=event_type,
            timestamp=_optional_float(raw.get("timestamp")),
            text=_optional_string(raw.get("text")),
            tool_name=_optional_string(raw.get("tool_name")),
            tool_arguments=tool_arguments,
            tool_output=_optional_string(raw.get("tool_output")),
            command=_optional_string(raw.get("command")),
            files_accessed=tuple(str(value) for value in raw.get("files_accessed", []) or []),
            files_modified=tuple(str(value) for value in raw.get("files_modified", []) or []),
            tokens_input=_optional_int(raw.get("tokens_input")),
            tokens_output=_optional_int(raw.get("tokens_output")),
        )


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def load_events(path: str | Path) -> list[Event]:
    events = [Event.from_dict(raw, index) for index, raw in enumerate(read_jsonl(path), start=1)]
    if len({event.step for event in events}) != len(events):
        raise ValueError(f"Duplicate event steps in {path}")
    return sorted(events, key=lambda event: event.step)
