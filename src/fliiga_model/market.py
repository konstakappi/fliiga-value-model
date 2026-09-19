from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

import pandas as pd

from .data import load_fixtures, load_games
from .model import PoissonStrengthModel
from .odds import expected_value_with_push, fair_odds_with_push

ODDS_COLUMNS = {
    "bookmaker",
    "event_start",
    "home_team",
    "away_team",
    "total_line",
    "side",
    "decimal_odds",
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def normalize_team(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    key = re.sub(r"[^a-z0-9]", "", text.casefold())
    aliases = {
        "esportoilers": "oilers",
        "westendindians": "indians",
        "scclassic": "classic",
        "spvseinajoki": "spv",
        "seinajoenpeliveljet": "spv",
        "tpssalibandy": "tps",
        "turkups": "tps",
    }
    return aliases.get(key, key)


class OddsDatabase:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE IF NOT EXISTS odds_snapshots (
                id INTEGER PRIMARY KEY,
                collected_at TEXT NOT NULL,
                bookmaker TEXT NOT NULL,
                event_id TEXT,
                event_start TEXT NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                home_key TEXT NOT NULL,
                away_key TEXT NOT NULL,
                market TEXT NOT NULL DEFAULT 'totals',
                total_line REAL NOT NULL,
                side TEXT NOT NULL CHECK (side IN ('over', 'under')),
                decimal_odds REAL NOT NULL CHECK (decimal_odds > 1.0),
                source_url TEXT,
                UNIQUE(collected_at, bookmaker, event_start, home_key, away_key,
                       market, total_line, side)
            );
            CREATE INDEX IF NOT EXISTS ix_odds_event
                ON odds_snapshots(home_key, away_key, event_start, total_line, side);
            CREATE TABLE IF NOT EXISTS bets (
                id INTEGER PRIMARY KEY,
                placed_at TEXT NOT NULL,
                bookmaker TEXT NOT NULL,
                event_start TEXT NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                home_key TEXT NOT NULL,
                away_key TEXT NOT NULL,
                market TEXT NOT NULL DEFAULT 'totals',
                total_line REAL NOT NULL,
                side TEXT NOT NULL CHECK (side IN ('over', 'under')),
                decimal_odds REAL NOT NULL CHECK (decimal_odds > 1.0),
                stake REAL NOT NULL CHECK (stake > 0),
                note TEXT
            );
            """
        )
        self.connection.commit()

    def import_csv(self, source: str | Path, collected_at: str | None = None) -> int:
        frame = pd.read_csv(source)
        frame.columns = [str(column).strip().lower() for column in frame.columns]
        missing = ODDS_COLUMNS - set(frame.columns)
        if missing:
            raise ValueError(f"Odds CSV is missing columns: {sorted(missing)}")
        default_timestamp = collected_at or utc_now()
        inserted = 0
        for row in frame.to_dict("records"):
            side = str(row["side"]).strip().lower()
            odds = float(row["decimal_odds"])
            line = float(row["total_line"])
            if side not in {"over", "under"}:
                raise ValueError("side must be 'over' or 'under'")
            if odds <= 1 or line < 0:
                raise ValueError("decimal_odds must exceed 1 and total_line cannot be negative")
            timestamp = _iso(row.get("collected_at") or default_timestamp)
            values = (
                timestamp,
                str(row["bookmaker"]).strip(),
                _optional(row.get("event_id")),
                _iso(row["event_start"]),
                str(row["home_team"]).strip(),
                str(row["away_team"]).strip(),
                normalize_team(row["home_team"]),
                normalize_team(row["away_team"]),
                line,
                side,
                odds,
                _optional(row.get("source_url")),
            )
            cursor = self.connection.execute(
                """
                INSERT OR IGNORE INTO odds_snapshots
                (collected_at, bookmaker, event_id, event_start, home_team, away_team,
                 home_key, away_key, total_line, side, decimal_odds, source_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
            inserted += cursor.rowcount
        self.connection.commit()
        return inserted

    def snapshots(self) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM odds_snapshots ORDER BY collected_at", self.connection)

    def record_bet(
        self,
        *,
        bookmaker: str,
        event_start: str,
        home_team: str,
        away_team: str,
        total_line: float,
        side: str,
        decimal_odds: float,
        stake: float,
        placed_at: str | None = None,
        note: str = "",
    ) -> int:
        side = side.lower()
        if side not in {"over", "under"} or decimal_odds <= 1 or stake <= 0:
            raise ValueError("Invalid bet values")
        cursor = self.connection.execute(
            """
            INSERT INTO bets
            (placed_at, bookmaker, event_start, home_team, away_team, home_key, away_key,
             total_line, side, decimal_odds, stake, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _iso(placed_at or utc_now()), bookmaker, _iso(event_start), home_team, away_team,
                normalize_team(home_team), normalize_team(away_team), float(total_line), side,
                float(decimal_odds), float(stake), note,
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def clv_report(self) -> pd.DataFrame:
        query = """
        SELECT b.*, o.decimal_odds AS closing_odds, o.collected_at AS closing_collected_at
        FROM bets b
        LEFT JOIN odds_snapshots o ON o.id = (
            SELECT o2.id FROM odds_snapshots o2
            WHERE o2.bookmaker = b.bookmaker
              AND o2.home_key = b.home_key AND o2.away_key = b.away_key
              AND o2.event_start = b.event_start AND o2.market = b.market
              AND o2.total_line = b.total_line AND o2.side = b.side
              AND o2.collected_at <= b.event_start
            ORDER BY o2.collected_at DESC LIMIT 1
        )
        ORDER BY b.event_start DESC, b.id DESC
        """
        frame = pd.read_sql_query(query, self.connection)
        if frame.empty:
            return frame
        frame["clv"] = frame["decimal_odds"] / frame["closing_odds"] - 1.0
        return frame


def build_value_report(
    database: OddsDatabase,
    games_path: str | Path,
    fixtures_path: str | Path,
    *,
    min_ev: float = 0.0,
    half_life: float = 120.0,
    l2: float = 1.0,
    now: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    games = load_games(games_path)
    fixtures = load_fixtures(fixtures_path).copy()
    fixtures["home_key"] = fixtures["home_team"].map(normalize_team)
    fixtures["away_key"] = fixtures["away_team"].map(normalize_team)
    fixtures["date"] = pd.to_datetime(fixtures["date"])
    cutoff = pd.Timestamp(now or datetime.now(UTC)).tz_localize(None)
    fixtures = fixtures[fixtures["date"] >= cutoff - pd.Timedelta(hours=4)]

    odds = database.snapshots()
    columns = [
        "event_start", "home_team", "away_team", "bookmaker", "total_line", "side",
        "decimal_odds", "model_probability", "push_probability", "fair_odds", "ev",
        "kelly_20pct", "collected_at", "source_url",
    ]
    if odds.empty or fixtures.empty:
        return pd.DataFrame(columns=columns)
    odds["event_start_dt"] = pd.to_datetime(odds["event_start"], utc=True).dt.tz_localize(None)
    odds["collected_dt"] = pd.to_datetime(odds["collected_at"], utc=True).dt.tz_localize(None)

    # Only the newest observation of each offered price is actionable.
    keys = ["bookmaker", "home_key", "away_key", "event_start", "total_line", "side"]
    odds = odds.sort_values("collected_dt").drop_duplicates(keys, keep="last")
    joined = odds.merge(fixtures, on=["home_key", "away_key"], suffixes=("", "_fixture"))
    joined = joined[
        (joined["event_start_dt"] - joined["date"]).abs() <= pd.Timedelta(hours=6)
    ].copy()
    if joined.empty:
        return pd.DataFrame(columns=columns)

    model = PoissonStrengthModel(half_life_days=half_life, l2=l2).fit(games)
    results: list[dict[str, object]] = []
    for row in joined.itertuples(index=False):
        total = model.predict_total(row.home_team_fixture, row.away_team_fixture, row.total_line)
        probability = total.over_probability if row.side == "over" else total.under_probability
        ev = expected_value_with_push(probability, total.push_probability, row.decimal_odds)
        full_kelly = max(0.0, ev / max(row.decimal_odds - 1.0, 1e-12))
        results.append(
            {
                "event_start": row.event_start,
                "home_team": row.home_team_fixture,
                "away_team": row.away_team_fixture,
                "bookmaker": row.bookmaker,
                "total_line": row.total_line,
                "side": row.side,
                "decimal_odds": row.decimal_odds,
                "model_probability": probability,
                "push_probability": total.push_probability,
                "fair_odds": fair_odds_with_push(probability, total.push_probability),
                "ev": ev,
                "kelly_20pct": 0.20 * full_kelly,
                "collected_at": row.collected_at,
                "source_url": row.source_url,
            }
        )
    report = pd.DataFrame(results)
    best_keys = ["event_start", "home_team", "away_team", "total_line", "side"]
    report = report.sort_values("decimal_odds", ascending=False).drop_duplicates(best_keys)
    report = report[report["ev"] >= min_ev]
    return report.sort_values(["ev", "event_start"], ascending=[False, True]).reset_index(drop=True)


def _iso(value: object) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("Europe/Helsinki")
    return timestamp.tz_convert("UTC").isoformat()


def _optional(value: object) -> str | None:
    return None if value is None or pd.isna(value) or str(value).strip() == "" else str(value)
