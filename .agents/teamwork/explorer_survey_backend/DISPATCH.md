## 2026-11-05T05:37:27Z
You are the Backend Architecture Explorer (teamwork_explorer) for the SYNAPSE-TITAN platform.

Working Directory: C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\explorer_survey_backend
Project Repository: C:\Users\Shivam\Desktop\trade_bot

MANDATORY FIRST STEP:
Read the authoritative user request at:
C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\ORIGINAL_REQUEST.md

OBJECTIVES:
1. Conduct a deep investigation of the existing backend architecture in C:\Users\Shivam\Desktop\trade_bot:
   - Analyze server.py, src/execution/live_bot.py, src/execution/broker.py, src/execution/market_sessions.py, src/data/, and database handling in data/trading_ledger.db.
   - Inspect existing FastAPI endpoints, websocket/polling mechanisms, background tasks, and threading/async design.
   - Inspect existing backend tests under tests/ (e.g. test_market_sessions.py, test_e2e_platform.py, test_phase1_phase2_fixes.py) and how they run with Windows `py`.
2. Investigate requirements R2 & R3:
   - TradingSession configuration data model: fields needed (session_id, market, instruments, horizon, duration, capital, currency, strategy_config, risk_config, status, timestamps, etc.).
   - Database schema migrations in SQLite: how TradingSession table should be created/migrated without corrupting existing orders/portfolio tables.
   - FastAPI REST API endpoints required: create, fetch, update, start, pause, resume, stop, auto-select recommendations, and performance metrics.
   - Validation logic required: independent backend validation of all parameters (positive capital, currency matching market, instruments allowed for market/provider, duration boundaries, session-end policies).
   - Execution guardrails: strict isolation of virtual paper trading from real brokerage execution, refusing execution without active session, halting on session expiry or market data staleness.
3. Identify integration points:
   - How `live_bot.py` or `order_controller` will check for active session and enforce session boundaries (basket of instruments, capital allocation, session expiration).
   - How controls (START, PAUSE, STOP) will affect the bot runtime loop.
4. Output Requirements:
   - Write your comprehensive findings to `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\explorer_survey_backend\analysis.md`.
   - Write a self-contained `handoff.md` summarizing your architectural blueprint, exact schemas, endpoint signatures, and proposed implementation plan.
   - When finished, send a message back to the orchestrator with your completion report.
