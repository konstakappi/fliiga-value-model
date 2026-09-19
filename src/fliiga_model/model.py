from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import nbinom, poisson


@dataclass(frozen=True)
class MatchPrediction:
    home_team: str
    away_team: str
    expected_home_goals: float
    expected_away_goals: float
    home_probability: float
    draw_probability: float
    away_probability: float


@dataclass(frozen=True)
class TotalPrediction:
    line: float
    expected_total_goals: float
    over_probability: float
    push_probability: float
    under_probability: float
    dispersion: float


class PoissonStrengthModel:
    """Recency-weighted attack/defence Poisson model with L2 shrinkage."""

    def __init__(self, half_life_days: float = 120.0, l2: float = 1.0, max_goals: int = 20):
        if half_life_days <= 0 or l2 < 0 or max_goals < 5:
            raise ValueError("Invalid model hyperparameters")
        self.half_life_days = float(half_life_days)
        self.l2 = float(l2)
        self.max_goals = int(max_goals)
        self.teams: list[str] = []
        self.team_index: dict[str, int] = {}
        self.params_: np.ndarray | None = None
        self.fit_date_: pd.Timestamp | None = None
        self.total_dispersion_: float | None = None

    def fit(self, games: pd.DataFrame, as_of: pd.Timestamp | str | None = None) -> PoissonStrengthModel:
        required = {"date", "home_team", "away_team", "home_goals", "away_goals"}
        if missing := required - set(games.columns):
            raise ValueError(f"Missing columns: {sorted(missing)}")
        if len(games) < 10:
            raise ValueError("At least 10 completed games are required")

        data = games.copy()
        data["date"] = pd.to_datetime(data["date"])
        self.fit_date_ = pd.Timestamp(as_of) if as_of is not None else data["date"].max()
        if self.fit_date_.tzinfo is not None:
            self.fit_date_ = self.fit_date_.tz_localize(None)
        data = data[data["date"] <= self.fit_date_].copy()
        if len(data) < 10:
            raise ValueError("At least 10 games must be dated on or before as_of")

        self.teams = sorted(set(data["home_team"]) | set(data["away_team"]))
        self.team_index = {team: index for index, team in enumerate(self.teams)}
        n_teams = len(self.teams)
        home_idx = data["home_team"].map(self.team_index).to_numpy(dtype=int)
        away_idx = data["away_team"].map(self.team_index).to_numpy(dtype=int)
        home_goals = data["home_goals"].to_numpy(dtype=float)
        away_goals = data["away_goals"].to_numpy(dtype=float)
        age_days = (self.fit_date_ - data["date"]).dt.total_seconds().to_numpy() / 86_400
        weights = np.power(0.5, np.maximum(age_days, 0.0) / self.half_life_days)

        mean_goals = max((home_goals.sum() + away_goals.sum()) / (2 * len(data)), 0.1)
        initial = np.zeros(2 + 2 * n_teams)
        initial[0] = np.log(mean_goals)

        def objective(raw: np.ndarray) -> float:
            intercept, home_advantage = raw[:2]
            attack = raw[2 : 2 + n_teams]
            defence = raw[2 + n_teams :]
            # Centering makes the team strengths identifiable.
            attack = attack - attack.mean()
            defence = defence - defence.mean()
            log_home = np.clip(
                intercept + home_advantage + attack[home_idx] - defence[away_idx], -5, 5
            )
            log_away = np.clip(intercept + attack[away_idx] - defence[home_idx], -5, 5)
            lambda_home = np.exp(log_home)
            lambda_away = np.exp(log_away)
            home_nll = lambda_home - home_goals * log_home + gammaln(home_goals + 1)
            away_nll = lambda_away - away_goals * log_away + gammaln(away_goals + 1)
            penalty = self.l2 * (np.square(attack).sum() + np.square(defence).sum())
            return float(np.sum(weights * (home_nll + away_nll)) + penalty)

        result = minimize(objective, initial, method="L-BFGS-B", options={"maxiter": 2_000})
        if not result.success:
            raise RuntimeError(f"Model fitting failed: {result.message}")
        fitted = result.x.copy()
        fitted[2 : 2 + n_teams] -= fitted[2 : 2 + n_teams].mean()
        fitted[2 + n_teams :] -= fitted[2 + n_teams :].mean()
        self.params_ = fitted

        intercept, home_advantage = fitted[:2]
        attack = fitted[2 : 2 + n_teams]
        defence = fitted[2 + n_teams :]
        fitted_home = np.exp(
            np.clip(intercept + home_advantage + attack[home_idx] - defence[away_idx], -5, 5)
        )
        fitted_away = np.exp(
            np.clip(intercept + attack[away_idx] - defence[home_idx], -5, 5)
        )
        fitted_total = fitted_home + fitted_away
        observed_total = home_goals + away_goals
        numerator = np.sum(weights * (np.square(observed_total - fitted_total) - fitted_total))
        denominator = np.sum(weights * np.square(fitted_total))
        self.total_dispersion_ = max(0.0, float(numerator / denominator)) if denominator else 0.0
        return self

    def expected_goals(self, home_team: str, away_team: str) -> tuple[float, float]:
        if self.params_ is None:
            raise RuntimeError("Fit the model before predicting")
        unknown = {home_team, away_team} - set(self.team_index)
        if unknown:
            raise ValueError(f"Unknown teams: {sorted(unknown)}")
        n_teams = len(self.teams)
        intercept, home_advantage = self.params_[:2]
        attack = self.params_[2 : 2 + n_teams]
        defence = self.params_[2 + n_teams :]
        home_idx = self.team_index[home_team]
        away_idx = self.team_index[away_team]
        home = np.exp(intercept + home_advantage + attack[home_idx] - defence[away_idx])
        away = np.exp(intercept + attack[away_idx] - defence[home_idx])
        return float(home), float(away)

    def predict(self, home_team: str, away_team: str) -> MatchPrediction:
        home_xg, away_xg = self.expected_goals(home_team, away_team)
        scores = np.arange(self.max_goals + 1)
        home_pmf = poisson.pmf(scores, home_xg)
        away_pmf = poisson.pmf(scores, away_xg)
        # Put the omitted upper tail into the last bucket so probabilities sum to one.
        home_pmf[-1] += max(0.0, 1.0 - home_pmf.sum())
        away_pmf[-1] += max(0.0, 1.0 - away_pmf.sum())
        matrix = np.outer(home_pmf, away_pmf)
        home_probability = float(np.tril(matrix, -1).sum())
        draw_probability = float(np.trace(matrix))
        away_probability = float(np.triu(matrix, 1).sum())
        return MatchPrediction(
            home_team=home_team,
            away_team=away_team,
            expected_home_goals=home_xg,
            expected_away_goals=away_xg,
            home_probability=home_probability,
            draw_probability=draw_probability,
            away_probability=away_probability,
        )

    def predict_total(self, home_team: str, away_team: str, line: float) -> TotalPrediction:
        if not np.isfinite(line) or line < 0:
            raise ValueError("Total line must be a finite non-negative number")
        home_xg, away_xg = self.expected_goals(home_team, away_team)
        mean = home_xg + away_xg
        alpha = self.total_dispersion_ or 0.0

        if alpha > 1e-8:
            size = 1.0 / alpha
            probability = size / (size + mean)
            distribution = nbinom(size, probability)
        else:
            distribution = poisson(mean)

        rounded = round(line)
        if np.isclose(line, rounded):
            integer_line = int(rounded)
            under = float(distribution.cdf(integer_line - 1))
            push = float(distribution.pmf(integer_line))
            over = float(distribution.sf(integer_line))
        else:
            cutoff = int(np.floor(line))
            under = float(distribution.cdf(cutoff))
            push = 0.0
            over = float(distribution.sf(cutoff))

        return TotalPrediction(
            line=float(line),
            expected_total_goals=mean,
            over_probability=over,
            push_probability=push,
            under_probability=under,
            dispersion=alpha,
        )
