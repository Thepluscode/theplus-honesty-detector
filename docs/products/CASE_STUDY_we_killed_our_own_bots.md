# We Killed Our Own Trading Bots — And Built the Tool That Did It

> If you're about to pay $200 for an EA, drop $500 on a prop-firm challenge, or
> talk yourself into deploying the "73% win rate over 30 years" backtest you've
> been staring at: read this first. It might save you the money.

---

## The setup, said plainly

I spent about a year building a multi-broker algorithmic trading platform.
Two of them, actually — one in Python, one in TypeScript. Nine broker
integrations. Strategies for FX, equities, crypto. Risk controls. Crash recovery.
A whole dashboard. Real engineering.

I also spent that year mostly believing the strategies worked. The backtests
looked good. One of them — `box_symmetric` — was the only thing I'd ever marked
"production-proven": **35.8% win rate, positive expectancy.** That was the
headline I was telling myself.

Then I audited it honestly. The audit took two weeks. The verdict took thirty
seconds:

> `box_symmetric` — aggregate Sharpe **−4.13**, profit factor **0.54**,
> sum-of-fold return **−62.6%**, **0% of folds positive**.

The "35.8% win rate" was in-sample, tuned-config overfitting. The honest
out-of-sample walk-forward — same code, same data, no tuning — lost money
catastrophically. I'd been wrong for a year about my own work.

So I did the only honest thing left: tested the rest of it under the same
discipline. All of it. And then I built the tool that does the same thing to
yours.

---

## Beat 1: Five hypotheses tested. Zero deployable edges.

Every hypothesis was tested under the same rules: out-of-sample, real costs,
pre-registered pass/fail criteria, cluster-robust statistics, no goalpost-moving.

| # | What we tested | Result | Killer fact |
|---|---|---|---|
| 1 | **TA strategies** (box / OBV / Keltner / VWAP / breakout) | **NO EDGE** | 0 of 110 walk-forward folds positive on 3 yrs of EURUSD 5m |
| 2 | **Retail funding-rate arb** (BTC / ETH, 6.7 yr history) | **NO EDGE** | Gross premium real (+~15%/yr). 0 of 9 deadbands net-positive after fees + slippage + borrow |
| 3 | **Cross-sectional factors / Carhart momentum** | **NO EDGE** | Ken French data 1927–2026: full-history t = 4.52 → 0.67 since 2000. Arbitraged away. |
| 4 | **Small-cap PEAD** (post-earnings drift, reaction-based) | **NO EDGE** | 122 long events, week-clustered **t = 0.20**, 4/8 cohorts positive. Coin flip. |
| 5 | **Small-cap index reconstitution** | **PASSED — but arbitraged to marginal** | 390 S&P-600 add-events: net +3.6%, t = 9.64. Decayed from +10% (2020) to **+0.7% (2026)**. Real, dead in 2026. |

**Net: 5/5 not deployable at retail.** The only formal pass (index reconstitution)
survives statistical robustness — we ruled out look-ahead artifacts — but the
edge has been arbitraged down to ~1% gross in recent years. After survivorship
correction and real retail execution slippage, it's ~zero today.

> Every receipt is in this repo: `EDGE_FINDINGS.md`,
> the audit tools (`tools/strategy_edge_audit.py`,
> `tools/funding_arb_feasibility.py`, `tools/pead_precheck.py`,
> `tools/index_recon_precheck.py`), and the JSON reports in `reports/`.
> The sibling-platform live-trade audit (396 real paper trades) is available
> on request.

---

## Beat 2: The product refused to give its own operator good news

After all this, I built the tool. It does what the audits did, but for anyone
with a trade log — upload a CSV, get a falsifiable EDGE / NO-EDGE verdict with
overfitting flags. Five tiers of pre-registered criteria. No optimism gradient.

Then I pointed it at my own production paper-trading bots, which had just had a
visibly green 30-day window: **+$785 P&L over 6 trades, +$1,360 all-time over
44 trades**. The dashboard looked fine. A meme-stock-style "trust me bro" pitch
could have been written from this output alone.

Here's what my own product said when I fed it the 12 visible real trades
(excluding ghost / crash-recovery / no-fill rows):

```
audit (n=12 real trades, default gate min_trades=30)  →  HTTP 200
   verdict     : INSUFFICIENT_SAMPLE
   total_trades: 12
   flags       : insufficient_sample=true, thin_sample=true
```

**It refused to flatter me.** It didn't say "67% win rate, edge confirmed!"
(which is what the visible 12 trades would naively suggest). It said *"twelve
trades is not enough data for a statistically meaningful verdict — I won't give
you one."*

Every competitor in this space would have spat out a marketing-friendly summary
on n=12. Ours refused, on its own operator, on a visibly green sample. That's
the brand: the *only* trading-strategy auditor whose competitive advantage is
**refusing to flatter you.**

*(The 44-trade verdict goes here — see "The receipts, fully" below for how to
get it.)*

---

## Beat 3: The math behind why every "great backtest" is suspect

I dug into *why* my own bots lost. The numbers reveal the failure as
**mechanical, not a tuning miss.** Here are the live results from one of the
the sibling platform (396 real paper trades) decomposed:

| Strategy | Win rate | Payoff (avg W / avg L) | Breakeven WR | Gap | Expectancy |
|---|---|---|---|---|---|
| Crypto momentum | 33% | 1.71 ($3.89 / $2.28) | 37% | **−4 pts** | −$0.13 / trade |
| Stock ORB | 37% | 1.49 ($8.76 / $5.88) | 40% | **−3 pts** | −$0.14 / trade |
| Forex pullbackContinuation | 0% | n/a | n/a | broken | −$14 / trade |

A breakout/trend system with payoff ~1.6 and win rate ~35% is *exactly* what
**random entries produce.** With a fixed stop:target, the win rate is set by
geometry — probability of hitting target before stop — not by signal quality.
These land precisely where no-signal entries would, and cost drag tips the
small remainder negative.

So why doesn't tuning help? Because **expectancy = WR · avgW − (1−WR) · |avgL|**,
and the three levers all dead-end on a no-signal base:

1. **Raise win rate above breakeven** → needs entries that actually predict
   direction. There's no signal to amplify (out-of-sample tests prove it).
2. **Raise payoff** → on a no-signal base, widening the target lowers WR
   proportionally. You just slide along the random-entry frontier. Expectancy
   stays pinned at ≈ −cost.
3. **Cut cost** → helpful, but it gets you to breakeven, not profit.

This is *mathematically* — not just empirically — why the bots can't be tuned
into profitability. The full reverse-engineering is in
`EDGE_FINDINGS.md` → "Appendix: Why it fails."

---

## What this means for *your* strategy

Every backtest with a green equity curve and a "70% win rate" claim is, until
proven otherwise:

- **Overfit** — in-sample / tuned params; collapses out-of-sample. This is
  exactly how the box_symmetric "35.8% WR" story died — and it's the most
  common failure mode in retail backtesting.
- **Sample-variance** — a small positive run dressed as signal. With high
  per-trade variance, a *t-stat below 2* means you can't distinguish your
  results from a coin flip, no matter how green the curve looks.
- **Cost-fragile** — looks fine gross, dies net. Most retail backtests bury
  slippage and fee assumptions in a place where you won't look.
- **Decayed** — a real, documented anomaly (like the index effect) that's been
  arbitraged down to a margin you can't extract at retail size today.

If your strategy doesn't survive an honest audit, deploying capital to it is
not aggressive — it's expensive education. There's a better way to find out.

---

## What the tool actually does

Upload a trade log or return series. We run it through the same five-criterion
gate I used on my own bots:

- **`agg_sharpe ≥ 0.5`** (aggregate of chronological folds)
- **`≥ 60% of folds positive`** (regime test — bad regimes decide)
- **`mean profit factor ≥ 1.1`**
- **`total trades ≥ 30`** (statistical floor — anything less returns
  INSUFFICIENT_SAMPLE, period)
- Plus overfitting flags: in-sample → out-of-sample Sharpe collapse,
  cost-fragility, regime-fragility, thin-sample warnings.

You get a falsifiable **EDGE** or **NO DURABLE EDGE** verdict — never a
"promising, needs more data," never a "great win rate!", never a curve fit
to make you feel good. Strict criteria are *hard-coded constants* in the
codebase and locked under regression tests. If we soften them to retain a
paying user, the brand dies.

**Free tier:** one audit/day, single file, full verdict + overfitting flags.

The free verdict is the funnel. We will *never* gate the truth behind a paywall.
Paid tiers buy you volume (batch), automation (API), and shareable proof pages —
not better answers.

→ Run yours: **[`/honesty`](https://theplus-bot-production.up.railway.app/honesty)**

---

## The receipts, fully

Nothing here is asserted on trust. Everything is reproducible from the public
repo and the production endpoints:

| What | Where |
|---|---|
| Full strategy audit | `EDGE_FINDINGS.md` |
| Live-trade audit (real paper trades) | Sibling-platform audit: 396 trades, IS→OOS t collapse 0.01 → −6.36 — available on request |
| Audit tools (run them yourself) | `tools/strategy_edge_audit.py`, `tools/funding_arb_feasibility.py`, `tools/pead_precheck.py`, `tools/index_recon_precheck.py` |
| Audit reports (raw JSON output) | `reports/edge_audit_*.json`, `reports/funding_arb_*.json`, `reports/pead_precheck.json`, `reports/index_recon_precheck*.json` |
| The reverse-engineering ("why it fails") | "Appendix" sections in both `EDGE_FINDINGS.md` files |
| The edge-hunt closure (binding rules) | "EDGE HUNT CLOSED" sections in both `EDGE_FINDINGS.md` files |
| The tool itself, end-to-end tested in prod | `backend_api/honesty_{ingest,core,api}.py` + `backend_api/tests/test_honesty*.py` (22/22 tests pass) |

> *Standing offer to drop in here when the operator's full 44-trade history is
> exported via the dashboard CSV: the n≥30 audit result — almost certainly
> NO DURABLE EDGE given the underlying t-stat math (~0.3) — to make Beat 2
> quantitative as well as qualitative. Until then, the INSUFFICIENT_SAMPLE result
> on 12 trades is the demo: the product refuses to flatter even on thin data.*

---

## One last honest disclaimer

This tool analyses trade data **you** provide. It is not investment advice. It
makes no recommendations about what to trade, when, or how. Past performance —
even genuine past performance — is not a guarantee of future returns.

The verdict it gives is statistical. It will sometimes call genuinely-positive
strategies inconclusive (if your sample is thin), and it will sometimes give
high t-stats to lucky runs (no test is perfect). What it will *never* do is
manufacture a green light to keep you happy. That's the entire point.

---

*Built by someone who spent a year being wrong about their own work, and
decided to ship the discipline that finally proved it.*
