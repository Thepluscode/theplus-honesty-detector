# Pushback Response Playbook

Reference drafts for responding to technical pushback on Honesty Detector audits,
launch posts, and case studies. Use these as starting points — adapt to the
specific comment, but keep the structure and tone consistent.

## Response Principles

1. **Acknowledge the question as legitimate.** Never get defensive. Skepticism is the right starting point in this space.
2. **Reframe to methodology, not outcome.** The product's value is the discipline, not any single verdict.
3. **Cite the receipts.** Always point back to `EDGE_FINDINGS.md`, the open-source repo, or specific scripts they can run themselves.
4. **Invite replication.** If they can reproduce it, the discussion ends. If they can't, the methodology stands.
5. **Stay short.** Two short paragraphs beat one long one. Skimmability wins on social platforms.

---

## 1. Pushback on Walk-Forward Fold Methodology

**Typical comment:**
> "Why contiguous folds? Calendar-based folds (e.g., 6-month blocks) are the standard for handling seasonality."

**Draft response:**

Fair question. We chose contiguous folds because the goal of `strategy_edge_audit.py` is to test whether the raw signal persists when you simply roll forward — without assuming the market obeys calendar regularities. Calendar folds can mask weak strategies that happen to align with strong periods (e.g., a Q4 rally rescuing an otherwise flat signal).

The script is open-source, so calendar folds are a one-line change if you want to test them. In this case it wouldn't have moved the verdict — zero folds came back positive under contiguous splits, so any reasonable folding scheme lands in the same place.

---

## 2. Pushback on T-Stat Collapse (e.g., Carhart Momentum)

**Typical comment:**
> "The Carhart momentum factor has a t-stat of 4.52 over nearly a century. You're calling it dead because it's 0.67 since 2000? That's cherry-picking."

**Draft response:**

The 4.52 t-stat over the full Ken French sample is real — momentum had a genuine edge for decades. The collapse to 0.67 since 2000 isn't a cherry-pick; it's the standard story for academic factors once they get published, productised, and arbitraged. Our audit weights modern out-of-sample performance because that's what determines whether you make money today, not in 1985.

Three things drive the verdict:
- **Modern OOS performance**: t = 0.67 since 2000 means we can't reject the null at any sensible threshold.
- **Net of realistic costs**: the historical edge shrinks further once slippage, fees, and turnover drag are applied.
- **Regime robustness**: confirmed across rolling windows and cluster-robust SEs, not a single cutoff.

`tools/alpha_zoo/alpaca_to_csv.py` reproduces the Ken French pull and the rolling t-stat calculation if you want to run it end-to-end.

---

## 3. Pushback on "NO EDGE" Verdicts vs. Live P&L

**Typical comment:**
> "Your tool said NO EDGE but my dashboard shows the strategy up $500 this week. The tool's wrong."

**Draft response:**

That gap is exactly what the tool is built to surface. A green P&L over a short window is a sample size of one — it tells you what happened, not whether it'll keep happening. The audit asks four things your dashboard usually doesn't:

- **Does the signal survive out-of-sample folds?** Most overfit strategies collapse the moment you withhold the data they were tuned on.
- **Does it survive realistic costs?** Gross edges routinely flip negative once slippage and fees are honest.
- **Is the sample large enough to distinguish skill from luck?** A few hundred trades isn't usually enough for a noisy signal.
- **Does it hold across regimes?** A strategy that only works in one volatility regime is a regime bet, not an edge.

If your strategy passes all four, the tool returns EDGE. If it doesn't, the $500 this week is more likely variance than signal. Run the audit locally from the repo — the verdict comes with the full breakdown so you can see which gate it failed.

---

## 4. General Skepticism / "This Sounds Like a Scam"

**Typical comment:**
> "If you found no edge, why are you selling a tool? Sounds like another grift."

**Draft response:**

Reasonable read — this space earns its skepticism. Three things that should help:

1. **The product is the discipline, not the edge.** I spent a year building bots, convinced one of mine worked, and the audit tool is what proved it didn't. What I'm selling is the forensic harness that catches that delusion, not a magic signal.
2. **My own failure is the case study.** The whole launch hinges on the `box_symmetric` strategy I almost shipped. Receipts are in `EDGE_FINDINGS.md` and the case study doc.
3. **The core audit is free and open-source.** Web UI is free, full code is on GitHub. The paid tier is for volume, automation, and shareable proof pages — not for gating the truth.

The goal is loss prevention. For most retail traders, the biggest possible win is not deploying the next overfit strategy. That's what this is for.

---

## 5. Pushback on Sample Size Requirements

**Typical comments:**
> "Your minimum trade count is too strict — I have 100 winning trades and it still says INSUFFICIENT_SAMPLE."
> "If my Sharpe is 2.5, why do I need 500+ trades?"
> "You're killing valid strategies with arbitrary thresholds."

**Draft response:**

INSUFFICIENT_SAMPLE isn't a "no edge" verdict — it's a "we can't tell yet" verdict, and the distinction matters. The required sample size isn't arbitrary; it's a function of the signal-to-noise ratio of your strategy. High-variance strategies need more trades to separate skill from luck, lower-variance ones need fewer. The audit uses standard power analysis, not a fixed floor.

A few specifics:
- **At Sharpe ~1.0**, you typically need 200–400 trades before a t-test rejects the null with any confidence.
- **At Sharpe ~2.5** with stable variance, the threshold drops sharply — but stable variance is what most retail strategies don't have.
- **The asymmetry is deliberate.** A false-positive EDGE verdict gets a real person to deploy real capital. A false-INSUFFICIENT just means "wait, collect more data, run it again." We'd rather err on the second.

If you think the threshold is mis-calibrated for your strategy class, the power calculation is in the script — open an issue with the trade log and we'll look at whether the variance estimate is off.

---

## 6. Pushback on Transaction Cost Assumptions

**Typical comments:**
> "Your slippage numbers are way too high — I trade liquid ES futures, not penny stocks."
> "IBKR charges me $0.005/share, your 5bp default is retail nonsense."
> "I use limit orders, no slippage applies."

**Draft response:**

Defaults are intentionally conservative — the audit is meant to be a stress test, not a flattering simulation. That said, the cost model is configurable; the defaults are a starting point, not a verdict. You can pass your own per-trade cost, slippage in bps, and turnover penalty via the CLI flags (see `--help` on `strategy_edge_audit.py`).

Two things worth keeping in mind even after you customise:
- **Realised slippage > quoted spread.** Even on liquid instruments, queue position, partial fills, and impact at size mean the cost you see in a backtest underestimates the cost you'd pay in production. The default haircut accounts for that gap.
- **Limit orders aren't free.** They have an opportunity cost — the trades you *don't* get filled on are usually the ones you most wanted. A backtest that assumes 100% limit-order fills is a different (and easier) strategy than the live one.

The useful exercise isn't "what cost makes my strategy work" — it's the sensitivity sweep. Run the audit across a range of cost assumptions and look at where the edge breaks. If it survives only at near-zero costs, you've found a fragile strategy, not a robust one.

---

## Tone Guide

**Do:**
- Lead with the legitimate part of the question.
- Use concrete numbers and file names — they signal you've actually done the work.
- Offer a path to verify (run the script, read the file, fork the repo).
- Concede where the questioner is partially right.

**Don't:**
- Use phrases like "great question" — they read as canned.
- Stack three rhetorical questions in a row.
- Promise outcomes ("this will save you money"). Promise methodology ("this will tell you the truth").
- Get pulled into arguments about specific strategies that aren't in the audit set. Redirect to "run it and share the output."

---

## When to Escalate

Move from public reply to DM / longer-form when:
- The questioner is a credentialed quant or academic with a substantive methodological critique.
- The thread is being read by a high-signal audience and a detailed walkthrough would build more trust than a short reply.
- The pushback names a specific bug or data error — those get acknowledged publicly and fixed, not debated.

When in doubt, the answer is: "Run it locally, share the output, let's compare."
