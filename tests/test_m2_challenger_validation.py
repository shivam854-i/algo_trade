"""Milestone 2 Empirical Challenger 2 Stress Test Suite.

Empirically validates backend parameter validations, route precedence disambiguation,
bot execution basket confinement, and capital boundary headroom constraints in:
- `server.py`
- `src/execution/session_manager.py`
- `src/execution/live_bot.py`
"""

from datetime import datetime, timezone
import math
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from server import app
from src.data.provider_base import BaseMarketDataProvider, LiveQuote
from src.execution.broker import PaperBroker
from src.execution.live_bot import LiveBotController
from src.execution.session_manager import (
    DurationType,
    SessionEndPolicy,
    SessionManager,
    SessionMarket,
    TradingHorizon,
)
from src.pipeline import MarketPredictionEngine


class MockChallengerQuoteProvider(BaseMarketDataProvider):
    """Deterministic mock market data provider for empirical challenge scenarios."""

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
def isolated_bot(tmp_path: Path):
    """Creates isolated PaperBroker, SessionManager, and LiveBotController in a clean temp DB."""
    db_file = tmp_path / "challenger_validation.db"
    broker = PaperBroker(account_id="CHALLENGER_ACC", initial_capital=100000.0, db_path=db_file)
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
    bot._initialized = True
    return bot, manager, broker


# ==============================================================================
# 1. Capital Validation Stress Tests
# ==============================================================================


class TestCapitalValidationStress:
    """Stress tests malicious, boundary, and non-numeric capital payloads."""

    @pytest.mark.parametrize("bad_capital", [-1.0, -500.0, -10000.0, 0.0, -0.0001])
    def test_invalid_capital_negative_and_zero(self, bad_capital):
        """Verifies strictly positive requirement rejects negative and zero capital."""
        client = TestClient(app)
        res = client.post(
            "/api/sessions",
            json={
                "market": "US_EQUITIES",
                "instruments": ["AAPL"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": bad_capital,
                "currency": "USD",
            },
        )
        assert res.status_code in (400, 422), f"Expected 400/422 for capital={bad_capital}, got {res.status_code}"

        # Directly stress SessionManager independent validation
        mgr = SessionManager(ledger=None, db_path=Path(":memory:"))
        with pytest.raises(ValueError, match="strictly positive"):
            mgr.validate_session_parameters(
                market="US_EQUITIES",
                currency="USD",
                instruments=["AAPL"],
                allocated_capital=bad_capital,
                horizon="1d",
                duration_type="FIXED",
                duration_minutes=60,
                session_end_policy="CLOSE_ALL",
            )

    @pytest.mark.parametrize("sub_min_capital", [0.01, 100.0, 500.0, 999.99])
    def test_invalid_capital_below_minimum_threshold(self, sub_min_capital):
        """Verifies capital < 1,000 is rejected on backend."""
        client = TestClient(app)
        res = client.post(
            "/api/sessions",
            json={
                "market": "US_EQUITIES",
                "instruments": ["AAPL"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": sub_min_capital,
                "currency": "USD",
            },
        )
        assert res.status_code in (400, 422)

        mgr = SessionManager(ledger=None, db_path=Path(":memory:"))
        with pytest.raises(ValueError, match="outside allowed limits"):
            mgr.validate_session_parameters(
                market="US_EQUITIES",
                currency="USD",
                instruments=["AAPL"],
                allocated_capital=sub_min_capital,
                horizon="1d",
                duration_type="FIXED",
                duration_minutes=60,
                session_end_policy="CLOSE_ALL",
            )

    @pytest.mark.parametrize("excess_capital", [10_000_000.01, 15_000_000.0, 100_000_000.0])
    def test_invalid_capital_above_maximum_threshold(self, excess_capital):
        """Verifies capital > 10,000,000 is rejected on backend."""
        client = TestClient(app)
        res = client.post(
            "/api/sessions",
            json={
                "market": "US_EQUITIES",
                "instruments": ["AAPL"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": excess_capital,
                "currency": "USD",
            },
        )
        assert res.status_code in (400, 422)

        mgr = SessionManager(ledger=None, db_path=Path(":memory:"))
        with pytest.raises(ValueError, match="outside allowed limits"):
            mgr.validate_session_parameters(
                market="US_EQUITIES",
                currency="USD",
                instruments=["AAPL"],
                allocated_capital=excess_capital,
                horizon="1d",
                duration_type="FIXED",
                duration_minutes=60,
                session_end_policy="CLOSE_ALL",
            )

    @pytest.mark.parametrize("malformed", ["not_a_number", "", "NaN_string", "true", "$50000"])
    def test_invalid_capital_non_numeric_strings(self, malformed):
        """Verifies unparseable non-numeric strings are rejected."""
        client = TestClient(app)
        res = client.post(
            "/api/sessions",
            json={
                "market": "US_EQUITIES",
                "instruments": ["AAPL"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": malformed,
                "currency": "USD",
            },
        )
        assert res.status_code == 422

        mgr = SessionManager(ledger=None, db_path=Path(":memory:"))
        with pytest.raises(ValueError, match="Invalid allocated capital"):
            mgr.validate_session_parameters(
                market="US_EQUITIES",
                currency="USD",
                instruments=["AAPL"],
                allocated_capital=malformed,
                horizon="1d",
                duration_type="FIXED",
                duration_minutes=60,
                session_end_policy="CLOSE_ALL",
            )

    @pytest.mark.parametrize("special_float", ["NaN", "Infinity", "-Infinity"])
    def test_invalid_capital_nan_and_inf_payloads(self, special_float):
        """Verifies IEEE 754 NaN and +/-Infinity strings are rejected."""
        client = TestClient(app)
        res = client.post(
            "/api/sessions",
            json={
                "market": "US_EQUITIES",
                "instruments": ["AAPL"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": special_float,
                "currency": "USD",
            },
        )
        assert res.status_code in (400, 422)

        mgr = SessionManager(ledger=None, db_path=Path(":memory:"))
        raw_val = float(special_float)
        with pytest.raises(ValueError):
            mgr.validate_session_parameters(
                market="US_EQUITIES",
                currency="USD",
                instruments=["AAPL"],
                allocated_capital=raw_val,
                horizon="1d",
                duration_type="FIXED",
                duration_minutes=60,
                session_end_policy="CLOSE_ALL",
            )


# ==============================================================================
# 2. Currency Mismatch Stress Tests
# ==============================================================================


class TestCurrencyMismatchStress:
    """Stress tests market and currency inconsistencies."""

    def test_currency_mismatch_indian_nse_with_usd(self):
        """Verifies INDIAN_NSE paired with USD is rejected."""
        client = TestClient(app)
        res = client.post(
            "/api/sessions",
            json={
                "market": "INDIAN_NSE",
                "instruments": ["RELIANCE.NS"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": 50000.0,
                "currency": "USD",
            },
        )
        assert res.status_code in (400, 422)
        assert "Currency mismatch" in str(res.json())

        mgr = SessionManager(ledger=None, db_path=Path(":memory:"))
        with pytest.raises(ValueError, match="Currency mismatch"):
            mgr.validate_session_parameters(
                market="INDIAN_NSE",
                currency="USD",
                instruments=["RELIANCE.NS"],
                allocated_capital=50000.0,
                horizon="1d",
                duration_type="FIXED",
                duration_minutes=60,
                session_end_policy="CLOSE_ALL",
            )

    def test_currency_mismatch_us_equities_with_inr(self):
        """Verifies US_EQUITIES paired with INR is rejected."""
        client = TestClient(app)
        res = client.post(
            "/api/sessions",
            json={
                "market": "US_EQUITIES",
                "instruments": ["AAPL"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": 50000.0,
                "currency": "INR",
            },
        )
        assert res.status_code in (400, 422)
        assert "Currency mismatch" in str(res.json())

        mgr = SessionManager(ledger=None, db_path=Path(":memory:"))
        with pytest.raises(ValueError, match="Currency mismatch"):
            mgr.validate_session_parameters(
                market="US_EQUITIES",
                currency="INR",
                instruments=["AAPL"],
                allocated_capital=50000.0,
                horizon="1d",
                duration_type="FIXED",
                duration_minutes=60,
                session_end_policy="CLOSE_ALL",
            )

    @pytest.mark.parametrize("mkt,curr", [
        ("CRYPTO", "INR"),
        ("COMMODITIES", "INR"),
        ("FOREX", "INR"),
        ("US_EQUITIES", "EUR"),
    ])
    def test_currency_mismatch_cross_asset_payloads(self, mkt, curr):
        """Verifies global/crypto/commodity markets require USD, rejecting INR and EUR."""
        client = TestClient(app)
        res = client.post(
            "/api/sessions",
            json={
                "market": mkt,
                "instruments": ["BTC-USD"] if mkt == "CRYPTO" else (["GC=F"] if mkt == "COMMODITIES" else ["AAPL"]),
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": 50000.0,
                "currency": curr,
            },
        )
        assert res.status_code in (400, 422)


# ==============================================================================
# 3. Jurisdiction Mismatch Stress Tests
# ==============================================================================


class TestJurisdictionMismatchStress:
    """Stress tests cross-market instrument intrusion payloads."""

    def test_jurisdiction_mismatch_aapl_in_indian_nse(self):
        """Verifies US stock AAPL cannot be attached to an INDIAN_NSE session."""
        client = TestClient(app)
        res = client.post(
            "/api/sessions",
            json={
                "market": "INDIAN_NSE",
                "instruments": ["AAPL"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": 50000.0,
                "currency": "INR",
            },
        )
        assert res.status_code in (400, 422)
        assert "mismatch" in str(res.json()).lower()

        mgr = SessionManager(ledger=None, db_path=Path(":memory:"))
        with pytest.raises(ValueError, match="does not belong to market"):
            mgr.validate_session_parameters(
                market="INDIAN_NSE",
                currency="INR",
                instruments=["AAPL"],
                allocated_capital=50000.0,
                horizon="1d",
                duration_type="FIXED",
                duration_minutes=60,
                session_end_policy="CLOSE_ALL",
            )

    def test_jurisdiction_mismatch_reliance_in_us_equities(self):
        """Verifies Indian stock RELIANCE.NS cannot be attached to a US_EQUITIES session."""
        client = TestClient(app)
        res = client.post(
            "/api/sessions",
            json={
                "market": "US_EQUITIES",
                "instruments": ["RELIANCE.NS"],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": 50000.0,
                "currency": "USD",
            },
        )
        assert res.status_code in (400, 422)
        assert "mismatch" in str(res.json()).lower()

        mgr = SessionManager(ledger=None, db_path=Path(":memory:"))
        with pytest.raises(ValueError, match="does not belong to market"):
            mgr.validate_session_parameters(
                market="US_EQUITIES",
                currency="USD",
                instruments=["RELIANCE.NS"],
                allocated_capital=50000.0,
                horizon="1d",
                duration_type="FIXED",
                duration_minutes=60,
                session_end_policy="CLOSE_ALL",
            )

    @pytest.mark.parametrize("mkt,bad_tk", [
        ("US_EQUITIES", "BTC-USD"),
        ("US_EQUITIES", "GC=F"),
        ("INDIAN_NSE", "EURUSD=X"),
        ("CRYPTO", "AAPL"),
        ("COMMODITIES", "RELIANCE.NS"),
    ])
    def test_jurisdiction_mismatch_cross_asset_symbols(self, mkt, bad_tk):
        """Verifies cross-asset instruments are blocked from mismatched market sessions."""
        client = TestClient(app)
        res = client.post(
            "/api/sessions",
            json={
                "market": mkt,
                "instruments": [bad_tk],
                "horizon": "1d",
                "duration_type": "FIXED",
                "duration_minutes": 60,
                "allocated_capital": 50000.0,
                "currency": "INR" if mkt == "INDIAN_NSE" else "USD",
            },
        )
        assert res.status_code in (400, 422)


# ==============================================================================
# 4. Route Precedence Collision Stress Tests
# ==============================================================================


class TestRoutePrecedenceCollisionStress:
    """Verifies that static session routes are never shadowed by {session_id} parameterized endpoints."""

    def test_route_precedence_physical_status_endpoint(self):
        """Verifies GET /api/sessions/status resolves to exchange status dictionary."""
        client = TestClient(app)
        res = client.get("/api/sessions/status")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, dict)
        # Verify it was not captured by session lookup (which would return session wrapper or 400/404)
        assert "session" not in data or "is_open" in str(data)

    def test_route_precedence_active_endpoint(self):
        """Verifies GET /api/sessions/active resolves to active session endpoint."""
        client = TestClient(app)
        res = client.get("/api/sessions/active")
        assert res.status_code == 200
        data = res.json()
        assert "session" in data

    def test_route_precedence_recommendations_endpoint(self):
        """Verifies POST /api/sessions/recommendations resolves to quantitative recommendations."""
        client = TestClient(app)
        res = client.post(
            "/api/sessions/recommendations",
            json={"market": "US_EQUITIES", "target_size": 3},
        )
        assert res.status_code == 200
        data = res.json()
        assert "selected_instruments" in data
        assert "evaluations" in data

    @pytest.mark.parametrize("subpath", ["status", "active", "recommendations"])
    def test_route_precedence_reserved_subpaths_collision_guards(self, subpath):
        """Verifies _guard_session_id intercepts reserved keywords when passed to parameterized paths."""
        client = TestClient(app)
        # Attempt to PUT /api/sessions/{reserved_subpath}
        r_put = client.put(f"/api/sessions/{subpath}", json={"name": "Attacking Route"})
        assert r_put.status_code == 400
        assert "reserved session route" in r_put.json()["detail"]

        # Attempt to POST /api/sessions/{reserved_subpath}/start
        r_start = client.post(f"/api/sessions/{subpath}/start")
        assert r_start.status_code == 400
        assert "reserved session route" in r_start.json()["detail"]

        # Attempt to POST /api/sessions/{reserved_subpath}/stop
        r_stop = client.post(f"/api/sessions/{subpath}/stop")
        assert r_stop.status_code == 400
        assert "reserved session route" in r_stop.json()["detail"]

        # Attempt to GET /api/sessions/{reserved_subpath}/performance
        r_perf = client.get(f"/api/sessions/{subpath}/performance")
        assert r_perf.status_code == 400
        assert "reserved session route" in r_perf.json()["detail"]


# ==============================================================================
# 5. Bot Basket Confinement Stress Tests
# ==============================================================================


class TestBasketConfinementStress:
    """Stress tests autonomous bot execution strictly confined to approved session basket."""

    def test_basket_confinement_tampered_armed_tickers_rejected(self, isolated_bot):
        """Verifies autonomous loop refuses to evaluate or open positions on unapproved tickers."""
        bot, manager, broker = isolated_bot

        # Session is strictly approved for AAPL only
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
        assert bot.armed_tickers == {"AAPL"}

        # Adversarially tamper with armed_tickers by injecting foreign symbols
        bot.armed_tickers.add("NVDA")
        bot.armed_tickers.add("MSFT")
        bot.armed_tickers.add("TSLA")

        # Run bot iteration
        bot.step_tick()

        # Verify open positions: absolutely NO positions opened for NVDA, MSFT, or TSLA
        open_positions = broker.get_open_positions()
        traded_tickers = [p.ticker for p in open_positions]
        for t in traded_tickers:
            assert t in session.instruments, f"CRITICAL: Bot executed trade on unapproved instrument {t} outside basket!"

    def test_basket_confinement_unapproved_instrument_zero_trades(self, isolated_bot):
        """Verifies zero executed trades outside basket across multiple simulated ticks."""
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

        # Force unapproved tickers into armed set
        bot.armed_tickers = {"NVDA", "BTC-USD", "RELIANCE.NS"}

        # Run 3 consecutive ticks
        for _ in range(3):
            bot.step_tick()

        # Zero positions must be opened because none of the armed tickers are in session basket
        assert len(broker.get_open_positions()) == 0


# ==============================================================================
# 6. Capital Headroom Stress Tests
# ==============================================================================


class TestCapitalHeadroomStress:
    """Stress tests capital headroom allocation limits across positions."""

    def test_capital_headroom_enforcement_prevents_overallocation(self, isolated_bot):
        """Verifies bot never allocates more than session allocated_capital across positions."""
        bot, manager, broker = isolated_bot
        session_cap = 5000.0

        session = manager.create_session({
            "market": "US_EQUITIES",
            "instruments": ["AAPL", "NVDA"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 60,
            "allocated_capital": session_cap,
            "currency": "USD",
        })
        manager.start_session(session.id, bot)

        # Manually occupy $4,950 of the $5,000 session headroom
        pos1 = broker.open_position(
            ticker="AAPL",
            direction="LONG",
            current_price=150.0,
            target_price=160.0,
            stop_price=140.0,
            custom_allocated_capital=4950.0,
            session_id=session.id,
        )
        assert pos1 is not None

        # Verify headroom is only $50 (< $100 min trade notional)
        open_pos = broker.get_open_positions()
        invested = sum(p.allocated_capital for p in open_pos)
        assert invested == 4950.0

        # Run autonomous step tick
        bot.step_tick()

        # Total capital invested must remain strictly <= 5000.0
        open_pos_after = broker.get_open_positions()
        total_invested_after = sum(p.allocated_capital for p in open_pos_after)
        assert total_invested_after <= session_cap, (
            f"Capital headroom breached! Total invested {total_invested_after} exceeds session cap {session_cap}"
        )

    def test_capital_headroom_exhaustion_forces_cash_fallback(self, isolated_bot):
        """Verifies that when session headroom is 100% exhausted, bot halts all new allocations."""
        bot, manager, broker = isolated_bot
        session_cap = 3000.0

        session = manager.create_session({
            "market": "US_EQUITIES",
            "instruments": ["AAPL", "NVDA"],
            "horizon": "1d",
            "duration_type": "FIXED",
            "duration_minutes": 60,
            "allocated_capital": session_cap,
            "currency": "USD",
        })
        manager.start_session(session.id, bot)

        # Consume 100% of the session capital
        pos = broker.open_position(
            ticker="AAPL",
            direction="LONG",
            current_price=150.0,
            target_price=160.0,
            stop_price=140.0,
            custom_allocated_capital=session_cap,
            session_id=session.id,
        )
        assert pos is not None
        assert pos.allocated_capital == session_cap

        # Bot step tick should detect 0 remaining headroom and make no new orders
        initial_open_count = len(broker.get_open_positions())
        bot.step_tick()
        assert len(broker.get_open_positions()) == initial_open_count
        assert sum(p.allocated_capital for p in broker.get_open_positions()) == session_cap
