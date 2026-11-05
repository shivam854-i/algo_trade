# M2 Reviewer 2 Plan
Review `server.py` and `src/execution/live_bot.py`.
Verify 11 REST API endpoints, static route precedence before `/api/sessions/{session_id}`, Pydantic v2 independent backend validation, active session gating in `step_tick()`, basket confinement, capital boundary, dynamic horizon parameter mapping, quantitative decision engine integration, explainable activity feed logging, and session expiry enforcement.
Run `py -m pytest tests/test_trading_session_lifecycle.py -v`.
Run `py -m pytest tests/test_milestone_m2_sessions.py -v`.
Write handoff.md with verdict (APPROVE or REQUEST_CHANGES).
