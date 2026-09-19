from __future__ import annotations

import math


def fair_odds(probability: float) -> float:
    return math.inf if probability <= 0 else 1.0 / probability


def proportional_devig(home: float, draw: float, away: float) -> tuple[float, float, float]:
    odds = (home, draw, away)
    if any(not math.isfinite(value) or value <= 1.0 for value in odds):
        raise ValueError("Decimal odds must be finite and greater than 1.0")
    inverse = [1.0 / value for value in odds]
    total = sum(inverse)
    return tuple(value / total for value in inverse)  # type: ignore[return-value]


def two_way_devig(first: float, second: float) -> tuple[float, float]:
    if any(not math.isfinite(value) or value <= 1.0 for value in (first, second)):
        raise ValueError("Decimal odds must be finite and greater than 1.0")
    inverse = (1.0 / first, 1.0 / second)
    total = sum(inverse)
    return inverse[0] / total, inverse[1] / total


def market_anchored_total_probabilities(
    model_over: float,
    push_probability: float,
    over_odds: float,
    under_odds: float,
    reliability: float,
) -> tuple[float, float]:
    """Blend a totals model with the no-vig market when team data is sparse."""
    return market_anchored_two_way_probabilities(
        model_over,
        push_probability,
        over_odds,
        under_odds,
        reliability,
    )


def market_anchored_two_way_probabilities(
    model_first: float,
    push_probability: float,
    first_odds: float,
    second_odds: float,
    reliability: float,
) -> tuple[float, float]:
    """Blend any two-way model with the no-vig market when data is sparse."""
    if not 0 <= reliability <= 1:
        raise ValueError("Reliability must be between 0 and 1")
    if not 0 <= push_probability < 1:
        raise ValueError("Push probability must be between 0 and 1")
    non_push = 1.0 - push_probability
    if not 0 <= model_first <= non_push:
        raise ValueError("Model probability is inconsistent with push probability")
    market_first, _ = two_way_devig(first_odds, second_odds)
    model_first_conditional = model_first / non_push
    blended_first_conditional = (
        reliability * model_first_conditional + (1.0 - reliability) * market_first
    )
    first = blended_first_conditional * non_push
    second = (1.0 - blended_first_conditional) * non_push
    return first, second


def expected_value(probability: float, decimal_odds: float) -> float:
    return probability * decimal_odds - 1.0


def expected_value_with_push(
    win_probability: float, push_probability: float, decimal_odds: float
) -> float:
    loss_probability = max(0.0, 1.0 - win_probability - push_probability)
    return win_probability * (decimal_odds - 1.0) - loss_probability


def fair_odds_with_push(win_probability: float, push_probability: float) -> float:
    return math.inf if win_probability <= 0 else (1.0 - push_probability) / win_probability


def fractional_kelly(probability: float, decimal_odds: float, fraction: float = 0.20) -> float:
    if not 0 <= fraction <= 1:
        raise ValueError("Kelly fraction must be between 0 and 1")
    edge = decimal_odds * probability - 1.0
    full_kelly = edge / (decimal_odds - 1.0)
    return max(0.0, full_kelly * fraction)
