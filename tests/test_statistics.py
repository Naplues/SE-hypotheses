import pytest

from rfm.statistics import (
    exact_mcnemar,
    holm_adjust,
    wilcoxon_signed_rank,
    wilson_interval,
)


def test_exact_mcnemar_tracks_direction() -> None:
    result = exact_mcnemar([True, True, True, False], [False, False, True, False])
    assert result["left_only"] == 2
    assert result["right_only"] == 0
    assert result["p_value"] == pytest.approx(0.5)


def test_wilcoxon_and_holm() -> None:
    result = wilcoxon_signed_rank([1, 2, 3, 4], [2, 3, 4, 5])
    assert result["rank_biserial"] == pytest.approx(1.0)
    adjusted = holm_adjust([0.01, 0.04, 0.03])
    assert adjusted == pytest.approx([0.03, 0.06, 0.06])


def test_wilson_interval() -> None:
    low, high = wilson_interval(5, 10)
    assert low < 0.5 < high
