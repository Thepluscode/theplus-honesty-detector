#!/usr/bin/env python3
"""Generate a synthetic multi-symbol OHLCV CSV for trying alpha_bench.py.

Produces a long/tidy file with a deliberately *planted* cross-sectional
momentum effect, so a benchmark run shows some live momentum/reversal alphas
rather than an all-dead random panel. Replace this with your own universe
(e.g. an Alpaca multi-stock export) for real research.

    python3 make_sample_data.py --symbols 40 --days 500 --out sample_universe.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", type=int, default=40)
    ap.add_argument("--days", type=int, default=500)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="sample_universe.csv")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    dates = pd.bdate_range("2021-01-04", periods=args.days)
    symbols = [f"SYM{i:02d}" for i in range(args.symbols)]

    rows = []
    # Per-symbol latent momentum loading: tomorrow's return leans on a decaying
    # average of recent returns (planted signal a momentum factor can detect).
    prev_ret = np.zeros(args.symbols)
    price = rng.uniform(20, 200, args.symbols)
    for d in dates:
        noise = rng.normal(0, 0.015, args.symbols)
        ret = 0.15 * prev_ret + noise  # weak autocorrelation -> momentum signal
        prev_ret = ret
        close = price * (1 + ret)
        high = np.maximum(price, close) * (1 + rng.uniform(0, 0.01, args.symbols))
        low = np.minimum(price, close) * (1 - rng.uniform(0, 0.01, args.symbols))
        open_ = price
        volume = rng.uniform(1e5, 5e6, args.symbols)
        for i, sym in enumerate(symbols):
            rows.append(
                (d.date().isoformat(), sym, round(open_[i], 4), round(high[i], 4),
                 round(low[i], 4), round(close[i], 4), int(volume[i]))
            )
        price = close

    df = pd.DataFrame(
        rows, columns=["date", "symbol", "open", "high", "low", "close", "volume"]
    )
    out = Path(args.out)
    df.to_csv(out, index=False)
    print(f"Wrote {len(df):,} rows ({args.symbols} symbols x {args.days} days) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
