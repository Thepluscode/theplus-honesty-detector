#!/usr/bin/env python3
"""
Strategy edge audit — honest, no-flattery cross-strategy walk-forward.

Answers ONE question per strategy: does it have a statistically
meaningful edge that survives realistic costs, out of sample?

Design decisions made specifically to prevent self-deception:

1. DEFAULT PARAMS, NOT TUNED CONFIGS. Each strategy runs on its
   code-default parameters via a neutral base config. Using the
   bespoke ``*_optimised.yaml`` configs would be in-sample
   overfitting — they were tuned on this exact 3yr EURUSD dataset,
   so a walk-forward over the same data would be contaminated. The
   audit tests raw edge, not memorised tuning.

2. NORMALISED COST MODEL, IDENTICAL FOR ALL. Every strategy pays the
   same realistic retail-EURUSD cost: slippage_ticks=15 (~1.5 pip
   round trip), commission 0, tick 0.00001. Differences in result
   reflect edge, not different cost assumptions.

3. ROLLING WALK-FORWARD, FROZEN CONFIG. 6-month window, 3-month
   step across 3 years (2023-2026). No per-fold re-tuning. A real
   edge persists across regimes; an overfit one does not.

4. STRICT VERDICT. "Has edge" requires ALL of: aggregate Sharpe
   >= 0.5, >=60% positive-Sharpe folds, mean profit factor >= 1.1,
   and >=30 total trades (statistical floor). Anything less is
   "NO DURABLE EDGE" — stated plainly.

Off-design strategies (built for other markets/timeframes) are run
anyway for completeness but flagged ``OFF-DESIGN`` — their numbers
on EURUSD 5m are indicative only, not a fair test of their thesis.

---------------------------------------------------------------------------
DEPENDENCY NOTE (theplus-honesty-detector)
---------------------------------------------------------------------------
This tool was originally part of theplus-bot, which supplied a full
backtesting engine (``tradebot.config`` and ``tradebot.engine_v2``).
Those modules are NOT included in this public companion repo — they
constitute the private trading platform and are not needed to inspect,
reproduce, or extend the audit methodology or its results.

To run the audit against your own strategies you need to supply:

  1. ``load_config(path: str) -> cfg``
       Reads a YAML config file and returns a config object the
       engine understands.

  2. ``engine_v2.run(cfg, fold_df, paper=True, verbose=False) -> trades_df``
       Runs one strategy fold over a DataFrame of OHLCV bars and
       returns a trades DataFrame with at minimum columns:
         pnl (float), exit_reason (str), day (date, optional),
         r_multiple (float, optional), bars_held (int, optional)

  3. ``compute_metrics`` is inlined below — no external dep needed.

The JSON reports in ``reports/`` already contain the full output of the
audit as run against the private theplus-bot strategies. Those are the
receipts — you do not need to re-run the engine to inspect them.
---------------------------------------------------------------------------

Usage:
    python tools/strategy_edge_audit.py \\
        --data data/sample/EURUSD_5m_20230101_20260101.csv \\
        --report-out reports/edge_audit_$(date +%Y%m%d).json
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# (name, on_design_for_eurusd_5m, note)
_STRATEGIES = [
    ("box_symmetric",        True,  "the only 'production-proven' strategy"),
    ("box_longonly",         True,  "long-only box variant"),
    ("box_adaptive",         True,  "adaptive box (no shipped config)"),
    ("breakout_pullback",    True,  "breakout + pullback entry"),
    ("keltner_fade",         True,  "Keltner channel mean-reversion"),
    ("vwap_reversal",        True,  "VWAP reversal mean-reversion"),
    ("obv_mean_reversion",   True,  "OBV divergence mean-reversion"),
    ("trend_breakout",       False, "OFF-DESIGN: built for 4h crypto trend"),
    ("rsi2_mean_reversion",  False, "OFF-DESIGN: built for stocks"),
    ("stocks_momentum",      False, "OFF-DESIGN: built for equities"),
    ("fx_carry_trend",       False, "OFF-DESIGN: needs rate-diff data, not price-only"),
]

_BASE_CONFIG = """\
mode: "backtest"
symbol: "EUR_USD"
timeframe: "5m"
timezone: "Europe/London"
data:
  source: "csv"
  path: "{data_path}"
broker:
  name: "paper"
  initial_equity: 10000
  commission_pct: 0.0
  slippage_ticks: 15
  tick_size: 0.00001
risk:
  risk_pct_per_trade: 0.005
  daily_r_limit: 3.0
  max_positions: 1
  use_advanced: false
strategy:
  name: "{strategy}"
logging:
  level: "ERROR"
  log_json: false
"""


def _build_folds(df, window_months: int, step_months: int):
    import pandas as pd
    from dateutil.relativedelta import relativedelta
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    start, end = df["timestamp"].min(), df["timestamp"].max()
    cur = start
    while cur + relativedelta(months=window_months) <= end:
        win_end = cur + relativedelta(months=window_months)
        chunk = df[(df["timestamp"] >= cur) & (df["timestamp"] < win_end)].copy()
        chunk = chunk.reset_index(drop=True)
        yield cur, win_end, chunk
        cur = cur + relativedelta(months=step_months)


def compute_metrics(trades_df, initial_equity: float = 10000.0) -> dict:
    """
    Standalone compute_metrics — inlined from the original trading engine.

    Aggregates a trades DataFrame into the metrics dict consumed by
    _audit_strategy. Column expectations:
      pnl          (float, required)
      exit_reason  (str,   optional — used to exclude crash_recovery rows)
      day          (date,  optional — used for daily-level Sharpe)
      r_multiple   (float, optional)
      bars_held    (int,   optional)
    """
    import numpy as np

    if trades_df is None or len(trades_df) == 0:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "profit_factor": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_pct": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "expectancy": 0.0,
            "avg_r_multiple": 0.0,
            "avg_bars_held": 0.0,
            "final_equity": initial_equity,
            "total_return_pct": 0.0,
            "cagr": 0.0,
        }

    pnls = trades_df["pnl"].values
    total = len(pnls)
    _exit_reasons = (trades_df["exit_reason"].values
                     if "exit_reason" in trades_df.columns
                     else [None] * total)
    _neutral = np.array([
        (p == 0) or (str(r) in ("crash_recovery", "bot_stopped"))
        for p, r in zip(pnls, _exit_reasons)
    ])
    wins = pnls[(pnls > 0) & ~_neutral]
    losses = pnls[(pnls < 0) & ~_neutral]
    _counted = len(wins) + len(losses)

    win_rate = len(wins) / _counted if _counted > 0 else 0.0
    total_pnl = float(np.sum(pnls))
    gross_profit = float(np.sum(wins)) if len(wins) > 0 else 0.0
    gross_loss = float(np.abs(np.sum(losses))) if len(losses) > 0 else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
    avg_loss = float(np.mean(losses)) if len(losses) > 0 else 0.0
    expectancy = float(np.mean(pnls)) if total > 0 else 0.0

    if "day" in trades_df.columns:
        daily_returns = trades_df.groupby("day")["pnl"].sum().values
    else:
        daily_returns = pnls
    if len(daily_returns) > 1 and np.std(daily_returns) > 0:
        sharpe = (np.mean(daily_returns) / np.std(daily_returns)) * np.sqrt(252)
    else:
        sharpe = 0.0

    cumulative = np.cumsum(pnls)
    equity_curve = initial_equity + cumulative
    peak = np.maximum.accumulate(equity_curve)
    drawdown = peak - equity_curve
    max_dd = float(np.max(drawdown)) if len(drawdown) > 0 else 0.0
    max_dd_pct = max_dd / float(np.max(peak)) if np.max(peak) > 0 else 0.0
    final_equity = float(equity_curve[-1]) if len(equity_curve) > 0 else initial_equity
    total_return_pct = (final_equity - initial_equity) / initial_equity * 100

    if "day" in trades_df.columns:
        years = trades_df["day"].nunique() / 252.0
    else:
        years = total / (252 * 2)
    if years > 0 and final_equity > 0:
        cagr = (final_equity / initial_equity) ** (1.0 / years) - 1.0
    else:
        cagr = 0.0

    avg_r = float(trades_df["r_multiple"].mean()) if "r_multiple" in trades_df.columns else 0.0
    avg_bars = float(trades_df["bars_held"].mean()) if "bars_held" in trades_df.columns else 0.0

    return {
        "total_trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 4),
        "total_pnl": round(total_pnl, 2),
        "profit_factor": round(profit_factor, 4),
        "sharpe_ratio": round(float(sharpe), 4),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct * 100, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "expectancy": round(expectancy, 2),
        "avg_r_multiple": round(avg_r, 4),
        "avg_bars_held": round(avg_bars, 1),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return_pct, 2),
        "cagr": round(cagr * 100, 2),
    }


def _audit_strategy(strategy: str, data_path: Path, df, window_months: int,
                    step_months: int, min_trades_floor: int) -> dict:
    # TODO: Supply your own load_config and engine runner.
    # See the DEPENDENCY NOTE at the top of this file.
    # Required signatures:
    #   load_config(path: str) -> cfg
    #   engine_run(cfg, fold_df, paper=True, verbose=False) -> trades_df
    # compute_metrics is inlined above — no external dep needed.
    #
    # The pre-computed audit results are in reports/edge_audit_20260518.json.
    # You do not need to re-run to inspect those receipts.

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
        tf.write(_BASE_CONFIG.format(strategy=strategy, data_path=data_path))
        tmp_cfg_path = tf.name

    try:
        cfg = load_config(tmp_cfg_path)  # noqa: F821 — supply your own; see DEPENDENCY NOTE
    except Exception as e:
        return {"strategy": strategy, "error": f"config load failed: {e}"}

    fold_metrics = []
    for win_start, win_end, fold_df in _build_folds(df, window_months, step_months):
        if len(fold_df) < 500:
            continue
        try:
            trades = engine_run(cfg, fold_df, paper=True, verbose=False)  # noqa: F821
            m = compute_metrics(trades, initial_equity=10000.0)
        except Exception as e:
            fold_metrics.append({"error": str(e)[:120], "total_trades": 0,
                                 "sharpe_ratio": 0.0, "profit_factor": 0.0,
                                 "max_drawdown_pct": 0.0, "total_return_pct": 0.0})
            continue
        fold_metrics.append(m)

    folds = [f for f in fold_metrics if "error" not in f]
    n = len(folds)
    if n == 0:
        return {"strategy": strategy, "error": "no folds completed",
                "n_folds": 0, "total_trades": 0}

    total_trades = sum(f["total_trades"] for f in folds)
    traded = [f for f in folds if f["total_trades"] > 0]
    n_pos = sum(1 for f in folds if f["sharpe_ratio"] > 0)
    agg_sharpe = sum(f["sharpe_ratio"] for f in folds) / n
    pct_pos = n_pos / n
    pfs = [f["profit_factor"] for f in traded
           if f["profit_factor"] not in (float("inf"),) and f["profit_factor"] > 0]
    mean_pf = sum(pfs) / len(pfs) if pfs else 0.0
    worst_dd = max((f["max_drawdown_pct"] for f in folds), default=0.0)
    total_ret = sum(f["total_return_pct"] for f in folds)

    has_edge = (
        agg_sharpe >= 0.5
        and pct_pos >= 0.60
        and mean_pf >= 1.1
        and total_trades >= min_trades_floor
    )

    return {
        "strategy": strategy,
        "n_folds": n,
        "total_trades": total_trades,
        "agg_sharpe": round(agg_sharpe, 3),
        "pct_positive_folds": round(pct_pos, 3),
        "mean_profit_factor": round(mean_pf, 3),
        "worst_fold_max_dd_pct": round(worst_dd, 2),
        "sum_fold_return_pct": round(total_ret, 2),
        "verdict": "EDGE" if has_edge else "NO DURABLE EDGE",
        "criteria": {
            "agg_sharpe>=0.5": agg_sharpe >= 0.5,
            "pct_positive>=0.60": pct_pos >= 0.60,
            "mean_pf>=1.1": mean_pf >= 1.1,
            f"total_trades>={min_trades_floor}": total_trades >= min_trades_floor,
        },
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--data", required=True, type=Path)
    p.add_argument("--window-months", type=int, default=6)
    p.add_argument("--step-months", type=int, default=3)
    p.add_argument("--min-trades-floor", type=int, default=30)
    p.add_argument("--report-out", type=Path, default=None)
    p.add_argument("--only", default=None,
                   help="comma-separated strategy names to limit the audit")
    args = p.parse_args(argv)

    import logging
    logging.basicConfig(level=logging.ERROR)
    import pandas as pd

    if not args.data.exists():
        print(f"ERROR: data file not found: {args.data}", file=sys.stderr)
        return 1
    df = pd.read_csv(args.data)
    print(f"Loaded {len(df)} bars from {args.data}")
    print(f"Walk-forward: {args.window_months}mo window / "
          f"{args.step_months}mo step | DEFAULT params | "
          f"normalised cost (15-tick slippage)\n")

    only = set(s.strip() for s in args.only.split(",")) if args.only else None
    results = []
    for name, on_design, note in _STRATEGIES:
        if only and name not in only:
            continue
        print(f"  auditing {name} ...", flush=True)
        r = _audit_strategy(name, args.data, df,
                            args.window_months, args.step_months,
                            args.min_trades_floor)
        r["on_design"] = on_design
        r["note"] = note
        results.append(r)

    # Rank: edge first, then by aggregate Sharpe
    results.sort(key=lambda r: (r.get("verdict") != "EDGE",
                                -r.get("agg_sharpe", -99)))

    print("\n" + "=" * 92)
    print("STRATEGY EDGE AUDIT — EURUSD 5m, 3yr walk-forward, default params, real costs")
    print("=" * 92)
    hdr = (f"{'strategy':<22}{'fld':>4}{'trades':>7}{'aggSh':>7}"
           f"{'%pos':>6}{'PF':>6}{'wDD%':>7}{'ret%':>8}  verdict")
    print(hdr)
    print("-" * 92)
    for r in results:
        if "error" in r and "agg_sharpe" not in r:
            print(f"{r['strategy']:<22}{'—':>4}{'—':>7}  ERROR: {r['error'][:50]}")
            continue
        flag = "" if r["on_design"] else " *OFF-DESIGN"
        print(
            f"{r['strategy']:<22}"
            f"{r['n_folds']:>4}"
            f"{r['total_trades']:>7}"
            f"{r['agg_sharpe']:>7.2f}"
            f"{r['pct_positive_folds']*100:>5.0f}%"
            f"{r['mean_profit_factor']:>6.2f}"
            f"{r['worst_fold_max_dd_pct']:>7.1f}"
            f"{r['sum_fold_return_pct']:>8.1f}"
            f"  {r['verdict']}{flag}"
        )
    print("-" * 92)
    n_edge = sum(1 for r in results if r.get("verdict") == "EDGE")
    n_on = sum(1 for r in results if r.get("on_design"))
    n_on_edge = sum(1 for r in results
                    if r.get("on_design") and r.get("verdict") == "EDGE")
    print(f"\nVERDICT: {n_edge}/{len(results)} strategies show a durable edge "
          f"({n_on_edge}/{n_on} on-design).")
    print("Default params, out-of-sample, real costs. No tuning, no flattery.")
    print("=" * 92)

    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "method": "rolling walk-forward, default params, normalised "
                      "15-tick EURUSD cost, frozen config",
            "data": str(args.data),
            "window_months": args.window_months,
            "step_months": args.step_months,
            "min_trades_floor": args.min_trades_floor,
            "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "results": results,
        }
        with args.report_out.open("w") as f:
            json.dump(payload, f, indent=2, default=str)
        print(f"\nReport: {args.report_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
