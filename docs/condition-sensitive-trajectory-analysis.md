# Qualitative trajectory analysis of condition-sensitive tasks

## Scope and method

This analysis covers the 34 tasks, among the 269 blocks with complete evaluator outcomes,
for which at least one of the five conditions succeeded and at least one failed. The outcome
signature is ordered as `Original / Correct / Wrong Location / Wrong Cause / Wrong Repair`,
where `1` denotes resolved and `0` unresolved.

For all 170 trajectories, the analysis compared evaluator outcome, final edited files,
gold-file overlap, gold-line overlap, search and edit activity, and test execution. Detailed
manual inspection focused on outcome patterns that can distinguish hypothesis guidance from
ordinary run-to-run branching. Statements about anchoring and recovery remain exploratory
because adjudicated behavioral labels and hypothesis identifiers are absent.

## Overview of the 34 tasks

There are 17 distinct outcome signatures. No single monotonic ordering of conditions explains
the results.

| Signature | Count | Interpretation |
|---|---:|---|
| `01000` | 5 | Only the correct hypothesis succeeds |
| `00001` | 3 | Only wrong repair succeeds |
| `10111` | 3 | Correct hypothesis alone turns success into failure |
| `11110` | 3 | Wrong repair alone turns success into failure |
| `00011` | 3 | Wrong cause and wrong repair succeed |
| `10000` | 2 | Original alone succeeds |
| `01100` | 2 | Correct and wrong location succeed |
| `01111` | 2 | All hypothesis-bearing conditions succeed |
| `00110` | 2 | Wrong location and wrong cause succeed |
| `10101` | 2 | Original, wrong location, and wrong repair succeed |
| Other signatures | 7 | One task each |

Within these 34 tasks, the number of successes is almost balanced across conditions:
Original 16, Correct 15, Wrong Location 16, Wrong Cause 17, and Wrong Repair 15. Relative to
Original, Correct produces 9 gains and 10 losses; Wrong Location 6 gains and 6 losses; Wrong
Cause 8 gains and 7 losses; and Wrong Repair 8 gains and 9 losses. This symmetry is inconsistent
with a simple model in which correct hints consistently rescue tasks and misleading hints
consistently damage them.

## Full task inventory

### Correct-hypothesis-dominant cases

| Task | Signature |
|---|---|
| `astropy__astropy-13033` | `01000` |
| `django__django-12663` | `01000` |
| `django__django-13794` | `01000` |
| `django__django-16256` | `01000` |
| `sympy__sympy-20428` | `01000` |
| `django__django-11964` | `01100` |
| `sympy__sympy-17630` | `01100` |
| `django__django-14765` | `01111` |
| `sympy__sympy-18211` | `01111` |

### Misleading-condition rescue cases

| Task | Signature |
|---|---|
| `django__django-15022` | `00001` |
| `sphinx-doc__sphinx-8475` | `00001` |
| `sphinx-doc__sphinx-9711` | `00001` |
| `django__django-16454` | `00010` |
| `pylint-dev__pylint-7080` | `00011` |
| `pylint-dev__pylint-8898` | `00011` |
| `pytest-dev__pytest-6197` | `00011` |
| `django__django-16560` | `00110` |
| `sphinx-doc__sphinx-8548` | `00110` |

### Hint-induced failure or mixed cases

| Task | Signature |
|---|---|
| `astropy__astropy-7606` | `10000` |
| `sympy__sympy-16597` | `10000` |
| `pylint-dev__pylint-4970` | `10001` |
| `django__django-16950` | `10010` |
| `pylint-dev__pylint-6528` | `10101` |
| `scikit-learn__scikit-learn-25102` | `10101` |
| `psf__requests-5414` | `10110` |
| `django__django-15572` | `10111` |
| `django__django-15916` | `10111` |
| `pytest-dev__pytest-7324` | `10111` |
| `sympy__sympy-15875` | `11001` |
| `scikit-learn__scikit-learn-12973` | `11010` |
| `sympy__sympy-21612` | `11100` |
| `django__django-17084` | `11110` |
| `scikit-learn__scikit-learn-14629` | `11110` |
| `sympy__sympy-13877` | `11110` |

## Cross-trajectory qualitative findings

### 1. Success on boundary tasks usually requires more exploration, not less

For each task, successful-condition means were compared with failed-condition means. Across
the 34 tasks, the median within-task differences were:

- runtime: +83.9 seconds;
- time to first successful edit: +24.1 seconds;
- total tokens: +428,364;
- steps: +14.8;
- tool calls: +7.3;
- tests: +0.4.

Successful trajectories used more steps in 21 of 34 tasks and more tests in 19 of 34. Thus,
for these condition-sensitive tasks, early convergence is not generally beneficial. A hint can
reduce the search space on the full dataset, but on difficult boundary cases it can also induce
premature commitment. Extra exploration and validation often distinguish success from failure.

### 2. Reaching the correct code region is the strongest observable discriminator

Successful trajectories had higher task-level mean gold-file precision in 11 tasks and lower
precision in only 3; 20 were tied. Gold-file recall was higher in 12 and lower in 3. Gold added-
line recall was higher in 18 tasks, lower in 3, and tied in 13. The median successful-minus-
failed difference in gold added-line recall was +0.0375.

This does not mean copying the developer patch is necessary. It means that outcome changes are
more consistently associated with selecting the correct implementation locus and mechanism than
with the nominal correctness label of the supplied hypothesis.

### 3. Passing self-selected tests is weak evidence of correctness

Many unresolved trajectories explicitly concluded that their tests passed. Examples include the
four failing non-Correct trajectories for `astropy__astropy-13033` and several failing variants
of `django__django-13794`. Their tests exercised the behavior the agent had implemented, but did
not sufficiently discriminate it from the benchmark's expected semantics. Conversely, some
resolved runs reported infrastructure or unrelated test failures.

The qualitative failure mode is therefore not simply “did not test.” It is often “tested a
locally coherent but semantically incomplete patch.” Evaluator outcome should remain the primary
correctness measure, while agent-run tests are evidence about validation effort rather than proof
of correctness.

### 4. Misleading hypotheses sometimes function as search perturbations

Nine tasks are resolved only under one or more misleading conditions. In these cases, the supplied
wrong hypothesis did not necessarily determine the final patch. The trajectory often continued
searching and arrived at a different implementation locus. For example:

- In `pylint-dev__pylint-7080`, Original, Correct, and Wrong Location all fail, whereas Wrong Cause
  and Wrong Repair succeed. The successful runs reach relevant discovery/filtering code and obtain
  better gold-file overlap; the failed runs can still report passing targeted tests.
- In `django__django-16454`, only Wrong Cause succeeds even though all conditions identify the
  subparser inheritance problem. The decisive difference is an implementation detail in how
  `CommandParser` state is propagated, not merely initial problem recognition.
- In `django__django-15022` and two Sphinx tasks, only Wrong Repair succeeds. With one repetition,
  this is evidence of beneficial execution branching, not evidence that a wrong repair is superior.

### 5. Wrong-repair hints can cause clear mislocalization

The three `11110` tasks provide the cleanest negative cases because all conditions except Wrong
Repair succeed:

- `django__django-17084`: successful runs modify `django/db/models/sql/query.py`, while Wrong Repair
  commits to `django/db/models/aggregates.py` and performs no benchmark-recognized test execution.
- `scikit-learn__scikit-learn-14629`: successful runs add the required behavior to
  `sklearn/multioutput.py`; Wrong Repair instead changes `sklearn/model_selection/_validation.py`.
- `sympy__sympy-13877`: the four successful runs modify `sympy/matrices/matrices.py`; Wrong Repair
  modifies `sympy/core/exprtools.py`.

These are direct examples of hypothesis-induced search displacement. They support a bounded claim
that a wrong repair can anchor the agent on the wrong subsystem. They do not establish an overall
anchoring rate because the same condition also rescues other tasks.

## Representative case studies

### `django__django-13794`: correct architectural localization

Only Correct succeeds. Original and all misleading conditions patch
`django/template/defaultfilters.py`, treating the symptom inside the `add` filter. The Correct
trajectory follows the supplied hypothesis to `django/utils/functional.py`, where it repairs lazy
proxy behavior. This is the clearest example of a correct hypothesis moving the agent from a
surface workaround to the underlying abstraction. Gold-file precision changes from 0 in Original
and all misleading conditions to 1 under Correct, and gold added-line recall changes from 0 to 1.

### `sympy__sympy-20428`: mechanism-level guidance

Only Correct succeeds. Original, Wrong Location, and Wrong Cause modify dense polynomial handling;
Wrong Repair modifies polynomial classes. Correct reaches
`sympy/polys/domains/expressiondomain.py` and changes zero recognition for expressions. Gold-file
precision and gold added-line recall are both 1 only in the Correct trajectory. This case shows a
correct hypothesis identifying the upstream semantic predicate rather than patching downstream
normalization symptoms.

### `astropy__astropy-13033`: same file, different semantics

All five runs edit `astropy/timeseries/core.py`, and all run targeted tests; only Correct succeeds.
The failure cannot be explained by file localization. The Correct patch changes the required-column
validation behavior more comprehensively, while the other runs implement alternative error-message
formats that satisfy their own reproductions. This demonstrates why gold-file overlap alone is
insufficient and why evaluator-sensitive semantic details matter.

### `astropy__astropy-7606`: correct location but unstable patch details

Original alone succeeds. Every condition edits `astropy/units/core.py`; Wrong Cause even reports a
passing unit suite. The outcome difference therefore reflects patch details or hidden-test coverage,
not gross mislocalization. It is a warning against attributing every flip to anchoring.

### `django__django-14765`: any structured hint avoids an underspecified shortcut

Original fails while all four hypothesis-bearing conditions succeed. Every run edits
`django/db/migrations/state.py`, but the Original patch simply removes conversion logic. The hinted
runs preserve or add an explicit input invariant. Here the value of the hint appears to be forcing
the agent to represent the intended precondition, even when the supplied hypothesis is misleading.

## Interpretation for the research questions

### RQ1

The 34 tasks explain why aggregate repair rates are nearly identical. Condition-specific gains and
losses cancel, and the sensitive subset itself has almost equal success counts across conditions.
Correct hypotheses are highly valuable in a small set of architectural or mechanism-localization
problems, but can also divert runs that Original solves. The principal aggregate benefit remains
efficiency, not a higher number of resolved tasks.

### RQ2

There is qualitative evidence of anchoring in the three `11110` cases because Wrong Repair alone
moves the final patch to a different, incorrect subsystem. However, the misleading-only success
cases show that a wrong initial hypothesis can be rejected or can perturb search beneficially.
Therefore, “received a wrong hypothesis” must not be equated with “remained anchored to it.”

### RQ3

The present traces contain examples suggestive of both persistence and recovery, but recovery cannot
be measured reliably without marking the first contradiction and the step at which the agent abandons
the hypothesis. The required adjudicated annotations remain necessary for confirmatory recovery rates
and recovery latency.

## Recommended coding scheme for final annotation

For each of the 102 misleading-condition trajectories in this subset, annotate:

1. whether the hypothesis is explicitly adopted before independent evidence;
2. first action consistent with the hypothesized location/cause/repair;
3. first contradictory observation;
4. whether the hypothesis is revised or abandoned;
5. whether the final patch remains in the hypothesized locus or mechanism;
6. whether a discriminating test is executed after revision;
7. contradiction and recovery steps.

Double-code at least the three `11110`, five `01000`, and nine misleading-rescue cases. These strata
contain the strongest evidence for harm, benefit, and recovery respectively and will provide a more
informative reliability assessment than an unstratified random sample alone.

## Limitations

- Only one run exists for each task-condition pair, so execution stochasticity is inseparable from
  treatment effects at the individual-task level.
- Agent-authored reasoning is a report of its process, not a complete record of latent belief.
- Agent-selected tests frequently fail to distinguish plausible but benchmark-incomplete patches.
- Missing `hypothesis_id` values prevent linking behavior to a particular hypothesis candidate.
- These findings are exploratory and should not replace the prespecified adjudicated RQ2/RQ3 analysis.

## Procedural reference

Kassis, T., Agarwal, V., He, Y., Patel, D., & Brueckner, A. M. (2026). Scientific Agent Skills:
A Library of Procedural Knowledge for Research Agents. arXiv:2609.00065.
https://doi.org/10.48550/arXiv.2609.00065
