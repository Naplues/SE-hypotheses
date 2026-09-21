from __future__ import annotations

import math
import random
from collections import Counter
from collections.abc import Iterable, Sequence


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    size = len(ordered)
    if size == 0:
        return float("nan")
    midpoint = size // 2
    if size % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def wilson_interval(
    successes: int, total: int, z: float = 1.959963984540054
) -> tuple[float, float]:
    if total == 0:
        return (float("nan"), float("nan"))
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    spread = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return (max(0.0, center - spread), min(1.0, center + spread))


def exact_mcnemar(left: Sequence[bool], right: Sequence[bool]) -> dict[str, float | int]:
    if len(left) != len(right):
        raise ValueError("Paired samples must have equal length")
    b = sum(a and not c for a, c in zip(left, right, strict=True))
    c = sum(not a and c for a, c in zip(left, right, strict=True))
    discordant = b + c
    if discordant == 0:
        p_value = 1.0
    else:
        tail = sum(math.comb(discordant, index) for index in range(min(b, c) + 1)) / (2**discordant)
        p_value = min(1.0, 2 * tail)
    return {"n": len(left), "left_only": b, "right_only": c, "p_value": p_value}


def paired_risk_difference(
    left: Sequence[bool],
    right: Sequence[bool],
    seed: int = 0,
    bootstrap_samples: int = 5000,
) -> dict[str, float]:
    if len(left) != len(right) or not left:
        raise ValueError("Paired risk difference requires non-empty equal-length samples")
    differences = [float(b) - float(a) for a, b in zip(left, right, strict=True)]
    rng = random.Random(seed)
    estimates = []
    for _ in range(bootstrap_samples):
        estimates.append(mean([differences[rng.randrange(len(differences))] for _ in differences]))
    estimates.sort()
    low = estimates[int(0.025 * (bootstrap_samples - 1))]
    high = estimates[int(0.975 * (bootstrap_samples - 1))]
    return {"estimate": mean(differences), "ci95_low": low, "ci95_high": high}


def average_ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        rank = ((cursor + 1) + end) / 2
        for index in range(cursor, end):
            ranks[indexed[index][0]] = rank
        cursor = end
    return ranks


def wilcoxon_signed_rank(left: Sequence[float], right: Sequence[float]) -> dict[str, float | int]:
    if len(left) != len(right):
        raise ValueError("Paired samples must have equal length")
    differences = [b - a for a, b in zip(left, right, strict=True) if b != a]
    if not differences:
        return {
            "n": 0,
            "w_plus": 0.0,
            "w_minus": 0.0,
            "z": 0.0,
            "p_value": 1.0,
            "rank_biserial": 0.0,
        }
    absolute = [abs(value) for value in differences]
    ranks = average_ranks(absolute)
    w_plus = sum(
        rank for rank, difference in zip(ranks, differences, strict=True) if difference > 0
    )
    w_minus = sum(
        rank for rank, difference in zip(ranks, differences, strict=True) if difference < 0
    )
    n = len(differences)
    expected = n * (n + 1) / 4
    tie_counts = Counter(absolute)
    tie_correction = sum(count**3 - count for count in tie_counts.values()) / 48
    variance = n * (n + 1) * (2 * n + 1) / 24 - tie_correction
    if variance <= 0:
        z = 0.0
        p_value = 1.0
    else:
        correction = 0.5 if w_plus > expected else (-0.5 if w_plus < expected else 0.0)
        z = (w_plus - expected - correction) / math.sqrt(variance)
        p_value = math.erfc(abs(z) / math.sqrt(2))
    total_rank = w_plus + w_minus
    effect = (w_plus - w_minus) / total_rank if total_rank else 0.0
    return {
        "n": n,
        "w_plus": w_plus,
        "w_minus": w_minus,
        "z": z,
        "p_value": p_value,
        "rank_biserial": effect,
    }


def holm_adjust(p_values: Iterable[float]) -> list[float]:
    values = list(p_values)
    order = sorted(range(len(values)), key=values.__getitem__)
    adjusted = [0.0] * len(values)
    running = 0.0
    size = len(values)
    for position, index in enumerate(order):
        candidate = min(1.0, (size - position) * values[index])
        running = max(running, candidate)
        adjusted[index] = running
    return adjusted
