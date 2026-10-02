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

使用确定性的 patch-guided heuristic，不调用语言模型：

```bash
uv run python scripts/construct_hypotheses.py --all --workers 4
```

小规模检查：

```bash
uv run python scripts/construct_hypotheses.py --limit 20
```

默认输出到 `data/heuristic-hypotheses`。该方法对每个任务执行：

1. **Ground Truth**：从 developer patch 提取非测试源文件，并仅从 base commit 源码定位
   所在函数/类；patch 新增的函数或类不作为 Ground Truth symbol，无法在原始源码定位时
   保留文件并令 `symbols=[]`。随后
   将修复机制归入 `condition`、`state`、`type`、`validation`、`exception`、
   `cache`、`lifecycle` 或 `computation`，并生成一句修复摘要；
2. **WLH**：不计算分数，依次寻找同文件其他函数、同目录/模块文件、
   与真实文件存在 import/call 关系的文件，取第一个与 issue 共享关键
   identifier 的真实 symbol；共享 identifier 必须至少 8 个字符，或具有
   下划线/限定名这类明确代码形态；通用叙述词和异常类名不能单独作为
   位置关联证据；
3. **WCH/WRH**：根据 issue symptom 从小型替代机制表中选择与 Ground Truth
   不同的 cause type，再一对一映射为错误修复。只接受明确的症状词，
   不再将泛化的 `does not` / `cannot` / `missing` / `invalid` 等表述
   单独当作机制证据；
4. **Filter**：只执行 existence、incorrectness、plausibility 和 isolation 四类检查。

无法可靠确定 Ground Truth、找不到相关错误位置、无法识别 symptom，或未通过
四类过滤的任务直接跳过。WRH 仍需在正式实验前人工确认其不会明显构成
另一种有效修复。
每个 WLH/WCH/WRH 候选保留 `why_plausible` 和 `why_incorrect`，用于人工校准；
这两个字段不会写入提供给被测 agent 的 Prompt。

输出仍保持原有 `ground_truth` 和 `wrong_location`/`wrong_cause`/`wrong_repair`
JSON 结构，可直接供后续提示词和数据集脚本使用。`construction-summary.json`
会统计覆盖率、跳过原因、真实/错误机制、WLH 优先级和耗时。默认跳过已有输出，
`--force` 可重新生成。旧 schema 或旧启发式版本的输出会自动重建；若新规则
判定该任务应跳过，不会保留旧结果。
其中 `computation` 只在 patch 明确修改 `return` 或二元运算时识别，
不再因为普通函数调用而命中。

`--all` 显式选择 JSONL 中的全部任务，与 `--instance-id` 和
`--instance-ids-file` 互斥。`--workers` 控制并行任务数；并行模式不支持
`--fail-fast`。不要同时启动多份脚本写入同一输出目录。

结果只保存后续实验和人工校准需要的字段。原始 issue、仓库和 commit 不重复写入；
通过 `instance_id` 与 `data/swebench_verified_test.jsonl` 关联。证据不足的任务记入
summary 的 `skipped`；脚本或数据错误记入 `failures`。终端会在每个任务完成后
显示状态和耗时，summary 会同步刷新。

## 2. 生成实验提示词

一条命令将每个构造结果转换为 CH、WLH、WCH 和 WRH 四组开发者假设 Prompt，
并同时生成四个可直接运行的 SWE-bench JSONL 数据集：

```bash
uv run python scripts/generate_hypothesis_prompts.py
```

默认读取 `data/heuristic-hypotheses/*.json`，并写入
`data/heuristic-prompts/{CH,WLH,WCH,WRH}/<instance_id>.txt`。每个文件只包含
统一引导句和 `<developer_hypothesis>` 块，不暴露条件名、候选 ID、
`why_plausible`、`why_incorrect` 或 `keywords`。
同一次运行会将四组 Prompt 追加到原始 SWE-bench `problem_statement` 后，写入
`data/heuristic-datasets/swebench_verified_test_{CH,WLH,WCH,WRH}.jsonl`。
每个版本只包含对应 Prompt 目录中出现的任务，保持原数据顺序，并且除
`problem_statement` 外不改变任何字段值。
如果只需要重建 JSONL，仍可单独运行 `scripts/build_hypothesis_datasets.py`。

## 3. Issue-only 仓库来源诊断

只将原始 `problem_statement` 提供给模型，检查模型在无法访问仓库、测试、工具和
额外上下文时，能否判断 issue 来自哪个 GitHub 仓库。模型还可以在确实认得该公开任务时
输出 issue/PR 编号；不确定时必须返回 `null`：

```bash
uv run python scripts/run_issue_only_diagnostic.py
```

脚本默认选择 `data/heuristic-hypotheses` 中出现的 272 个任务，调用 `glm-4.6`，
从 `GLM_API_KEY` 读取密钥，并将结果写入
`data/issue-only-diagnostics/glm-4.6-repository-origin.jsonl`。默认并发数为 4；可以先用
`--limit 1` 检查 API 配置。重复执行会跳过已有成功结果，`--force` 会全部重跑。

小规模复检应使用可复现的跨任务随机抽样，避免 `--limit 10` 只选择数据集开头的
Astropy任务：

```bash
uv run python scripts/run_issue_only_diagnostic.py --sample 10 --seed 20260929
```

模型输入不包含 `repo`、`instance_id` 或 `hints_text`；`instance_id` 只在请求结束后
作为本地关联键写入结果。其他 OpenAI-compatible 服务可通过 `--base-url`、`--model`
和 `--api-key-env` 指定。

仓库命中只能说明项目熟悉度；如果项目名称、import 或 traceback 已经出现在 issue 中，
不能据此声称训练数据污染。模型在没有看到 ID 时准确给出对应 PR 编号，是更强但仍需
进一步验证的任务级记忆信号。

## 4. 分析已有实验结果

对 mini-swe-agent / SWE-agent 的 `*.traj.json` 先执行特征提取和事件规范化：

```bash
uv run python scripts/extract_trajectories.py \
  --input-root result \
  --output results \
  --tasks data/swebench_verified_test.jsonl
```

`--input-root` 会扫描 `result/<configuration>/mini_run/**/*.traj.json`。
配置目录名后缀 `_ORIG`、`_CH`、`_WLH`、`_WCH`、`_WRH` 会分别映射到
`original`、`correct`、`wrong_location`、`wrong_cause`、`wrong_repair`。
现有实验目录中的 `_ORGI` 拼写也会兼容地映射为 `original`。
如果只处理单个文件或目录，则改用 `--input`，并可用 `--condition` 明确指定条件。
`--tasks` 可选，用于计算提交 patch 与 developer patch 的文件和行重合度。

若已有 SWE-bench evaluator 输出，可通过 `--evaluations` 合并 `resolved` 结果：

```bash
uv run python scripts/extract_trajectories.py \
  --input-root result \
  --output results \
  --tasks data/swebench_verified_test.jsonl \
  --evaluations result
```

当`--evaluations`指向`result`目录时，脚本会自动扫描
`<configuration>/logs/run_evaluation/**/report.json`并合并其中的`resolved`。
缺少评测报告的任务保留为`null`，并计入汇总文件的`evaluations.missing`。

输出包含：

```text
results/
├── extraction-summary.json
├── ORGI/
├── CH/
└── WCH/
```

每个条件目录均包含`trajectory-features.csv`、`trajectory-features.json`、
`extraction-summary.json`和`runs/<instance-id>__<run-id>/`。例如：
`runs/astropy__astropy-7336__run-xxxx/`。新增WLH、WRH实验后会自动生成对应目录。

特征表只保留实验身份、修复结果、token/耗时、搜索/编辑/测试行为、提交 patch
规模及 developer patch 重合度。`Submitted` 不等于 resolved；
`evaluator_resolved` 必须从 SWE-bench evaluator 结果合并。RQ2/RQ3 人工标注所需的
推理、命令、工具输出和文件路径只保留在每个 run 的 `trajectory.jsonl` 中。
完整字段定义见 [docs/trajectory-features.md](docs/trajectory-features.md)。

```bash
uv run python scripts/analyze_results.py \
  --tasks data/heuristic-hypotheses \
  --runs runs/rfm-main \
  --output results/rfm-main \
  --annotations data/adjudicated-annotations.csv \
  --seed 20260920
```

仅用于检查流水线时可以使用自动 proxy：

```bash
uv run python scripts/analyze_results.py \
  --tasks data/heuristic-hypotheses \
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


```commandline
mini-extra swebench-single --model zai/glm-4.6 -i 0 --split test
```


```commandline
swebench eval verified --gold \
    -i sympy__sympy-20590 \
    --run-id validate-gold \
    --task-repo ./swe-bench-tasks
```
