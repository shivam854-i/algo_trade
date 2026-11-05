## 2026-11-05T07:20:21Z
You are Milestone 2 Iteration 2 Explorer 2 for the SYNAPSE-TITAN platform.

## Context & Gate Failure
Milestone 2 Iteration 1 verification gate failed due to cross-session metric and trade telemetry leakage reported by `m2_challenger_1` (and noted by `m2_reviewer_1`):
In `src/execution/session_manager.py` (lines 743-755):
In `compute_session_performance()`:
When calculating metrics for a session with 0 closed trades, the code falls back to `SELECT * FROM trades WHERE account_id = ?`. This mistakenly attributes historical closed trades, win rates, and realized P&L from earlier sessions on that account to the new session.

Test Failure:
`tests/test_m2_challenger_lifecycle.py::TestEmpiricalEdgeCases::test_stress_session_isolation_and_no_telemetry_leakage`
AssertionError: VULNERABILITY: Session sess_2c4db634f817 leaked 1 trades from prior session sess_ea8cde700967!

## Mandatory Reading & Working Directory
- Authoritative requirements: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\ORIGINAL_REQUEST.md` (read first).
- Project scope & layout: `C:\Users\Shivam\Desktop\trade_bot\PROJECT.md`.
- Challenger 1 report: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_challenger_1\handoff.md`.
- Reviewer 1 report: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_reviewer_1\handoff.md`.
- Your working directory: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_explorer_2`.

## Your Mission
Investigate `src/execution/session_manager.py:730-760` and `tests/test_m2_challenger_lifecycle.py`.
Design the exact fix for `compute_session_performance()`:
- Eliminate the fallback to `SELECT * FROM trades WHERE account_id = ?`.
- Ensure a session with 0 closed trades returns clean, zeroed accounting: `total_trades = 0`, `winning_trades = 0`, `win_rate = 0.0`, `realized_pnl = 0.0`, while accurately reflecting starting capital, available cash, and open positions strictly tagged with `session_id`.
Recommend the clean, robust fix blueprint. Do NOT implement code directly.
Write your analysis in `analysis.md` and complete handoff report in `handoff.md`, then notify caller via `send_message`.
