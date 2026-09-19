import numpy as np

from fliiga_model.odds import (
    expected_value,
    expected_value_with_push,
    fractional_kelly,
    market_anchored_total_probabilities,
    market_anchored_two_way_probabilities,
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


def test_market_anchor_follows_reliability():
    market_over, _ = two_way_devig(1.75, 1.96)
    low_data_over, low_data_under = market_anchored_total_probabilities(
        0.83, 0.0, 1.75, 1.96, reliability=0.0
    )
    full_model_over, _ = market_anchored_total_probabilities(
        0.83, 0.0, 1.75, 1.96, reliability=1.0
    )
    assert np.isclose(low_data_over, market_over)
    assert np.isclose(low_data_over + low_data_under, 1.0)
    assert np.isclose(full_model_over, 0.83)


def test_generic_market_anchor_supports_handicap_push():
    first, second = market_anchored_two_way_probabilities(
        0.45, 0.10, 1.90, 1.90, reliability=0.0
    )
    assert np.isclose(first, 0.45)
    assert np.isclose(second, 0.45)
