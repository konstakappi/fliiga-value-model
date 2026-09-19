# Walk-forward backtest

Run date: 19 September 2026  
Data: 1,440 completed men's F-liiga matches from 2020/21 onward  
Test set: 1,170 matches after an initial 250-match training window  
Refit interval: 50 matches

Every prediction was generated using only matches available before the predicted
match. Hyperparameters were fixed at a 120-day half-life and L2 penalty of 1.0.

## Aggregate result

| Metric | Model | Expanding league-average baseline |
|---|---:|---:|
| Total-goals MAE | 2.683 | 2.788 |
| Total-goals RMSE | 3.361 | 3.524 |
| MAE improvement | 3.76% | — |
| 1X2 log loss | 0.612 | — |
| 1X2 Brier score | 0.356 | — |

Mean predicted total was 10.815 goals and mean observed total was 10.724, so the
model overpredicted by 0.091 goals on average. Absolute error was at most two
goals in 44.6% of matches and at most three goals in 62.0%.

## By season

| Season | Matches | Model MAE | Baseline MAE | 1X2 log loss |
|---|---:|---:|---:|---:|
| 2021/22 | 199 | 2.696 | 2.769 | 0.622 |
| 2022/23 | 223 | 2.588 | 2.557 | 0.598 |
| 2023/24 | 254 | 2.621 | 2.683 | 0.669 |
| 2024/25 | 250 | 2.707 | 2.973 | 0.636 |
| 2025/26 | 235 | 2.800 | 2.938 | 0.542 |

The model beat the baseline in four of five complete season segments, but the
edge is modest and was not present in 2022/23.

## What this does not prove

This test measures predictive accuracy, not betting profitability. A valid ROI
test requires timestamped, pre-match totals lines and prices. The repository's
`totals-backtest` command is ready for that dataset and reports flat-stake ROI,
profit, bet count, win rate and average estimated EV without future leakage.

The report is not evidence of guaranteed future profit. Reassess calibration,
ROI, CLV and drawdown after a sufficiently large prospective odds sample.
