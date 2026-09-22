# RFM Experiments

本仓库只包含两个主要功能：

1. 从 SWE-bench 任务构造 Ground Truth 和误导性假设；
2. 读取已经完成的 agent 修复结果与轨迹，计算 RQ1–RQ3。

## 安装

```bash
uv sync --extra dev
```

运行测试：

```bash
uv run pytest
```

`data/swebench_verified_repos.json` 是 500 个 Verified 任务的仓库索引，保存
`instance_id`、GitHub clone URL 和 `base_commit`。它可以通过下面的辅助脚本从
Hugging Face 数据集重新生成：

```bash
uv sync --extra download
uv run python src/tmp/a.py
```

假设构造以 `swebench_verified_test.jsonl` 为事实来源，因为其中同时包含 issue、patch、
tests、仓库和 commit；仓库索引用于独立查看或预取仓库。

如果 Git 仓库下载不稳定，可以只下载某个任务 `base_commit` 的源码快照：

```bash
uv run python scripts/download_commit_archive.py \
  --instance-id astropy__astropy-12907
```

顺序下载 JSONL 中的全部任务：

```bash
uv run python scripts/download_commit_archive.py --all
```

压缩包缓存在 `data/repo-archives`，源码解压到
`data/repository-snapshots/<instance_id>`，下载元数据和 archive SHA-256 位于
`data/repository-snapshots/.metadata`。批量结果写入 `download-summary.json`。重复执行会跳过
已有快照；使用 `--force` 重新下载。

## 1. 构造 Ground Truth 和 Hypotheses

```bash
uv run python scripts/construct_hypotheses.py \
  --model YOUR_PINNED_CLAUDE_MODEL_ID \
  --instance-ids-file data/instance-ids.txt
```

快速试运行一个任务：

```bash
uv run python scripts/construct_hypotheses.py \
  --model YOUR_PINNED_CLAUDE_MODEL_ID \
  --limit 1
```

并行构造多个任务：

```bash
uv run python scripts/construct_hypotheses.py \
  --model YOUR_PINNED_CLAUDE_MODEL_ID \
  --all \
  --workers 2
```

`--all` 显式选择 JSONL 中的全部任务，与 `--instance-id` 和 `--instance-ids-file` 互斥。
它可以与 `--limit` 组合进行小规模试运行，也可以与 `--workers` 组合并行构造。

`--workers` 默认为 1。每个 worker 启动独立的 Claude Code 子进程，主进程统一写入
`construction-summary.json`。建议从 2 开始；并发过高可能触发模型服务限流，且费用会
同时产生。并行模式不支持 `--fail-fast`。不要手工启动多份脚本并写同一输出目录。

请将 `YOUR_PINNED_CLAUDE_MODEL_ID` 替换为实际且固定的 Claude 模型标识。默认读取
`data/swebench_verified_test.jsonl`，私有工作目录为 `data/construction-workspace`，结果写入
`data/constructed-hypotheses`，源码从 `data/repository-snapshots` 读取；需要时可通过
`--input`、`--workspace`、`--output` 和 `--snapshots` 覆盖。运行环境固定使用 `claude`
命令、单次调用 10 分钟超时和最多 4 个 turn。脚本先在本地从 base commit 快照提取
developer patch 和 test patch 各个 hunk 前后最多 40 行的源码，总计最多约 24,000 字符，
再连同 issue 和 patch 交给模型。两次模型调用均不开放仓库工具，要求一次响应完成，
避免模型反复探索；Prompt 也不再包含冗长的 `PASS_TO_PASS` 列表。
Hypothesis 每类只生成一个候选，减少不必要的生成。
为避免 Hypothesis 阶段反复探索仓库，脚本会先从 Ground Truth 文件周边收集最多 12 个真实
源文件作为 Wrong Location 候选；第二次 Claude 调用禁用仓库工具，只根据 issue、精简
Ground Truth 和候选路径一次性生成 WLH/WCH/WRH。
超时针对每次 Claude 调用：超过 600 秒后终止子进程，并按 `ground_truth` 或
`hypotheses` 阶段记入 `failures`。一个任务包含两次调用，因此任务级最长时间可接近
20 分钟。

脚本对每个任务自动完成：

1. 读取已经下载的 `base_commit` 源码快照及其元数据；
2. 校验任务、仓库、commit 和 archive SHA-256；
3. 本地提取 patch hunk 附近的 base-commit 源码并运行 Ground Truth Prompt；
4. 校验 Ground Truth 文件属于 developer patch 且存在于 base commit；
5. 组装并运行 Hypothesis Prompt；
6. 校验 Wrong Location、Wrong Cause 和 Wrong Repair 候选，并确保错误位置不与真实位置重叠；
7. 证据不足时记录跳过原因，否则输出一个任务 JSON。

Ground Truth 和 Hypothesis 阶段都不提供仓库工具。脚本在调用前计算源码树 SHA-256，并在
每次调用后重新计算；摘要不一致时任务失败。Ground Truth 仍由模型根据 issue、开发者 patch、
测试 patch 和源码片段生成，并非由脚本硬编码推断。

输出格式：

```json
{
  "schema_version": 3,
  "instance_id": "owner__repo-1",
  "ground_truth": {
    "files": ["src/file.py"],
    "symbols": ["function"],
    "cause": "...",
    "repair": "..."
  },
  "hypotheses": {
    "wrong_location": [],
    "wrong_cause": [],
    "wrong_repair": []
  },
  "generated_by": {
    "model": "...",
    "claude_code_version": "..."
  }
}
```

结果只保存后续实验和人工校准需要的字段。原始 issue、仓库和 commit 不重复写入；需要时用
`instance_id` 与 `data/swebench_verified_test.jsonl` 关联。Ground Truth 的证据仅在构造期间
用于校验和生成误导假设，不写入最终结果。详细 Prompt 保存在私有 `workspace/prompts` 中。
通过校验的 Ground Truth 原始响应还会以提示词和模型指纹为键保存在私有
`workspace/checkpoints` 中；Hypothesis 阶段失败后使用 `--retry-failed`，可以直接复用它，
无需再次支付 Ground Truth 的时间和费用。更换模型或提示词后旧 checkpoint 会自动失效；
`--force` 会绕过 checkpoint 并重新生成两个阶段。

`workspace` 包含 developer patch 和 Prompt，必须与被测 agent 隔离。源码快照同样不能
提供给后续被测 agent；`output` 中的任务 JSON 才是后续实验使用的数据。

默认跳过已经存在的输出，也跳过历史上已失败或已判定无法构造的任务；使用 `--force`
才会重新尝试。这些历史状态按任务保存在 `output/.construction-state/`，并会从已有的
`construction-summary.json` 自动迁移。批量运行时，其他任务仍继续执行；使用 `--fail-fast`
可在首次失败时停止。
批量重试历史失败任务时使用 `--retry-failed`；它不会重跑已完成结果，也不会重试
已明确判定无法构造的 `skipped` 任务。此时显示的 `not_failed` 只是本次筛选结果，
不会被保存为任务的历史跳过状态。

Ground Truth 无法从仓库证据中确认，或 WLH/WCH/WRH 任一类无法在不编造证据的
前提下生成时，该任务不会输出 JSON，而是记入 summary 的 `skipped`：

```json
{
  "instance_id": "owner__repo-1",
  "reason": "hypotheses: no plausible wrong location exists"
}
```

正常跳过不计入 `failures`，不会导致批处理返回失败；Claude 调用错误、格式错误和校验
不一致仍记入 `failures`，避免把系统故障伪装成数据不适用。
Claude 达到 `max_turns` 但未产生结果时不会自动重试，而是按当前阶段记为正常跳过，
例如 `ground_truth: max_turns`，避免重复消耗时间和模型费用。
连接中断、DNS、限流或服务暂时不可用等瞬时错误会自动重试一次。600 秒硬超时不会在同一
次运行中立即再等 600 秒；应使用 `--retry-failed` 重新执行，此时已有 Ground Truth checkpoint
会被复用。

运行时终端会在每个任务结束后显示 Ground Truth、Hypothesis 和任务总耗时。
`construction-summary.json` 的 `timing` 保存每个实际执行任务的耗时，并提供
count、total、mean、median、min 和 max 汇总统计。因已有输出而直接跳过的任务不计入
耗时统计。Summary 会在每个任务结束后刷新，中途停止时已记录的耗时不会丢失。

```json
{
  "timing": {
    "wall_seconds": 123.456,
    "task_seconds": {"count": 1, "mean": 123.1, "median": 123.1},
    "ground_truth_seconds": {"count": 1, "mean": 60.2},
    "hypothesis_seconds": {"count": 1, "mean": 61.8},
    "tasks": [
      {
        "instance_id": "owner__repo-1",
        "outcome": "completed",
        "ground_truth_seconds": 60.2,
        "ground_truth_cached": false,
        "hypothesis_seconds": 61.8,
        "total_seconds": 123.1
      }
    ]
  }
}
```

## 2. 生成实验提示词

一条命令将每个构造结果转换为 CH、WLH、WCH 和 WRH 四组开发者假设 Prompt，
并同时生成四个可直接运行的 SWE-bench JSONL 数据集：

```bash
uv run python scripts/generate_hypothesis_prompts.py
```

默认读取 `data/constructed-hypotheses/*.json`，并写入
`data/hypothesis-prompts/{CH,WLH,WCH,WRH}/<instance_id>.txt`。每个文件只包含
统一引导句和 `<developer_hypothesis>` 块，不暴露条件名、候选 ID、
`why_plausible`、`why_incorrect` 或 `keywords`。
同一次运行会将四组 Prompt 追加到原始 SWE-bench `problem_statement` 后，写入
`data/hypothesis-datasets/swebench_verified_test_{CH,WLH,WCH,WRH}.jsonl`。
每个版本只包含对应 Prompt 目录中出现的任务，保持原数据顺序，并且除
`problem_statement` 外不改变任何字段值。
如果只需要重建 JSONL，仍可单独运行 `scripts/build_hypothesis_datasets.py`。

## 3. 分析已有实验结果

```bash
uv run python scripts/analyze_results.py \
  --tasks data/constructed-hypotheses \
  --runs runs/rfm-main \
  --output results/rfm-main \
  --annotations data/adjudicated-annotations.csv \
  --seed 20260920
```

仅用于检查流水线时可以使用自动 proxy：

```bash
uv run python scripts/analyze_results.py \
  --tasks data/constructed-hypotheses \
  --runs runs/rfm-main \
  --output results/rfm-main-proxy \
  --use-proxies
```

自动 proxy 不能作为论文中的 confirmatory behavioral labels。

每个运行目录只需要三个文件：

```text
runs/rfm-main/<run-id>/
├── run.json
├── result.json
└── trajectory.jsonl
```

最小 `run.json`：

```json
{
  "run_id": "run-001",
  "instance_id": "owner__repo-1",
  "agent_id": "openhands-1.0",
  "model_id": "model-version",
  "repetition": 1,
  "condition": "wrong_location",
  "hypothesis_id": "wl1"
}
```

当一个条件有多个候选假设时，`hypothesis_id` 必填。`result.json` 至少需要：

```json
{"resolved": true}
```

也可以包含 `status`、`tokens_total`、`tool_calls`、`runtime_seconds` 和 `steps`。

分析要求每个 `(instance, agent, model, repetition)` block 同时包含：

- `original`
- `correct`
- `wrong_location`
- `wrong_cause`
- `wrong_repair`

输出：

```text
results/rfm-main/
├── run-table.csv
├── report.json
└── report.md
```

- RQ1：修复率、exact McNemar、paired risk difference、Wilcoxon、Holm correction；
- RQ2：误导假设锚定率；
- RQ3：观察到矛盾后的恢复率、持续错误率和恢复延迟。

轨迹字段和人工标注格式见 [docs/trajectory-schema.md](docs/trajectory-schema.md) 与
[docs/protocol.md](docs/protocol.md)。
