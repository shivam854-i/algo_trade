# Milestone 2 Iteration 2 Worker Dispatch

## Objective
Implement production-grade fixes for:
1. TOCTOU concurrency race condition in `SessionManager.start_session()` (Tier 1 partial unique index in SQLite + Tier 2 atomic conditional UPDATE with `NOT EXISTS` and descriptive `RuntimeError` on conflict).
2. Telemetry leakage in `SessionManager.compute_session_performance()` (remove account-wide fallback, strictly isolate closed trades and metrics by `session_id`, and ensure `PaperBroker.open_position()` auto-resolves `effective_session_id`).
3. Order tagging in `PaperBroker._record_order_event()` and `queue_pre_market_order()`, and pass `account_id=session.account_id` in `server.py:start_trading_session()`.
4. Ensure `tests/test_m2_challenger_lifecycle.py` passes all 16 tests, including `test_stress_concurrent_race_condition_to_start_two_sessions` and `test_stress_session_isolation_and_no_telemetry_leakage`.

## Exclusive Write Boundaries
- `src/execution/broker.py`
- `src/execution/session_manager.py`
- `server.py`
- `tests/test_m2_challenger_lifecycle.py`

## Inputs & Blueprints
- Plan: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_worker_1\plan.md`
- Explorer 1 Handoff: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_explorer_1\handoff.md`
- Explorer 2 Handoff: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_explorer_2\handoff.md`
- Explorer 3 Handoff: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_explorer_3\handoff.md`
- Original Request: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\ORIGINAL_REQUEST.md`
- Project Plan: `C:\Users\Shivam\Desktop\trade_bot\PROJECT.md`

## Verification Requirements
Execute and document passing output in your `handoff.md`:
1. `py -m pytest tests/test_m2_challenger_lifecycle.py -v` (16 passed)
2. `py -m pytest tests/test_m2_challenger_validation.py -v` (43 passed)
3. `py -m pytest tests/test_trading_session_lifecycle.py -v` (22 passed)
4. `py -m pytest tests/test_milestone_m2_sessions.py tests/test_strategy_*.py tests/test_market_sessions.py -v`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## 2026-11-05T07:36:20Z
[Message from d0b51128-456f-4a81-855c-2a488d288844]
You are m2_i2_worker_1, the Backend Concurrency and Telemetry Implementer for Milestone 2 Iteration 2 of the SYNAPSE-TITAN platform.

Working Directory: C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_worker_1
Repository Root: C:\Users\Shivam\Desktop\trade_bot
Orchestrator ID: d0b51128-456f-4a81-855c-2a488d288844

Instructions:
1. Read your dispatch instructions and implementation plan:
   - C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_worker_1\DISPATCH.md
   - C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_worker_1\plan.md
   - C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_explorer_1\handoff.md
   - C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_explorer_2\handoff.md
   - C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_explorer_3\handoff.md
   - C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\ORIGINAL_REQUEST.md
   - C:\Users\Shivam\Desktop\trade_bot\PROJECT.md

2. Exclusive Write Boundaries:
   - src/execution/broker.py
   - src/execution/session_manager.py
   - server.py
   - tests/test_m2_challenger_lifecycle.py

3. Implementation Details:
   a. In src/execution/broker.py:
      - Add partial unique index idx_single_active_session in _init_db() on trading_sessions(account_id) WHERE status IN ('RUNNING', 'PAUSED').
      - In open_position(): auto-resolve effective_session_id from active session if not explicitly provided.
      - In _record_order_event() and queue_pre_market_order(): tag effective_session_id into INSERT INTO orders.
   b. In src/execution/session_manager.py:
      - In start_session(): implement atomic conditional UPDATE with NOT EXISTS checking account active sessions, and catch sqlite3.IntegrityError to raise RuntimeError("Cannot start session #{session_id}: Account already has active session ...").
      - In compute_session_performance(): remove account-wide fallback (lines 746-748 and 752-754) and query strictly by session_id.
   c. In server.py:
      - In start_trading_session(): pass account_id=session.account_id when calling start_session.
   d. In tests/test_m2_challenger_lifecycle.py:
      - In test_stress_compute_performance_accounting_accuracy: ensure broker.active_session_id is set to session.id when opening positions directly.

4. Run all verification tests:
   - py -m pytest tests/test_m2_challenger_lifecycle.py -v (all 16 tests must pass)
   - py -m pytest tests/test_m2_challenger_validation.py -v (all 43 tests must pass)
   - py -m pytest tests/test_trading_session_lifecycle.py -v (all 22 tests must pass)
   - py -m pytest tests/test_milestone_m2_sessions.py tests/test_strategy_*.py tests/test_market_sessions.py -v

5. MANDATORY INTEGRITY WARNING:
   DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

6. Write progress.md with timestamped steps during your work, and write a complete, self-contained handoff.md in your working directory (.agents/teamwork/m2_i2_worker_1/handoff.md) documenting exact code changes, test commands, and verbatim test output. Then send a message to the orchestrator.
