"""Carhart (1997) UMD momentum factor — extracted for walk-forward testing.

Ported from HKUDS/Vibe-Trading's ``academic_carhart_mom`` (the single factor that
survived the alpha-zoo IC bench on the S&P 500). Self-contained: pandas + numpy
only, no alpha_zoo_pkg dependency.

Two variants:
  - ``zoo``       : ret_252 - ret_21  (exactly what the bench scored)
  - ``canonical`` : skip-a-month 12-1 return, ret(t-252 -> t-21)  (textbook UMD)

Gross numbers the zoo variant produced (S&P 500, 2021-2026, 21-day forward IC):
    IC mean 0.039 | IR 0.22 | t 7.3 | positive-IC ratio 63%
These are GROSS of cost, on current (survivorship-biased) constituents, with
overlapping 21-day windows inflating the t-stat. Treat as a hypothesis to be
killed or confirmed by a net-of-cost, point-in-time walk-forward.

Data contract: ``close`` is a WIDE DataFrame, index = DatetimeIndex (daily bars),
columns = symbol. All functions return same-shape frames / aligned series.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def cross_sectional_zscore(df: pd.DataFrame) -> pd.DataFrame:
    """Per-date z-score across symbols: (x - row_mean) / row_std (ddof=1).

    Rows with zero or undefined std become NaN (never silent zero). +/-inf -> NaN.
    """
    mean = df.mean(axis=1, skipna=True)
    std = df.std(axis=1, ddof=1, skipna=True)
    z = df.sub(mean, axis=0).div(std.where(std > 0), axis=0)
    return z.replace([np.inf, -np.inf], np.nan)


def carhart_umd(
    close: pd.DataFrame,
    *,
    long: int = 252,
    short: int = 21,
    variant: str = "zoo",
) -> pd.DataFrame:
    """Carhart UMD momentum, cross-sectionally z-scored per date.

    Args:
        close: wide prices (index=date, columns=symbol).
        long: long lookback in trading days (252 ~ 12 months).
        short: short lookback in trading days (21 ~ 1 month).
        variant: ``"zoo"`` reproduces the benched factor (ret_long - ret_short);
            ``"canonical"`` uses the textbook skip-a-month 12-1 return.

    Returns:
        Factor scores, same shape as close. Higher = momentum winner. The first
        ``long`` rows are NaN (warmup); dates with <2 valid names are NaN.
    """
    if variant == "zoo":
        raw = close.pct_change(long) - close.pct_change(short)
    elif variant == "canonical":
        # Return from t-long to t-short (skip the most recent `short` days).
        raw = close.shift(short) / close.shift(long) - 1.0
    else:
        raise ValueError(f"variant must be 'zoo' or 'canonical', got {variant!r}")
    raw = raw.replace([np.inf, -np.inf], np.nan)
    return cross_sectional_zscore(raw)


def forward_returns(close: pd.DataFrame, horizon: int = 21) -> pd.DataFrame:
    """Forward simple return over ``horizon`` bars, aligned to the signal date."""
    return close.pct_change(horizon).shift(-horizon)


def information_coefficient(
    factor: pd.DataFrame, fwd: pd.DataFrame, *, min_names: int = 5
) -> dict[str, float]:
    """Daily cross-sectional Spearman IC between factor and forward returns.

    Mirrors the alpha-zoo bench: rank both per date, Pearson on ranks, drop dates
    with fewer than ``min_names`` valid pairs.

    Returns:
        Dict with ic_mean, ic_std, ir, t_stat, positive_ratio, n_days.
    """
    dates = factor.index.intersection(fwd.index)
    cols = factor.columns.intersection(fwd.columns)
    f = factor.loc[dates, cols]
    r = fwd.loc[dates, cols]
    mask = f.notna() & r.notna()
    f, r = f.where(mask), r.where(mask)
    ic = f.rank(axis=1).corrwith(r.rank(axis=1), axis=1)
    ic = ic[mask.sum(axis=1) >= min_names].dropna()
    if ic.empty:
        return {"ic_mean": float("nan"), "ic_std": float("nan"), "ir": float("nan"),
                "t_stat": float("nan"), "positive_ratio": float("nan"), "n_days": 0}
    n = len(ic)
    mean, std = float(ic.mean()), float(ic.std())
    return {
        "ic_mean": round(mean, 6),
        "ic_std": round(std, 6),
        "ir": round(mean / std, 4) if std > 0 else 0.0,
        "t_stat": round(mean / (std / np.sqrt(n)), 3) if std > 0 else 0.0,
        "positive_ratio": round(float((ic > 0).mean()), 4),
        "n_days": n,
    }


def long_short_backtest(
    factor: pd.DataFrame,
    close: pd.DataFrame,
    *,
    horizon: int = 21,
    quantile: float = 0.2,
    cost_bps: float = 10.0,
) -> dict[str, object]:
    """Minimal NON-overlapping long-short reference backtest (a starting point —
    use your own walk-forward harness for the real verdict).

    Rebalances every ``horizon`` bars: long the top ``quantile`` by factor,
    short the bottom, equal-weight, hold ``horizon`` bars. Subtracts
    ``cost_bps`` per unit of one-way turnover at each rebalance.

    Returns:
        Dict with period_returns_net (Series), gross_cum, net_cum,
        mean_period_net, sharpe_net (annualized ~252/horizon periods/yr),
        avg_turnover, n_periods.
    """
    fwd = close.pct_change(horizon).shift(-horizon)
    rebal = factor.index[::horizon]
    prev_long: set = set()
    prev_short: set = set()
    rows: list[tuple] = []
    for d in rebal:
        f = factor.loc[d].dropna()
        if len(f) < 5:
            continue
        k = max(1, int(len(f) * quantile))
        longs = set(f.nlargest(k).index)
        shorts = set(f.nsmallest(k).index)
        r = fwd.loc[d]
        long_ret = r.reindex(longs).mean()
        short_ret = r.reindex(shorts).mean()
        if pd.isna(long_ret) or pd.isna(short_ret):
            continue
        gross = long_ret - short_ret
        # one-way turnover vs previous rebalance (fraction of names changed)
        turn = 0.0
        if prev_long or prev_short:
            turn = (len(longs ^ prev_long) + len(shorts ^ prev_short)) / (2 * k)
        net = gross - turn * (cost_bps / 1e4)
        rows.append((d, gross, net, turn))
        prev_long, prev_short = longs, shorts

    if not rows:
        return {"error": "no valid rebalance periods"}
    idx = [x[0] for x in rows]
    net = pd.Series([x[2] for x in rows], index=idx)
    gross = pd.Series([x[1] for x in rows], index=idx)
    turns = pd.Series([x[3] for x in rows], index=idx)
    periods_per_yr = 252 / horizon
    sharpe = (net.mean() / net.std() * np.sqrt(periods_per_yr)) if net.std() > 0 else float("nan")
    return {
        "period_returns_net": net,
        "gross_cum": float((1 + gross).prod() - 1),
        "net_cum": float((1 + net).prod() - 1),
        "mean_period_net": round(float(net.mean()), 5),
        "sharpe_net": round(float(sharpe), 3),
        "avg_turnover": round(float(turns.mean()), 3),
        "n_periods": len(rows),
    }


if __name__ == "__main__":
    # Quick self-check on your fetched universe (run from a TCC-accessible context,
    # e.g. your own Terminal with Full Disk Access):
    #   python carhart_umd.py sp500_universe.csv
    import sys

    if len(sys.argv) > 1:
        df = pd.read_csv(sys.argv[1])
        close = df.pivot_table(index="date", columns="symbol", values="close", aggfunc="last")
        close.index = pd.to_datetime(close.index)
        close = close.sort_index()
        for v in ("zoo", "canonical"):
            f = carhart_umd(close, variant=v)
            print(v, information_coefficient(f, forward_returns(close, 21)))
        print("backtest:", {k: val for k, val in
                            long_short_backtest(carhart_umd(close), close).items()
                            if k != "period_returns_net"})
