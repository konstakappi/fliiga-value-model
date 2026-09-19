from __future__ import annotations

import math

import pandas as pd

from .model import PoissonStrengthModel
from .odds import (
    expected_value,
    expected_value_with_push,
    fair_odds,
    fair_odds_with_push,
    fractional_kelly,
    proportional_devig,
    two_way_devig,
)


def predict_fixtures(model: PoissonStrengthModel, fixtures: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for fixture in fixtures.itertuples(index=False):
        prediction = model.predict(fixture.home_team, fixture.away_team)
        probabilities = {
            "home": prediction.home_probability,
            "draw": prediction.draw_probability,
            "away": prediction.away_probability,
        }
        row: dict[str, object] = {
            "date": fixture.date,
            "home_team": fixture.home_team,
            "away_team": fixture.away_team,
            "expected_home_goals": prediction.expected_home_goals,
            "expected_away_goals": prediction.expected_away_goals,
            **{f"{side}_probability": value for side, value in probabilities.items()},
            **{f"{side}_fair_odds": fair_odds(value) for side, value in probabilities.items()},
        }

        odds = [getattr(fixture, f"{side}_odds", math.nan) for side in ("home", "draw", "away")]
        if all(pd.notna(value) for value in odds):
            market = proportional_devig(*odds)
            for side, price, market_probability in zip(("home", "draw", "away"), odds, market):
                row[f"{side}_odds"] = price
                row[f"{side}_market_probability"] = market_probability
                row[f"{side}_edge"] = probabilities[side] - market_probability
                row[f"{side}_ev"] = expected_value(probabilities[side], price)
                row[f"{side}_kelly_20pct"] = fractional_kelly(probabilities[side], price)

        total_line = getattr(fixture, "total_line", math.nan)
        total_odds = [getattr(fixture, f"{side}_odds", math.nan) for side in ("over", "under")]
        if pd.notna(total_line):
            total = model.predict_total(fixture.home_team, fixture.away_team, float(total_line))
            total_probabilities = {
                "over": total.over_probability,
                "under": total.under_probability,
            }
            row.update(
                {
                    "total_line": total.line,
                    "expected_total_goals": total.expected_total_goals,
                    "total_dispersion": total.dispersion,
                    "over_probability": total.over_probability,
                    "push_probability": total.push_probability,
                    "under_probability": total.under_probability,
                    "over_fair_odds": fair_odds_with_push(
                        total.over_probability, total.push_probability
                    ),
                    "under_fair_odds": fair_odds_with_push(
                        total.under_probability, total.push_probability
                    ),
                }
            )
            if all(pd.notna(value) for value in total_odds):
                market = two_way_devig(*total_odds)
                non_push = max(1e-15, 1.0 - total.push_probability)
                for side, price, market_probability in zip(
                    ("over", "under"), total_odds, market
                ):
                    conditional_model_probability = total_probabilities[side] / non_push
                    row[f"{side}_odds"] = price
                    row[f"{side}_market_probability"] = market_probability
                    row[f"{side}_edge"] = conditional_model_probability - market_probability
                    row[f"{side}_ev"] = expected_value_with_push(
                        total_probabilities[side], total.push_probability, price
                    )
        rows.append(row)
    return pd.DataFrame(rows)
