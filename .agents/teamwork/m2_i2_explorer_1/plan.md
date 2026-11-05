# M2 Iteration 2 Explorer 1 Plan
Investigate TOCTOU concurrency race in `SessionManager.start_session()`.
Analyze `tests/test_m2_challenger_lifecycle.py::TestEmpiricalConcurrentDatabaseUpdates::test_stress_concurrent_race_condition_to_start_two_sessions`.
Design atomic SQLite transaction or partial unique index solution to prevent multiple concurrent active sessions.
Write analysis.md and handoff.md.
