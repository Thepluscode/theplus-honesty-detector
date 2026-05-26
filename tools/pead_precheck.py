#!/usr/bin/env python3
"""PEAD free pre-check — small-cap post-earnings drift, reaction-based.

Implements §8 of research/EDGE_HYPOTHESIS_smallcap_pead.md: the $0, long-side,
survivorship-caveated kill-gate. Uses only free data (yfinance prices +
yfinance earnings dates). NOT the full study — a preliminary read that either
kills the idea cheaply or earns a paid-data deep dive.

Signal (no fitted thresholds):
  - reaction = announcement-session return (close/prev_close - 1)
  - volume confirmation: announcement volume >= 2x trailing-20d median
  - long the TOP DECILE of reaction (across the run's events) that are vol-confirmed
  - entry = NEXT session open (no look-ahead); exit = open 40 sessions later
  - net = (exit/entry - 1) - COST_ROUNDTRIP

Gate (pre-registered): net mean drift > 0 AND week-clustered t >= 2.0 AND
>= 60% of annual cohorts net-positive. Honest caveats printed with the result.
"""
from __future__ import annotations
import argparse, json, sys, time, warnings
from datetime import datetime, timezone
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

COST_ROUNDTRIP = 0.004   # 40 bps, per the spec's pessimistic small-cap model
HOLD = 40                # trading days
VOL_MULT = 2.0           # volume confirmation
TOP_DECILE = 0.10

# Fallback small-cap-ish universe if the S&P 600 fetch fails (kept modest).
_FALLBACK = ["PLUG","FUBO","SFIX","GPRO","RIG","AMC","BBBY","CLF","SAVE","RUN",
    "FSLR","CROX","SKX","BLDR","BLD","EXP","MUR","CIVI","SM","CALX","AEIS","KFY",
    "SPSC","SPNS","UFPI","MMSI","STAA","CVCO","PRGS","SLAB","SANM","POWI","RMBS",
    "AVAV","MGY","ENSG","SHAK","WING","PRDO","CEIX","ARCH","HCC","BTU","GES",
    "ZEUS","KBH","MHO","TMHC","SKY","CVI","DK","PBF","WKC","ANDE","CALM","SEB",
    "JBLU","ALK","HA","ATSG","SNCY","SBLK","GNK","DAC","KSS","M","JWN","GPS"]


def get_universe(max_tickers: int) -> list[str]:
    try:
        tbls = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_600_companies")
        for t in tbls:
            for col in ("Symbol", "Ticker symbol", "Ticker"):
                if col in t.columns:
                    syms = [str(s).replace(".", "-").strip().upper() for s in t[col].tolist()]
                    syms = [s for s in syms if s and s.isascii() and 1 <= len(s) <= 6]
                    if len(syms) > 100:
                        print(f"universe: S&P 600 from Wikipedia, {len(syms)} symbols")
                        return syms[:max_tickers]
    except Exception as e:
        print(f"universe: Wikipedia fetch failed ({str(e)[:60]}); using fallback list")
    return _FALLBACK[:max_tickers]


def events_for_ticker(tk: str):
    import yfinance as yf
    out = []
    t = yf.Ticker(tk)
    px = t.history(start="2018-01-01", auto_adjust=False)
    if px is None or len(px) < HOLD + 60 or "Volume" not in px.columns:
        return out
    px = px.copy()
    _ix = pd.to_datetime(px.index)
    px.index = (_ix.tz_convert(None) if _ix.tz is not None else _ix).normalize()
    px = px[~px.index.duplicated()].sort_index()
    close = px["Close"].values
    openp = px["Open"].values
    vol = px["Volume"].values
    med20 = px["Volume"].rolling(20).median().shift(1).values  # trailing, excl. day
    dates = px.index
    ed = t.get_earnings_dates(limit=40)
    if ed is None or len(ed) == 0:
        return out
    def _naive(d):
        ts = pd.Timestamp(d)
        return (ts.tz_convert(None) if ts.tz is not None else ts).normalize()
    edates = sorted({_naive(d) for d in ed.index if pd.notna(d)})
    pos = {d: i for i, d in enumerate(dates)}
    for d in edates:
        # announcement session = first trading day >= earnings date
        idx = dates.searchsorted(d, side="left")
        if idx <= 20 or idx + HOLD + 1 >= len(dates):
            continue
        if close[idx - 1] <= 0 or med20[idx] in (0, np.nan) or np.isnan(med20[idx]):
            continue
        reaction = close[idx] / close[idx - 1] - 1.0
        vr = vol[idx] / med20[idx] if med20[idx] > 0 else 0.0
        entry = openp[idx + 1]
        exit_ = openp[idx + 1 + HOLD]
        if entry <= 0 or exit_ <= 0:
            continue
        gross = exit_ / entry - 1.0
        net = gross - COST_ROUNDTRIP
        wk = dates[idx].strftime("%G-W%V")
        out.append((tk, dates[idx].date().isoformat(), wk, float(reaction), float(vr), float(net)))
    return out


def cluster_t(df: pd.DataFrame) -> float:
    """t-stat on week-level mean drift (clusters correlated same-week events)."""
    wk = df.groupby("week")["net"].mean()
    n = len(wk)
    if n < 2 or wk.std(ddof=1) == 0:
        return 0.0
    return float(wk.mean() / (wk.std(ddof=1) / np.sqrt(n)))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--max-tickers", type=int, default=120)
    p.add_argument("--out", default="reports/pead_precheck.json")
    a = p.parse_args(argv)

    uni = get_universe(a.max_tickers)
    print(f"running on {len(uni)} tickers (free yfinance data)\n")
    rows = []
    ok = fail = 0
    for i, tk in enumerate(uni, 1):
        try:
            ev = events_for_ticker(tk)
            rows.extend(ev); ok += 1
        except Exception as e:
            fail += 1
            if fail <= 5:
                print(f"  {tk}: skip ({str(e)[:50]})")
        if i % 20 == 0:
            print(f"  ...{i}/{len(uni)} tickers, {len(rows)} events so far")
        time.sleep(0.25)

    print(f"\ntickers ok={ok} fail={fail} | total events={len(rows)}")
    if len(rows) < 50:
        print("INSUFFICIENT EVENTS — data pull too thin to judge. Verdict: INCONCLUSIVE.")
        return 0

    df = pd.DataFrame(rows, columns=["ticker","date","week","reaction","vol_ratio","net"])
    df["year"] = df["date"].str[:4]
    # top-decile positive reaction, volume-confirmed = the long basket
    thr = df["reaction"].quantile(1 - TOP_DECILE)
    longs = df[(df["reaction"] >= thr) & (df["vol_ratio"] >= VOL_MULT)].copy()
    print(f"reaction top-decile threshold = {thr:+.2%} | long events (vol-confirmed) = {len(longs)}")
    if len(longs) < 30:
        print("INSUFFICIENT LONG EVENTS — Verdict: INCONCLUSIVE (need more tickers/history).")
        return 0

    mean_net = longs["net"].mean()
    t = cluster_t(longs)
    per_year = longs.groupby("year")["net"].mean()
    cohorts_pos = (per_year > 0).mean()

    print("\n================ PEAD PRE-CHECK RESULT (long-side, free, sample) ================")
    print(f"long events: {len(longs)}  across {longs['week'].nunique()} earnings-weeks, "
          f"{longs['ticker'].nunique()} tickers, years {per_year.index.min()}-{per_year.index.max()}")
    print(f"net mean drift/event (40d, after {COST_ROUNDTRIP:.1%} cost): {mean_net:+.3%}")
    print(f"week-clustered t-stat: {t:+.2f}")
    print(f"annual cohorts net-positive: {cohorts_pos:.0%}  ({(per_year>0).sum()}/{len(per_year)})")
    print("per-year net mean:")
    for y, v in per_year.items():
        print(f"   {y}: {v:+.3%}  (n={int((longs['year']==y).sum())})")
    gate = (mean_net > 0) and (t >= 2.0) and (cohorts_pos >= 0.60)
    print("-" * 80)
    print(f"GATE (net>0 AND t>=2.0 AND >=60% cohorts+): {'PASS -> worth paid-data study' if gate else 'FAIL -> archive (free gate saved the spend)'}")
    print("CAVEATS: survivorship-biased (current S&P600 = alive names); yfinance "
          "earnings dates ~5-6yr; long-side only; sample not full universe. A PASS "
          "here is necessary-not-sufficient; a FAIL is a strong kill signal.")
    print("=" * 80)

    try:
        import os
        os.makedirs("reports", exist_ok=True)
        with open(a.out, "w") as f:
            json.dump({"computed_at": datetime.now(timezone.utc).isoformat(),
                       "n_events": len(df), "n_long": len(longs),
                       "mean_net": mean_net, "week_clustered_t": t,
                       "cohorts_positive": cohorts_pos,
                       "per_year": {k: float(v) for k, v in per_year.items()},
                       "gate_pass": bool(gate),
                       "cost_roundtrip": COST_ROUNDTRIP, "hold_days": HOLD}, f, indent=2)
        print(f"report: {a.out}")
    except Exception as e:
        print("report write failed:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
