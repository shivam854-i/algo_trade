# Milestone 2 Iteration 2 Worker Plan

1. Implement Tier 1 & Tier 2 Concurrency Fix:
   - In `src/execution/broker.py`: Add partial unique index `idx_single_active_session` in `_init_db()`.
   - In `src/execution/session_manager.py`: Atomic conditional UPDATE with `NOT EXISTS` in `start_session()`, catching `sqlite3.IntegrityError` and rowcount == 0 to raise `RuntimeError("Cannot start session #{session_id}: Account already has active session #{active.id} ({active.status}). Pause or stop the active session first.")`.
2. Implement Telemetry Isolation Fix:
   - In `src/execution/session_manager.py`: Remove account-wide fallback in `compute_session_performance()`. Query strictly by `session_id`.
   - In `src/execution/broker.py`: Auto-resolve `effective_session_id` in `open_position()` if not passed.
   - In `tests/test_m2_challenger_lifecycle.py`: Ensure `broker.active_session_id = session.id` in `test_stress_compute_performance_accounting_accuracy`.
3. Implement Storage & Order Tagging Fix:
   - In `src/execution/broker.py`: Record `session_id` in `_record_order_event()` and `queue_pre_market_order()`.
   - In `server.py`: Pass `account_id=session.account_id` in `start_trading_session()`.
4. Run all test suites:
   - `py -m pytest tests/test_m2_challenger_lifecycle.py -v` (16/16 must pass)
   - `py -m pytest tests/test_m2_challenger_validation.py -v` (43/43 must pass)
   - `py -m pytest tests/test_trading_session_lifecycle.py -v` (22/22 must pass)
   - `py -m pytest tests/test_milestone_m2_sessions.py tests/test_strategy_*.py tests/test_market_sessions.py -v` (all must pass)
5. Write handoff.md with verified passing commands and outputs.
