# theplus-honesty-detector

This repo contains the audit tools, pre-computed reports, and case study from a rigorous edge-hunting exercise that returned 5/5 hypotheses not deployable at retail. It is a companion to a private trading platform (theplus-bot); the platform is not included. The public artifact is the audit discipline: the tools that produced falsifiable verdicts, the raw JSON output, and the methodology that refused to flatter.

## Key files

```
tools/strategy_edge_audit.py      # Walk-forward TA audit — requires private engine (see DEPENDENCY NOTE in file)
tools/funding_arb_feasibility.py  # Funding-rate arb simulation — fully self-contained, Binance public API
tools/pead_precheck.py            # PEAD free pre-check — fully self-contained, yfinance
tools/index_recon_precheck.py     # S&P 600 index recon pre-check — fully self-contained, Wikipedia + yfinance
tools/alpha_zoo/                  # 452-factor IC benchmark — own requirements.txt; alpaca_to_csv.py needs credentials
EDGE_FINDINGS.md                  # The evidence record — load-bearing, do not reopen closed conclusions
reports/                          # Pre-computed JSON output from all four tools
docs/products/CASE_STUDY_we_killed_our_own_bots.md  # Full narrative + math
requirements.txt                  # Runtime deps for the three self-contained tools
```

## Hard rules

**Do not soften the verdict criteria.** The five thresholds in `strategy_edge_audit.py` (`agg_sharpe >= 0.5`, `pct_positive_folds >= 60%`, `mean_profit_factor >= 1.1`, `total_trades >= 30`, frozen-config walk-forward) are hard-coded constants. Do not make them configurable, add override flags, or lower them for any reason. If you believe they are wrong, open an issue and make the statistical case before touching the code.

**Do not add a strategy-tuning surface.** This repo audits edge hypotheses. It does not build, tune, or collect strategies. Do not add parameter sweeps, optimisation loops, or configuration surfaces that could be used to fit a strategy to a dataset.

**Reuse `tools/strategy_edge_audit.py` patterns for any new audit tool.** New tools should follow the same structure: no per-fold tuning, normalised costs that flatter you the least, a strict binary EDGE / NO DURABLE EDGE verdict, and an honest caveats block. The tone is in the file — read it before writing anything new.

**New audit tools must be added to EDGE_FINDINGS.md only after a pre-registered pass/fail test.** Write down the hypothesis and the pass/fail criteria before running the tool. Record the pre-registration date. Add the result to the table in EDGE_FINDINGS.md after the run, not before. Do not move the goalposts.

## Running the self-contained tools

```bash
./setup.sh   # creates venv, installs requirements.txt

python tools/funding_arb_feasibility.py --symbol BTCUSDT
python tools/pead_precheck.py
python tools/index_recon_precheck.py
```

`strategy_edge_audit.py` needs `tradebot.engine_v2` from the private platform. The pre-computed output is in `reports/edge_audit_20260518.json`.

## What this repo is not

A place to tune strategies. A source of trading signals. A backtest platform. The edge hunt is closed — see the "EDGE HUNT CLOSED" section in `EDGE_FINDINGS.md` for the binding rules on reopening it.
