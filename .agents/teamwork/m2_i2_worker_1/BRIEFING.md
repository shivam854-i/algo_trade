# BRIEFING — 2026-11-05T07:40:00Z

## Mission
Implement backend concurrency and telemetry isolation fixes for Milestone 2 Iteration 2 (TOCTOU race in start_session, telemetry leakage in compute_session_performance, orders session_id tagging in PaperBroker, and server.py account scoping).

## 🔒 My Identity
- Archetype: Backend Concurrency and Telemetry Implementer
- Roles: implementer, qa, specialist
- Working directory: C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_worker_1
- Original parent: d0b51128-456f-4a81-855c-2a488d288844
- Milestone: M2 Iteration 2

## 🔒 Key Constraints
- Exclusive write boundaries:
  - `src/execution/broker.py`
  - `src/execution/session_manager.py`
  - `server.py`
  - `tests/test_m2_challenger_lifecycle.py`
- DO NOT CHEAT: Genuine logic only, no hardcoded results or dummy facades.
- Minimal change principle: only modify what is necessary.
- Pass all 4 test suites without regressions:
  - `tests/test_m2_challenger_lifecycle.py` (16 passed)
  - `tests/test_m2_challenger_validation.py` (43 passed)
  - `tests/test_trading_session_lifecycle.py` (22 passed)
  - `tests/test_milestone_m2_sessions.py`, `tests/test_strategy_*.py`, `tests/test_market_sessions.py`

## Current Parent
- Conversation ID: d0b51128-456f-4a81-855c-2a488d288844
- Updated: 2026-11-05T07:40:00Z

## Task Summary
- **What to build**:
  1. `src/execution/broker.py`:
     - Add partial unique index `idx_single_active_session` in `_init_db()` on `trading_sessions(account_id) WHERE status IN ('RUNNING', 'PAUSED')`.
     - In `open_position()`: auto-resolve `effective_session_id` from active session in SQLite if not provided or set on self.
     - In `_record_order_event()` and `queue_pre_market_order()`: tag `session_id` in `INSERT INTO orders` statements.
  2. `src/execution/session_manager.py`:
     - In `start_session()`: atomic conditional `UPDATE` with `NOT EXISTS (SELECT 1 FROM trading_sessions WHERE account_id = ? AND status IN ('RUNNING', 'PAUSED'))` and catch `sqlite3.IntegrityError` to raise descriptive `RuntimeError`.
     - In `compute_session_performance()`: remove account-wide fallback and query strictly by `session_id`.
  3. `server.py`:
     - In `start_trading_session()`: pass `account_id=session.account_id` when checking active session.
  4. `tests/test_m2_challenger_lifecycle.py`:
     - In `test_stress_compute_performance_accounting_accuracy`: ensure `broker.active_session_id = session.id` when testing directly.
- **Success criteria**: All tests across the 4 test suites pass cleanly.
- **Interface contracts**: `PROJECT.md` § Interface Contracts
- **Code layout**: `PROJECT.md` § Code Layout

## Key Decisions Made
- Use defense-in-depth for concurrency: partial unique index in SQLite + atomic conditional update with NOT EXISTS + rowcount check + sqlite3.IntegrityError wrapping.
- Strictly isolate closed trades and open positions by session_id in `compute_session_performance`.
- Tag orders with `session_id` consistently across all broker entry points.

## Artifact Index
- `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_worker_1\plan.md` — Implementation plan
- `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_worker_1\progress.md` — Liveness and progress tracker
- `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_i2_worker_1\handoff.md` — Final handoff report

## Change Tracker
- **Files modified**: None yet
- **Build status**: Pending
- **Pending issues**: None

## Quality Status
- **Build/test result**: Pending initial test run
- **Lint status**: Clean
- **Tests added/modified**: `tests/test_m2_challenger_lifecycle.py`

## Loaded Skills
- None
