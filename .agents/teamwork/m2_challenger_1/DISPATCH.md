## 2026-11-05T07:05:47Z
You are Milestone 2 Empirical Challenger 1 for the SYNAPSE-TITAN platform.

Your task is to empirically stress-test the session lifecycle state machine, pause/resume time dilation, expiry enforcement, and concurrent session isolation in `src/execution/session_manager.py` and `src/execution/broker.py`.

## Mandatory Reading & Working Directory
- Authoritative requirements: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\ORIGINAL_REQUEST.md` (read first).
- Project scope & layout: `C:\Users\Shivam\Desktop\trade_bot\PROJECT.md`.
- Implementer's handoff: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_worker_1\handoff.md`.
- Your working directory: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_challenger_1`.

## Empirical Challenge Tasks
1. Write a dedicated empirical challenge test file: `tests/test_m2_challenger_lifecycle.py` containing at least 10 stress tests:
   - Rapid state transition sequences (CREATED -> RUNNING -> PAUSED -> RESUMED -> PAUSED -> RESUMED -> STOPPED).
   - Time dilation verification: verify that a session with 1 hour duration paused for 30 minutes expires exactly 90 minutes after start.
   - Expiry policy execution: test `CLOSE_ALL` (all open positions flattened via broker) vs `KEEP_OPEN` (positions preserved).
   - Single active session enforcement: attempt to start a second session while one is RUNNING or PAUSED; verify strict 409/RuntimeError rejection.
   - Concurrent SQLite database updates under multithreading/rapid loop.
2. Run your challenge suite with `py -m pytest tests/test_m2_challenger_lifecycle.py -v`.
3. Deliver your verdict (**`APPROVE`** or **`REQUEST_CHANGES`**) with test results and findings in `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_challenger_1\handoff.md` and notify caller via `send_message`.
