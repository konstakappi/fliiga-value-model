import numpy as np
import pandas as pd

from fliiga_model.model import PoissonStrengthModel


def synthetic_games() -> pd.DataFrame:
    teams = ["Alpha", "Beta", "Gamma", "Delta"]
    rows = []
    date = pd.Timestamp("2025-01-01")
    for round_number in range(6):
        for home_index, home in enumerate(teams):
            for away_index, away in enumerate(teams):
                if home == away:
                    continue
                rows.append(
                    {
                        "date": date,
                        "home_team": home,
                        "away_team": away,
                        "home_goals": 7 + (home_index < away_index),
                        "away_goals": 5 + (away_index == 0),
                    }
                )
                date += pd.Timedelta(days=1)
    return pd.DataFrame(rows)


def test_probabilities_sum_to_one():
    model = PoissonStrengthModel().fit(synthetic_games())
    prediction = model.predict("Alpha", "Beta")
    total = prediction.home_probability + prediction.draw_probability + prediction.away_probability
    assert np.isclose(total, 1.0)
    assert prediction.expected_home_goals > 0
    assert prediction.expected_away_goals > 0


def test_unknown_team_is_rejected():
    model = PoissonStrengthModel().fit(synthetic_games())
    try:
        model.predict("Alpha", "Unknown")
    except ValueError as error:
        assert "Unknown teams" in str(error)
    else:
        raise AssertionError("Unknown team should have raised ValueError")


def test_total_probabilities_sum_to_one():
    model = PoissonStrengthModel().fit(synthetic_games())
    prediction = model.predict_total("Alpha", "Beta", 12.5)
    assert np.isclose(
        prediction.over_probability
        + prediction.push_probability
        + prediction.under_probability,
        1.0,
    )
    assert prediction.push_probability == 0


def test_integer_total_has_push_probability():
    model = PoissonStrengthModel().fit(synthetic_games())
    prediction = model.predict_total("Alpha", "Beta", 12.0)
    assert prediction.push_probability > 0


def test_match_reliability_is_bounded_and_uses_effective_games():
    games = synthetic_games()
    model = PoissonStrengthModel(half_life_days=30).fit(games)
    reliability = model.match_reliability("Alpha", "Beta")
    assert 0 < reliability < 1
    assert model.team_effective_games_["Alpha"] > 0


def test_half_goal_handicap_probabilities_sum_to_one_without_push():
    model = PoissonStrengthModel().fit(synthetic_games())
    prediction = model.predict_handicap("Alpha", "Beta", -1.5)
    assert np.isclose(
        prediction.home_cover_probability + prediction.away_cover_probability, 1.0
    )
    assert prediction.push_probability == 0


def test_integer_handicap_has_push_probability():
    model = PoissonStrengthModel().fit(synthetic_games())
    prediction = model.predict_handicap("Alpha", "Beta", -1.0)
    assert prediction.push_probability > 0
    assert np.isclose(
        prediction.home_cover_probability
        + prediction.push_probability
        + prediction.away_cover_probability,
        1.0,
    )
