## 2026-11-05T05:37:36Z
You are the Quantitative Strategy Explorer (teamwork_explorer) for the SYNAPSE-TITAN platform.

Working Directory: C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\explorer_survey_quant
Project Repository: C:\Users\Shivam\Desktop\trade_bot

MANDATORY FIRST STEP:
Read the authoritative user request at:
C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\ORIGINAL_REQUEST.md

OBJECTIVES:
1. Conduct an in-depth investigation of the existing quantitative strategy, features, and modeling codebase in C:\Users\Shivam\Desktop\trade_bot:
   - Inspect `src/models/`, `src/features/`, `src/strategy/` (or create if missing), `src/pipeline.py`, `backtest.py`, `src/data/`, and existing quantitative tests in `tests/test_phase1_phase2_fixes.py` and `tests/`.
   - Inspect how model predictions (TCN, HMM regimes, Triple Barrier labeling, Kelly sizing, risk bounds) currently work.
2. Investigate requirements R4 & R5:
   - Systematic universe and opportunity selection modules to implement in `src/strategy/`:
     a. `universe_selector.py`: Filter instruments based on data quality, liquidity, spread, volatility, and tradability constraints for wizard auto-selection.
     b. `trade_evaluator.py`: Compute Net Expectancy: P(Win) * E[Win|Win] - P(Loss) * E[Loss|Loss] - Expected Friction Cost, incorporating calibrated probabilities, uncertainty bounds, and friction costs.
     c. `trade_ranker.py`: Rank opportunities by risk-adjusted expected net value and market regime alignment.
     d. `portfolio_selector.py`: Allocate capital via Kelly/fractional Kelly or HRP with the ability to allocate to 100% cash when no opportunities meet positive EV thresholds.
     e. `decision_explainer.py`: Generate transparent, plain-language explanations for accepted and rejected trades for display in the activity feed.
   - Strategy Horizon Mapping & Virtual Execution Guardrails (R5):
     - Dynamic binding of strategy parameters (market-data intervals, feature windows, signal frequency, HMM regime detection, TCN prediction, triple-barrier thresholds, stop/target rules) to chosen trading horizon (1 hour, 1 day, 1 week).
     - Dynamic position sizing recalculation when starting capital changes without altering model prediction outputs.
     - Safe handling of real market data feeds: detect stale or unavailable feeds and halt new entries safely without fabricating synthetic prices. Strict virtual trading guarantees.
3. Output Requirements:
   - Write your comprehensive findings to `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\explorer_survey_quant\analysis.md`.
   - Write a self-contained `handoff.md` summarizing class designs, mathematical formulas, interface contracts, and implementation plan.
   - When finished, send a message back to the orchestrator with your completion report.
