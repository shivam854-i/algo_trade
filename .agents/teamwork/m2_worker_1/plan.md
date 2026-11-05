# Milestone 2 Worker Plan

1. Implement `src/execution/session_manager.py` (TradingSession, SessionState, SessionManager)
2. Update `src/execution/broker.py` with guarded SQLite migrations (`trading_sessions` table and `session_id` columns)
3. Update `server.py` with 11 REST API endpoints, route precedence, and Pydantic v2 independent validation
4. Update `src/execution/live_bot.py` with active session enforcement, basket confinement, capital boundary, dynamic horizon parameter binding, quantitative decision engine integration, explainability logging, and expiry enforcement
5. Create and run `tests/test_trading_session_lifecycle.py` verifying all lifecycle transitions, edge cases, and safeguards
6. Run existing test suites (`tests/test_milestone_m2_sessions.py`, `tests/test_strategy_*.py`) to guarantee zero regression
