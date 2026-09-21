# RFM analysis protocol

## Experimental unit

The paired unit is:

```text
instance_id × agent_id × model_id × repetition
```

Every unit must contain exactly one run under each condition: `original`, `correct`,
`wrong_location`, `wrong_cause`, and `wrong_repair`. The analysis rejects missing or
duplicated conditions.

## Required run files

Each run directory contains:

- `run.json`: identifiers, condition, and selected `hypothesis_id`;
- `result.json`: resolution outcome and optional cost/efficiency metrics;
- `trajectory.jsonl`: normalized agent events.

Agent-specific OpenHands or SWE-agent exports must be converted to this contract before
analysis. The scientific analysis does not depend on an agent implementation.

## Behavioral annotations

Confirmatory RQ2/RQ3 results use an adjudicated CSV with these fields:

```csv
run_id,anchored,contradiction_seen,recovered,persistent,contradiction_step,recovery_step
```

Only misleading-condition runs require annotations. Boolean values use `yes` or `no`.
`persistent` may be blank. Step fields may be blank when the event did not occur.

`recovered=yes` requires both `anchored=yes` and `contradiction_seen=yes`.

`--use-proxies` exists only for software-pipeline checks. Proxy results must not be reported
as confirmatory behavioral findings.

## Reported analyses

### RQ1 — Repair effectiveness

- resolution rate and Wilson 95% interval per condition;
- exact paired McNemar test against `original`;
- paired risk difference with bootstrap interval;
- paired Wilcoxon signed-rank tests for tokens, tool calls, runtime, and steps;
- Holm correction within each family of comparisons.

### RQ2 — Anchoring

- overall anchoring rate across misleading conditions;
- anchoring rate by `wrong_location`, `wrong_cause`, and `wrong_repair`.

### RQ3 — Recovery

Eligible runs are anchored runs where contradictory evidence was observed. Report:

- recovery rate;
- persistence rate when labeled;
- median `recovery_step - contradiction_step` among recovered runs.

## Integrity checks

- Never mix synthetic and real runs in one report.
- Pin agent and model versions in `run.json` identifiers.
- Keep construction workspaces private because they contain developer patches.
- Archive constructed task JSON, run directories, annotations, and the analysis seed.
