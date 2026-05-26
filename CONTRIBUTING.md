# Contributing

## What we welcome

**Methodology critique.** If you think the audit criteria are too loose, too strict, or wrong in some measurable way — open an issue with the argument. Evidence preferred over opinion. We changed our own conclusions when the evidence required it; we'll do the same for external challenges.

**Audit tooling improvements.** Better statistical methods, cleaner implementations, tighter edge-case handling. The walk-forward harness in `tools/strategy_edge_audit.py`, the feasibility simulations, and the pre-checks are all fair targets.

**New free pre-check tools.** Tools that test a fresh edge hypothesis using only free public data and return a falsifiable EDGE / NO EDGE verdict under the same standard: out-of-sample, real costs, pre-registered pass/fail criteria, no goalpost-moving. See the existing tools for the expected structure and the tone.

**Bug fixes.** Reproducibility failures, wrong numbers, broken data fetches — PRs welcome directly for these.

## What we do not accept

**Strategy submissions.** This repo tests whether edges exist. It does not build, tune, or collect strategies. Do not open PRs or issues proposing new trading strategies to add.

**Backtest results without input data.** Any result claim without the data and code to reproduce it is unverifiable and will be closed.

**Anything that softens the verdict criteria.** The five pass/fail thresholds (`agg_sharpe >= 0.5`, `pct_positive_folds >= 60%`, `mean_profit_factor >= 1.1`, `total_trades >= 30`, frozen-config walk-forward) are hard-coded constants for a reason. PRs that lower them, make them configurable, or add override flags will not be merged. If you believe the thresholds are wrong, open an issue and make the statistical case.

## How to propose changes

Open an issue first for anything non-trivial — new audit tools, methodology changes, significant refactors. Describe the hypothesis, the proposed change, and how you'd verify it produced the right answer. This avoids wasted work if the direction is wrong.

PRs welcome without a prior issue for: typo fixes, dependency updates, documentation clarifications, reproducibility fixes.

Keep PRs small and single-purpose. A PR that changes both the statistical method and the data fetching is harder to review than two PRs.

Before submitting, verify the three self-contained tools still produce the same verdicts as the pre-computed reports in `reports/`. If your change affects the numbers, document why the new numbers are correct.
