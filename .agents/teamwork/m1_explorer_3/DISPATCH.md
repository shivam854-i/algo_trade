## 2026-11-05T05:49:44Z
From: d0b51128-456f-4a81-855c-2a488d288844
Priority: MESSAGE_PRIORITY_HIGH

You are the Portfolio and Explainability Explorer (teamwork_explorer) for Milestone 1 of the SYNAPSE-TITAN platform.

Working Directory: C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m1_explorer_3
Project Repository: C:\Users\Shivam\Desktop\trade_bot

MANDATORY FIRST STEP:
Read the authoritative user request at:
C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\ORIGINAL_REQUEST.md
Also read the project architecture at:
C:\Users\Shivam\Desktop\trade_bot\PROJECT.md
And reference prior findings at:
C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\explorer_survey_quant\handoff.md

OBJECTIVES FOR MILESTONE 1 (Quantitative Strategy Engine - Part C):
1. Focus on `PortfolioSelector` (`src/strategy/portfolio_selector.py`):
   - Design data structures: `PortfolioAllocationResult`.
   - Implement Fractional Kelly mode:
     f_i^* = P(Win_i) - \frac{1 - P(Win_i)}{b_i}, \quad w_i = \min(c_{kelly} \cdot f_i^* \cdot VolScalar \cdot DDScalar, 0.20)
   - Implement Hierarchical Risk Parity (HRP) mode on eligible assets with Marchenko-Pastur RMT de-noising and gross leverage scaling.
   - Enforce the MANDATORY 100% CASH ALLOCATION GUARANTEE:
     Whenever zero candidate opportunities meet the positive Net Expectancy hurdle (EV > 0), or during market Crisis regime, return:
     `weights={"CASH": 1.0}`, `cash_weight=1.0`, `is_100_percent_cash=True`, `allocated_capital={}`, `shares={}`.
   - Dynamic Capital Scaling Invariant: Model predictions (P(Win), targets, barriers) remain decoupled from capital; dollar amounts and share quantities scale linearly with initial virtual capital.
2. Focus on `DecisionExplainer` (`src/strategy/decision_explainer.py`):
   - Design data structures: `PlainLanguageExplanation`.
   - Produce transparent, plain-language text explanations for:
     a. Accepted trades (stating EV, win probability, statutory fees deducted, regime alignment, position sizing rationale).
     b. Rejected trades (negative EV, friction hurdle failure, or microstructure circuit breaker).
     c. 100% Cash preservation (clear explanation of why capital is kept in cash).
3. Output Requirements:
   - Write your recommendation report to `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m1_explorer_3\analysis.md`.
   - Write a self-contained `handoff.md` with complete class blueprints, formulas, and test specifications for `tests/test_strategy_portfolio_selector.py` and `tests/test_strategy_decision_explainer.py`.
   - Send a completion message back when done.
