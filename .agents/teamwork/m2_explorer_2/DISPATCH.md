## 2026-11-05T06:23:58Z

From: d0b51128-456f-4a81-855c-2a488d288844 (Parent Orchestrator)
Priority: MESSAGE_PRIORITY_HIGH

You are the FastAPI Endpoints & Validation Explorer (teamwork_explorer) for Milestone 2 of the SYNAPSE-TITAN platform.

Working Directory: C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_explorer_2
Project Repository: C:\Users\Shivam\Desktop\trade_bot

MANDATORY FIRST STEP:
Read the authoritative user request at:
C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\ORIGINAL_REQUEST.md
Also read the project architecture at:
C:\Users\Shivam\Desktop\trade_bot\PROJECT.md
And reference prior findings at:
C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\explorer_survey_backend\handoff.md

OBJECTIVES FOR MILESTONE 2 (Part B: REST APIs & Validation):
1. Focus on FastAPI Endpoints in `server.py`:
   - Design 11 endpoints with Pydantic request/response schemas:
     1. `POST /api/sessions` — Create session with independent backend validation.
     2. `GET /api/sessions/active` — Return currently active session or `{"session": null}`.
     3. `GET /api/sessions/{session_id}` — Get session by ID.
     4. `GET /api/sessions` — List sessions with query filters (status, market, limit).
     5. `PUT /api/sessions/{session_id}` — Update session parameters (allowed in CREATED or PAUSED state).
     6. `POST /api/sessions/{session_id}/start` — Start trading session, arm bot, allocate capital.
     7. `POST /api/sessions/{session_id}/pause` — Pause session, halt new entries, preserve positions.
     8. `POST /api/sessions/{session_id}/resume` — Resume session, adjust expiry countdown.
     9. `POST /api/sessions/{session_id}/stop` — Stop session and trigger session-end policy.
     10. `POST /api/sessions/recommendations` — Auto-select recommended stock basket with rationales powered by `UniverseSelector.auto_select_basket`.
     11. `GET /api/sessions/{session_id}/performance` — Financial KPIs, P&L, drawdown, trade history.
   - Route Disambiguation: Ensure `/api/sessions/status` (existing physical exchange endpoint) is strictly preserved and does NOT get masked by `/api/sessions/{session_id}`.
2. Focus on Independent Backend Validation:
   - Capital validation: strictly positive amount, enforce min/max boundaries (e.g. min 1,000 max 10,000,000).
   - Currency validation: INR for `INDIAN_NSE`, USD for `US_EQUITIES`, `CRYPTO`, `FOREX`, `COMMODITIES`. Reject currency mismatches.
   - Instrument validation: check that every ticker belongs to the selected market jurisdiction via `MarketCalendarManager.detect_market_type` or `ASSET_CATALOG`.
   - Duration validation: duration_type in `FIXED`, `CUSTOM`, `MANUAL_STOP`; if duration_minutes provided, check positive and <= 10080 (1 week).
   - Session-end policy: in `CLOSE_ALL`, `KEEP_OPEN`.
3. Output Requirements:
   - Write your implementation recommendation to `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_explorer_2\analysis.md`.
   - Write a self-contained `handoff.md` with Pydantic schemas, endpoint code snippets, and API test specifications.
   - Send a completion message when finished.
