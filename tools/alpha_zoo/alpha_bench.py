#!/usr/bin/env python3
"""Standalone alpha-zoo IC benchmark — no agent, no shell, no LLM, no network.

Extracted from HKUDS/Vibe-Trading (MIT). This script runs the *exact* same
information-coefficient (IC) pipeline as ``vibe-trading alpha bench`` but against
**your own** OHLCV data, on your own machine, with zero outbound calls and zero
code execution beyond the vendored pure-pandas factor definitions.

What it does
------------
For every alpha in the bundled zoo (Kakushadze 101 + GTJA 191 + Qlib 158 +
academic factors, ~452 total) it:

  1. computes the factor value across your cross-section of symbols each bar,
  2. computes the daily Spearman rank IC vs next-bar forward returns,
  3. reports IC mean / std / IR / positive-ratio / t-stat,
  4. buckets each alpha into alive / reversed / dead.

Categorisation thresholds (verbatim from the upstream ``bench_runner.py``):
  - alive    : ic_mean > 0.02 and ic_positive_ratio >= 0.55 and |t| > 2
  - reversed : ic_mean < -0.02 and |t| > 2
  - dead     : everything else

Input data contract
--------------------
A long/tidy CSV or Parquet with one row per (date, symbol, bar):

    date,symbol,open,high,low,close,volume[,amount]
    2020-01-02,AAPL,100.0,101.2,99.5,100.8,12000000
    2020-01-02,MSFT,...

Cross-sectional IC is only meaningful with **many symbols per bar** — this is a
ranking signal across a universe, not a single-instrument timing signal. Aim for
a few dozen+ liquid names. Single-symbol forex/crypto series will not produce
useful IC here (the upstream tool rejects single-asset universes for the same
reason).

Usage
-----
    python3 alpha_bench.py UNIVERSE.csv --zoo alpha101 --top 20
    python3 alpha_bench.py UNIVERSE.parquet --theme momentum --out results.csv
    python3 alpha_bench.py --list-zoos
"""

from __future__ import annotations

import argparse
import logging
import math
import sys
from pathlib import Path
from typing import Any

# --- wire up the vendored, renamed package (cannot collide with theplus-bot/src) ---
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from alpha_zoo_pkg.factors.factor_analysis_core import compute_ic_series  # noqa: E402
from alpha_zoo_pkg.factors.registry import (  # noqa: E402
    Registry,
    RegistryError,
    SkipAlpha,
    get_default_registry,
)

logging.basicConfig(
    level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("alpha_bench")

# Categorisation thresholds — copied verbatim from upstream bench_runner.py so
# results match `vibe-trading alpha bench`. Do not tune without re-baselining.
_ALIVE_IC = 0.02
_ALIVE_POS_RATIO = 0.55
_T_THRESHOLD = 2.0

_OHLCV_FIELDS = ("open", "high", "low", "close", "volume", "amount")


# --------------------------------------------------------------------------- #
# IC statistics (pure math, mirrors upstream)
# --------------------------------------------------------------------------- #
def t_stat(ic_mean: float, ic_std: float, n: int) -> float:
    """Two-sided t-statistic of the IC series (upstream bench_runner.t_stat)."""
    if not (n > 0 and ic_std > 0 and math.isfinite(ic_std)):
        return 0.0
    return ic_mean / (ic_std / math.sqrt(n))


def categorise(ic_mean: float, ic_std: float, pos_ratio: float, n: int) -> str:
    """Bucket an alpha into alive / reversed / dead (upstream thresholds)."""
    t = t_stat(ic_mean, ic_std, n)
    if ic_mean > _ALIVE_IC and pos_ratio >= _ALIVE_POS_RATIO and abs(t) > _T_THRESHOLD:
        return "alive"
    if ic_mean < -_ALIVE_IC and abs(t) > _T_THRESHOLD:
        return "reversed"
    return "dead"


# --------------------------------------------------------------------------- #
# Data loading — your universe, your disk, no network
# --------------------------------------------------------------------------- #
def load_panel(
    path: Path,
    *,
    date_col: str,
    symbol_col: str,
    col_map: dict[str, str],
) -> dict[str, pd.DataFrame]:
    """Load a long/tidy OHLCV file into the wide panel contract.

    Returns a dict keyed by field (open/high/low/close/volume[/amount]/vwap),
    each value a wide DataFrame: index = DatetimeIndex, columns = symbol.
    """
    if path.suffix.lower() in (".parquet", ".pq"):
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    missing = [c for c in (date_col, symbol_col) if c not in df.columns]
    if missing:
        raise ValueError(
            f"input missing required columns {missing}; found {list(df.columns)}"
        )

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])

    panel: dict[str, pd.DataFrame] = {}
    for field in _OHLCV_FIELDS:
        src_col = col_map.get(field, field)
        if src_col not in df.columns:
            if field in ("open", "high", "low", "close", "volume"):
                if field == "volume":
                    continue  # some asset classes lack volume; alphas needing it skip
                raise ValueError(f"input missing required price column '{src_col}'")
            continue
        wide = df.pivot_table(
            index=date_col, columns=symbol_col, values=src_col, aggfunc="last"
        ).sort_index()
        panel[field] = wide.astype(float)

    if "close" not in panel:
        raise ValueError("could not build a 'close' panel — check --close-col mapping")

    # Synthetic VWAP = (O+H+L+C)/4 when not supplied — mirrors the upstream
    # sp500/btc loaders. vwap() in base.py prefers panel['vwap'] when present.
    if "vwap" not in panel and all(k in panel for k in ("open", "high", "low", "close")):
        panel["vwap"] = (
            panel["open"] + panel["high"] + panel["low"] + panel["close"]
        ) / 4.0

    return panel


def forward_returns(panel: dict[str, pd.DataFrame], horizon: int) -> pd.DataFrame:
    """Forward simple return aligned to the factor timestamp.

    horizon=1 reproduces upstream exactly: ``close.pct_change().shift(-1)``.
    """
    close = panel.get("close")
    if close is None:
        raise ValueError("panel missing 'close' — cannot derive forward returns")
    return close.pct_change(horizon).shift(-horizon)


# --------------------------------------------------------------------------- #
# Bench loop
# --------------------------------------------------------------------------- #
def run(
    panel: dict[str, pd.DataFrame],
    return_df: pd.DataFrame,
    alpha_ids: list[str],
    registry: Registry,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Compute IC stats for each alpha. Returns (rows, skipped)."""
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    total = len(alpha_ids)

    for idx, aid in enumerate(alpha_ids, start=1):
        try:
            factor_df = registry.compute(aid, panel)
            ic = compute_ic_series(factor_df, return_df)
            if ic.empty:
                skipped.append({"id": aid, "reason": "empty IC series"})
                continue
            ic_mean = float(ic.mean())
            ic_std = float(ic.std())
            n = int(len(ic))
            pos = float((ic > 0).mean())
            ir = ic_mean / ic_std if ic_std > 0 else 0.0
            meta = registry.get(aid).meta or {}
            rows.append(
                {
                    "id": aid,
                    "zoo": registry.get(aid).zoo,
                    "ic_mean": round(ic_mean, 6),
                    "ic_std": round(ic_std, 6),
                    "ir": round(ir, 4),
                    "t_stat": round(t_stat(ic_mean, ic_std, n), 3),
                    "ic_positive_ratio": round(pos, 4),
                    "ic_count": n,
                    "category": categorise(ic_mean, ic_std, pos, n),
                    "theme": ",".join(meta.get("theme", []) or []),
                    "formula_latex": meta.get("formula_latex", ""),
                }
            )
        except (SkipAlpha, RegistryError, RuntimeError, KeyError, ValueError) as exc:
            skipped.append({"id": aid, "reason": str(exc)})
        except Exception as exc:  # noqa: BLE001 — isolate one bad alpha, keep going
            logger.exception("unexpected failure on %s", aid)
            skipped.append({"id": aid, "reason": f"unexpected: {exc}"})

        if idx % 50 == 0 or idx == total:
            print(f"  ... {idx}/{total} alphas evaluated", file=sys.stderr)

    return rows, skipped


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_table(rows: list[dict[str, Any]], top: int) -> None:
    if not rows:
        print("\nNo alphas produced an IC series — check you have enough symbols per bar.")
        return
    by_ir = sorted(rows, key=lambda r: r["ir"], reverse=True)
    hdr = f"{'rank':>4}  {'alpha_id':<18} {'zoo':<9} {'IC':>9} {'IR':>8} {'t':>7} {'IC+%':>6} {'N':>5}  cat"
    print(f"\nTop {min(top, len(by_ir))} by IR")
    print(hdr)
    print("-" * len(hdr))
    for i, r in enumerate(by_ir[:top], start=1):
        print(
            f"{i:>4}  {r['id']:<18} {r['zoo']:<9} {r['ic_mean']:>9.4f} "
            f"{r['ir']:>8.3f} {r['t_stat']:>7.2f} {r['ic_positive_ratio']*100:>5.1f}% "
            f"{r['ic_count']:>5}  {r['category']}"
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Standalone alpha-zoo IC benchmark (no network, no LLM, no shell).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("data", nargs="?", help="Long/tidy OHLCV CSV or Parquet.")
    ap.add_argument("--zoo", help="Filter to one zoo: alpha101 | gtja191 | qlib158 | academic.")
    ap.add_argument("--theme", help="Filter to one theme tag (e.g. momentum, reversal, volume).")
    ap.add_argument("--top", type=int, default=20, help="How many top-IR alphas to print.")
    ap.add_argument("--horizon", type=int, default=1, help="Forward-return horizon in bars.")
    ap.add_argument("--date-col", default="date")
    ap.add_argument("--symbol-col", default="symbol")
    ap.add_argument("--open-col", default="open")
    ap.add_argument("--high-col", default="high")
    ap.add_argument("--low-col", default="low")
    ap.add_argument("--close-col", default="close")
    ap.add_argument("--volume-col", default="volume")
    ap.add_argument("--amount-col", default="amount")
    ap.add_argument("--out", help="Write full per-alpha results to this CSV.")
    ap.add_argument("--list-zoos", action="store_true", help="Print registry health and exit.")
    args = ap.parse_args(argv)

    registry = get_default_registry()
    health = registry.health()

    if args.list_zoos:
        print(f"Registry: {health['loaded']} alphas loaded, {health['failed']} failed.")
        counts: dict[str, int] = {}
        for aid in registry.list():
            counts[registry.get(aid).zoo] = counts.get(registry.get(aid).zoo, 0) + 1
        for zoo, n in sorted(counts.items()):
            print(f"  {zoo:<12} {n:>4} alphas")
        if health["failed"]:
            for e in health["errors"][:10]:
                print(f"  ! {e['alpha_id']}: {e['reason']}", file=sys.stderr)
        return 0

    if not args.data:
        ap.error("DATA file is required (or use --list-zoos)")

    if args.horizon < 1:
        ap.error("--horizon must be >= 1 (lookahead ban)")

    data_path = Path(args.data).expanduser()
    if not data_path.is_file():
        ap.error(f"data file not found: {data_path}")

    col_map = {
        "open": args.open_col,
        "high": args.high_col,
        "low": args.low_col,
        "close": args.close_col,
        "volume": args.volume_col,
        "amount": args.amount_col,
    }

    print(f"Loading {data_path} ...", file=sys.stderr)
    panel = load_panel(
        data_path, date_col=args.date_col, symbol_col=args.symbol_col, col_map=col_map
    )
    n_dates, n_syms = panel["close"].shape
    print(
        f"Panel: {n_dates} bars x {n_syms} symbols "
        f"(fields: {sorted(panel.keys())})",
        file=sys.stderr,
    )
    if n_syms < 5:
        print(
            f"WARNING: only {n_syms} symbols — cross-sectional IC needs >=5 valid "
            "names per bar to score a date. Results will be sparse or empty.",
            file=sys.stderr,
        )

    return_df = forward_returns(panel, args.horizon)

    alpha_ids = registry.list(zoo=args.zoo or None, theme=args.theme or None)
    if not alpha_ids:
        print(
            f"No alphas matched (zoo={args.zoo!r}, theme={args.theme!r}). "
            f"Loaded zoos: see --list-zoos.",
            file=sys.stderr,
        )
        return 1
    print(f"Benchmarking {len(alpha_ids)} alphas (horizon={args.horizon}) ...", file=sys.stderr)

    rows, skipped = run(panel, return_df, alpha_ids, registry)

    cats = {"alive": 0, "reversed": 0, "dead": 0}
    for r in rows:
        cats[r["category"]] += 1
    print(
        f"\nResult: {len(rows)} scored, {len(skipped)} skipped  |  "
        f"alive={cats['alive']}  reversed={cats['reversed']}  dead={cats['dead']}"
    )
    _print_table(rows, args.top)

    if rows:
        worst = sorted(rows, key=lambda r: r["ic_mean"])[:5]
        print("\nMost-reversed (lowest IC mean):")
        for r in worst:
            print(f"  {r['id']:<18} IC={r['ic_mean']:>9.4f}  t={r['t_stat']:>6.2f}  {r['category']}")

    if args.out:
        out_path = Path(args.out).expanduser()
        pd.DataFrame(rows).to_csv(out_path, index=False)
        print(f"\nFull results -> {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
