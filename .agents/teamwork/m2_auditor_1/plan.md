# M2 Forensic Auditor Plan
Audit implementation integrity for Milestone 2:
1. Verify genuine logic: zero hardcoded expected values or bypasses.
2. Verify SQLite migrations: inspect table schemas and column migrations in `broker.py`.
3. Verify test validity: ensure `tests/test_trading_session_lifecycle.py` tests genuine assertions (no `assert True`).
4. Verify virtual trading isolation: confirm `PAPER_TRADING_ONLY = True` and real broker adapters remain blocked.
Write handoff.md with verdict (CLEAN or INTEGRITY VIOLATION).
