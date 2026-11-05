"""SYNAPSE-TITAN Milestone 2 Empirical Challenge Test Suite.

Adversarial stress-testing suite for:
1. Rapid state transition sequences (CREATED -> RUNNING -> PAUSED -> RESUMED -> PAUSED -> RESUMED -> STOPPED)
2. Time dilation verification (1h session paused 30m expires exactly 90m after start)
3. Expiry policy execution (CLOSE_ALL flattens positions vs KEEP_OPEN preserves positions)
4. Single active session enforcement (strict RuntimeError and HTTP 409 Conflict when RUNNING or PAUSED)
5. Concurrent SQLite database updates under heavy multithreading and race conditions
"""

import concurrent.futures
from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading
from typing import Any, Dict, List
import uuid

import pytest
from starlette.testclient import TestClient

from server import app
from src.data.provider_base import BaseMarketDataProvider, LiveQuote
from src.execution.broker import (
    PAPER_TRADING_ONLY,
    PaperBroker,
    TradingLedgerDB,
)
from src.execution.live_bot import LiveBotController
from src.execution.session_manager import (
    DurationType,
    SessionEndPolicy,
    SessionManager,
    SessionMarket,
    SessionStatus,
    TradingHorizon,
    TradingSession,
)
from src.pipeline import MarketPredictionEngine


class MockChallengerQuoteProvider(BaseMarketDataProvider):
    """Deterministic mock provider providing valid quotes for stress testing."""

    def __init__(self, quotes=None):
        self._quotes = quotes or {}

    def get_quote(self, ticker: str, market_open: bool = True) -> LiveQuote:
        if ticker in self._quotes:
            return self._quotes[ticker]
        now_iso = datetime.now(timezone.utc).isoformat()
        return LiveQuote(
            ticker=ticker,
            last_price=150.0,
            bid_price=149.95,
            ask_price=150.05,
            volume=200000.0,
            timestamp_utc=now_iso,
            received_at_utc=now_iso,
            is_delayed=False,
            delay_minutes=0,
            is_stale=False,
            age_seconds=1.0,
            latency_ms=5.0,
            provider_name="MockChallengerQuoteProvider",
            day_open=148.0,
            day_high=152.0,
            day_low=147.5,
            prev_close=148.5,
            status="LIVE",
        )

    def get_health_status(self):
        return {
            "provider_name": "MockChallengerQuoteProvider",
            "is_connected": True,
            "is_realtime": True,
            "symbols_tracked": list(self._quotes.keys()),
        }


@pytest.fixture
def challenger_env(tmp_path: Path):
    """Provides a completely isolated DB, PaperBroker, SessionManager, and LiveBotController."""
    db_file = tmp_path / f"challenger_test_{uuid.uuid4().hex[:8]}.db"
    account_id = f"CHALLENGER_ACC_{uuid.uuid4().hex[:6]}"
    broker = PaperBroker(account_id=account_id, initial_capital=100000.0, db_path=db_file)
    manager = SessionManager(ledger=broker.ledger)
    engine = MarketPredictionEngine()
    provider = MockChallengerQuoteProvider()
    bot = LiveBotController(
        engine=engine,
        broker=broker,
        data_provider=provider,
        session_manager=manager,
        require_session=True,
    )
    bot.live_prices = {"AAPL": 150.0, "MSFT": 300.0, "GOOGL": 140.0, "NVDA": 500.0, "AMZN": 180.0}
    return {
        "db_file": db_file,
        "account_id": account_id,
        "broker": broker,
        "manager": manager,
        "bot": bot,
        "provider": provider,
    }


def _create_sample_session(
    manager: SessionManager,
    account_id: str,
    duration_type: str = "FIXED",
    duration_minutes: int = 60,
    policy: str = "CLOSE_ALL",
    market: str = "US_EQUITIES",
    currency: str = "USD",
    capital: float = 25000.0,
) -> TradingSession:
    """Helper to create a validated sample session."""
    payload = {
        "name": f"Stress Session {uuid.uuid4().hex[:6]}",
        "market": market,
        "currency": currency,
        "instruments": ["AAPL", "MSFT", "GOOGL"],
        "allocated_capital": capital,
        "horizon": "1d",
        "duration_type": duration_type,
        "duration_minutes": duration_minutes,
        "session_end_policy": policy,
        "account_id": account_id,
    }
    return manager.create_session(payload)


# =========================================================================
# Task 1.1: Rapid State Transition Sequences
# =========================================================================

class TestEmpiricalRapidStateTransitions:
    """Stress tests rapid sequences of valid and invalid state transitions."""

    def test_stress_rapid_state_transitions_full_lifecycle(self, challenger_env):
        """Stress test: CREATED -> RUNNING -> PAUSED -> RESUMED -> PAUSED -> RESUMED -> STOPPED."""
        mgr: SessionManager = challenger_env["manager"]
        bot: LiveBotController = challenger_env["bot"]
        acc_id: str = challenger_env["account_id"]

        session = _create_sample_session(mgr, acc_id, duration_minutes=60)
        assert session.status == SessionStatus.CREATED.value
        assert not session.is_active
        assert not session.is_running
        assert not session.is_paused
        assert not session.is_terminal

        # 1. CREATED -> RUNNING
        s_running1 = mgr.start_session(session.id, bot=bot)
        assert s_running1.status == SessionStatus.RUNNING.value
        assert s_running1.is_active
        assert s_running1.is_running
        assert not s_running1.is_paused
        assert s_running1.started_at is not None
        assert s_running1.expires_at is not None
        assert bot.is_running is True
        assert bot.active_session_id == session.id
        assert bot.broker.active_session_id == session.id

        # 2. RUNNING -> PAUSED (Pause #1)
        s_paused1 = mgr.pause_session(session.id, bot=bot)
        assert s_paused1.status == SessionStatus.PAUSED.value
        assert s_paused1.is_active
        assert not s_paused1.is_running
        assert s_paused1.is_paused
        assert s_paused1.paused_at is not None
        assert bot.is_running is False

        # 3. PAUSED -> RESUMED (Resume #1)
        s_resumed1 = mgr.resume_session(session.id, bot=bot)
        assert s_resumed1.status == SessionStatus.RUNNING.value
        assert s_resumed1.is_running
        assert not s_resumed1.is_paused
        assert s_resumed1.paused_at is None
        assert s_resumed1.resumed_at is not None
        assert bot.is_running is True

        # 4. RUNNING -> PAUSED (Pause #2)
        s_paused2 = mgr.pause_session(session.id, bot=bot)
        assert s_paused2.status == SessionStatus.PAUSED.value
        assert s_paused2.is_paused
        assert bot.is_running is False

        # 5. PAUSED -> RESUMED (Resume #2)
        s_resumed2 = mgr.resume_session(session.id, bot=bot)
        assert s_resumed2.status == SessionStatus.RUNNING.value
        assert s_resumed2.is_running
        assert bot.is_running is True

        # 6. RESUMED (RUNNING) -> STOPPED
        s_stopped = mgr.stop_session(session.id, bot=bot, reason="CHALLENGER_COMPLETION")
        assert s_stopped.status == SessionStatus.STOPPED.value
        assert not s_stopped.is_active
        assert not s_stopped.is_running
        assert not s_stopped.is_paused
        assert s_stopped.is_terminal
        assert s_stopped.ended_at is not None
        assert bot.is_running is False
        assert bot.active_session_id is None
        assert bot.broker.active_session_id is None

    def test_stress_rapid_oscillating_pause_resume_50_iterations(self, challenger_env):
        """Rapidly oscillate between PAUSED and RUNNING states 50 times in a tight loop."""
        mgr: SessionManager = challenger_env["manager"]
        bot: LiveBotController = challenger_env["bot"]
        acc_id: str = challenger_env["account_id"]

        session = _create_sample_session(mgr, acc_id, duration_minutes=120)
        mgr.start_session(session.id, bot=bot)

        initial_expires_at = datetime.fromisoformat(mgr.get_session(session.id).expires_at)

        for i in range(50):
            p = mgr.pause_session(session.id, bot=bot)
            assert p.status == SessionStatus.PAUSED.value
            assert p.paused_at is not None
            assert bot.is_running is False

            r = mgr.resume_session(session.id, bot=bot)
            assert r.status == SessionStatus.RUNNING.value
            assert r.paused_at is None
            assert r.resumed_at is not None
            assert bot.is_running is True

        final = mgr.get_session(session.id)
        assert final.status == SessionStatus.RUNNING.value
        assert final.accumulated_pause_seconds >= 0
        final_expires_at = datetime.fromisoformat(final.expires_at)
        assert final_expires_at >= initial_expires_at

    def test_stress_invalid_state_transition_matrix(self, challenger_env):
        """Stress-tests exhaustive matrix of prohibited state transitions."""
        mgr: SessionManager = challenger_env["manager"]
        acc_id: str = challenger_env["account_id"]

        # 1. CREATED state invalid transitions
        s1 = _create_sample_session(mgr, acc_id)
        with pytest.raises(ValueError, match="Cannot pause session in state 'CREATED'"):
            mgr.pause_session(s1.id)
        with pytest.raises(ValueError, match="Cannot resume session in state 'CREATED'"):
            mgr.resume_session(s1.id)

        # 2. RUNNING state invalid transitions
        s_run = mgr.start_session(s1.id)
        with pytest.raises(ValueError, match="Cannot start session in state 'RUNNING'"):
            mgr.start_session(s_run.id)
        with pytest.raises(ValueError, match="Cannot resume session in state 'RUNNING'"):
            mgr.resume_session(s_run.id)

        # 3. PAUSED state invalid transitions
        s_paused = mgr.pause_session(s_run.id)
        with pytest.raises(ValueError, match="Cannot start session in state 'PAUSED'"):
            mgr.start_session(s_paused.id)
        with pytest.raises(ValueError, match="Cannot pause session in state 'PAUSED'"):
            mgr.pause_session(s_paused.id)

        # 4. STOPPED state invalid transitions
        s_stopped = mgr.stop_session(s_paused.id)
        with pytest.raises(ValueError, match="Cannot start session in state 'STOPPED'"):
            mgr.start_session(s_stopped.id)
        with pytest.raises(ValueError, match="Cannot pause session in state 'STOPPED'"):
            mgr.pause_session(s_stopped.id)
        with pytest.raises(ValueError, match="Cannot resume session in state 'STOPPED'"):
            mgr.resume_session(s_stopped.id)
        # Idempotent stop on already STOPPED
        s_stopped_again = mgr.stop_session(s_stopped.id)
        assert s_stopped_again.status == SessionStatus.STOPPED.value

        # 5. COMPLETED state invalid transitions
        # Create and force to COMPLETED
        s_comp = _create_sample_session(mgr, acc_id)
        with mgr.ledger._get_connection() as conn:
            conn.execute("UPDATE trading_sessions SET status = 'COMPLETED' WHERE id = ?", (s_comp.id,))
            conn.commit()

        with pytest.raises(ValueError, match="Cannot start session in state 'COMPLETED'"):
            mgr.start_session(s_comp.id)
        with pytest.raises(ValueError, match="Cannot pause session in state 'COMPLETED'"):
            mgr.pause_session(s_comp.id)
        with pytest.raises(ValueError, match="Cannot resume session in state 'COMPLETED'"):
            mgr.resume_session(s_comp.id)
        # Idempotent stop on already COMPLETED
        s_comp_stopped = mgr.stop_session(s_comp.id)
        assert s_comp_stopped.status == SessionStatus.COMPLETED.value


# =========================================================================
# Task 1.2: Time Dilation Verification
# =========================================================================

class TestEmpiricalTimeDilation:
    """Stress tests time dilation: 1h duration paused for 30m expires exactly 90m after start."""

    def test_stress_time_dilation_exact_90min_offset(self, challenger_env):
        """Verify: 1 hour duration paused for 30 minutes expires exactly 90 minutes after start."""
        mgr: SessionManager = challenger_env["manager"]
        acc_id: str = challenger_env["account_id"]
        bot: LiveBotController = challenger_env["bot"]

        # Create session with 60 minutes duration
        session = _create_sample_session(mgr, acc_id, duration_type="FIXED", duration_minutes=60)
        s_running = mgr.start_session(session.id, bot=bot)

        # Baseline start time T0
        t0 = datetime.fromisoformat(s_running.started_at)
        initial_expires_at = datetime.fromisoformat(s_running.expires_at)
        assert initial_expires_at == t0 + timedelta(minutes=60)

        # Pause at T0 + 10 minutes
        t_pause = t0 + timedelta(minutes=10)
        mgr.pause_session(session.id, bot=bot)

        # Simulate staying paused for exactly 30 minutes (until T0 + 40m).
        # We simulate this precisely by setting `paused_at` in SQLite to `now - 30 minutes`
        now_utc = datetime.now(timezone.utc)
        simulated_paused_at = now_utc - timedelta(minutes=30)
        with mgr.ledger._get_connection() as conn:
            conn.execute(
                "UPDATE trading_sessions SET paused_at = ? WHERE id = ?",
                (simulated_paused_at.isoformat(), session.id),
            )
            conn.commit()

        # Resume session now
        s_resumed = mgr.resume_session(session.id, bot=bot)

        # Verification of pause duration & time dilation
        # Tolerating +/- 2 seconds for execution runtime
        assert abs(s_resumed.accumulated_pause_seconds - 1800) <= 2

        new_exp_dt = datetime.fromisoformat(s_resumed.expires_at)
        original_exp_dt = datetime.fromisoformat(initial_expires_at.isoformat())

        # Exact time dilation invariant: new expiry == original expiry + pause duration (30 min)
        expected_new_expiry = original_exp_dt + timedelta(minutes=30)
        diff_seconds = abs((new_exp_dt - expected_new_expiry).total_seconds())
        assert diff_seconds <= 2, f"Expected expiry offset ~1800s, got diff {diff_seconds}s"

        # Overall lifecycle duration from T0 to expiry must be exactly 90 minutes (5400s)
        total_duration_seconds = (new_exp_dt - t0).total_seconds()
        assert abs(total_duration_seconds - 5400) <= 2, (
            f"Expected session to expire exactly 90m (5400s) after start, got {total_duration_seconds}s"
        )

        # Check remaining seconds and expiry boundary logic
        # 1 second before new expiry: not expired
        t_just_before = new_exp_dt - timedelta(seconds=1)
        assert not s_resumed.is_expired(now_utc=t_just_before)
        rem = s_resumed.remaining_seconds(now_utc=t_just_before)
        assert rem == 1

        # At exact new expiry: expired
        assert s_resumed.is_expired(now_utc=new_exp_dt)
        rem_at_exp = s_resumed.remaining_seconds(now_utc=new_exp_dt)
        assert rem_at_exp == 0

        # Enforce expiry at exact 90m mark
        expired_sess = mgr.check_and_enforce_expiry(bot=bot, now_utc=new_exp_dt)
        assert expired_sess is not None
        assert expired_sess.status == SessionStatus.COMPLETED.value
        assert expired_sess.is_terminal

    def test_stress_time_dilation_multiple_pauses_cumulative(self, challenger_env):
        """Multi-pause cumulative dilation: three separate pauses summing to 60m on a 60m session."""
        mgr: SessionManager = challenger_env["manager"]
        acc_id: str = challenger_env["account_id"]
        bot: LiveBotController = challenger_env["bot"]

        session = _create_sample_session(mgr, acc_id, duration_minutes=60)
        mgr.start_session(session.id, bot=bot)
        initial_sess = mgr.get_session(session.id)
        t0 = datetime.fromisoformat(initial_sess.started_at)
        init_exp = datetime.fromisoformat(initial_sess.expires_at)

        pause_durations_minutes = [20, 15, 25]  # total = 60 minutes
        cumulative_pause_seconds = 0

        for pause_min in pause_durations_minutes:
            mgr.pause_session(session.id, bot=bot)

            # Check that remaining seconds is frozen during pause
            p_sess = mgr.get_session(session.id)
            rem_paused_1 = p_sess.remaining_seconds()
            rem_paused_2 = p_sess.remaining_seconds(now_utc=datetime.now(timezone.utc) + timedelta(hours=5))
            assert rem_paused_1 == rem_paused_2, "Remaining seconds must stay frozen while PAUSED"

            # Simulate pause duration
            now_utc = datetime.now(timezone.utc)
            sim_paused_at = now_utc - timedelta(minutes=pause_min)
            with mgr.ledger._get_connection() as conn:
                conn.execute(
                    "UPDATE trading_sessions SET paused_at = ? WHERE id = ?",
                    (sim_paused_at.isoformat(), session.id),
                )
                conn.commit()

            r_sess = mgr.resume_session(session.id, bot=bot)
            cumulative_pause_seconds += pause_min * 60
            assert abs(r_sess.accumulated_pause_seconds - cumulative_pause_seconds) <= 3

        # Final check: total pause is 60 minutes, session duration was 60 minutes.
        # Expiry must be 120 minutes (7200s) from start
        final_sess = mgr.get_session(session.id)
        final_exp = datetime.fromisoformat(final_sess.expires_at)
        total_time_from_t0 = (final_exp - t0).total_seconds()
        assert abs(total_time_from_t0 - 7200) <= 5


# =========================================================================
# Task 1.3: Expiry Policy Execution (CLOSE_ALL vs KEEP_OPEN)
# =========================================================================

class TestEmpiricalExpiryPolicy:
    """Stress tests expiry policy execution on session completion and manual stop."""

    def test_stress_expiry_policy_close_all(self, challenger_env):
        """Verify: Session with CLOSE_ALL flattens all open positions via broker on expiry."""
        mgr: SessionManager = challenger_env["manager"]
        acc_id: str = challenger_env["account_id"]
        bot: LiveBotController = challenger_env["bot"]
        broker: PaperBroker = challenger_env["broker"]

        session = _create_sample_session(mgr, acc_id, duration_minutes=30, policy="CLOSE_ALL")
        mgr.start_session(session.id, bot=bot)

        # Open 3 positions in PaperBroker
        broker.open_position("AAPL", "LONG", current_price=150.0, target_price=165.0, stop_price=145.0, allocation_weight_pct=10.0)
        broker.open_position("MSFT", "LONG", current_price=300.0, target_price=330.0, stop_price=290.0, allocation_weight_pct=10.0)
        broker.open_position("GOOGL", "SHORT", current_price=140.0, target_price=130.0, stop_price=145.0, allocation_weight_pct=10.0)

        open_positions = broker.get_open_positions()
        assert len(open_positions) == 3

        # Simulate expiry
        exp_time = datetime.fromisoformat(session.expires_at) if session.expires_at else datetime.now(timezone.utc)
        curr_session = mgr.get_session(session.id)
        t_expiry = datetime.fromisoformat(curr_session.expires_at) + timedelta(seconds=1)

        completed_sess = mgr.check_and_enforce_expiry(bot=bot, now_utc=t_expiry)
        assert completed_sess is not None
        assert completed_sess.status == SessionStatus.COMPLETED.value
        assert bot.is_running is False
        assert bot.active_session_id is None

        # Empirical verification: ALL open positions must be flattened
        remaining_positions = broker.get_open_positions()
        assert len(remaining_positions) == 0, f"Expected 0 open positions, found {len(remaining_positions)}"

        # Verify closed trades logged with exact exit reason
        closed_trades = broker.get_closed_trades()
        assert len(closed_trades) == 3
        for trade in closed_trades:
            assert trade.exit_reason == "SESSION_EXPIRED_CLOSE_ALL"
            assert trade.session_id == session.id

    def test_stress_expiry_policy_keep_open(self, challenger_env):
        """Verify: Session with KEEP_OPEN preserves all open positions intact on expiry."""
        mgr: SessionManager = challenger_env["manager"]
        acc_id: str = challenger_env["account_id"]
        bot: LiveBotController = challenger_env["bot"]
        broker: PaperBroker = challenger_env["broker"]

        session = _create_sample_session(mgr, acc_id, duration_minutes=30, policy="KEEP_OPEN")
        mgr.start_session(session.id, bot=bot)

        # Open 3 positions in PaperBroker
        broker.open_position("AAPL", "LONG", current_price=150.0, target_price=165.0, stop_price=145.0, allocation_weight_pct=10.0)
        broker.open_position("MSFT", "LONG", current_price=300.0, target_price=330.0, stop_price=290.0, allocation_weight_pct=10.0)
        broker.open_position("GOOGL", "SHORT", current_price=140.0, target_price=130.0, stop_price=145.0, allocation_weight_pct=10.0)

        assert len(broker.get_open_positions()) == 3

        # Simulate expiry
        curr_session = mgr.get_session(session.id)
        t_expiry = datetime.fromisoformat(curr_session.expires_at) + timedelta(seconds=1)

        completed_sess = mgr.check_and_enforce_expiry(bot=bot, now_utc=t_expiry)
        assert completed_sess is not None
        assert completed_sess.status == SessionStatus.COMPLETED.value
        assert bot.is_running is False
        assert bot.active_session_id is None

        # Empirical verification: Positions must REMAIN OPEN
        remaining_positions = broker.get_open_positions()
        assert len(remaining_positions) == 3, f"Expected 3 preserved positions, found {len(remaining_positions)}"

        # Verify no trades closed
        closed_trades = broker.get_closed_trades()
        assert len(closed_trades) == 0

    def test_stress_manual_stop_policy_close_all_vs_keep_open(self, challenger_env):
        """Verify: manual stop_session() respects CLOSE_ALL (flattens) vs KEEP_OPEN (preserves)."""
        mgr: SessionManager = challenger_env["manager"]
        acc_id: str = challenger_env["account_id"]
        bot: LiveBotController = challenger_env["bot"]
        broker: PaperBroker = challenger_env["broker"]

        # 1. Test CLOSE_ALL under manual stop
        sess_close = _create_sample_session(mgr, acc_id, policy="CLOSE_ALL")
        mgr.start_session(sess_close.id, bot=bot)
        broker.open_position("AAPL", "LONG", current_price=150.0, target_price=165.0, stop_price=145.0, allocation_weight_pct=10.0)
        assert len(broker.get_open_positions()) == 1

        mgr.stop_session(sess_close.id, bot=bot, reason="MANUAL_STOP")
        assert len(broker.get_open_positions()) == 0
        closed = broker.get_closed_trades()
        assert len(closed) == 1
        assert closed[0].exit_reason == "SESSION_STOPPED_MANUAL_STOP"

        # 2. Reset and test KEEP_OPEN under manual stop
        broker.reset_account(100000.0)
        sess_keep = _create_sample_session(mgr, acc_id, policy="KEEP_OPEN")
        mgr.start_session(sess_keep.id, bot=bot)
        broker.open_position("MSFT", "LONG", current_price=300.0, target_price=330.0, stop_price=290.0, allocation_weight_pct=10.0)
        assert len(broker.get_open_positions()) == 1

        mgr.stop_session(sess_keep.id, bot=bot, reason="MANUAL_STOP")
        # Position must remain open!
        assert len(broker.get_open_positions()) == 1
        assert len(broker.get_closed_trades()) == 0


# =========================================================================
# Task 1.4: Single Active Session Enforcement
# =========================================================================

class TestEmpiricalSingleActiveSessionEnforcement:
    """Stress tests strict single active session isolation and conflict rejections."""

    def test_stress_single_active_session_rejection_when_running(self, challenger_env):
        """Attempt to start Session B while Session A is RUNNING -> raises RuntimeError and HTTP 409."""
        mgr: SessionManager = challenger_env["manager"]
        acc_id: str = challenger_env["account_id"]
        bot: LiveBotController = challenger_env["bot"]

        sess_a = _create_sample_session(mgr, acc_id)
        sess_b = _create_sample_session(mgr, acc_id)

        mgr.start_session(sess_a.id, bot=bot)
        assert mgr.get_session(sess_a.id).status == SessionStatus.RUNNING.value

        # Python API: Attempt to start Session B must raise RuntimeError
        with pytest.raises(RuntimeError, match="Account already has active session"):
            mgr.start_session(sess_b.id, bot=bot)

        # REST API Verification: POST /api/sessions/{id}/start must return HTTP 409 Conflict
        client = TestClient(app)
        # Create session via REST API
        r_create = client.post("/api/sessions", json={
            "market": "US_EQUITIES",
            "instruments": ["NVDA"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 60,
            "allocated_capital": 10000.0,
            "currency": "USD",
        })
        assert r_create.status_code == 201
        rest_sess_id = r_create.json()["session"]["id"]

        # Ensure an active session is running in server's manager
        r_active = client.get("/api/sessions/active")
        active_id = r_active.json().get("session", {}).get("id") if r_active.json().get("session") else None

        if active_id:
            # Another session is active, so starting rest_sess_id must return 409
            r_start_conflict = client.post(f"/api/sessions/{rest_sess_id}/start")
            assert r_start_conflict.status_code == 409
        else:
            # Start rest_sess_id first, then create a second one and verify 409
            r_start_1 = client.post(f"/api/sessions/{rest_sess_id}/start")
            assert r_start_1.status_code == 200

            r_create_2 = client.post("/api/sessions", json={
                "market": "US_EQUITIES",
                "instruments": ["AAPL"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": 10000.0,
                "currency": "USD",
            })
            sess_2_id = r_create_2.json()["session"]["id"]
            r_start_2 = client.post(f"/api/sessions/{sess_2_id}/start")
            assert r_start_2.status_code == 409
            assert "already" in r_start_2.json()["detail"].lower() or "running" in r_start_2.json()["detail"].lower()

            # Clean up
            client.post(f"/api/sessions/{rest_sess_id}/stop")

    def test_stress_single_active_session_rejection_when_paused(self, challenger_env):
        """Attempt to start Session B while Session A is PAUSED -> raises RuntimeError and HTTP 409."""
        mgr: SessionManager = challenger_env["manager"]
        acc_id: str = challenger_env["account_id"]
        bot: LiveBotController = challenger_env["bot"]

        sess_a = _create_sample_session(mgr, acc_id)
        sess_b = _create_sample_session(mgr, acc_id)

        mgr.start_session(sess_a.id, bot=bot)
        mgr.pause_session(sess_a.id, bot=bot)
        assert mgr.get_session(sess_a.id).status == SessionStatus.PAUSED.value

        # Attempt to start Session B while Session A is PAUSED
        with pytest.raises(RuntimeError, match="Account already has active session"):
            mgr.start_session(sess_b.id, bot=bot)

    def test_stress_single_active_session_allowed_after_terminal_states(self, challenger_env):
        """Active session lock is cleanly released once previous session is STOPPED or COMPLETED."""
        mgr: SessionManager = challenger_env["manager"]
        acc_id: str = challenger_env["account_id"]
        bot: LiveBotController = challenger_env["bot"]

        # Session 1: Started then STOPPED
        s1 = _create_sample_session(mgr, acc_id)
        mgr.start_session(s1.id, bot=bot)
        mgr.stop_session(s1.id, bot=bot)

        # Session 2: Can now be started successfully
        s2 = _create_sample_session(mgr, acc_id)
        s2_run = mgr.start_session(s2.id, bot=bot)
        assert s2_run.status == SessionStatus.RUNNING.value

        # Session 2: Force completion via expiry
        t_exp = datetime.fromisoformat(s2_run.expires_at) + timedelta(seconds=1)
        s2_comp = mgr.check_and_enforce_expiry(bot=bot, now_utc=t_exp)
        assert s2_comp.status == SessionStatus.COMPLETED.value

        # Session 3: Can now be started successfully
        s3 = _create_sample_session(mgr, acc_id)
        s3_run = mgr.start_session(s3.id, bot=bot)
        assert s3_run.status == SessionStatus.RUNNING.value


# =========================================================================
# Task 1.5: Concurrent SQLite Database Updates Under Multithreading
# =========================================================================

class TestEmpiricalConcurrentDatabaseUpdates:
    """Stress tests SQLite concurrency, database locks, and race conditions."""

    def test_stress_concurrent_sqlite_updates_multithreading(self, challenger_env):
        """Spawn 10 concurrent threads executing 20 operations each simultaneously (200 ops)."""
        mgr: SessionManager = challenger_env["manager"]
        acc_id: str = challenger_env["account_id"]
        bot: LiveBotController = challenger_env["bot"]

        # Session 1 is RUNNING (receiving metrics and state queries)
        session_running = _create_sample_session(mgr, acc_id, duration_minutes=180)
        mgr.start_session(session_running.id, bot=bot)

        # Session 2 is PAUSED on an isolated account (testing parameter updates)
        acc_id_2 = f"{acc_id}_PAUSED"
        session_paused = _create_sample_session(mgr, acc_id_2, duration_minutes=180)
        mgr.start_session(session_paused.id)
        mgr.pause_session(session_paused.id)

        errors = []
        num_threads = 10
        ops_per_thread = 20
        barrier = threading.Barrier(num_threads)

        def worker(thread_idx: int):
            try:
                barrier.wait(timeout=5)
                for i in range(ops_per_thread):
                    if thread_idx % 3 == 0:
                        # Metrics write to running session
                        metrics = {
                            "iteration": i,
                            "thread_idx": thread_idx,
                            "cash": 25000.0 + (i * 10),
                            "pnl": float(i * 5),
                        }
                        mgr.update_session_metrics(session_running.id, metrics)
                    elif thread_idx % 3 == 1:
                        # Session reads and list operations
                        s = mgr.get_session(session_running.id)
                        assert s is not None
                        active = mgr.get_active_session(acc_id)
                        assert active is not None
                        all_sess = mgr.list_sessions(account_id=acc_id)
                        assert len(all_sess) >= 1
                    else:
                        # Parameter updates on paused session (allowed)
                        mgr.update_session(session_paused.id, {"name": f"Stress-T{thread_idx}-I{i}"})
            except Exception as e:
                errors.append((thread_idx, str(e)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        # Empirical assertion: ZERO database locks or concurrency errors
        assert len(errors) == 0, f"Encountered {len(errors)} thread errors: {errors}"

        # Final sanity check: DB is healthy and session readable
        final_sess = mgr.get_session(session_running.id)
        assert final_sess is not None
        assert final_sess.status == SessionStatus.RUNNING.value

    def test_stress_concurrent_race_condition_to_start_two_sessions(self, challenger_env):
        """Simultaneous race condition: Two threads attempt start_session at the exact same instant."""
        mgr: SessionManager = challenger_env["manager"]
        acc_id: str = challenger_env["account_id"]

        sess_1 = _create_sample_session(mgr, acc_id)
        sess_2 = _create_sample_session(mgr, acc_id)

        barrier = threading.Barrier(2)
        results = {}

        def racer(sess_id: str, racer_name: str):
            barrier.wait(timeout=5)
            try:
                res = mgr.start_session(sess_id)
                results[racer_name] = ("SUCCESS", res.id)
            except Exception as e:
                results[racer_name] = ("ERROR", str(e))

        t1 = threading.Thread(target=racer, args=(sess_1.id, "racer_1"))
        t2 = threading.Thread(target=racer, args=(sess_2.id, "racer_2"))

        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # Exactly ONE must succeed, and the other must be rejected
        statuses = [v[0] for v in results.values()]
        assert "SUCCESS" in statuses, f"At least one session should start: {results}"
        # If both raced, one should fail or if serialized, the second raises RuntimeError
        # If one succeeded and the other failed:
        if statuses.count("SUCCESS") == 1:
            error_msg = [v[1] for v in results.values() if v[0] == "ERROR"][0]
            assert "already has active session" in error_msg.lower() or "active session" in error_msg.lower()

        # Database invariant: At no point can two sessions be active for the same account
        active = mgr.get_active_session(acc_id)
        assert active is not None

        with mgr.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM trading_sessions WHERE account_id = ? AND status IN ('RUNNING', 'PAUSED')",
                (acc_id,),
            )
            count = cursor.fetchone()["cnt"]
            assert count == 1, f"Expected exactly 1 active session in DB, found {count}"


# =========================================================================
# Additional Edge Case Stress Tests
# =========================================================================

class TestEmpiricalEdgeCases:
    """Additional edge cases: MANUAL_STOP duration and performance accounting."""

    def test_stress_manual_stop_session_never_auto_expires(self, challenger_env):
        """MANUAL_STOP duration type has expires_at=None and never automatically expires."""
        mgr: SessionManager = challenger_env["manager"]
        acc_id: str = challenger_env["account_id"]
        bot: LiveBotController = challenger_env["bot"]

        session = _create_sample_session(mgr, acc_id, duration_type="MANUAL_STOP", duration_minutes=None)
        assert session.duration_type == DurationType.MANUAL_STOP.value
        assert session.expires_at is None

        s_run = mgr.start_session(session.id, bot=bot)
        assert s_run.expires_at is None
        assert s_run.remaining_seconds() is None
        assert not s_run.is_expired()

        # Simulate 1 year (365 days) elapsed in the future
        far_future = datetime.now(timezone.utc) + timedelta(days=365)
        assert not s_run.is_expired(now_utc=far_future)

        # Expiry check must return None and keep session RUNNING
        res = mgr.check_and_enforce_expiry(bot=bot, now_utc=far_future)
        assert res is None
        assert mgr.get_session(session.id).status == SessionStatus.RUNNING.value

    def test_stress_compute_performance_accounting_accuracy(self, challenger_env):
        """Verify session performance calculation accounting accuracy with mixed trades and positions."""
        mgr: SessionManager = challenger_env["manager"]
        acc_id: str = challenger_env["account_id"]
        broker: PaperBroker = challenger_env["broker"]

        session = _create_sample_session(mgr, acc_id, capital=50000.0)
        mgr.start_session(session.id)

        # Trade 1: AAPL win (+500 net)
        pos1 = broker.open_position("AAPL", "LONG", current_price=100.0, target_price=110.0, stop_price=95.0, custom_allocated_capital=10000.0)
        broker.close_position(pos1.id, exit_price=105.0, exit_reason="TARGET")

        # Trade 2: MSFT loss (-200 net)
        pos2 = broker.open_position("MSFT", "LONG", current_price=200.0, target_price=220.0, stop_price=190.0, custom_allocated_capital=10000.0)
        broker.close_position(pos2.id, exit_price=196.0, exit_reason="STOP")

        # Position 3: Open position GOOGL
        broker.open_position("GOOGL", "LONG", current_price=100.0, target_price=120.0, stop_price=90.0, custom_allocated_capital=5000.0)

        perf = mgr.compute_session_performance(session.id)

        assert perf["session_id"] == session.id
        assert perf["total_trades"] == 2
        assert perf["winning_trades"] == 1
        assert perf["losing_trades"] == 1
        assert perf["win_rate_pct"] == 50.0
        assert perf["open_positions_count"] == 1
        assert perf["starting_capital"] == 50000.0
        assert perf["allocated_capital"] == 50000.0
        assert perf["realized_pnl"] != 0.0

    def test_stress_session_isolation_and_no_telemetry_leakage(self, challenger_env):
        """A new session with 0 trades must NOT inherit trades or PnL from an earlier session on the same account."""
        mgr: SessionManager = challenger_env["manager"]
        acc_id: str = challenger_env["account_id"]
        broker: PaperBroker = challenger_env["broker"]

        # Session 1: runs, completes 1 trade with +$50 profit, then stops
        s1 = _create_sample_session(mgr, acc_id, capital=20000.0)
        mgr.start_session(s1.id)
        broker.active_session_id = s1.id
        pos = broker.open_position("AAPL", "LONG", current_price=100.0, target_price=110.0, stop_price=95.0, custom_allocated_capital=2000.0)
        broker.close_position(pos.id, exit_price=105.0, exit_reason="TAKE_PROFIT")
        mgr.stop_session(s1.id)

        # Session 2: newly created on the same account, currently has 0 trades
        s2 = _create_sample_session(mgr, acc_id, capital=25000.0)
        mgr.start_session(s2.id)

        perf_s2 = mgr.compute_session_performance(s2.id)

        # STRICT ISOLATION ASSERTIONS:
        # Session 2 must report 0 trades and $0.00 realized PnL
        assert perf_s2["total_trades"] == 0, (
            f"VULNERABILITY: Session {s2.id} leaked {perf_s2['total_trades']} trades from prior session {s1.id}!"
        )
        assert perf_s2["realized_pnl"] == 0.0, (
            f"VULNERABILITY: Session {s2.id} leaked realized PnL ${perf_s2['realized_pnl']} from prior session {s1.id}!"
        )

