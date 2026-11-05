# M2 Iteration 2 Explorer 2 Plan
Investigate cross-session PnL and trade telemetry leakage in `SessionManager.compute_session_performance()`.
Analyze `tests/test_m2_challenger_lifecycle.py::TestEmpiricalEdgeCases::test_stress_session_isolation_and_no_telemetry_leakage`.
Design strict session-scoped trade query eliminating unconstrained account-wide fallback.
Write analysis.md and handoff.md.
