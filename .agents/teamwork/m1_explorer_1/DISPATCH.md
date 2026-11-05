## 2026-11-05T05:49:26Z
Sender: d0b51128-456f-4a81-855c-2a488d288844
Recipient: 4adb97e8-6a82-451d-a84d-805c57018d05
Priority: MESSAGE_PRIORITY_HIGH

You are the Universe and Horizon Explorer (teamwork_explorer) for Milestone 1 of the SYNAPSE-TITAN platform.

Working Directory: C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m1_explorer_1
Project Repository: C:\Users\Shivam\Desktop\trade_bot

MANDATORY FIRST STEP:
Read the authoritative user request at:
C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\ORIGINAL_REQUEST.md
Also read the project architecture at:
C:\Users\Shivam\Desktop\trade_bot\PROJECT.md
And reference prior findings at:
C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\explorer_survey_quant\handoff.md

OBJECTIVES FOR MILESTONE 1 (Quantitative Strategy Engine - Part A):
1. Focus on `UniverseSelector` (`src/strategy/universe_selector.py`):
   - Design data structures: `UniverseSelectionCriteria`, `CandidateEvaluation`, `UniverseSelectionResult`.
   - Formulate exact filtering rules: Data Quality Score (>=0.90 based on missing bars and zero-volume bars), ADV liquidity gate (>= $5M USD for US, >= ₹50M INR for NSE, >= $10M for Crypto), spread gate (<= 25 bps), and volatility tradability bounds (8% to 100% annualized).
   - Formulate composite scoring and bounded basket auto-selection (3 to 6 instruments) with clear rationale for the setup wizard.
2. Focus on `HorizonMapper` (`src/strategy/horizon_mapper.py`):
   - Dynamic binding across trading horizons: 1 hour (intraday 5m bars), 1 day (1h/15m bars), and 1 week (daily 1d bars).
   - Map lookback periods, bar intervals, EMA fast/slow spans, ATR windows, annualization factors (140.2 for 1h, 40.5 for 1d, 15.87 for 1wk), HMM windows, TCN sequence lengths and horizons, profit target and stop loss volatility multipliers, max holding bars, and default session-end policies.
3. Output Requirements:
   - Write your implementation recommendation report to `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m1_explorer_1\analysis.md`.
   - Write a self-contained `handoff.md` with complete class blueprints, formulas, and test specifications for `tests/test_strategy_universe_selector.py` and `tests/test_strategy_horizon_mapper.py`.
   - Send a completion message back when done.
