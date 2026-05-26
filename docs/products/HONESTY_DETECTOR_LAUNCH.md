# Honesty Detector — Launch Plan

> Companion to `HONESTY_DETECTOR_MVP.md` (the product spec). This is the GTM
> scoping: positioning, pre-launch blockers, pricing, channels, sequence,
> metrics. Written 2026-05-26 after the edge hunt closed and the product was
> prod-verified.

## 0. Where it stands today (the asset)

Live and verified in prod at `theplus-bot-production.up.railway.app/honesty`:
- Upload → falsifiable EDGE / NO-EDGE verdict with overfitting flags, IS vs OOS,
  per-strategy criteria. Auth-gated, persisted, share-able (Starter+),
  public report pages, batch (Pro). GDPR-clean (purge on delete).
- Full prod end-to-end verified: real authenticated audit returned `EDGE` on a
  60-trade CSV (`report_id 695e5b01-…`), and the GDPR cycle purged
  `honesty_reports: 1, user_account: 1`. 22/22 tests green.

There is no engineering blocker to taking traffic *today*. The blockers below are
trust, scale-safety, and distribution.

## 1. The one-line strategy

**"The lie detector for backtests."** We're the only tool in the space whose
core differentiator is **refusing to flatter** — and we have the receipts:
we killed our own platform's five trading strategies with this same audit
(`EDGE_FINDINGS.md` is public). Every competitor sells curves; we sell verdicts.

## 2. Wedge + ICP (pick ONE primary for launch)

The MVP spec named three plausible ICPs. For launch, **commit to ONE** to
sharpen messaging and channels. Ranked recommendation:

| Rank | ICP | Why | First channel |
|---:|---|---|---|
| **1 (recommended)** | **r/algotrading / r/Daytrading "is my backtest real?" posters** | Highly technical, deeply skeptical of "73% win rate" screenshots, *want* an objective check, free for them, viral within the community | Reddit (organic posts answering "evaluate my backtest" threads with verdicts) |
| 2 | Prop-firm challenge buyers (FTMO / MyForexFunds candidates) | About to pay $200–$500 challenge fees with a strategy; one bad audit saves real money; high urgency | Discord (prop-firm communities), targeted ads |
| 3 | EA / signal buyers on MQL5 / SimpleTrader / similar | Same dynamic, broader audience, more cynical sellers to disrupt | Niche forums; longer GTM |

**Pick #1.** Lowest cost to test, fastest signal on whether the wedge works,
audience already cares about the exact problem we solve.

## 3. Pre-launch must-fix list (BEFORE public traffic)

These are *real* before-Reddit-hits-it blockers. None require a redeploy beyond
what's already shipped, but they must be confirmed.

- [ ] **Multi-tenant isolation test** — explicitly verify a user cannot read
      another user's report by id OR by guessed public slug. The MVP spec
      flagged this as UNVERIFIED. Write an integration test (`test_honesty_isolation`)
      that creates two users and asserts cross-access 404s. *Hard launch gate.*
- [ ] **Rate-limit + abuse hardening confirmation** — the route uses slowapi
      5/minute on audit, but verify it actually applies in prod under load
      (one curl burst test). Add a per-IP fallback if the slowapi limiter
      is user-scoped only.
- [ ] **Disclaimer / ToS line in the UI** — one paragraph on `/honesty`:
      "This tool analyses trade data you provide. It is not investment advice
      and does not predict future returns. Verdicts apply to your data only."
      Hard requirement to avoid being misread as a trading signal.
- [ ] **Error responses don't leak detail** — confirm 500s don't echo stack
      traces or DB info. Quick prod check.
- [ ] **Capacity sanity** — Railway plan can handle a Reddit hug-of-death?
      Confirm autoscaling / a known throttle point. If unsure, add a global
      cap on concurrent audits in `honesty_api`.
- [ ] **Honest metrics endpoint** — `/api/honesty/stats` (public): total
      audits run, total NO-EDGE verdicts, % overfit-flagged. The numbers
      themselves are the marketing — "X% of backtests submitted to us
      get flagged as overfit" is the most honest, most viral stat there is.
      Cost: ~30 min of code.

Time-to-close-all: ~half a day of focused work. Nothing here is hard.

## 4. The trust artifact (the unfair advantage)

This is the single most differentiated thing we can ship and **must precede the
launch posts**: a public, hosted **"We Killed Our Own Bots" case study** page.

- **URL:** `/case-study/we-killed-our-own-bots` (or external blog post)
- **Content:** condensed, opinionated retelling of `EDGE_FINDINGS.md` +
  `EDGE_FINDINGS.md` + the sibling-platform live-trade audit: the strategies we built over ~1 year,
  the audit results (the 5/5 NO-DEPLOYABLE-EDGE table), the box_symmetric
  in-sample → OOS-collapse story, the per-strategy P&L decomposition
  (random-entry geometry + cost drag = the why-it-fails appendix), and the
  link to run your own.
- **Why it's a moat:** no competitor will ever do this. Every "backtest
  validator" sells optimism. We sell — and *prove* — skepticism, on our own
  work. The story IS the marketing.
- **Build cost:** ~half a day (the content is already written across the two
  EDGE_FINDINGS docs and the why-it-fails appendix).

## 5. Pricing (proposal — set in Stripe before launch)

Aligns to the existing tier scaffold (`models.TIER_LIMITS` already supports
free / starter / pro / enterprise; `honesty_batch` feature key already added).

| Tier | $/mo | What it unlocks |
|------|----:|------------------|
| **Free** | $0 | 1 audit / day, single-file uploads, basic verdict + flags |
| **Starter** | **$9** | Unlimited audits, shareable public report links, report history |
| **Pro** | **$29** | Batch (up to 25 files), API access, no daily cap |
| **Enterprise** | $199 | White-label public proof pages, higher API limits, SLA |

Rationale: $9 is the "Reddit/algotrader-impulse-buy" price (cheaper than one
TradingView Pro). $29 keeps Pro accessible to serious individuals + small prop
shops. Enterprise is for fund-of-EA marketplaces / prop-firm white-labels later;
don't optimise for it at launch.

**Free tier discipline:** never gate the *verdict itself* behind a paywall.
Honest verdicts are the brand. Paywall *volume* and *convenience*, not the truth.

## 6. Distribution sequence (the first 2 weeks)

**Day -3 to Day 0 (Pre-launch):**
1. Close every box in §3.
2. Ship the case-study page (§4) — *this must be live before any post*.
3. Set Stripe prices (§5).
4. Soft-test with 5 friendly users uploading real trade logs. Iterate UX.

**Day 0 (Launch — Reddit):**
- Post on **r/algotrading**: title something like
  *"I spent a year building trading bots, then audited them honestly — 0/5
  had a real edge. I open-sourced the audit tool and made it a web product."*
- Lead with the case study. Don't pitch the product first; pitch the *story*.
  Product link in body, not title.
- Stay in the thread for 24h answering everything. **Do not market;
  evangelize the discipline.** People who want to be sold a 65% win rate
  will leave; people who want to know the truth will stay and become users.
- Cross-post (clearly, not spammy) to **r/Daytrading**, **r/quant**,
  **r/Forex** with the same case-study lead.

**Day 1–3:** Reply in every "is my backtest real?" thread on those subs with
"happy to run yours through our audit if you share the trades — here's what it
said about ours." Demonstrate, don't pitch.

**Day 7 (HackerNews):** Show HN with the title:
*"Show HN: I audited my own trading bots and they had no edge. Now you can audit yours."*
HN audience over-indexes on intellectual honesty; the framing fits perfectly.

**Day 10–14:** Outreach to two prop-firm communities (Discord) with a free
"audit any strategy before paying a challenge fee" offer. Measure conversion.

## 7. Metrics + kill criteria (be honest)

**Watch (first 30 days):**
- Audits run (free signups → first-audit conversion)
- % of audits that return EDGE vs NO-EDGE (the honest stat, **publish it**)
- Free → Starter conversion (the price-point validity check)
- Reddit engagement on launch post (upvotes, comments, time-in-thread)

**Pre-registered kill criteria** (so we don't deceive ourselves like we did
with the bots):
- If **< 200 audits run in 30 days** → wedge or channel wrong; iterate or stop.
- If **< 2% Free→Starter conversion in 60 days** → pricing or value gap;
  reprice or scope down.
- If **users actively reject NO-EDGE verdicts as "the tool is wrong"** rather
  than engaging with the math → the ICP doesn't *want* honesty; pivot ICP
  or kill the product.

That last one is the real risk and it's worth saying clearly.

## 8. Honest risks (and the counter)

- **People don't want honest verdicts.** True for sellers; not true for the
  buyer-side ICP we picked (§2). Mitigated by ICP choice.
- **It's a thin-feature business.** True. Defended by *brand and distribution*
  (the case study + the "we killed our own" credibility), not by algorithm
  moat. Price reflects this (low Free friction, value in volume/proof).
- **A competitor copies it.** They can copy the harness; they can't copy the
  "we proved our own product had no edge and published it" story without
  doing the same painful year of work. The moat is the receipts.
- **Regulatory.** This is data analysis on user-supplied trade history, not
  investment advice, not a signal recommendation. The disclaimer (§3) handles
  it. If you ever start recommending strategies, the calculus changes — don't.

## 9. Decisions only the operator can make (open)

1. **Brand voice** — sharp/skeptical/snarky ("we killed our own bots") vs
   measured/professional. Recommend sharp for the algotrading wedge.
2. **Domain** — own subdomain (e.g. `honesty.theplus-tech.com`) vs the
   theplus-bot Railway URL? A clean domain helps trust + shareability.
3. **Founder face** — is this Theophilus-publicly-leads, or anonymous? The case
   study's credibility benefits from a real name + a year of receipts.
4. **The first Reddit post wording** — I can draft it; you should approve before it goes live.

## 10. What I can do next (in order)

- Write the case-study page content (~half a day; the source material is
  already in the two `EDGE_FINDINGS` docs and the why-it-fails appendix).
- Write `test_honesty_isolation` (the multi-tenant IDOR test — the hardest
  pre-launch gate; ~30 min).
- Ship the public `/api/honesty/stats` endpoint (the "X% overfit" line is
  marketing gold and a 30-min build).
- Draft the launch posts (Reddit + HN) for your review.

Pick the order. None of these is a multi-day undertaking — the heavy lifting
(the product) is done.
