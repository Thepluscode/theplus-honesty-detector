# EDGE FINDINGS — Definitive (2026-05-18)

> **Read this before writing or running any trading strategy in this repo.**
> This document is load-bearing. It records evidence, not opinion. Do not
> reopen these conclusions from optimism, and do not let an autonomous
> agent restart strategy tuning without overturning this evidence first.

## TL;DR

After ~1 year of development and a rigorous evidence pass on 2026-05-18:
**this toolset, at retail cost structure, contains no demonstrated
tradeable edge.** The engineering platform is strong. The alpha is absent.

| Path | Verdict | Evidence |
|------|---------|----------|
| Technical-analysis strategies (box, OBV, RSI2, Keltner, VWAP, breakout, adaptive) | **NO EDGE** | 0/110 walk-forward strategy-folds positive |
| Funding-rate arb — gross premium | Real (+~15%/yr, positive every year) | 6.7yr Binance history |
| Funding-rate arb — net, retail-harvestable | **NO EDGE** | 0/9 deadbands net-positive across regimes (BTC+ETH) |
| Cross-sectional factors (alpha-zoo 452) / Carhart momentum | **NO EDGE** | Best factor dead OOS (IC t 7.3→1.5); Ken French UMD t 4.52→0.67 since 2000, negative net of cost (2026-05-23) |

There is no honest path where more commits to these strategies become
profitable. The promotion pipeline that kept blocking strategies was
correct every time.

## 1. TA strategy edge audit

- Tool: `tools/strategy_edge_audit.py`
- Method: 3yr EURUSD 5m (218k bars), rolling 6mo/3mo walk-forward,
  **default params** (using tuned configs = in-sample overfitting,
  since they were fitted on this same data), normalised realistic
  cost (15-tick slippage), no per-fold tuning.
- Result: **0 of 7 on-design strategies show an edge. 0% positive
  folds across all 110 strategy-folds.** Aggregate Sharpe ranged
  −3.1 (best, OBV) to −17.1 (keltner_fade). Every raw signal loses
  money fast on realistic cost.
- Report: `reports/edge_audit_20260518.json`
- Implication: the strategies have no edge in their raw signal. A
  good-looking in-sample backtest produced by tuning a zero-edge
  signal on the same data is the textbook definition of overfitting.

## 2. Funding-rate arb feasibility

- Tool: `tools/funding_arb_feasibility.py`
- Method: full Binance public funding history (BTC 7328 pts / 6.7yr,
  ETH 7094 / 6.5yr; 2019→2026, all regimes), delta-neutral capture,
  net of fees (5bps/leg) + slippage (2bps/leg) + short-spot borrow
  (10% APR).
- Naive result: net **−7.9%** ann (BTC), −5.3% (ETH). BUT **gross is
  positive every single year** (~14-16% ann) including 2022's
  LUNA/FTX crash. The structural premium is economically real — the
  naive flip-on-every-sign-change execution destroys it via churn
  cost (~22% ann drag).
- Flip-discipline rescue test (`--sweep`, fixed 9-point deadband
  grid, NOT optimised): **0/9 deadbands net-positive across all
  regimes for BOTH BTC and ETH.** Best case ~break-even, below the
  ~5% risk-free T-bill hurdle, worst-year still negative.
- Reports: `reports/funding_arb_feasibility_20260518.json`,
  `reports/funding_arb_sweep_20260518.json`
- Implication: a real structural premium exists but is **not
  net-harvestable at retail cost**. Flip discipline does not rescue
  it at any threshold.

### Bounded caveat (not hope)

This is the verdict on the **retail-accessible** version (Binance
USDT-perp, simple delta-neutral, retail fees). Cross-exchange /
coin-margined / funding-market-making variants are untested and
require non-retail sophistication with generally worse retail
economics. The simple version a retail operator can run is dead.

### Refusals (recorded so the discipline is auditable)

- Did **not** test altcoins to hunt a winner — alts have higher
  borrow + more flip churn; BTC/ETH was the most favorable case by
  design. Testing alts after a BTC/ETH failure is goalpost-moving.
- Did **not** lower the cost assumptions to manufacture a pass.
  5bps/leg + 2bps slip is realistic-to-optimistic retail.

## 3. Cross-sectional factor hunt (alpha-zoo) + momentum validation (2026-05-23)

- Tool: `tools/alpha_zoo/` — 452 pure-pandas factors (alpha101 / gtja191 /
  qlib158 + FF5/Carhart, vendored from HKUDS/Vibe-Trading), Spearman rank-IC engine.
- Hunt result: of 452 factors, academic **Carhart momentum** (12-1 skip-month)
  was the standout — **in-sample only**. IC 0.039 / t 7.3 ("alive") in-sample
  collapses to IC 0.018 / t 1.5 ("dead") out-of-sample.
- **Data gate (2026-05-23):** the hunt ran on Alpaca + a *current* S&P 500
  snapshot → survivorship-biased upward (the code itself flags it at
  `tools/alpha_zoo/alpaca_to_csv.py:254`). All factors are price/volume-only
  (even FF5 uses price proxies), so validating the lead needs only
  delisting-inclusive prices + point-in-time index membership (~$50-80/mo via
  Sharadar/Norgate) — NOT fundamentals. Acquirable, so the gate was passable.
- **Free pre-check before any spend — Ken French UMD momentum factor**
  (survivorship-bias-free, cost-free, 1927→2026, n=1191 months):

  | Window | Sharpe | t-stat | Net Sharpe @ 4% cost |
  |--------|-------:|-------:|---------------------:|
  | Full (1927+) | 0.45 | 4.52 | 0.21 |
  | 2000+ | 0.13 | 0.67 | −0.10 |
  | 2010+ | 0.25 | 1.02 | −0.08 |
  | 2020+ | 0.21 | 0.53 | −0.07 |

  The century-long t-stat 4.52 collapses to 0.67 since 2000 (premium
  arbitraged away post-publication). Every recent window is gross Sharpe
  ~0.13–0.25 and **negative net of realistic momentum-turnover cost**
  (conclusion robust even at an optimistic 2%). Tail risk: −54% in the
  2009 momentum crash, −53% worst month.
- **Verdict: NO EDGE.** "Monthly factors persist" was the in-sample,
  survivorship-biased artifact. The textbook factor's *true* recent edge is
  ~0 and negative after costs; theplus-bot's noisier retail version on a
  smaller universe is strictly worse. **Momentum lead ARCHIVED — no data
  purchased, no point-in-time backtest built; the free gate saved the spend.**
- Bounded caveat (not hope): only **risk-managed / vol-scaled momentum** is
  empirically less-dead (it tames the crashes), but it is heavily arbitraged
  and not worth chasing at retail given this stack's base rate.
- Reproduce: Ken French `F-F_Momentum_Factor_CSV.zip`, gross + cost-netted
  Sharpe by window (script run 2026-05-23).

## What this project IS

A genuinely strong systematic-trading **research platform**: safety
gates, crash recovery, the promotion pipeline, observability, and —
proven on 2026-05-18 — honest evaluation harnesses that produce
falsifiable verdicts and refuse to flatter. That is rare and real.

## What this project is NOT

A profit engine. Not with TA. Not with retail funding carry.

## Operating rules that follow

1. **Do not run live/paper TA strategies expecting profit.** They
   have no edge; trading them only pays spreads to learn nothing.
2. **The platform stays** — it is the right harness for rigorously
   testing future edge hypotheses (it just did exactly that).
3. **Profitability, if pursued, is a NEW research project** with a
   different edge source (differentiated data, structural niche, or
   non-retail execution), entered with eyes open about the low base
   rate — not a continuation of this codebase's premise.
4. **No agent may restart strategy tuning** to chase profitability
   without first producing evidence that overturns §1 and §2 above,
   to the same standard (full-history, out-of-sample, real costs,
   no tuning, bad regimes decide).

## Appendix — Why it fails (the geometry, 2026-05-26)

The TA strategies here fail for the same **structural** reason, derivable without
a backtest: a low-win-rate breakout/mean-reversion system with a fixed
stop:target has its win rate set by **geometry** — P(hit target before stop) —
not by signal quality. With no predictive edge in the entry, the win rate lands
at the random-entry value implied by the payoff ratio, and realistic cost tips it
negative. Expectancy = WR·avgW − (1−WR)·|avgL|; on a no-signal base, tuning the
stop/target only slides you *along* the random-entry frontier (WR trades off
against payoff, expectancy pinned at ≈ −cost), and tuning parameters on the same
data just fits noise — which is the 0/110 OOS collapse in §1. So profit requires a
**genuine predictive edge or a structural/cost advantage** (a NEW edge source),
never a re-tune. This makes rule #4 *mathematically*, not just empirically, correct.

The sibling project's live trades make this quantitative — a live-trade audit of
the companion platform (crypto momentum: 33% WR vs 37% breakeven; stock ORB: 37%
vs 40% — both ~3–4 pts short, expectancy ≈ −cost). Details available on request.

## Cross-refs

- `reports/edge_audit_20260518.json` — full walk-forward results
- `reports/funding_arb_feasibility_20260518.json` — funding-arb simulation
- `reports/funding_arb_sweep_20260518.json` — deadband robustness sweep

---

## ✅ EDGE HUNT CLOSED — 2026-05-26

Five hypotheses were tested under the same falsifiable discipline (out-of-sample,
real costs, pre-registered pass/fail, cluster-robust statistics, no goalpost-moving):

| # | Hypothesis | Result | Free gate? |
|---|------------|--------|------------|
| 1 | TA strategies (box / OBV / Keltner / VWAP / breakout) | NO EDGE (0/110 walk-forward folds, EURUSD 5m) | — |
| 2 | Retail funding-rate arb (BTC/ETH, 6.7yr history) | NO EDGE (0/9 deadbands net-positive) | — |
| 3 | Cross-sectional factors / Carhart momentum | NO EDGE (Ken French t 4.52 → 0.67 since 2000) | yes |
| 4 | Small-cap PEAD (reaction-based) | NO EDGE (t = 0.20, 4/8 cohorts positive) | yes ($0) |
| 5 | S&P 600 index reconstitution | **PASSED gate, but real-and-arbitraged-to-marginal** (2020 +10% → 2026 +0.7%) | yes ($0) |

**Net: 5/5 not deployable.** The only formal pass (#5) survived robustness
(look-ahead ruled out — effective-day bar flat at −0.11%; post-effective ≈ 0)
but has decayed to ~1% gross in recent years — net of survivorship + real
execution at retail size, ~zero. The free-pre-check discipline saved meaningful
research $ and surfaced the rigorous truth.

### The meta-insight (load-bearing)
The free, publicly-discussed edge space accessible to a retail operator is
exhausted. Each "edge" we tested was either (a) overfitting on noise,
(b) cost-killed at the relevant frequency, or (c) a documented anomaly
arbitraged to ~zero. The bottleneck is not coding skill, agent choice, or
parameter tuning — it is the **absence of a predictive signal** markets
haven't already extracted. The why-it-fails appendix above proves this
mechanically: on a no-signal base, tuning WR / payoff / cost cannot create
expectancy.

### Operating rules going forward (binding)
1. **The edge hunt is CLOSED.** No further strategy re-tuning, parameter
   sweeps, or "let's try one more configuration" on any strategy in the
   table above. Rule #4 (§Operating rules) applies categorically to all five.
2. **Reopening requires a NEW edge SOURCE** (not in the table) **+** a free
   or cheap kill-gate **+** the same OOS / cluster-robust-t / real-cost /
   pre-registered pass/fail standard. Qualifying new sources (none currently
   held): differentiated/private data; a capacity-constrained structural
   niche; a non-retail execution advantage. NOT qualifying: another
   price-pattern; an LLM-tuned backtest; more parameters on existing signals;
   "let me try with Codex / a different agent."
3. **The harness is the asset.** Spend and engineering go into the
   honesty-detector product (already live — see
   `docs/products/HONESTY_DETECTOR_MVP.md`), not into chasing returns on
   these strategies.
4. This closure is itself **overturnable — by evidence of the same standard
   that produced it, not by hope, optimism, or a new tool.**

Cross-ref: Live-trade audit of the sibling project — same verdict on real paper
trades; 396 trades, all bots net-negative, crypto IS→OOS t collapse 0.01 → −6.36.
Details available on request.
