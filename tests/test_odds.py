import numpy as np

from fliiga_model.odds import (
    expected_value,
    expected_value_with_push,
    fractional_kelly,
    proportional_devig,
    two_way_devig,
)


def test_devig_sums_to_one():
    probabilities = proportional_devig(1.80, 4.80, 3.60)
    assert np.isclose(sum(probabilities), 1.0)


def test_ev_and_kelly():
    assert np.isclose(expected_value(0.48, 2.25), 0.08)
    assert fractional_kelly(0.48, 2.25) > 0
    assert fractional_kelly(0.40, 2.25) == 0


def test_two_way_devig_and_push_ev():
    assert np.isclose(sum(two_way_devig(1.90, 1.90)), 1.0)
    assert np.isclose(expected_value_with_push(0.50, 0.10, 1.90), 0.05)
