from __future__ import annotations

import numpy as np
import pandas as pd

from .market import ODDS_COLUMNS, normalize_team
from .model import PoissonStrengthModel
from .odds import expected_value, expected_value_with_push


def walk_forward_backtest(
    games: pd.DataFrame,
    min_train_games: int = 60,
    retrain_every: int = 10,
    half_life_days: float = 120.0,
    l2: float = 1.0,
) -> tuple[pd.DataFrame, dict[str, float]]:
    data = games.sort_values("date").reset_index(drop=True).copy()
    if len(data) <= min_train_games:
        raise ValueError("Not enough games for the requested backtest")

    rows: list[dict[str, object]] = []
    model: PoissonStrengthModel | None = None
    for index in range(min_train_games, len(data)):
        test = data.iloc[index]
        if model is None or (index - min_train_games) % retrain_every == 0:
            training = data.iloc[:index]
            model = PoissonStrengthModel(half_life_days=half_life_days, l2=l2).fit(
                training, as_of=training["date"].max()
            )
        if test.home_team not in model.team_index or test.away_team not in model.team_index:
            continue
        prediction = model.predict(test.home_team, test.away_team)
        expected_total = prediction.expected_home_goals + prediction.expected_away_goals
        observed_total = float(test.home_goals + test.away_goals)
        probabilities = np.array(
            [prediction.home_probability, prediction.draw_probability, prediction.away_probability]
        )
        outcome = 0 if test.home_goals > test.away_goals else 1 if test.home_goals == test.away_goals else 2
        one_hot = np.eye(3)[outcome]
        row: dict[str, object] = {
            "date": test.date,
            "home_team": test.home_team,
            "away_team": test.away_team,
            "home_goals": test.home_goals,
            "away_goals": test.away_goals,
            "home_probability": probabilities[0],
            "draw_probability": probabilities[1],
            "away_probability": probabilities[2],
            "log_loss": -np.log(max(probabilities[outcome], 1e-15)),
            "brier_score": np.square(probabilities - one_hot).sum(),
            "expected_total_goals": expected_total,
            "observed_total_goals": observed_total,
            "total_absolute_error": abs(observed_total - expected_total),
            "total_squared_error": (observed_total - expected_total) ** 2,
            "naive_expected_total": float(
                (data.iloc[:index]["home_goals"] + data.iloc[:index]["away_goals"]).mean()
            ),
        }
        if {"home_odds", "draw_odds", "away_odds"} <= set(data.columns):
            sides = ("home", "draw", "away")
            odds = [test[f"{side}_odds"] for side in sides]
            if all(pd.notna(value) for value in odds):
                evs = [expected_value(probability, price) for probability, price in zip(probabilities, odds)]
                best = int(np.argmax(evs))
                row.update(
                    {
                        "best_side": sides[best],
                        "best_odds": odds[best],
                        "best_ev": evs[best],
                        "best_won": float(best == outcome),
                    }
                )
        rows.append(row)

    results = pd.DataFrame(rows)
    metrics = {
        "matches": float(len(results)),
        "log_loss": float(results["log_loss"].mean()),
        "brier_score": float(results["brier_score"].mean()),
        "total_mae": float(results["total_absolute_error"].mean()),
        "total_rmse": float(np.sqrt(results["total_squared_error"].mean())),
    }
    naive_error = results["observed_total_goals"] - results["naive_expected_total"]
    metrics["naive_total_mae"] = float(naive_error.abs().mean())
    metrics["naive_total_rmse"] = float(np.sqrt(np.square(naive_error).mean()))
    metrics["mae_improvement_vs_naive_pct"] = float(
        100 * (metrics["naive_total_mae"] - metrics["total_mae"])
        / metrics["naive_total_mae"]
    )
    if "best_ev" in results:
        bets = results[results["best_ev"] >= 0.05].copy()
        profits = np.where(bets["best_won"] == 1, bets["best_odds"] - 1, -1)
        metrics["bets_at_5pct_ev"] = float(len(bets))
        metrics["flat_stake_roi"] = float(profits.mean()) if len(bets) else float("nan")
    return results, metrics


def totals_odds_backtest(
    games: pd.DataFrame,
    odds: pd.DataFrame,
    *,
    min_train_games: int = 250,
    retrain_every: int = 25,
    half_life_days: float = 120.0,
    l2: float = 1.0,
    min_ev: float = 0.05,
    bookmaker: str | None = None,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Backtest one best totals selection per match using pre-match odds snapshots."""
    missing = ODDS_COLUMNS - set(odds.columns)
    if missing:
        raise ValueError(f"Odds data is missing columns: {sorted(missing)}")

    history = games.sort_values("date").reset_index(drop=True).copy()
    history["home_key"] = history["home_team"].map(normalize_team)
    history["away_key"] = history["away_team"].map(normalize_team)
    history["date"] = pd.to_datetime(history["date"], utc=True).dt.tz_localize(None)

    quotes = odds.copy()
    quotes.columns = [str(column).strip().lower() for column in quotes.columns]
    quotes["home_key"] = quotes["home_team"].map(normalize_team)
    quotes["away_key"] = quotes["away_team"].map(normalize_team)
    quotes["event_dt"] = pd.to_datetime(quotes["event_start"], utc=True).dt.tz_localize(None)
    quotes["collected_dt"] = pd.to_datetime(
        quotes.get("collected_at", quotes["event_start"]), utc=True
    ).dt.tz_localize(None)
    quotes["side"] = quotes["side"].astype(str).str.lower()
    quotes["total_line"] = pd.to_numeric(quotes["total_line"], errors="raise")
    quotes["decimal_odds"] = pd.to_numeric(quotes["decimal_odds"], errors="raise")
    if bookmaker:
        quotes = quotes[quotes["bookmaker"].str.casefold() == bookmaker.casefold()]
    quotes = quotes[
        quotes["side"].isin(["over", "under"])
        & (quotes["decimal_odds"] > 1)
        & (quotes["collected_dt"] <= quotes["event_dt"])
    ].copy()

    # Use the last available quote for each book/line/side, then select at most one bet per match.
    quote_keys = [
        "bookmaker", "event_dt", "home_key", "away_key", "total_line", "side"
    ]
    quotes = quotes.sort_values("collected_dt").drop_duplicates(quote_keys, keep="last")
    event_keys = ["event_dt", "home_key", "away_key"]

    rows: list[dict[str, object]] = []
    model: PoissonStrengthModel | None = None
    last_training_size = -1
    for event_number, (event_key, offers) in enumerate(quotes.groupby(event_keys, sort=True)):
        event_dt, home_key, away_key = event_key
        candidates = history[
            (history["home_key"] == home_key)
            & (history["away_key"] == away_key)
            & ((history["date"] - event_dt).abs() <= pd.Timedelta(hours=8))
        ]
        if candidates.empty:
            continue
        game = candidates.iloc[(candidates["date"] - event_dt).abs().argmin()]
        training = history[history["date"] < event_dt]
        if len(training) < min_train_games:
            continue
        if (
            model is None
            or event_number % retrain_every == 0
            or len(training) < last_training_size
        ):
            model = PoissonStrengthModel(half_life_days=half_life_days, l2=l2).fit(
                training.drop(columns=["home_key", "away_key"]),
                as_of=training["date"].max(),
            )
            last_training_size = len(training)
        if game.home_team not in model.team_index or game.away_team not in model.team_index:
            continue

        evaluated: list[dict[str, object]] = []
        for offer in offers.itertuples(index=False):
            total = model.predict_total(game.home_team, game.away_team, offer.total_line)
            probability = (
                total.over_probability if offer.side == "over" else total.under_probability
            )
            ev = expected_value_with_push(
                probability, total.push_probability, offer.decimal_odds
            )
            evaluated.append(
                {
                    "date": game.date,
                    "home_team": game.home_team,
                    "away_team": game.away_team,
                    "home_goals": int(game.home_goals),
                    "away_goals": int(game.away_goals),
                    "bookmaker": offer.bookmaker,
                    "total_line": float(offer.total_line),
                    "side": offer.side,
                    "decimal_odds": float(offer.decimal_odds),
                    "model_probability": probability,
                    "push_probability": total.push_probability,
                    "expected_total_goals": total.expected_total_goals,
                    "ev": ev,
                    "collected_at": offer.collected_at
                    if hasattr(offer, "collected_at") else None,
                }
            )
        if not evaluated:
            continue
        best = max(evaluated, key=lambda row: float(row["ev"]))
        if float(best["ev"]) < min_ev:
            continue
        observed = int(game.home_goals + game.away_goals)
        line = float(best["total_line"])
        side = str(best["side"])
        is_push = np.isclose(observed, line)
        won = observed > line if side == "over" else observed < line
        best["result"] = "push" if is_push else "win" if won else "loss"
        best["profit"] = 0.0 if is_push else float(best["decimal_odds"]) - 1 if won else -1.0
        rows.append(best)

    results = pd.DataFrame(rows)
    metrics = {
        "bets": float(len(results)),
        "flat_stake_profit": float(results["profit"].sum()) if len(results) else 0.0,
        "flat_stake_roi": float(results["profit"].mean()) if len(results) else float("nan"),
        "average_model_ev": float(results["ev"].mean()) if len(results) else float("nan"),
        "win_rate_excluding_pushes": float(
            (results["result"] == "win").sum()
            / max(1, (results["result"] != "push").sum())
        ) if len(results) else float("nan"),
    }
    return results, metrics
