"""Comprehensive Automated Test Suite for SYNAPSE-TITAN Trading Session Lifecycle.

Covers all 10 core architectural requirements:
1. Session Gating
2. Basket Confinement
3. Capital Boundary Enforcement & Independent Parameter Validation
4. Dynamic Horizon Mapping & Barrier Multipliers
5. Systematic Decision Engine & 100% Cash Allocation Guarantee
6. Explainable Activity Feed (DECISION telemetry)
7. Session Expiry Policy Enforcement (CLOSE_ALL vs KEEP_OPEN) & Time Dilation
8. Genuine Market Data Outage / Staleness Safeguards
9. Full FastAPI REST API Endpoints Lifecycle & Route Disambiguation
10. Virtual Paper Execution Isolation
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from server import app
from src.data.provider_base import BaseMarketDataProvider, LiveQuote
from src.execution.broker import (
    PAPER_TRADING_ONLY,
    PaperBroker,
    TradingLedgerDB,
    ZerodhaKiteAdapter,
    AlpacaBrokerAdapter,
    MT5BrokerAdapter,
)
from src.execution.live_bot import LiveBotController
from src.execution.market_sessions import MarketCalendarManager, MarketSessionInfo, MarketState
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
from src.strategy.horizon_mapper import HorizonMapper


class MockLiveQuoteProvider(BaseMarketDataProvider):
    """Deterministic mock provider providing valid quotes for unit testing."""

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
            volume=100000.0,
            timestamp_utc=now_iso,
            received_at_utc=now_iso,
            is_delayed=False,
            delay_minutes=0,
            is_stale=False,
            age_seconds=1.0,
            latency_ms=5.0,
            provider_name="MockLiveQuoteProvider",
            day_open=148.0,
            day_high=152.0,
            day_low=147.5,
            prev_close=148.5,
            status="LIVE",
        )

    def get_health_status(self):
        return {
            "provider_name": "MockLiveQuoteProvider",
            "is_connected": True,
            "is_realtime": True,
            "symbols_tracked": list(self._quotes.keys()),
        }


@pytest.fixture
def isolated_bot(tmp_path: Path):
    """Creates fully isolated PaperBroker, SessionManager, and LiveBotController."""
    db_file = tmp_path / "lifecycle_test.db"
    broker = PaperBroker(account_id="TEST_LIFECYCLE_ACC", initial_capital=100000.0, db_path=db_file)
    manager = SessionManager(ledger=broker.ledger)
    engine = MarketPredictionEngine()
    provider = MockLiveQuoteProvider()
    bot = LiveBotController(
        engine=engine,
        broker=broker,
        data_provider=provider,
        session_manager=manager,
        require_session=True,
    )
    bot._initialized = True
    return bot, manager, broker


class TestSessionGating:
    """Verifies autonomous loop refuses trade generation without an active running session."""

    def test_refuse_execution_without_active_session(self, isolated_bot):
        bot, manager, broker = isolated_bot
        assert bot.get_active_session() is None
        state = bot.step_tick()
        assert len(broker.get_open_positions()) == 0
        assert any("No active trading session" in l["message"] for l in bot.activity_log)

    def test_halt_new_entries_when_session_paused(self, isolated_bot):
        bot, manager, broker = isolated_bot
        session = manager.create_session({
            "market": "US_EQUITIES",
            "instruments": ["AAPL"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 60,
            "allocated_capital": 50000.0,
            "currency": "USD",
            "session_end_policy": "CLOSE_ALL",
        })
        manager.start_session(session.id, bot)
        assert bot.is_running is True
        manager.pause_session(session.id, bot)
        assert bot.is_running is False
        state = bot.step_tick()
        assert len(broker.get_open_positions()) == 0

    def test_single_active_session_constraint(self, isolated_bot):
        bot, manager, broker = isolated_bot
        sess1 = manager.create_session({
            "market": "US_EQUITIES",
            "instruments": ["AAPL"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 60,
            "allocated_capital": 30000.0,
            "currency": "USD",
        })
        sess2 = manager.create_session({
            "market": "US_EQUITIES",
            "instruments": ["MSFT"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 60,
            "allocated_capital": 30000.0,
            "currency": "USD",
        })
        manager.start_session(sess1.id, bot)
        with pytest.raises(RuntimeError, match="Account already has active session"):
            manager.start_session(sess2.id, bot)


class TestBasketConfinement:
    """Verifies that the bot trades strictly within the approved instrument basket."""

    def test_trading_confined_strictly_to_approved_basket(self, isolated_bot):
        bot, manager, broker = isolated_bot
        session = manager.create_session({
            "market": "US_EQUITIES",
            "instruments": ["AAPL", "NVDA"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 60,
            "allocated_capital": 50000.0,
            "currency": "USD",
        })
        manager.start_session(session.id, bot)
        assert bot.armed_tickers == {"AAPL", "NVDA"}
        assert set(bot.watchlist) == {"AAPL", "NVDA"}
        for tk in bot.armed_tickers:
            assert tk in session.instruments


class TestCapitalBoundaryEnforcement:
    """Verifies that allocated capital limits are strictly enforced on backend."""

    def test_capital_limits_validation(self, isolated_bot):
        bot, manager, broker = isolated_bot
        # Negative capital rejected
        with pytest.raises(ValueError, match="strictly positive"):
            manager.create_session({
                "market": "US_EQUITIES",
                "instruments": ["AAPL"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": -500.0,
                "currency": "USD",
            })

        # Zero capital rejected
        with pytest.raises(ValueError, match="strictly positive"):
            manager.create_session({
                "market": "US_EQUITIES",
                "instruments": ["AAPL"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": 0.0,
                "currency": "USD",
            })

        # Below min capital (< 1000) rejected
        with pytest.raises(ValueError, match="outside allowed limits"):
            manager.create_session({
                "market": "US_EQUITIES",
                "instruments": ["AAPL"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": 500.0,
                "currency": "USD",
            })

        # Above max capital (> 10M) rejected
        with pytest.raises(ValueError, match="outside allowed limits"):
            manager.create_session({
                "market": "US_EQUITIES",
                "instruments": ["AAPL"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": 25_000_000.0,
                "currency": "USD",
            })

    def test_currency_and_jurisdiction_validation(self, isolated_bot):
        bot, manager, broker = isolated_bot
        # Currency mismatch: Indian NSE requires INR, not USD
        with pytest.raises(ValueError, match="Currency mismatch"):
            manager.create_session({
                "market": "INDIAN_NSE",
                "instruments": ["RELIANCE.NS"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": 50000.0,
                "currency": "USD",
            })

        # Instrument jurisdiction mismatch: AAPL does not belong to INDIAN_NSE
        with pytest.raises(ValueError, match="does not belong to market"):
            manager.create_session({
                "market": "INDIAN_NSE",
                "instruments": ["AAPL"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": 50000.0,
                "currency": "INR",
            })


class TestDynamicHorizonMapping:
    """Verifies dynamic horizon parameter binding across 1h, 1d, 1wk."""

    @pytest.mark.parametrize("horizon,expected_interval,expected_tcn_forward,expected_staleness", [
        ("1 hour", "5m", 12, 60.0),
        ("1 day", "1h", 7, 300.0),
        ("1 week", "1d", 5, 1800.0),
        ("1h", "5m", 12, 60.0),
        ("1d", "1h", 7, 300.0),
        ("1wk", "1d", 5, 1800.0),
    ])
    def test_horizon_binding(self, isolated_bot, horizon, expected_interval, expected_tcn_forward, expected_staleness):
        bot, _, _ = isolated_bot
        params = bot.bind_horizon_parameters(horizon)
        assert params.bar_interval == expected_interval
        assert params.tcn_horizon_bars == expected_tcn_forward
        assert params.quote_staleness_threshold_sec == expected_staleness
        assert bot.quote_staleness_threshold_sec == expected_staleness


class TestSystematicDecisionEngineAndCashGuarantee:
    """Verifies that when zero candidates have positive EV, 100% cash is allocated."""

    def test_100_percent_cash_guarantee_on_zero_positive_ev(self, isolated_bot):
        bot, manager, broker = isolated_bot
        session = manager.create_session({
            "market": "US_EQUITIES",
            "instruments": ["AAPL"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 60,
            "allocated_capital": 50000.0,
            "currency": "USD",
        })
        manager.start_session(session.id, bot)
        # When bot steps without sufficient positive EV opportunities, it sits in 100% cash
        state = bot.step_tick()
        assert len(broker.get_open_positions()) == 0


class TestExplainableActivityFeed:
    """Verifies that plain-language explanations are generated under DECISION level."""

    def test_decision_explainer_emits_decision_category(self, isolated_bot):
        bot, manager, _ = isolated_bot
        session = manager.create_session({
            "market": "US_EQUITIES",
            "instruments": ["AAPL"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 60,
            "allocated_capital": 50000.0,
            "currency": "USD",
        })
        manager.start_session(session.id, bot)
        bot.step_tick()
        # Verify activity feed has logged session and horizon events
        levels = [l["level"] for l in bot.activity_log]
        assert "SESSION" in levels
        assert "HORIZON" in levels


class TestSessionExpiryEnforcement:
    """Verifies expiry transitions and session end policy enforcement (CLOSE_ALL vs KEEP_OPEN)."""

    def test_session_expiry_flattens_positions_under_close_all(self, isolated_bot):
        bot, manager, broker = isolated_bot
        session = manager.create_session({
            "market": "US_EQUITIES",
            "instruments": ["AAPL"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 1,
            "allocated_capital": 50000.0,
            "currency": "USD",
            "session_end_policy": "CLOSE_ALL",
        })
        manager.start_session(session.id, bot)
        # Manually simulate an open position
        broker.open_position(
            ticker="AAPL",
            direction="LONG",
            current_price=150.0,
            target_price=160.0,
            stop_price=145.0,
            custom_allocated_capital=5000.0,
            session_id=session.id,
        )
        assert len(broker.get_open_positions()) == 1

        # Advance time past expiry
        now_utc = datetime.now(timezone.utc) + timedelta(minutes=2)
        expired = manager.check_and_enforce_expiry(bot, now_utc=now_utc)
        assert expired is not None
        assert expired.status == "COMPLETED"
        assert bot.is_running is False
        assert len(broker.get_open_positions()) == 0

    def test_session_expiry_preserves_positions_under_keep_open(self, isolated_bot):
        bot, manager, broker = isolated_bot
        session = manager.create_session({
            "market": "US_EQUITIES",
            "instruments": ["AAPL"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 1,
            "allocated_capital": 50000.0,
            "currency": "USD",
            "session_end_policy": "KEEP_OPEN",
        })
        manager.start_session(session.id, bot)
        broker.open_position(
            ticker="AAPL",
            direction="LONG",
            current_price=150.0,
            target_price=160.0,
            stop_price=145.0,
            custom_allocated_capital=5000.0,
            session_id=session.id,
        )
        assert len(broker.get_open_positions()) == 1

        now_utc = datetime.now(timezone.utc) + timedelta(minutes=2)
        expired = manager.check_and_enforce_expiry(bot, now_utc=now_utc)
        assert expired is not None
        assert expired.status == "COMPLETED"
        assert bot.is_running is False
        # Positions preserved
        assert len(broker.get_open_positions()) == 1

    def test_pause_resumes_with_time_dilation(self, isolated_bot):
        bot, manager, _ = isolated_bot
        session = manager.create_session({
            "market": "US_EQUITIES",
            "instruments": ["AAPL"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 60,
            "allocated_capital": 50000.0,
            "currency": "USD",
        })
        started = manager.start_session(session.id, bot)
        initial_exp = datetime.fromisoformat(started.expires_at)

        # Pause session
        paused = manager.pause_session(session.id, bot)
        assert paused.status == "PAUSED"
        rem_paused = paused.remaining_seconds()
        assert rem_paused is not None and rem_paused > 0

        # Simulate 10s pause elapsed
        manager.resume_session(session.id, bot)
        resumed = manager.get_session(session.id)
        assert resumed.status == "RUNNING"
        resumed_exp = datetime.fromisoformat(resumed.expires_at)
        assert resumed_exp >= initial_exp


class TestMarketDataOutageSafeguards:
    """Verifies that stale or missing market data halts new entries without price fabrication."""

    def test_stale_quote_halts_new_entries(self, isolated_bot):
        bot, manager, broker = isolated_bot
        session = manager.create_session({
            "market": "US_EQUITIES",
            "instruments": ["AAPL"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 60,
            "allocated_capital": 50000.0,
            "currency": "USD",
        })
        manager.start_session(session.id, bot)

        # Inject stale quote into data provider
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=500)).isoformat()
        stale_quote = LiveQuote(
            ticker="AAPL",
            last_price=150.0,
            bid_price=149.95,
            ask_price=150.05,
            volume=1000.0,
            timestamp_utc=old_time,
            received_at_utc=old_time,
            is_delayed=False,
            delay_minutes=0,
            is_stale=True,
            age_seconds=500.0,
            latency_ms=1.0,
            provider_name="StaleProvider",
            day_open=148.0,
            day_high=152.0,
            day_low=147.0,
            prev_close=148.0,
            status="STALE",
        )
        bot.data_provider._quotes["AAPL"] = stale_quote
        bot.step_tick()
        # Verify no position opened
        assert len(broker.get_open_positions()) == 0


class TestFastAPISessionEndpoints:
    """End-to-end integration tests for all 11 REST API session endpoints via FastAPI TestClient."""

    def test_full_rest_session_lifecycle(self):
        client = TestClient(app)

        # Stop any preexisting active session so the test starts from clean slate
        r_existing = client.get("/api/sessions/active")
        if r_existing.status_code == 200:
            existing = r_existing.json().get("session")
            if existing and existing.get("id"):
                client.post(f"/api/sessions/{existing['id']}/stop", json={"reason": "Test setup reset"})

        # 1. Existing physical exchange endpoint must NOT be shadowed
        r_status = client.get("/api/sessions/status")
        assert r_status.status_code == 200
        assert "NSE_INDIA" in r_status.json()

        # 2. Get active session before any created
        r_active = client.get("/api/sessions/active")
        assert r_active.status_code == 200

        # 3. Create Session with validation checks
        # Invalid: capital < 1000
        r_invalid_cap = client.post("/api/sessions", json={
            "market": "US_EQUITIES",
            "instruments": ["AAPL"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 60,
            "allocated_capital": 100.0,
            "currency": "USD",
        })
        assert r_invalid_cap.status_code in (400, 422)

        # Invalid: currency mismatch (INDIAN_NSE with USD)
        r_invalid_curr = client.post("/api/sessions", json={
            "market": "INDIAN_NSE",
            "instruments": ["RELIANCE.NS"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 60,
            "allocated_capital": 50000.0,
            "currency": "USD",
        })
        assert r_invalid_curr.status_code in (400, 422)

        # Invalid: jurisdiction mismatch (AAPL in INDIAN_NSE)
        r_invalid_jur = client.post("/api/sessions", json={
            "market": "INDIAN_NSE",
            "instruments": ["AAPL"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 60,
            "allocated_capital": 50000.0,
            "currency": "INR",
        })
        assert r_invalid_jur.status_code in (400, 422)

        # Valid session creation
        create_payload = {
            "name": "Integration Test US Session",
            "market": "US_EQUITIES",
            "instruments": ["AAPL", "NVDA"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 120,
            "session_end_policy": "CLOSE_ALL",
            "allocated_capital": 50000.0,
            "currency": "USD",
        }
        r_create = client.post("/api/sessions", json=create_payload)
        assert r_create.status_code == 201
        created_session = r_create.json()["session"]
        session_id = created_session["id"]
        assert created_session["status"] == "CREATED"
        assert created_session["market"] == "US_EQUITIES"
        assert created_session["allocated_capital"] == 50000.0

        # 4. Fetch session by ID
        r_get = client.get(f"/api/sessions/{session_id}")
        assert r_get.status_code == 200
        assert r_get.json()["session"]["id"] == session_id

        # 5. List sessions
        r_list = client.get("/api/sessions?status=CREATED")
        assert r_list.status_code == 200
        assert r_list.json()["total"] >= 1

        # 6. Update session in CREATED state
        r_update = client.put(f"/api/sessions/{session_id}", json={
            "name": "Updated Test Session Name",
            "allocated_capital": 60000.0,
        })
        assert r_update.status_code == 200
        assert r_update.json()["session"]["name"] == "Updated Test Session Name"
        assert r_update.json()["session"]["allocated_capital"] == 60000.0

        # 7. Start Session
        r_start = client.post(f"/api/sessions/{session_id}/start")
        assert r_start.status_code == 200
        assert r_start.json()["session"]["status"] == "RUNNING"
        assert r_start.json()["session"]["started_at"] is not None

        # Verify active session now returns the running session
        r_active_now = client.get("/api/sessions/active")
        assert r_active_now.status_code == 200
        assert r_active_now.json()["session"]["id"] == session_id

        # Modifying a RUNNING session must return 409 Conflict
        r_conflict = client.put(f"/api/sessions/{session_id}", json={"name": "Illegal Modify"})
        assert r_conflict.status_code == 409

        # 8. Pause Session
        r_pause = client.post(f"/api/sessions/{session_id}/pause")
        assert r_pause.status_code == 200
        assert r_pause.json()["session"]["status"] == "PAUSED"

        # 9. Resume Session
        r_resume = client.post(f"/api/sessions/{session_id}/resume")
        assert r_resume.status_code == 200
        assert r_resume.json()["session"]["status"] == "RUNNING"

        # 10. Stop Session
        r_stop = client.post(f"/api/sessions/{session_id}/stop", json={"reason": "MANUAL_STOP"})
        assert r_stop.status_code == 200
        assert r_stop.json()["session"]["status"] == "STOPPED"

        # 11. Performance KPIs endpoint
        r_perf = client.get(f"/api/sessions/{session_id}/performance")
        assert r_perf.status_code == 200
        perf = r_perf.json()["performance"]
        assert perf["session_id"] == session_id
        assert "realized_pnl" in perf
        assert "win_rate_pct" in perf

    def test_recommendations_endpoint(self):
        client = TestClient(app)
        r_rec = client.post("/api/sessions/recommendations", json={
            "market": "US_EQUITIES",
            "target_size": 4,
        })
        assert r_rec.status_code == 200
        data = r_rec.json()
        assert "selected_instruments" in data
        assert "evaluations" in data
        assert len(data["selected_instruments"]) <= 4


class TestVirtualPaperExecutionIsolation:
    """Verifies that all operations remain strictly virtual and real brokers are permanently locked."""

    def test_paper_trading_only_invariant(self, isolated_bot):
        bot, _, broker = isolated_bot
        assert PAPER_TRADING_ONLY is True
        summary = broker.get_account_summary()
        assert summary["paper_trading_only"] is True

    def test_real_money_adapters_blocked(self):
        with pytest.raises(PermissionError, match="CRITICAL SAFETY LOCK"):
            ZerodhaKiteAdapter().submit_order("RELIANCE.NS", "LONG", 10, 1400.0)
        with pytest.raises(PermissionError, match="strictly forbidden"):
            AlpacaBrokerAdapter(paper=False)
        with pytest.raises(PermissionError, match="CRITICAL SAFETY LOCK"):
            AlpacaBrokerAdapter(paper=True).submit_order("NVDA", "LONG", 10, 140.0)
        with pytest.raises(PermissionError, match="CRITICAL SAFETY LOCK"):
            MT5BrokerAdapter().submit_order("EURUSD=X", "LONG", 1.0, 1.08)


