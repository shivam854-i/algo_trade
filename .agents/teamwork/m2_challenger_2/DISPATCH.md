## 2026-11-05T07:05:54Z
You are Milestone 2 Empirical Challenger 2 for the SYNAPSE-TITAN platform.

Your task is to empirically stress-test independent backend parameter validations, route precedence, bot basket confinement, and capital headroom constraints in `server.py` and `src/execution/live_bot.py`.

## Mandatory Reading & Working Directory
- Authoritative requirements: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\ORIGINAL_REQUEST.md` (read first).
- Project scope & layout: `C:\Users\Shivam\Desktop\trade_bot\PROJECT.md`.
- Implementer's handoff: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_worker_1\handoff.md`.
- Your working directory: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_challenger_2`.

## Empirical Challenge Tasks
1. Write a dedicated empirical challenge test file: `tests/test_m2_challenger_validation.py` containing at least 10 stress tests:
   - Malicious/invalid capital payloads: negative capital, 0 capital, capital < 1,000, capital > 10,000,000, non-numeric strings, NaN/Inf.
   - Currency mismatch payloads: `INDIAN_NSE` with `USD`, `US_EQUITIES` with `INR`.
   - Jurisdiction mismatch payloads: `AAPL` in an `INDIAN_NSE` session, `RELIANCE.NS` in a `US_EQUITIES` session.
   - Route precedence collisions: verify `GET /api/sessions/status`, `GET /api/sessions/active`, `POST /api/sessions/recommendations` resolve correctly and are never shadowed by `{session_id}`.
   - Bot execution confinement: attempt to force orders for tickers outside `active_session.instruments`; verify strict rejection and zero executed trades outside basket.
   - Capital headroom: verify bot never allocates more than `allocated_capital` across positions.
2. Run your challenge suite with `py -m pytest tests/test_m2_challenger_validation.py -v`.
3. Deliver your verdict (**`APPROVE`** or **`REQUEST_CHANGES`**) with test results and findings in `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_challenger_2\handoff.md` and notify caller via `send_message`.
