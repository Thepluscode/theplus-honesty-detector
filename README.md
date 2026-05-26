# theplus-honesty-detector

**An honest backtest auditor — out-of-sample walk-forward, real costs, cluster-robust statistics. Refuses to flatter.**

---

We spent about a year building a multi-broker algorithmic trading platform. We also spent that year believing the strategies worked. Then we audited them honestly. Five hypotheses. Zero deployable edges. We open-sourced the audit — the tools that produced the verdicts, the raw JSON reports, and the full case study — because the discipline is more useful to other people than burying the result.

The flagship strategy, `box_symmetric`, carried a "35.8% win rate, positive expectancy" label in our own tracker. The honest out-of-sample walk-forward returned aggregate Sharpe **−4.13**, profit factor **0.54**, sum-of-fold return **−62.6%**, and **0 of 110 walk-forward folds positive**. Every strategy we tested failed the same gate. This repo is the record.

---

## The receipts

| What | Where |
|------|-------|
| Full evidence record | [`EDGE_FINDINGS.md`](EDGE_FINDINGS.md) |
| TA strategy walk-forward results | [`reports/edge_audit_20260518.json`](reports/edge_audit_20260518.json) |
| Funding-arb feasibility simulation | [`reports/funding_arb_feasibility_20260518.json`](reports/funding_arb_feasibility_20260518.json) |
| Funding-arb deadband sweep | [`reports/funding_arb_sweep_20260518.json`](reports/funding_arb_sweep_20260518.json) |
| PEAD free pre-check output | [`reports/pead_precheck.json`](reports/pead_precheck.json) |
| Index reconstitution pre-check output | [`reports/index_recon_precheck.json`](reports/index_recon_precheck.json) |
| Full case study (narrative + math) | [`docs/products/CASE_STUDY_we_killed_our_own_bots.md`](docs/products/CASE_STUDY_we_killed_our_own_bots.md) |

Or skip straight to the hosted tool and run your own strategy through the same gate:
**[theplus-bot-production.up.railway.app/honesty](https://theplus-bot-production.up.railway.app/honesty)**

---

## Run it yourself

Three of the four audit tools are fully self-contained (free public data, no private engine needed):

```bash
git clone https://github.com/Thepluscode/theplus-honesty-detector.git
cd theplus-honesty-detector
./setup.sh

# Funding-rate arb: pulls Binance public history, zero credentials needed
python tools/funding_arb_feasibility.py --symbol BTCUSDT

# PEAD free pre-check: uses yfinance, zero credentials needed
python tools/pead_precheck.py

# Index reconstitution pre-check: scrapes Wikipedia + yfinance, zero credentials needed
python tools/index_recon_precheck.py
```

`strategy_edge_audit.py` requires a backtesting engine (`tradebot.engine_v2`) that is part of the private platform and not included here. The JSON reports in `reports/` are its output — you do not need to re-run it to inspect the results. See the [dependency note](#notes--limitations) below.

---

## What the audit checks

**5 strict pass/fail criteria (all must hold for EDGE):**

- `agg_sharpe >= 0.5` — aggregate Sharpe across all chronological folds
- `pct_positive_folds >= 60%` — regime test; bad regimes decide
- `mean_profit_factor >= 1.1` — across folds
- `total_trades >= 30` — statistical floor; anything below returns `INSUFFICIENT_SAMPLE`, not a verdict
- Walk-forward is rolling, frozen config, default params — no per-fold tuning

**4 overfitting flags (reported alongside the verdict):**

- In-sample → out-of-sample Sharpe collapse
- Cost-fragility (verdict flips at realistic vs optimistic cost assumptions)
- Regime-fragility (positive folds concentrated in one market phase)
- Thin-sample warning (n < 100 trades — verdict is formally valid but statistically fragile)

These criteria are hard-coded constants in `tools/strategy_edge_audit.py` and in the live web tool's backend. They are not adjustable via UI or configuration.

---

## The 5/5 summary

| # | Hypothesis | Result | Key number |
|---|------------|--------|------------|
| 1 | TA strategies (box / OBV / Keltner / VWAP / breakout) | NO EDGE | 0/110 walk-forward folds positive |
| 2 | Retail funding-rate arb (BTC/ETH, 6.7yr history) | NO EDGE | 0/9 deadbands net-positive; gross ~15%/yr real, net −7.9% (BTC) |
| 3 | Cross-sectional factors / Carhart momentum | NO EDGE | Ken French t-stat 4.52 (full history) → 0.67 since 2000; negative net of cost |
| 4 | Small-cap PEAD (reaction-based, yfinance) | NO EDGE | week-clustered t = 0.20; 4/8 annual cohorts positive |
| 5 | S&P 600 index reconstitution | Passed gate — arbitraged to marginal | Decayed from +10% (2020) to +0.7% (2026); ~zero net at retail |

5/5 not deployable. The edge hunt is closed. See [`EDGE_FINDINGS.md`](EDGE_FINDINGS.md) for the full methodology, refusals, bounded caveats, and the geometric proof of why these strategies cannot be tuned into profitability.

---

## Want the hosted version?

**[theplus-bot-production.up.railway.app/honesty](https://theplus-bot-production.up.railway.app/honesty)**

Upload a trade log or return series. Get a falsifiable EDGE / NO DURABLE EDGE verdict with overfitting flags — the same gate described above, applied to your data. The tool refused to give its own operator a positive verdict on n=12 trades (`INSUFFICIENT_SAMPLE`), and it will do the same for you.

Free tier: one audit per day, single file, full verdict and flags. The verdict is never gated behind a paywall.

---

## Notes & limitations

**`strategy_edge_audit.py` — engine dependency.** This tool calls `tradebot.engine_v2`, the private backtesting engine from the companion trading platform. That module is not included in this repo. You can read the methodology in the source file, inspect the pre-computed results in `reports/edge_audit_20260518.json`, or adapt the walk-forward harness to your own engine. To use it directly you need to supply two functions matching the interface described in the `DEPENDENCY NOTE` block at the top of the file.

**The other three tools are self-contained.** `funding_arb_feasibility.py`, `pead_precheck.py`, and `index_recon_precheck.py` reproduce hypotheses 2, 4, and 5 respectively using only free public data and the dependencies in `requirements.txt`. Run them and you get the same verdicts we got.

**`tools/alpha_zoo/`** has its own `requirements.txt`. The IC benchmark (`alpha_bench.py`, `carhart_umd.py`) is self-contained. `alpaca_to_csv.py` additionally needs Alpaca credentials (see `.env.example`); it is not required to reproduce the Ken French momentum result.

**Survivorship bias.** The PEAD and index-recon pre-checks use yfinance and Wikipedia, which carry survivorship bias. The tools flag this explicitly. The results are conservative pre-checks, not definitive studies — which is why they are named pre-checks.

---

## License

MIT — see [LICENSE](LICENSE)

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

---

## Using with Claude Code

This project includes a `CLAUDE.md` that gives Claude Code full context on the repo's hard rules and key files.

```bash
claude    # Start Claude Code — reads CLAUDE.md automatically
```

---

*Built by someone who spent a year being wrong about their own work, and decided to ship the discipline that finally proved it.*
