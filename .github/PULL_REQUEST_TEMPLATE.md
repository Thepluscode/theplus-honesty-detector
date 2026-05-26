# Pull request

**Linked issue**
Closes #(issue number) — required for all non-trivial changes (anything beyond typos and small documentation fixes).

**What this changes**
One or two sentences describing the change.

**Verification**
For tool changes: confirm the three self-contained tools still produce verdicts consistent with the pre-computed reports in `reports/`. If numbers changed, explain why the new numbers are correct.

For methodology changes: link the issue where the statistical argument was made and agreed.

**Checklist**
- [ ] This does not soften the verdict criteria (thresholds in `strategy_edge_audit.py` and the live backend are unchanged)
- [ ] This does not add a strategy-tuning surface
- [ ] If a new audit tool is included, the pass/fail criteria were pre-registered in the linked issue before the tool was run
