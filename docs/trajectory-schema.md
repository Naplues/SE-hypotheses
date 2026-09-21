# Trajectory JSONL contract

Each line is one JSON object. Required fields:

```json
{"step": 1, "event_type": "file_read"}
```

- `step`: unique integer within the trajectory;
- `event_type`: one of `message`, `reasoning`, `tool_call`, `tool_result`, `file_read`,
  `file_write`, `shell`, `test`, `patch`, `final`, or `other`.

Optional fields used by the analysis:

```json
{
  "step": 2,
  "event_type": "tool_call",
  "text": "inspect parser",
  "tool_name": "read_file",
  "tool_arguments": {"path": "src/parser.py"},
  "tool_output": "...",
  "command": "pytest tests/test_parser.py",
  "files_accessed": ["src/parser.py"],
  "files_modified": [],
  "tokens_input": 120,
  "tokens_output": 35
}
```

Unknown fields are ignored, so adapters may retain additional agent-specific metadata.
Paths should be repository-relative whenever possible.
