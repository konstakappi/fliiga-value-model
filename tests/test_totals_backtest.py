import numpy as np
import pandas as pd

from fliiga_model.backtest import totals_odds_backtest


def test_totals_backtest_selects_one_best_offer_per_match():
    teams = ["Alpha", "Beta", "Gamma", "Delta"]
    rows = []
    date = pd.Timestamp("2025-01-01")
    for _ in range(6):
        for home in teams:
            for away in teams:
                if home != away:
                    rows.append({
                        "date": date, "home_team": home, "away_team": away,
                        "home_goals": 7, "away_goals": 5,
                    })
                    date += pd.Timedelta(days=1)
    games = pd.DataFrame(rows)
    target = games.iloc[-1]
    odds = pd.DataFrame([
        {
            "collected_at": target.date - pd.Timedelta(hours=2), "bookmaker": "Book A",
            "event_start": target.date, "home_team": target.home_team,
            "away_team": target.away_team, "total_line": 9.5, "side": "over",
            "decimal_odds": 2.20,
        },
        {
            "collected_at": target.date - pd.Timedelta(hours=2), "bookmaker": "Book A",
            "event_start": target.date, "home_team": target.home_team,
            "away_team": target.away_team, "total_line": 9.5, "side": "under",
            "decimal_odds": 1.70,
        },
        {
            "collected_at": target.date - pd.Timedelta(hours=2), "bookmaker": "Book B",
            "event_start": target.date, "home_team": target.home_team,
            "away_team": target.away_team, "total_line": 9.5, "side": "over",
            "decimal_odds": 2.30,
        },
        {
            "collected_at": target.date - pd.Timedelta(hours=2), "bookmaker": "Book B",
            "event_start": target.date, "home_team": target.home_team,
            "away_team": target.away_team, "total_line": 9.5, "side": "under",
            "decimal_odds": 1.65,
        },
    ])
    results, metrics = totals_odds_backtest(
        games, odds, min_train_games=20, retrain_every=1, min_ev=-1
    )
    assert len(results) == 1
    assert results.iloc[0]["bookmaker"] == "Book B"
    assert results.iloc[0]["result"] == "win"
    assert np.isclose(metrics["flat_stake_profit"], 1.30)
