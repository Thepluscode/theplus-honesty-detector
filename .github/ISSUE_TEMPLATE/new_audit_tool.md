---
name: New audit tool proposal
about: Propose a free pre-check tool for a fresh edge hypothesis
labels: new-tool
---

**Edge hypothesis**
State the hypothesis precisely. What market inefficiency or structural edge are you proposing to test?

**Why this hypothesis is not already covered**
Confirm it is not a variant of the 5 hypotheses already closed in EDGE_FINDINGS.md (TA strategies, retail funding arb, cross-sectional factors/momentum, PEAD, index reconstitution).

**Free pre-check methodology**
Describe the test in enough detail that someone else could implement it:
- Data source (must be free and publicly accessible)
- Signal construction (no fitted thresholds)
- Entry/exit rules (no look-ahead)
- Cost model (be pessimistic)

**Pre-registered pass/fail criteria**
State the exact thresholds the test must clear for you to call it a candidate edge. These must be written here before any results are produced. We will hold you to this.

Example format:
- net mean return > 0
- cluster-robust t >= 2.0
- >= 60% of annual cohorts net-positive

**Data source details**
- Name and URL of the free data source
- Date range available
- Known survivorship or selection biases in the source (be honest)

**What a failure means**
What conclusion will you accept if the pre-check returns NO EDGE?
