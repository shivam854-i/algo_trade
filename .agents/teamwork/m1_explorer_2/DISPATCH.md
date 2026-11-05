## 2026-11-05T05:49:37Z
You are the Trade Expectancy Explorer (teamwork_explorer) for Milestone 1 of the SYNAPSE-TITAN platform.

Working Directory: C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m1_explorer_2
Project Repository: C:\Users\Shivam\Desktop\trade_bot

MANDATORY FIRST STEP:
Read the authoritative user request at:
C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\ORIGINAL_REQUEST.md
Also read the project architecture at:
C:\Users\Shivam\Desktop\trade_bot\PROJECT.md
And reference prior findings at:
C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\explorer_survey_quant\handoff.md

OBJECTIVES FOR MILESTONE 1 (Quantitative Strategy Engine - Part B):
1. Focus on `TradeEvaluator` (`src/strategy/trade_evaluator.py`):
   - Design data structures: `TradeEvaluationResult`.
   - Implement exact mathematical Net Expectancy formula:
     $$\text{EV} = P(\text{Win}) \cdot \mathbb{E}[\text{Win} \mid \text{Win}] - P(\text{Loss}) \cdot \mathbb{E}[\text{Loss} \mid \text{Loss}] - \text{Expected Friction Cost}$$
   - Derive conservative win probability $p_{\text{conservative}} = \max(0.0, p - 1.0 \cdot \sigma_p)$ incorporating epistemic uncertainty margin:
     $$\sigma_p = \sqrt{\frac{p(1 - p)}{\min(N_{\text{bars}}, 250)}} \cdot \left(1.0 + 0.2 \cdot \frac{q_{90} - q_{10}}{\max(|q_{50}|, 1e-4)}\right)$$
   - Calculate conditional returns $\mathbb{E}[\text{Win} \mid \text{Win}]$ and $\mathbb{E}[\text{Loss} \mid \text{Loss}]$ including gap risk buffer ($0.10 \times \sigma_{\text{bar}}$).
   - Integrate with `FrictionEvaluator` from `src/execution/frictions.py` for statutory round-trip costs and Almgren-Chriss market impact.
   - Enforce rejection of all trades with $\text{EV} \le 0$ or below minimum hurdle (+0.20%).
2. Focus on `TradeRanker` (`src/strategy/trade_ranker.py`):
   - Design data structures: `RankedOpportunity`.
   - Calculate risk-adjusted value: $\text{EV} / \sigma_{\text{asset}}$.
   - Apply market regime alignment multipliers: State 0 Trending ($1.25\times$ for trend-aligned), State 1 Choppy ($1.15\times$ for mean-reverting), State 2 Crisis ($0.0\times$ hard veto).
   - Apply model synergy boost ($1.15\times$) when Causal TCN and Meta-Labeler strongly agree.
   - Sort opportunities descending and label ineligible trades.
3. Output Requirements:
   - Write your recommendation report to `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m1_explorer_2\analysis.md`.
   - Write a self-contained `handoff.md` with complete mathematical specifications, class designs, and test requirements for `tests/test_strategy_trade_evaluator.py` and `tests/test_strategy_trade_ranker.py`.
   - Send a completion message back when done.
