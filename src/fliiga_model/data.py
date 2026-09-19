from __future__ import annotations

from pathlib import Path

import pandas as pd

GAME_COLUMNS = {"date", "home_team", "away_team", "home_goals", "away_goals"}
FIXTURE_COLUMNS = {"date", "home_team", "away_team"}
ODDS_COLUMNS = {"home_odds", "draw_odds", "away_odds"}
TOTALS_COLUMNS = {"total_line", "over_odds", "under_odds"}


def _read_csv(source: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(source)
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    if "date" in frame:
        frame["date"] = pd.to_datetime(frame["date"], errors="raise", utc=True).dt.tz_localize(None)
    return frame


def load_games(source: str | Path) -> pd.DataFrame:
    frame = _read_csv(source)
    missing = GAME_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Games CSV is missing columns: {sorted(missing)}")

    frame = frame.dropna(subset=list(GAME_COLUMNS)).copy()
    frame["home_goals"] = pd.to_numeric(frame["home_goals"], errors="raise").astype(int)
    frame["away_goals"] = pd.to_numeric(frame["away_goals"], errors="raise").astype(int)
    if (frame[["home_goals", "away_goals"]] < 0).any().any():
        raise ValueError("Goals cannot be negative")
    if (frame["home_team"] == frame["away_team"]).any():
        raise ValueError("A team cannot play against itself")
    return frame.sort_values("date").reset_index(drop=True)


def load_fixtures(source: str | Path) -> pd.DataFrame:
    frame = _read_csv(source)
    missing = FIXTURE_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Fixtures CSV is missing columns: {sorted(missing)}")
    if (frame["home_team"] == frame["away_team"]).any():
        raise ValueError("A team cannot play against itself")
    for column in (ODDS_COLUMNS | TOTALS_COLUMNS) & set(frame.columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values("date").reset_index(drop=True)
