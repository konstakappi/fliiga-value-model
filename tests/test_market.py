import sqlite3

import numpy as np
import pandas as pd

from fliiga_model.market import OddsDatabase, normalize_team


def test_normalize_team_handles_punctuation_and_accents():
    assert normalize_team("O2-Jyväskylä") == "o2jyvaskyla"
    assert normalize_team("SPV Seinäjoki") == "spv"
    assert normalize_team("Westend Indians") == "indians"


def test_import_is_timestamped_and_idempotent(tmp_path):
    source = tmp_path / "odds.csv"
    pd.DataFrame([
        {
            "bookmaker": "Book A", "event_start": "2027-01-01 18:00",
            "home_team": "Classic", "away_team": "Oilers", "total_line": 10.5,
            "side": "over", "decimal_odds": 1.95,
        }
    ]).to_csv(source, index=False)
    with OddsDatabase(tmp_path / "odds.db") as database:
        assert database.import_csv(source, "2026-12-31T12:00:00+00:00") == 1
        assert database.import_csv(source, "2026-12-31T12:00:00+00:00") == 0
        assert len(database.snapshots()) == 1


def test_clv_uses_last_quote_before_start(tmp_path):
    database_path = tmp_path / "odds.db"
    source = tmp_path / "odds.csv"
    pd.DataFrame([
        {
            "collected_at": "2026-12-31T17:30:00+00:00", "bookmaker": "Book A",
            "event_start": "2026-12-31T18:00:00+00:00", "home_team": "Classic",
            "away_team": "Oilers", "total_line": 10.5, "side": "over",
            "decimal_odds": 1.80,
        },
        {
            "collected_at": "2026-12-31T18:05:00+00:00", "bookmaker": "Book A",
            "event_start": "2026-12-31T18:00:00+00:00", "home_team": "Classic",
            "away_team": "Oilers", "total_line": 10.5, "side": "over",
            "decimal_odds": 1.70,
        },
    ]).to_csv(source, index=False)
    with OddsDatabase(database_path) as database:
        database.import_csv(source)
        database.record_bet(
            bookmaker="Book A", event_start="2026-12-31T18:00:00+00:00",
            home_team="Classic", away_team="Oilers", total_line=10.5, side="over",
            decimal_odds=2.0, stake=10, placed_at="2026-12-31T12:00:00+00:00",
        )
        report = database.clv_report()
    assert np.isclose(report.iloc[0]["closing_odds"], 1.80)
    assert np.isclose(report.iloc[0]["clv"], 2.0 / 1.8 - 1)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 1
