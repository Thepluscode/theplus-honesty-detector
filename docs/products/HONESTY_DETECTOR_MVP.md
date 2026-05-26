# "Does Your Backtest Survive?" — Honesty Detector MVP

> Build-ready product spec. Design + concrete build plan only — no feature code here.
> Companion to `EDGE_FINDINGS.md` (the proof the harness produces). Grounded in
> code actually read: `tools/strategy_edge_audit.py`, `tools/funding_arb_feasibility.py`,
> and the private platform's engine and API modules.

## 1. The product in one line
Upload a strategy's realized trade history (or a return series). We re-run it through the *same* honest, no-flattery, walk-forward + real-cost + strict-verdict audit that just killed our own strategies, and return a falsifiable **EDGE / NO-EDGE** report with explicit overfitting flags. Zero trading alpha required — we sell the *verdict*, not a strategy.

## 2. The wedge (sharpest first use-case + ICP)
**Wedge: the "prove it before I trust the seller" check for paid signals / EAs / strategy marketplaces.** The sharpest first use-case is the buyer-side gut check on a strategy someone is trying to sell you. Forums/Discord/MQL5/TradingView/prop-pass services are flooded with "73% win rate" equity-curve screenshots (we shipped one ourselves — `strategyCatalog.ts` RSI(2) "73% over 30 years", now removed per `PIVOT_SCOPE.md`). The moment is specific: someone is about to pay $200–$2000 for an EA/signal and has nothing objective to lean on.
**ICP (primary):** the evaluating buyer — a retail/semi-pro algo trader (often on prop capital) with a candidate strategy's trade log who wants a third-party, hard-to-game verdict before risking money or a challenge fee.
**Why buyer-side, not "test my own":** the buyer has no attachment, so a NO-EDGE verdict is useful not insulting (authors churn, buyers evangelize); it is viral ("run it through the survival test" becomes a demand on every seller → sellers then come for a passing badge = expansion path); it needs only a trade-log CSV, no broker/code/IP.
**Positioning:** not a backtester (you have one and it lied) — a *lie detector for backtests*. The asset is credibility: the harness that issued NO-EDGE verdicts on its own author's strategies and published it.

## 3. The ONE core MVP flow
Single synchronous-feeling flow. No strategy accounts, no broker OAuth, no portfolio dashboard.
1. Sign in (existing auth) → `Depends(get_current_user)`
2. Upload one CSV (trade log OR return series) → `POST /api/honesty/audit`
3. Validate shape & parse → new `honesty_ingest`
4. Temporal split (IS/OOS walk-forward) → new `honesty_core` (reuses `compute_metrics`)
5. Strict verdict + overfitting flags → new `honesty_core` (reuses verdict logic)
6. Return JSON; render verdict card → frontend `HonestyReport`

Free = one rate-limited synchronous audit per upload (the verdict, flags, OOS-vs-IS gap). Honesty is the marketing; paid sells volume/automation/shareable proof. No async queue (it is P&L aggregation across folds, not engine replay); hard row cap keeps it inside an HTTP timeout.

## 4. Input data contract (broker-agnostic)
One of two shapes, detected by columns. No broker connection, instrument metadata, or internal config required — only realized outcomes ordered in time.
**Shape A — Trade log (preferred):** Required `exit_time` (aliases close_time/timestamp/date/time; ISO-8601 or epoch ms) and `pnl` (aliases profit/net_pnl/pl/return; float, sign matters, 0 ok). Optional `entry_time`, `r_multiple`, `fees`/`commission`/`slippage` (apply real cost stress if P&L is gross, else synthesize a normalized stress per `strategy_edge_audit.py`), `symbol`.
**Shape B — Return series:** Required `period` (date/timestamp/day) and `return` (ret/pnl/pct_return/daily_return); unit declared by `return_kind` form field (`pct`|`currency`). Normalized to the same `{time, pnl}` rows `compute_metrics` consumes (per-row P&L fallback, engine_v2 lines 583-587).
**Validation (fail-closed, specific messages):** (1) ≤5MB, ≤50k rows else 413. (2) exactly one recognizable shape else 422 listing found cols vs expected. (3) `pnl`/`return` floats on ≥99% rows; NaN/blank dropped+counted+surfaced. (4) time parses on 100% kept rows, monotonic after sort, reject >5% out-of-order duplicate timestamps. (5) <`min_trades_floor` (default 30, same constant) → verdict forced to `INSUFFICIENT_SAMPLE` (flag, not crash; engine requires total_trades>=30). (6) no future timestamps >now+1d, no <1d spans. (7) CSV only.

## 5. Audit methodology (faithful to the engines)
Port the discipline of `strategy_edge_audit.py` to broker-agnostic input. Do NOT re-run `engine_v2.run` — the user already has the trades; we need only the verdict math which `compute_metrics` + the verdict block encode.
1. **Walk-forward folds:** reuse `_build_folds` shape (lines 91-103) — rolling window over time-sorted rows. Default: contiguous IS (first 50%) vs OOS (last 50%) PLUS an N-fold rolling pass (6mo window / 3mo step where span allows; fall back to fixed K=4 equal folds for short series). Per fold call `engine_v2.compute_metrics`.
2. **Strict verdict:** reuse criteria (lines 151-156) verbatim — `agg_sharpe>=0.5` AND `pct_positive_folds>=0.60` AND `mean_profit_factor>=1.1` AND `total_trades>=30`. All-or-nothing → EDGE else NO DURABLE EDGE. Return per-criterion booleans (engine `"criteria"` dict) — falsifiable.
3. **Overfitting flags (differentiator):** `OVERFIT_OOS_COLLAPSE` if OOS Sharpe<0 while IS Sharpe>=0.5 (the box_symmetric failure: IS 35.8% WR positive → honest OOS Sharpe -4.1); `COST_FRAGILE` if EDGE→NO-EDGE under a modest cost haircut (port funding_arb deadband/sweep idea — real edge survives a band); `THIN_SAMPLE` if <100 trades, `INSUFFICIENT_SAMPLE` if <30; `REGIME_FRAGILE` if pct_positive_folds in 0.4–0.6.
4. **No tuning, no flattery** — never search params on user data; only measure.

## 6. Build checklist — reuse vs new (file by file)

> **Note for readers of this public repo:** the `REUSE:` file:line citations
> below reference modules in the **private trading platform** (the FastAPI app
> that hosts the live tool at theplus-bot-production.up.railway.app/honesty).
> Those files are intentionally NOT included in this public companion repo —
> this repo ships the audit *receipts* (standalone tools + `EDGE_FINDINGS.md` +
> JSON reports). The citations are kept verbatim so the build plan is reproducible
> for anyone forking the SaaS side; for the audit math itself, the canonical
> implementation is in `tools/strategy_edge_audit.py` (in this repo).

**REUSE:** `engine_v2.py:539-644 compute_metrics` (core per-fold math; broker-agnostic via per-row P&L fallback); `strategy_edge_audit.py:91-103 _build_folds` (port); `strategy_edge_audit.py:151-174` verdict+criteria (port verbatim constants); `funding_arb_feasibility.py:96-234 _simulate`/`--sweep` (cost-fragility concept); `auth.py:516-567 get_current_user` (Depends, returns Pydantic UserModel with .id/.email/.subscription_tier/.features); `models.py:10-14,206-346 TIER_LIMITS`/`SubscriptionTier`/`User.features`; `feature_gate.py` decorators + `register_routes(app)` pattern (370-430); `stripe_service.py` (unchanged); `main.py:123 limiter` + `register_routes(app, limiter)`/`limiter.limit(...)` (see marketplace_api.py:1436-1467); `database.get_db`/`get_db_context`; `main.py:1879-1894 _route_modules` registration list.
**BUILD NEW:** `backend_api/honesty_ingest.py` (CSV→`{time,pnl}`, alias resolution, §4 validation, typed IngestError; no tradebot.config/engine_v2.run dep); `backend_api/honesty_core.py` (`run_audit(rows,*,min_trades_floor=30,window_months=6,step_months=3)` — folds + compute_metrics per fold + IS/OOS + cost-stress + ported verdict; only place importing engine_v2); `backend_api/honesty_api.py` (`register_routes(app, limiter)`, Pydantic shapes, Depends(get_current_user), feature_gate/tier checks, limiter); `HonestyReport` DB model (id, user_id FK, created_at, verdict, flags JSON, metrics JSON, input_hash, public_slug) + Alembic migration; `frontend/src/pages/HonestyReport.tsx` (+uploader); `tests/test_honesty_core.py` (normal/boundary-exactly-30/malformed/adversarial/regression on box_symmetric IS+/OOS- → NO DURABLE EDGE + OVERFIT_OOS_COLLAPSE).
**Build order:** ingest→core→tests(TDD)→api→register in main.py→frontend. Also rebuild wiped `.venv` (Py3.11 + requirements.txt).

## 7. API surface
All via `honesty_api.register_routes(app, limiter)` added to `_route_modules` (main.py:1879). Every route `Depends(get_current_user)`.
Pydantic: `AuditOptions{return_kind:Literal["pct","currency"]|None, window_months=6, step_months=3, min_trades_floor=30}`; `FoldMetric{period_start,period_end,total_trades,sharpe_ratio,profit_factor,max_drawdown_pct,total_return_pct}`; `OverfittingFlags{overfit_oos_collapse,cost_fragile,regime_fragile,thin_sample,insufficient_sample,is_oos_sharpe_gap}`; `AuditReport{report_id,verdict:Literal["EDGE","NO DURABLE EDGE","INSUFFICIENT_SAMPLE"],criteria:dict[str,bool],agg_sharpe,pct_positive_folds,mean_profit_factor,total_trades,in_sample:FoldMetric,out_of_sample:FoldMetric,folds:list[FoldMetric],flags:OverfittingFlags,rows_used,rows_dropped,method,computed_at}`.
Endpoints: `POST /api/honesty/audit` (FREE, limiter 5/minute, multipart file+options JSON → AuditReport, persists HonestyReport scoped to current_user.id); `GET /api/honesty/reports` (FREE, this-user-only list); `GET /api/honesty/reports/{report_id}` (FREE, 404 if not owned — IDOR guard); `POST /api/honesty/batch` (PRO, `@requires_feature("honesty_batch")` + check_usage_limit, files list → list[AuditReport]); `POST /api/honesty/audit` via API key (PRO, `@requires_feature("api_access")`); `POST /api/honesty/reports/{id}/share` (STARTER+, `@requires_tier(STARTER)` → {public_slug,public_url}); `GET /api/honesty/public/{slug}` (public, redacted, no raw rows).

## 8. Tier / pricing mapping
Gating mechanism = `models.TIER_LIMITS` (per-tier `features` dict + numeric limits) enforced by `feature_gate` decorators reading `current_user.subscription_tier`/`.features` from get_current_user; upgrades via unchanged stripe_service checkout→webhook→update_user_subscription.
FREE: single audit (get_current_user + limiter 5/minute, no feature gate — verdict is the funnel). STARTER: `@requires_tier(STARTER)` on history/share. PRO: batch via new key `"honesty_batch":True` in PRO/ENTERPRISE TIER_LIMITS (2-line edit, established pattern) + `@requires_feature("honesty_batch")`. PRO/ENTERPRISE API: existing `api_access` flag (already PRO True, FREE/STARTER False) — zero new flag. ENTERPRISE white-label proof pages: existing `white_label`. Only one new feature key needed; rides existing STARTER/PRO/ENTERPRISE price IDs (stripe_service.py:34-44 PRICE_IDS); dedicated price tier addable later via same env pattern.

## 9. Out of MVP scope
Broker/OAuth ingest; strategy-code re-run / engine_v2.run bar replay / param search / optimization; async jobs/workers; Excel/JSON/Parquet; multi-currency/FX normalization; portfolio correlation; the 9 broker adapters & live platform; Monte-Carlo/DSR/stationary-bootstrap CI (PR #44 blocked); report editing, team workspaces, SSO.

## 10. Honest risks
**Multi-tenant isolation — UNVERIFIED (top risk):** PIVOT_SCOPE.md says "tenant data separation unverified." This ingests users' proprietary P&L. Every query must filter `HonestyReport.user_id == current_user.id`; `/reports/{id}` must 404 (not 403) on non-owned (IDOR). Isolation test (user A can't read B by id or slug) is a release gate. Don't persist raw rows beyond what the report needs (store metrics + hash).
**Abuse/compute:** cheap audit but uploads are a DoS surface. Mitigate with existing machinery — 5MB/50k-row/one-file-free caps, slowapi limiter 5/minute (main.py:123), sample-floor short-circuit. Fold count bounded by span/step (no unbounded loops). Pathological inputs handled by ingest, not engine crashes — compute_metrics returns zeroed dict on empty (541-558), worst case = clean INSUFFICIENT_SAMPLE.
**Competitive (vs QuantConnect et al.):** we don't compete on backtesting. Backtesters generate curves and have no incentive to call yours a lie. Our wedge is the adversarial verdict on results you already have, from any source, plus the "killed our own strategies, published it" brand and buyer-side viral loop. Real threats: a quant can hand-roll walk-forward+DSR in a notebook (moat = productized broker-agnostic shareable verdict + trust brand, not math); the math is well-known and unpatentable. Honest limitation: thin-feature business defended by distribution/brand/viral loop, not algorithms — price accordingly (low free friction, value in volume/proof).
**Verdict honesty is a liability to keep:** the premise dies if we soften a verdict to retain a paying author. Strict criteria are hard-coded ported constants and must stay code-enforced and test-locked (regression on box_symmetric IS+/OOS-), per the same anti-self-deception discipline in both source tools.
