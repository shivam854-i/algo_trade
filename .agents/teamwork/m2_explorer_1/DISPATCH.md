## 2026-11-05T06:23:48Z
You are the Session Model & SQLite Migration Explorer (teamwork_explorer) for Milestone 2 of the SYNAPSE-TITAN platform.

Working Directory: C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_explorer_1
Project Repository: C:\Users\Shivam\Desktop\trade_bot

MANDATORY FIRST STEP:
Read the authoritative user request at:
C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\ORIGINAL_REQUEST.md
Also read the project architecture at:
C:\Users\Shivam\Desktop\trade_bot\PROJECT.md
And reference prior findings at:
C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\explorer_survey_backend\handoff.md

OBJECTIVES FOR MILESTONE 2 (Part A: Session Model & Database Migrations):
1. Focus on `TradingSession` data model in `src/execution/session_manager.py`:
   - Design complete dataclass and serialization methods (`to_dict`, `from_dict`, `from_row`).
   - Define lifecycle states: `CREATED`, `RUNNING`, `PAUSED`, `COMPLETED`, `STOPPED`.
   - Fields: `id`, `user_id`, `account_id`, `name`, `market`, `instruments` (JSON list), `horizon`, `duration_type` (`FIXED`, `CUSTOM`, `MANUAL_STOP`), `duration_minutes`, `session_end_policy` (`CLOSE_ALL`, `KEEP_OPEN`), `allocated_capital`, `currency` (`USD`, `INR`), `strategy_config` (JSON), `risk_config` (JSON), `status`, `created_at`, `started_at`, `paused_at`, `resumed_at`, `ended_at`, `expires_at`, `accumulated_pause_seconds`, `current_metrics` (JSON), `last_heartbeat_at`.
2. Focus on SQLite schema migrations in `src/execution/broker.py`:
   - Design idempotent migration in `TradingLedgerDB._init_db()` creating `trading_sessions` table with indexes (`idx_sessions_status`, `idx_sessions_market`, `idx_sessions_account`).
   - Add non-destructive `ALTER TABLE orders ADD COLUMN session_id TEXT`, `positions`, `trades`, `equity_history` inside `try...except` blocks.
3. Focus on `SessionManager` SQLite persistence operations:
   - `create_session`, `get_session`, `get_active_session`, `list_sessions`, `update_session`, `start_session`, `pause_session`, `resume_session`, `stop_session`, `check_and_enforce_expiry`, `update_session_metrics`.
4. Output Requirements:
   - Write your implementation specification to `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_explorer_1\analysis.md`.
   - Write a self-contained `handoff.md` with class blueprints and unit test specifications for `tests/test_trading_session_lifecycle.py`.
   - Send a completion message when finished.
