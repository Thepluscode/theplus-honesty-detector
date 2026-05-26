#!/usr/bin/env python3
"""Index-reconstitution free pre-check — S&P 600 ADD inclusion run-up.

Implements §8 of research/EDGE_HYPOTHESIS_smallcap_index_recon.md (long/add side,
free data). Tests the "index effect": forced index-fund buying near the effective
date pushes added small-caps up. We proxy announce->effective with a fixed window:
buy 5 trading days BEFORE the effective date, sell at the effective-date close,
net of 30bps. ADD events come from the Wikipedia S&P 600 "changes" table (free);
prices from yfinance (free).

Caveats (honest): the Wikipedia date is the EFFECTIVE date — announce is proxied
as effective-5d (S&P typically announces ~1 week prior). Survivorship: added names
are alive (long-side OK). Sample = whatever Wikipedia lists. NOT the full study.

Gate (pre-registered): net mean > 0 AND date-clustered t >= 2.0 AND >= 60% of
annual cohorts net-positive.
"""
from __future__ import annotations
import argparse, io, json, os, sys, time, warnings
from datetime import datetime, timezone
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

COST_ROUNDTRIP = 0.003   # 30 bps (SP600 names, per the spec)
LEAD = 5                 # trading days before effective date = announce proxy / entry
UA = {"User-Agent": "Mozilla/5.0 (research edge-check)"}


def get_add_events() -> pd.DataFrame:
    import httpx
    r = httpx.get("https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
                  headers=UA, timeout=30, follow_redirects=True)
    tbls = pd.read_html(io.StringIO(r.text))
    ch = None
    for t in tbls:
        flat = " ".join(str(c) for c in t.columns).lower()
        if "date" in flat and "added" in flat and "removed" in flat:
            ch = t; break
    if ch is None:
        raise RuntimeError("changes table not found on Wikipedia page")
    ch.columns = ["_".join(str(x) for x in c) if isinstance(c, tuple) else str(c) for c in ch.columns]
    dcol = next(c for c in ch.columns if c.lower().startswith("date"))
    acol = next(c for c in ch.columns if "added" in c.lower() and "ticker" in c.lower())
    out = []
    for _, row in ch.iterrows():
        tk = str(row[acol]).strip().upper()
        if not tk or tk in ("NAN", "—", "-", ""):
            continue
        d = pd.to_datetime(str(row[dcol]), errors="coerce")
        if pd.isna(d):
            continue
        out.append((tk.replace(".", "-"), d.normalize()))
    df = pd.DataFrame(out, columns=["ticker", "eff_date"]).drop_duplicates()
    return df


def price_history(tk: str):
    import yfinance as yf
    px = yf.Ticker(tk).history(start="2014-01-01", auto_adjust=True)
    if px is None or len(px) < LEAD + 5:
        return None
    ix = pd.to_datetime(px.index)
    px.index = (ix.tz_convert(None) if ix.tz is not None else ix).normalize()
    return px[~px.index.duplicated()].sort_index()


def cluster_t(df: pd.DataFrame) -> float:
    """t on per-effective-date mean net (clusters same-rebalance adds)."""
    g = df.groupby("eff_date")["net"].mean()
    n = len(g)
    if n < 2 or g.std(ddof=1) == 0:
        return 0.0
    return float(g.mean() / (g.std(ddof=1) / np.sqrt(n)))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="reports/index_recon_precheck.json")
    a = p.parse_args(argv)

    ev = get_add_events()
    print(f"S&P 600 ADD events from Wikipedia: {len(ev)} "
          f"({ev['eff_date'].min().date()}..{ev['eff_date'].max().date()})")
    rows = []
    tickers = sorted(ev["ticker"].unique())
    cache = {}
    ok = fail = 0
    for i, tk in enumerate(tickers, 1):
        try:
            cache[tk] = price_history(tk); ok += 1 if cache[tk] is not None else 0
        except Exception:
            cache[tk] = None; fail += 1
        if i % 25 == 0:
            print(f"  ...priced {i}/{len(tickers)} tickers")
        time.sleep(0.2)

    for _, e in ev.iterrows():
        px = cache.get(e["ticker"])
        if px is None:
            continue
        dates = px.index
        idx = dates.searchsorted(e["eff_date"], side="left")
        if idx < LEAD + 1 or idx >= len(dates):
            continue
        c = px["Close"].values
        entry, exit_ = c[idx - LEAD], c[idx]
        if entry <= 0 or exit_ <= 0 or c[idx - 1] <= 0:
            continue
        net = exit_ / entry - 1.0 - COST_ROUNDTRIP                       # eff-5 -> eff (run-up)
        net_day = c[idx] / c[idx - 1] - 1.0                              # single effective-day bar (gross)
        net_post = (c[idx + 5] / exit_ - 1.0 - COST_ROUNDTRIP) if idx + 5 < len(dates) else float("nan")  # eff -> eff+5
        rows.append((e["ticker"], e["eff_date"], e["eff_date"].strftime("%Y"),
                     float(net), float(net_day), float(net_post)))

    print(f"\ntickers priced ok={ok} | usable ADD events={len(rows)}")
    if len(rows) < 30:
        print("INSUFFICIENT EVENTS — Verdict: INCONCLUSIVE.")
        return 0

    df = pd.DataFrame(rows, columns=["ticker", "eff_date", "year", "net", "net_day", "net_post"])
    mean_net = df["net"].mean()
    t = cluster_t(df)
    per_year = df.groupby("year")["net"].mean()
    cohorts_pos = (per_year > 0).mean()
    day_mean = df["net_day"].mean()
    _post = df.dropna(subset=["net_post"])[["eff_date", "net_post"]].rename(columns={"net_post": "net"})
    post_mean = float(_post["net"].mean()) if len(_post) else float("nan")
    post_t = cluster_t(_post) if len(_post) else 0.0

    print("\n========= INDEX-RECON PRE-CHECK RESULT (S&P 600 adds, long, free) =========")
    print(f"events: {len(df)} across {df['eff_date'].nunique()} reconstitution dates, "
          f"{df['ticker'].nunique()} tickers, {per_year.index.min()}-{per_year.index.max()}")
    print(f"net mean return/event (announce~eff-5d -> eff close, after {COST_ROUNDTRIP:.1%}): {mean_net:+.3%}")
    print(f"date-clustered t-stat: {t:+.2f}")
    print(f"annual cohorts net-positive: {cohorts_pos:.0%} ({(per_year>0).sum()}/{len(per_year)})")
    print("per-year net mean:")
    for y, v in per_year.items():
        print(f"   {y}: {v:+.3%}  (n={int((df['year']==y).sum())})")
    print(f"robustness — effective-day bar (eff-1->eff) mean: {day_mean:+.3%}  "
          f"(= {day_mean/mean_net:.0%} of the run-up; a big share = concentrated event-day jump / look-ahead risk)")
    print(f"robustness — post-effective (eff->eff+5) mean: {post_mean:+.3%}  clustered-t = {post_t:+.2f}  "
          f"(real index effect predicts <= 0 reversion; positive here = suspicious)")
    gate = (mean_net > 0) and (t >= 2.0) and (cohorts_pos >= 0.60)
    print("-" * 78)
    print(f"GATE (net>0 AND t>=2.0 AND >=60% cohorts+): "
          f"{'PASS -> worth paid-data study' if gate else 'FAIL -> archive (free gate saved the spend)'}")
    print("CAVEATS: Wikipedia date = effective (announce proxied as eff-5d); survivorship "
          "(adds alive); sample = Wikipedia changes only; long-side only.")
    print("=" * 78)

    os.makedirs("reports", exist_ok=True)
    with open(a.out, "w") as f:
        json.dump({"computed_at": datetime.now(timezone.utc).isoformat(),
                   "n_events": len(df), "mean_net": mean_net, "date_clustered_t": t,
                   "cohorts_positive": cohorts_pos,
                   "per_year": {k: float(v) for k, v in per_year.items()},
                   "gate_pass": bool(gate), "cost_roundtrip": COST_ROUNDTRIP, "lead_days": LEAD}, f, indent=2)
    print(f"report: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
