## 2026-11-05T06:13:00Z
From: d0b51128-456f-4a81-855c-2a488d288844 (Lead Orchestrator)
Content:
You are Empirical Strategy Challenger 1 (teamwork_challenger) for Milestone 1 of the SYNAPSE-TITAN platform.

Working Directory: C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m1_challenger_1
Project Repository: C:\Users\Shivam\Desktop\trade_bot

MANDATORY FIRST STEP:
Read the authoritative user request at:
C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\ORIGINAL_REQUEST.md
Also read the project architecture at:
C:\Users\Shivam\Desktop\trade_bot\PROJECT.md
And Worker 1 handoff at:
C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m1_worker_1\handoff.md

OBJECTIVES:
Empirically challenge and stress-test the new quantitative modules in `src/strategy/`:
1. Stress-test `TradeEvaluator`:
   - Generate adversarial probability and barrier inputs (inverted barriers, zero probability, extreme quantile spreads).
   - Verify that Net Expectancy is strictly monotonic with respect to win probability and payoff odds.
   - Verify that every opportunity with EV <= 0 is rejected.
2. Stress-test `PortfolioSelector`:
   - Run adversarial stress scenarios with 0 qualifying opportunities: verify that the engine returns strictly 100% Cash (`weights={"CASH": 1.0}`, `is_100_percent_cash=True`).
   - Run stress scenarios with extreme drawdown (>= 15%): verify that the kill switch forces 100% Cash.
   - Verify single-position 20% leverage ceiling cannot be breached even with extreme Kelly values.
   - Verify dynamic capital scaling invariance: doubling or halving initial virtual capital does not alter model predictions.
3. Verification:
   - Run the full suite of strategy tests: `py -m pytest tests/test_strategy_*.py -v`
   - Run baseline mathematical invariants: `py tests/test_phase1_phase2_fixes.py`
4. Output Requirements:
   - Write your stress-test report to `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m1_challenger_1\analysis.md`.
   - Write a self-contained `handoff.md` with an explicit verdict: **APPROVE** or **REQUEST_CHANGES**.
   - Send a message back to the orchestrator with your verdict.
