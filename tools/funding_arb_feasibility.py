#!/usr/bin/env python3
"""
Funding-rate arbitrage — HISTORICAL feasibility study (not a trading bot).

The existing tools/funding_rate_arb_paper.py is a FORWARD paper
simulator: it needs ~10 real days to collect ~30 funding cycles and
only ever samples one regime. That can't answer the feasibility
question. This tool answers it: pull the FULL historical 8h funding
series from Binance's public endpoint (BTC goes back to 2019-09-10 —
COVID crash, 2021 boom, LUNA/FTX 2022 unwind, 2023 compression,
2024-26) and simulate the delta-neutral funding-capture strategy
across ALL of it, net of every cost, with a per-year regime
breakdown and a falsifiable verdict.

Same anti-self-deception discipline as tools/strategy_edge_audit.py:
no tuning, no flattery, model the costs that flatter you the least.

STRATEGY MODELLED
  Always position delta-neutral to RECEIVE funding:
    funding>0  -> short perp + long spot   (receive rate*notional)
    funding<0  -> long perp  + short spot  (receive |rate|*notional)
  Flip direction whenever the funding sign flips; pay full round-trip
  cost on every flip and on the initial open.

COSTS MODELLED (all of them — including the two the paper sim skips)
  * Trading fees: FEE_BPS_PER_LEG per leg, both legs, every flip+open.
  * Slippage: --slippage-bps per leg per rebalance.
  * Spot borrow cost: when SHORT spot (funding<0 direction), pay
    --borrow-apr on the notional for the time held. The paper sim
    explicitly does NOT model this; a feasibility study must.

COSTS NOT MODELLED (stated, not hidden — these UNDERSTATE real risk)
  * Perp liquidation / exchange-counterparty tail risk.
  * Intra-cycle spot/perp basis tracking error.
  * Funding-rate execution noise (uses the realised printed rate).
  * Capacity / market impact at size.
  A strategy that fails THIS optimistic model fails reality harder.

Usage:
  python tools/funding_arb_feasibility.py --symbols BTCUSDT,ETHUSDT \\
      --notional 1000 --report-out reports/funding_arb_feasibility.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Reused from tools/funding_rate_arb_skeleton.py for consistency.
FEE_BPS_PER_LEG = 5.0          # 0.05% taker per leg (Binance-realistic)
SAMPLES_PER_DAY = 3            # funding every 8h
DAYS_PER_YEAR = 365
_HIST_URL = "https://fapi.binance.com/fapi/v1/fundingRate"


def _fetch_funding_history(symbol: str, timeout: float = 20.0) -> list[dict]:
    """Paginate the full public funding-rate history for one perp.

    No auth. Binance caps each page at 1000 rows; walk forward by
    fundingTime until exhausted.
    """
    out: list[dict] = []
    # Binance returns the MOST RECENT page when no startTime is given,
    # which makes forward-pagination exhaust immediately. Start from a
    # fixed pre-history epoch (2019-01-01; perp funding began ~2019-09)
    # and always walk forward by fundingTime.
    start = 1546300800000  # 2019-01-01T00:00:00Z in ms
    while True:
        url = f"{_HIST_URL}?symbol={symbol}&limit=1000&startTime={start}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                page = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            raise SystemExit(f"{symbol}: network error: {e}") from None
        if not page:
            break
        if out and page[0]["fundingTime"] <= out[-1]["fundingTime"]:
            page = [p for p in page if p["fundingTime"] > out[-1]["fundingTime"]]
            if not page:
                break
        out.extend(page)
        if len(page) < 1000:
            break
        start = page[-1]["fundingTime"] + 1
        time.sleep(0.25)  # be polite to the public endpoint
    return out


def _simulate(symbol: str, hist: list[dict], notional: float,
              slippage_bps: float, borrow_apr: float,
              deadband: float = 0.0) -> dict:
    """Delta-neutral funding capture over the full history, net of all
    modelled costs. Returns metrics + per-year regime breakdown.

    ``deadband`` (per-8h rate, e.g. 0.0001 = 0.01%): when |rate| is
    below it, hold NO position this cycle (FLAT) — collect nothing,
    but pay no flip cost on funding-sign noise near zero. This is the
    flip-discipline rule. deadband=0.0 reproduces the naive
    always-in, flip-on-every-sign-change behaviour.

    Economic justification (not date-fitting): only take the position
    when the premium is large enough to be worth a round-trip; the
    sign noise that causes churn happens precisely when |rate|~0.
    """
    if len(hist) < 100:
        return {"symbol": symbol, "error": f"only {len(hist)} funding points"}

    fee_roundtrip = 2 * (FEE_BPS_PER_LEG / 10_000) * notional        # both legs
    slip_roundtrip = 2 * (slippage_bps / 10_000) * notional          # both legs
    open_flip_cost = fee_roundtrip + slip_roundtrip
    borrow_per_cycle = borrow_apr * notional / (SAMPLES_PER_DAY * DAYS_PER_YEAR)

    cycle_pnls: list[float] = []
    per_year: dict[str, dict] = defaultdict(
        lambda: {"gross": 0.0, "net": 0.0, "cycles": 0, "flips": 0})
    state = 0          # -1 long-perp, 0 flat, +1 short-perp
    flips = 0
    gross_total = 0.0
    net_total = 0.0
    cost_total = 0.0

    for i, row in enumerate(hist):
        rate = float(row["fundingRate"])
        ts = datetime.fromtimestamp(row["fundingTime"] / 1000, tz=timezone.utc)
        yr = str(ts.year)

        # Desired state under the deadband rule.
        if abs(rate) < deadband:
            desired = 0                          # FLAT — premium too small
        else:
            desired = 1 if rate > 0 else -1      # position to RECEIVE

        cost = 0.0
        if desired != state:                     # any state change => round-trip
            # Opening from flat, closing to flat, or flipping all cost a
            # neutral-pair round-trip in this model.
            if not (state == 0 and desired == 0):
                cost += open_flip_cost
                if i != 0 and state != 0 and desired != 0:
                    flips += 1
                    per_year[yr]["flips"] += 1
            state = desired

        # Gross funding only while actually in a position.
        gross = abs(rate) * notional if state != 0 else 0.0
        # Borrow cost only while short the spot leg (long-perp state).
        if state < 0:
            cost += borrow_per_cycle

        net = gross - cost
        cycle_pnls.append(net)
        gross_total += gross
        cost_total += cost
        net_total += net
        per_year[yr]["gross"] += gross
        per_year[yr]["net"] += net
        per_year[yr]["cycles"] += 1

    n = len(cycle_pnls)
    span_days = (hist[-1]["fundingTime"] - hist[0]["fundingTime"]) / 1000 / 86400
    years = span_days / 365 if span_days else 1e-9
    net_ann_pct = (net_total / notional) / years * 100
    gross_ann_pct = (gross_total / notional) / years * 100

    # Sharpe of the per-cycle net P&L (annualised: 3*365 cycles/yr).
    mean = net_total / n
    var = sum((x - mean) ** 2 for x in cycle_pnls) / n
    sd = var ** 0.5
    sharpe = (mean / sd) * ((SAMPLES_PER_DAY * DAYS_PER_YEAR) ** 0.5) if sd > 0 else 0.0

    # Max drawdown on the cumulative net curve.
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in cycle_pnls:
        cum += x
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    max_dd_pct = max_dd / notional * 100

    pos_cycles = sum(1 for x in cycle_pnls if x > 0)

    yearly = []
    worst_year_net_pct = 999.0
    for yr in sorted(per_year):
        py = per_year[yr]
        net_pct = py["net"] / notional * 100
        worst_year_net_pct = min(worst_year_net_pct, net_pct)
        yearly.append({
            "year": yr, "cycles": py["cycles"], "flips": py["flips"],
            "gross_pct": round(py["gross"] / notional * 100, 2),
            "net_pct": round(net_pct, 2),
        })

    # Falsifiable verdict: net-positive EVERY year (incl. the worst),
    # net Sharpe >= 0.5, and net annualised return clears a 5% hurdle
    # (you can put cash in T-bills for ~4-5% with zero crypto tail risk).
    edge = (
        worst_year_net_pct > 0.0
        and sharpe >= 0.5
        and net_ann_pct >= 5.0
    )

    return {
        "symbol": symbol,
        "funding_points": n,
        "span_days": round(span_days, 1),
        "first": datetime.fromtimestamp(hist[0]["fundingTime"]/1000,
                                        tz=timezone.utc).date().isoformat(),
        "last": datetime.fromtimestamp(hist[-1]["fundingTime"]/1000,
                                       tz=timezone.utc).date().isoformat(),
        "flips": flips,
        "gross_ann_pct": round(gross_ann_pct, 2),
        "net_ann_pct": round(net_ann_pct, 2),
        "cost_drag_ann_pct": round(gross_ann_pct - net_ann_pct, 2),
        "net_sharpe": round(sharpe, 2),
        "max_dd_pct": round(max_dd_pct, 2),
        "pct_cycles_net_positive": round(pos_cycles / n * 100, 1),
        "worst_year_net_pct": round(worst_year_net_pct, 2),
        "by_year": yearly,
        "verdict": "VIABLE EDGE" if edge else "NO VIABLE EDGE",
        "criteria": {
            "every_year_net_positive": worst_year_net_pct > 0.0,
            "net_sharpe>=0.5": sharpe >= 0.5,
            "net_ann>=5pct_tbill_hurdle": net_ann_pct >= 5.0,
        },
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--symbols", default="BTCUSDT,ETHUSDT",
                   help="comma-separated Binance perp symbols")
    p.add_argument("--notional", type=float, default=1000.0)
    p.add_argument("--slippage-bps", type=float, default=2.0,
                   help="per-leg slippage in bps applied each rebalance")
    p.add_argument("--borrow-apr", type=float, default=0.10,
                   help="annual borrow cost on short-spot legs (default 10%%)")
    p.add_argument("--deadband-bps", type=float, default=0.0,
                   help="single-run flip-discipline deadband, per-8h bps "
                        "(0 = naive always-in)")
    p.add_argument("--sweep", action="store_true",
                   help="robustness sweep across a deadband grid — a real "
                        "edge works across a WIDE band, an overfit one "
                        "spikes at one threshold")
    p.add_argument("--report-out", type=Path, default=None)
    args = p.parse_args(argv)

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    print(f"Funding-arb feasibility | notional ${args.notional:,.0f} | "
          f"fee {FEE_BPS_PER_LEG}bps/leg | slip {args.slippage_bps}bps/leg | "
          f"borrow {args.borrow_apr*100:.0f}% APR\n")

    # Fetch each symbol's full history ONCE; replay it for every deadband.
    hist_by_sym: dict[str, list] = {}
    for sym in symbols:
        print(f"  fetching {sym} full history ...", flush=True)
        try:
            hist_by_sym[sym] = _fetch_funding_history(sym)
        except SystemExit as e:
            hist_by_sym[sym] = e  # type: ignore

    if args.sweep:
        # Economically-spaced grid (per-8h rate). NOT optimised — fixed.
        grid_bps = [0.0, 0.2, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0]
        print("\n" + "=" * 96)
        print("FLIP-DISCIPLINE ROBUSTNESS SWEEP — net ann% (worst single year%) per deadband")
        print("A real edge: net-positive worst-year across a WIDE band. "
              "Overfit: a lone spike.")
        print("=" * 96)
        sweep_results = []
        for sym in symbols:
            h = hist_by_sym[sym]
            if isinstance(h, SystemExit):
                print(f"{sym}: ERROR {h}")
                continue
            print(f"\n{sym}:")
            print(f"  {'deadband/8h':>12} {'netAnn%':>9} {'worstYr%':>9} "
                  f"{'Sharpe':>7} {'flips':>6}  robust?")
            for gb in grid_bps:
                m = _simulate(sym, h, args.notional, args.slippage_bps,
                              args.borrow_apr, deadband=gb / 10_000)
                ok = m["worst_year_net_pct"] > 0 and m["net_ann_pct"] >= 5.0
                print(f"  {gb:>10.1f}bps {m['net_ann_pct']:>9.1f} "
                      f"{m['worst_year_net_pct']:>9.2f} {m['net_sharpe']:>7.2f} "
                      f"{m['flips']:>6}  {'YES' if ok else 'no'}")
                sweep_results.append({"symbol": sym, "deadband_bps": gb, **m})
        # Robustness verdict: a contiguous band of >=3 grid points passing.
        print("\n" + "=" * 96)
        for sym in symbols:
            srs = [r for r in sweep_results if r["symbol"] == sym]
            passes = [r["deadband_bps"] for r in srs
                      if r["worst_year_net_pct"] > 0 and r["net_ann_pct"] >= 5.0]
            n = len(passes)
            band = f"{min(passes):.1f}-{max(passes):.1f}bps" if passes else "none"
            verdict = ("ROBUST EDGE" if n >= 3 else
                       "FRAGILE/SINGLE-POINT (overfit risk)" if n in (1, 2) else
                       "NO EDGE AT ANY DEADBAND")
            print(f"{sym}: {n}/9 deadbands pass (band {band}) -> {verdict}")
        print("Bad years (2022 LUNA/FTX) decide. No tuning to specific dates.")
        print("=" * 96)
        if args.report_out:
            args.report_out.parent.mkdir(parents=True, exist_ok=True)
            with args.report_out.open("w") as f:
                json.dump({"method": "flip-discipline deadband robustness sweep",
                           "grid_bps": grid_bps,
                           "fee_bps_per_leg": FEE_BPS_PER_LEG,
                           "slippage_bps_per_leg": args.slippage_bps,
                           "borrow_apr": args.borrow_apr,
                           "notional": args.notional,
                           "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "sweep": sweep_results}, f, indent=2, default=str)
            print(f"\nReport: {args.report_out}")
        return 0

    results = []
    for sym in symbols:
        h = hist_by_sym[sym]
        if isinstance(h, SystemExit):
            results.append({"symbol": sym, "error": str(h)})
            continue
        print(f"  simulating {sym} (deadband {args.deadband_bps}bps) ...", flush=True)
        results.append(_simulate(sym, h, args.notional, args.slippage_bps,
                                  args.borrow_apr,
                                  deadband=args.deadband_bps / 10_000))

    print("\n" + "=" * 96)
    print("FUNDING-RATE ARB — HISTORICAL FEASIBILITY (delta-neutral, net of all modelled costs)")
    print("=" * 96)
    print(f"{'symbol':<10}{'pts':>6}{'yrs':>5}{'flips':>6}"
          f"{'grossAnn%':>10}{'netAnn%':>9}{'drag%':>7}"
          f"{'Sharpe':>7}{'maxDD%':>7}{'worstYr%':>9}  verdict")
    print("-" * 96)
    for r in results:
        if "error" in r:
            print(f"{r['symbol']:<10}  ERROR: {r['error'][:60]}")
            continue
        yrs = r["span_days"] / 365
        print(
            f"{r['symbol']:<10}{r['funding_points']:>6}{yrs:>5.1f}"
            f"{r['flips']:>6}{r['gross_ann_pct']:>10.1f}{r['net_ann_pct']:>9.1f}"
            f"{r['cost_drag_ann_pct']:>7.1f}{r['net_sharpe']:>7.2f}"
            f"{r['max_dd_pct']:>7.1f}{r['worst_year_net_pct']:>9.2f}  {r['verdict']}"
        )
    print("-" * 96)
    for r in results:
        if "error" in r or "by_year" not in r:
            continue
        print(f"\n{r['symbol']} per-year net (the regime test — bad years matter most):")
        for y in r["by_year"]:
            mark = "" if y["net_pct"] > 0 else "  <-- LOSS YEAR"
            print(f"  {y['year']}: net {y['net_pct']:>+7.2f}%  "
                  f"gross {y['gross_pct']:>+7.2f}%  "
                  f"cycles {y['cycles']:>4} flips {y['flips']:>3}{mark}")
    n_viable = sum(1 for r in results if r.get("verdict") == "VIABLE EDGE")
    print("\n" + "=" * 96)
    print(f"VERDICT: {n_viable}/{len([r for r in results if 'error' not in r])} "
          f"symbols show a viable edge (net-positive EVERY year, Sharpe>=0.5, "
          f">=5% net ann. over a T-bill).")
    print("Costs NOT modelled (liquidation, basis tracking, capacity) make "
          "reality WORSE than this. No tuning, no flattery.")
    print("=" * 96)

    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        with args.report_out.open("w") as f:
            json.dump({
                "method": "historical delta-neutral funding capture, full "
                          "Binance public history, all modelled costs",
                "fee_bps_per_leg": FEE_BPS_PER_LEG,
                "slippage_bps_per_leg": args.slippage_bps,
                "borrow_apr": args.borrow_apr,
                "notional": args.notional,
                "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "results": results,
            }, f, indent=2, default=str)
        print(f"\nReport: {args.report_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
