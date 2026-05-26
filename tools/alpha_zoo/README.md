# Standalone Alpha-Zoo IC Benchmark

A self-contained extraction of the alpha-zoo benchmark from
[HKUDS/Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) (MIT). It runs the
**exact** information-coefficient (IC) pipeline as `vibe-trading alpha bench`,
but with everything stripped away except the math:

- ❌ no agent, no LLM, no `bash`/shell tools
- ❌ no network calls, no data-provider SDKs (tushare/yfinance/ccxt)
- ❌ no FastAPI/MCP server, no code generation
- ✅ ~452 pure-pandas factor definitions + the IC scoring engine
- ✅ runs on your own OHLCV data, on your machine, offline

This is the "safe slice" of Vibe-Trading. None of the RCE / prompt-injection
surface from the full agent comes along — the only thing that executes is the
vendored, inspectable factor library.

## The alpha zoo

| Zoo | Count | Source |
|-----|------:|--------|
| `alpha101` | 101 | Kakushadze (2015), *101 Formulaic Alphas*, arXiv:1601.00991 |
| `gtja191`  | 191 | GuoTai JunAn *191 Alphas* report |
| `qlib158`  | 154 | Microsoft Qlib Alpha158 handcrafted features |
| `academic` |   6 | Fama-French 5 + Carhart momentum |

Per-zoo licences are preserved under `alpha_zoo_pkg/factors/zoo/*/LICENSE.md`.
Upstream licence: `LICENSE.vibe-trading`.

## Install

The only deps are pandas / numpy / pydantic. Run:

```bash
python3 -m pip install -r requirements.txt
```

## Quick start

```bash
# 1. See what's loaded
python3 alpha_bench.py --list-zoos

# 2. Make a synthetic universe to try it (or bring your own — see below)
python3 make_sample_data.py --symbols 40 --days 500 --out sample_universe.csv

# 3. Benchmark every alpha
python3 alpha_bench.py sample_universe.csv --top 20 --out results.csv

# Filter by zoo or theme
python3 alpha_bench.py sample_universe.csv --zoo alpha101
python3 alpha_bench.py sample_universe.csv --theme momentum
```

## Get your data from Alpaca

`alpaca_to_csv.py` fetches multi-symbol daily bars from Alpaca and writes the
exact tidy shape `alpha_bench.py` expects.

Credentials — create a local, gitignored `alpaca_credentials.json` next to the script
(this file is in `.gitignore` — never commit it):

```json
{ "api_key": "PK...", "api_secret": "...", "paper": true }
```

(or pass `--key/--secret`). Then:

```bash
# needs the SDK theplus-bot already uses; run in its venv or:
python3 -m pip install alpaca-trade-api

python3 alpaca_to_csv.py \
  --symbols AAPL,MSFT,NVDA,GOOGL,AMZN,META,JPM,JNJ,V,PG,UNH,HD,XOM \
  --start 2021-01-01 --out universe.csv

python3 alpha_bench.py universe.csv --top 20 --out results.csv
```

Notes:
- Free Alpaca accounts get the **IEX** feed only (`--feed iex`, the default).
  IEX has thinner history/coverage than SIP — fine for a research bench.
- One bad/illiquid symbol is skipped with a warning; the run continues.
- This is the *only* part of the toolkit that touches the network or your
  broker keys. `alpha_bench.py` itself stays fully offline.
- Requires: `python3 -m pip install alpaca-trade-api`

## Your data

Feed it a **long/tidy** CSV or Parquet — one row per (date, symbol):

```csv
date,symbol,open,high,low,close,volume
2021-01-04,AAPL,133.5,133.6,126.7,129.4,143301900
2021-01-04,MSFT,222.5,223.0,219.7,217.7,37130100
...
```

Optional `amount` (turnover) column unlocks ~40 GTJA factors that need it.
Column names are overridable (`--date-col`, `--close-col`, …).

**Cross-sectional IC needs a real cross-section.** These are ranking signals
*across a universe* on each bar — feed a few dozen+ liquid symbols. A single
EUR/USD or BTC series will not produce meaningful IC (use a multi-name basket).
An Alpaca multi-stock export works well; a single-pair forex series does not.

## How to read the output

For each alpha, per-bar **Spearman rank IC** between the factor and **next-bar
forward return** (`close.pct_change().shift(-1)`), then:

- **IC mean** — average daily rank correlation. >0.02 is interesting; >0.05 is strong.
- **IR** — IC mean / IC std (information ratio of the signal).
- **t** — t-stat of the IC series; `|t|>2` ≈ statistically distinguishable from 0.
- **IC+ %** — fraction of bars with positive IC.
- **category** (verbatim upstream thresholds):
  - `alive` — `IC>0.02 and IC+%≥0.55 and |t|>2`
  - `reversed` — `IC<-0.02 and |t|>2` (signal works inverted)
  - `dead` — everything else

## ⚠️ Read this before you trust a number

These factors were authored for **daily-bar, cross-sectional equity** universes
(mostly CN/US stocks). Treat any "alive" result as a **hypothesis, not alpha**:

1. **In-sample IC is not OOS edge.** A high IC on your history is exactly the
   overfitting trap already documented in this project's edge audits. Carry the
   survivors into your own walk-forward / OOS gate before believing them.
2. **No costs, no slippage, no capacity.** IC ignores execution entirely.
3. **Survivorship bias** lives in *your* symbol list — if you only include names
   that exist today, IC is biased up.
4. **Forward-return alignment assumes you can trade at the next bar.** Validate
   that against your real fill model.
5. **`reversed` is not a free short** — it's a flag to investigate, not deploy.

In short: this tells you *which textbook factors correlate with forward returns
on your data*. It does not tell you that you can make money from them.

## Provenance

Extracted from HKUDS/Vibe-Trading. Changes made during extraction:
- vendored only `factors/` (base ops, registry, IC core, the 4 zoos)
- renamed the package `src.factors` → `alpha_zoo_pkg.factors` (avoids collisions
  with `src/` in the original host repo)
- removed `dataclass(slots=True)` and one `str | None` annotation for Python 3.9
- replaced the network universe loaders with a local CSV/Parquet loader

The factor math and IC/categorisation thresholds are unchanged.
