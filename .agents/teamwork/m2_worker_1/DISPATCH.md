## 2026-11-05T06:35:47Z
You are the Backend Session Management & REST API Implementer (Worker) for Milestone 2 of the SYNAPSE-TITAN platform.

Your task is to implement the complete backend session architecture, SQLite schema migrations, 11 FastAPI REST endpoints with independent validation, autonomous bot execution loop guardrails, and automated lifecycle tests.

## 🔒 Key Constraints & Rules
- Path to authoritative user request: C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\ORIGINAL_REQUEST.md. You MUST read this file first.
- Working directory: C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_worker_1. Write all your agent coordination files (BRIEFING.md, progress.md, handoff.md) here.
- Target project repository: C:\Users\Shivam\Desktop\trade_bot.
- MANDATORY INTEGRITY WARNING:
  DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.
- All trading, orders, accounts, and capital must remain strictly virtual using genuine market data (PAPER_TRADING_ONLY = True). Real-money execution must remain permanently blocked.
- Do NOT break or regress any existing tests. Existing tests must pass 100%.

## Input Architectural Blueprints
Read the handoff reports produced by the 3 Milestone 2 Explorers:
1. `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_explorer_1\handoff.md`: Session Model (`TradingSession`, `SessionState`), SQLite migrations in `TradingLedgerDB`, and `SessionManager` implementation.
2. `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_explorer_2\handoff.md`: 11 FastAPI REST endpoints in `server.py`, route ordering precedence (preserving `/api/sessions/status`), Pydantic v2 schemas, and independent backend validation.
3. `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_explorer_3\handoff.md`: `LiveBotController` autonomous loop integration in `src/execution/live_bot.py` (active session gating, basket confinement, capital boundary, dynamic horizon parameter binding, quantitative decision engine integration via `TradeEvaluator`/`TradeRanker`/`PortfolioSelector`, explainable activity feed via `DecisionExplainer`, session expiry policy enforcement).

## Your Exclusive File Ownership
You have exclusive write access to:
- `src/execution/session_manager.py` (Create)
- `src/execution/broker.py` (Update `_init_db` with `trading_sessions` table and non-destructive `session_id` migrations)
- `server.py` (Add Pydantic schemas, validation functions, and 11 REST endpoints; ensure route ordering prevents shadowing `/api/sessions/status`)
- `src/execution/live_bot.py` (Update `LiveBotController` to enforce session gating, basket confinement, capital bounds, dynamic horizon mapping, systematic decision engine, DECISION logging, and expiry enforcement)
- `tests/test_trading_session_lifecycle.py` (Create comprehensive automated test suite covering all lifecycle state transitions, validations, expiry, and execution guardrails)

## Verification Requirements
You MUST run the tests yourself and report exact passing commands and outputs in your `handoff.md`:
1. Run `py -m pytest tests/test_trading_session_lifecycle.py -v`
2. Run existing tests to ensure zero regression:
   - `py -m pytest tests/test_milestone_m2_sessions.py`
   - `py -m pytest tests/test_strategy_horizon_mapper.py tests/test_strategy_trade_evaluator.py tests/test_strategy_trade_ranker.py tests/test_strategy_portfolio_selector.py tests/test_strategy_decision_explainer.py`
   - `py -m pytest tests/test_phase1_phase2_fixes.py`

When finished, write your self-contained `handoff.md` in `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_worker_1\handoff.md` and send a completion message to caller.
