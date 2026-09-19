from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .backtest import totals_odds_backtest, walk_forward_backtest
from .collector import FliigaCollector
from .data import load_fixtures, load_games
from .market import OddsDatabase, build_value_report
from .model import PoissonStrengthModel
from .predict import predict_fixtures


def main() -> None:
    parser = argparse.ArgumentParser(prog="fliiga-model")
    subparsers = parser.add_subparsers(dest="command", required=True)

    predict_parser = subparsers.add_parser("predict", help="Fit on history and price fixtures")
    predict_parser.add_argument("--games", required=True)
    predict_parser.add_argument("--fixtures", required=True)
    predict_parser.add_argument("--output", default="predictions.csv")
    predict_parser.add_argument("--half-life", type=float, default=120.0)
    predict_parser.add_argument("--l2", type=float, default=1.0)

    backtest_parser = subparsers.add_parser("backtest", help="Run chronological backtest")
    backtest_parser.add_argument("--games", required=True)
    backtest_parser.add_argument("--output", default="backtest_results.csv")
    backtest_parser.add_argument("--min-train-games", type=int, default=250)
    backtest_parser.add_argument("--retrain-every", type=int, default=50)

    totals_bt = subparsers.add_parser(
        "totals-backtest", help="Backtest totals bets from historical odds snapshots"
    )
    totals_bt.add_argument("--games", required=True)
    totals_bt.add_argument("--odds", required=True)
    totals_bt.add_argument("--output", default="totals_backtest.csv")
    totals_bt.add_argument("--min-train-games", type=int, default=250)
    totals_bt.add_argument("--retrain-every", type=int, default=25)
    totals_bt.add_argument("--min-ev", type=float, default=0.05)
    totals_bt.add_argument("--bookmaker")

    collect_parser = subparsers.add_parser("collect", help="Download public men's F-liiga data")
    collect_parser.add_argument("--games-output", default="data/fliiga_men_history.csv")
    collect_parser.add_argument("--fixtures-output", default="data/fliiga_men_fixtures.csv")

    odds_parser = subparsers.add_parser("odds-import", help="Import timestamped totals odds")
    odds_parser.add_argument("--input", required=True)
    odds_parser.add_argument("--db", default="data/odds.db")
    odds_parser.add_argument("--collected-at")

    value_parser = subparsers.add_parser("value-report", help="Create today's totals value list")
    value_parser.add_argument("--db", default="data/odds.db")
    value_parser.add_argument("--games", default="data/fliiga_men_history.csv")
    value_parser.add_argument("--fixtures", default="data/fliiga_men_fixtures.csv")
    value_parser.add_argument("--output", default="data/daily_value.csv")
    value_parser.add_argument("--min-ev", type=float, default=0.05)

    bet_parser = subparsers.add_parser("record-bet", help="Record a totals bet for CLV tracking")
    bet_parser.add_argument("--db", default="data/odds.db")
    for argument in ("bookmaker", "event-start", "home-team", "away-team", "side"):
        bet_parser.add_argument(f"--{argument}", required=True)
    bet_parser.add_argument("--line", type=float, required=True)
    bet_parser.add_argument("--odds", type=float, required=True)
    bet_parser.add_argument("--stake", type=float, required=True)
    bet_parser.add_argument("--placed-at")
    bet_parser.add_argument("--note", default="")

    clv_parser = subparsers.add_parser("clv-report", help="Compare bets with closing odds")
    clv_parser.add_argument("--db", default="data/odds.db")
    clv_parser.add_argument("--output", default="data/clv_report.csv")

    args = parser.parse_args()
    if args.command == "odds-import":
        with OddsDatabase(args.db) as database:
            count = database.import_csv(args.input, args.collected_at)
        print(f"Imported {count} new odds snapshots into {args.db}")
        return
    if args.command == "value-report":
        with OddsDatabase(args.db) as database:
            report = build_value_report(
                database, args.games, args.fixtures, min_ev=args.min_ev
            )
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        report.to_csv(args.output, index=False)
        print(report.to_string(index=False) if not report.empty else "No qualifying value bets")
        print(f"Saved {args.output}")
        return
    if args.command == "record-bet":
        with OddsDatabase(args.db) as database:
            bet_id = database.record_bet(
                bookmaker=args.bookmaker, event_start=args.event_start,
                home_team=args.home_team, away_team=args.away_team,
                total_line=args.line, side=args.side, decimal_odds=args.odds,
                stake=args.stake, placed_at=args.placed_at, note=args.note,
            )
        print(f"Recorded bet {bet_id}")
        return
    if args.command == "clv-report":
        with OddsDatabase(args.db) as database:
            report = database.clv_report()
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        report.to_csv(args.output, index=False)
        print(report.to_string(index=False) if not report.empty else "No recorded bets")
        print(f"Saved {args.output}")
        return
    if args.command == "totals-backtest":
        odds = pd.read_csv(args.odds)
        games = load_games(args.games)
        results, metrics = totals_odds_backtest(
            games, odds, min_train_games=args.min_train_games,
            retrain_every=args.retrain_every, min_ev=args.min_ev,
            bookmaker=args.bookmaker,
        )
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        results.to_csv(args.output, index=False)
        print(json.dumps(metrics, indent=2))
        print(f"Saved {args.output}")
        return
    if args.command == "collect":
        result = FliigaCollector().collect()
        result.completed.to_csv(args.games_output, index=False)
        result.fixtures.to_csv(args.fixtures_output, index=False)
        print(f"Saved {len(result.completed)} completed matches to {args.games_output}")
        print(f"Saved {len(result.fixtures)} fixtures to {args.fixtures_output}")
        return

    games = load_games(args.games)
    if args.command == "predict":
        fixtures = load_fixtures(args.fixtures)
        model = PoissonStrengthModel(half_life_days=args.half_life, l2=args.l2).fit(games)
        predictions = predict_fixtures(model, fixtures)
        predictions.to_csv(args.output, index=False)
        print(predictions.to_string(index=False))
        print(f"\nSaved {args.output}")
    else:
        results, metrics = walk_forward_backtest(
            games,
            min_train_games=args.min_train_games,
            retrain_every=args.retrain_every,
        )
        results.to_csv(args.output, index=False)
        print(json.dumps(metrics, indent=2))
        print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
