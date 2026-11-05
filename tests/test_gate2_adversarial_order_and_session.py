"""Empirical Challenger Gate 2 Verification Harness.

Adversarially probes:
1. Limit Order Routing via /api/dashboard/order (limit_price acceptance, execution price governance, soft cash hold, pre-market queueing).
2. Account Cash Resolution (soft cash hold vs current cash invariant, cumulative holds, cancellations, open tick transition).
3. MarketSessionRibbon Holiday Handling (NSE Republic Day, NYSE Christmas Day, countdown calculation, client resolution logic).
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest
from fastapi.testclient import TestClient

from server import app, _get_live_bot
from src.execution.broker import PaperBroker, TradingLedgerDB
from src.execution.market_sessions import (
    MarketCalendarManager,
    MarketSessionInfo,
    MarketState,
)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="function")
def isolated_broker():
    """Provides an isolated broker backed by an in-memory/temp ledger."""
    db_path = "data/test_challenger_gate2.db"
    broker = PaperBroker(account_id="CHALLENGER_TEST_ACC", initial_capital=100000.0)
    broker.reset_account(initial_capital=100000.0)
    yield broker
    broker.reset_account(initial_capital=100000.0)


# ============================================================================
# AREA 1: LIMIT ORDER ROUTING
# ============================================================================

class TestLimitOrderRouting:
    """Probes limit order handling via /api/dashboard/order."""

    def test_pre_market_limit_order_queueing_and_soft_hold(self, client):
        """Verify that when an exchange is closed, a LIMIT order queues with limit_price governing price and soft hold."""
        bot = _get_live_bot()
        bot.simulation_mode = False  # Ensure physical exchange schedule rules apply

        # Force state to closed by ensuring ticker is evaluated against physical calendar
        # NVDA is closed overnight
        # Ensure clean state by cancelling any existing pending orders for NVDA
        for p_ord in bot.broker.get_pending_orders("NVDA"):
            bot.broker.cancel_pending_order(p_ord["id"])

        summary_before = bot.broker.get_account_summary()
        current_cash_before = summary_before["current_cash"]
        reserved_cash_before = summary_before["reserved_cash"]
        avail_cash_before = summary_before["available_cash"]

        limit_price = 125.50
        alloc_weight = 10.0

        resp = client.post(
            "/api/dashboard/order",
            json={
                "ticker": "NVDA",
                "direction": "LONG",
                "allocation_weight_pct": alloc_weight,
                "order_type": "LIMIT",
                "limit_price": limit_price,
            },
        )
        assert resp.status_code == 200, f"Order failed: {resp.text}"
        data = resp.json()

        assert data["status"] == "QUEUED"
        assert data["state"] == "PRE_MARKET_PENDING"
        order = data["order"]
        assert order["ticker"] == "NVDA"
        assert order["order_type"] == "LIMIT"
        assert order["price"] == limit_price, "limit_price must be stored as order price"
        assert order["status"] == "PRE_MARKET_PENDING"

        # Check soft cash hold
        summary_after = bot.broker.get_account_summary()
        alloc_capital = order["allocated_capital"]
        assert alloc_capital > 0

        # Current cash must be completely UNTOUCHED
        assert summary_after["current_cash"] == current_cash_before, "current_cash was modified by soft hold!"
        # Reserved cash must increase by exact allocated capital
        assert summary_after["reserved_cash"] == pytest.approx(reserved_cash_before + alloc_capital, abs=0.01)
        # Available cash must decrease by exact allocated capital
        assert summary_after["available_cash"] == pytest.approx(avail_cash_before - alloc_capital, abs=0.01)
        # Backward compatibility 'cash' key must equal available_cash
        assert summary_after["cash"] == summary_after["available_cash"]

        # Target and stop price must be derived from limit_price, not market price
        assert order["target_price"] > limit_price
        assert order["stop_price"] < limit_price

        # Clean up
        cancel_resp = client.delete(f"/api/dashboard/orders/cancel/{order['order_id']}")
        assert cancel_resp.status_code == 200

        # Verify soft hold released
        summary_cleared = bot.broker.get_account_summary()
        assert summary_cleared["reserved_cash"] == reserved_cash_before
        assert summary_cleared["available_cash"] == avail_cash_before

    def test_open_market_limit_order_execution_price_governance(self, client):
        """Verify that when an asset is tradable (e.g. Crypto 24/7), limit_price governs execution price."""
        bot = _get_live_bot()

        limit_price = 55432.10
        resp = client.post(
            "/api/dashboard/order",
            json={
                "ticker": "BTC-USD",
                "direction": "LONG",
                "allocation_weight_pct": 5.0,
                "order_type": "LIMIT",
                "limit_price": limit_price,
            },
        )
        assert resp.status_code == 200, f"Order failed: {resp.text}"
        data = resp.json()

        assert data["status"] == "FILLED"
        pos = data["position"]
        assert pos["ticker"] == "BTC-USD"
        assert pos["entry_price"] == limit_price, f"Expected entry_price {limit_price}, got {pos['entry_price']}"

        # Target and stop prices must be anchored to limit_price
        assert pos["target_price"] > limit_price
        assert pos["stop_price"] < limit_price

        # Clean up position
        close_resp = client.post(f"/api/dashboard/close/{pos['id']}")
        assert close_resp.status_code == 200

    def test_market_order_ignores_limit_price(self, client):
        """Verify that an order with order_type='MARKET' uses live market price even if limit_price is provided."""
        bot = _get_live_bot()
        live_btc = bot.live_prices.get("BTC-USD", 65000.0)

        arbitrary_limit = 999999.0
        resp = client.post(
            "/api/dashboard/order",
            json={
                "ticker": "BTC-USD",
                "direction": "LONG",
                "allocation_weight_pct": 5.0,
                "order_type": "MARKET",
                "limit_price": arbitrary_limit,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "FILLED"
        pos = data["position"]
        # Entry price must NOT be the arbitrary limit price
        assert pos["entry_price"] != arbitrary_limit
        assert abs(pos["entry_price"] - live_btc) < live_btc * 0.1  # Within realistic band of live BTC

        client.post(f"/api/dashboard/close/{pos['id']}")

    def test_invalid_limit_prices_handled_gracefully(self, client):
        """Verify that non-positive limit_price falls back gracefully to market price."""
        bot = _get_live_bot()
        live_btc = bot.live_prices.get("BTC-USD", 65000.0)

        for invalid_limit in [-100.0, 0.0]:
            resp = client.post(
                "/api/dashboard/order",
                json={
                    "ticker": "BTC-USD",
                    "direction": "LONG",
                    "allocation_weight_pct": 5.0,
                    "order_type": "LIMIT",
                    "limit_price": invalid_limit,
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "FILLED"
            pos = data["position"]
            assert pos["entry_price"] > 0
            assert pos["entry_price"] != invalid_limit
            client.post(f"/api/dashboard/close/{pos['id']}")


# ============================================================================
# AREA 2: ACCOUNT CASH RESOLUTION & SOFT CASH HOLDS
# ============================================================================

class TestAccountCashResolution:
    """Probes soft cash hold accounting and available vs current cash invariants."""

    def test_cumulative_soft_holds_and_cancel_invariants(self, client):
        """Verify multiple soft cash holds accumulate and release cleanly without mutating current_cash."""
        bot = _get_live_bot()
        bot.simulation_mode = False

        # Clear any preexisting pending orders
        for ord_info in bot.broker.get_pending_orders():
            bot.broker.cancel_pending_order(ord_info["id"])

        s0 = bot.broker.get_account_summary()
        current_cash_0 = s0["current_cash"]
        avail_cash_0 = s0["available_cash"]
        assert s0["reserved_cash"] == 0.0

        # Queue Order 1 on closed market NVDA ($10,000)
        r1 = client.post(
            "/api/dashboard/order",
            json={"ticker": "NVDA", "direction": "LONG", "allocation_weight_pct": 10.0, "order_type": "LIMIT", "limit_price": 120.0},
        )
        assert r1.status_code == 200
        o1 = r1.json()["order"]
        alloc1 = o1["allocated_capital"]

        s1 = bot.broker.get_account_summary()
        assert s1["current_cash"] == current_cash_0, "current_cash changed after order 1!"
        assert s1["reserved_cash"] == pytest.approx(alloc1, abs=0.01)
        assert s1["available_cash"] == pytest.approx(avail_cash_0 - alloc1, abs=0.01)

        # Queue Order 2 on closed market AAPL ($15,000)
        orig_is_tradable = bot._is_ticker_tradable_now
        bot._is_ticker_tradable_now = lambda tk: (False, {"is_open": False, "exchange": "Closed", "schedule": "", "local_clock": "", "reason": "Closed", "next_state_time_utc": "2026-11-06T09:15:00Z"})
        try:
            r2 = client.post(
                "/api/dashboard/order",
                json={"ticker": "RELIANCE.NS", "direction": "LONG", "allocation_weight_pct": 15.0, "order_type": "LIMIT", "limit_price": 2800.0},
            )
        finally:
            bot._is_ticker_tradable_now = orig_is_tradable
        assert r2.status_code == 200
        o2 = r2.json()["order"]
        alloc2 = o2["allocated_capital"]

        s2 = bot.broker.get_account_summary()
        assert s2["current_cash"] == current_cash_0, "current_cash changed after order 2!"
        assert s2["reserved_cash"] == pytest.approx(alloc1 + alloc2, abs=0.01)
        assert s2["available_cash"] == pytest.approx(avail_cash_0 - alloc1 - alloc2, abs=0.01)

        # Cancel Order 1
        c1 = client.delete(f"/api/dashboard/orders/cancel/{o1['order_id']}")
        assert c1.status_code == 200
        s3 = bot.broker.get_account_summary()
        assert s3["current_cash"] == current_cash_0
        assert s3["reserved_cash"] == pytest.approx(alloc2, abs=0.01)
        assert s3["available_cash"] == pytest.approx(avail_cash_0 - alloc2, abs=0.01)

        # Cancel Order 2
        c2 = client.delete(f"/api/dashboard/orders/cancel/{o2['order_id']}")
        assert c2.status_code == 200
        s4 = bot.broker.get_account_summary()
        assert s4["current_cash"] == current_cash_0
        assert s4["reserved_cash"] == 0.0
        assert s4["available_cash"] == pytest.approx(avail_cash_0, abs=0.05)

    def test_soft_hold_exhaustion_rejection(self, isolated_broker):
        """Verify that an order attempting to reserve more than available cash is strictly rejected."""
        # Baseline cash is 100k
        # Reserve $95,000 via custom_allocated_capital
        o1 = isolated_broker.queue_pre_market_order(
            ticker="NVDA",
            direction="LONG",
            current_price=100.0,
            custom_allocated_capital=99980.0,
        )
        assert o1["allocated_capital"] == 99980.0

        summary = isolated_broker.get_account_summary()
        assert summary["available_cash"] < 50.0  # Remaining available cash is $20

        # Attempting another order must raise ValueError (alloc_cap < 50.0)
        with pytest.raises(ValueError, match="Insufficient unreserved cash"):
            isolated_broker.queue_pre_market_order(
                ticker="AAPL",
                direction="LONG",
                current_price=150.0,
                allocation_weight_pct=10.0,
            )

    def test_transition_from_soft_hold_to_hard_deduction(self, isolated_broker):
        """Verify that upon execution of a queued order, reserved cash releases and current cash is deducted."""
        initial_cash = 100000.0
        order = isolated_broker.queue_pre_market_order(
            ticker="NVDA",
            direction="LONG",
            current_price=120.0,
            target_price=135.0,
            stop_price=110.0,
            custom_allocated_capital=10000.0,
        )
        assert order["status"] == "PRE_MARKET_PENDING"

        s1 = isolated_broker.get_account_summary()
        assert s1["current_cash"] == initial_cash
        assert s1["reserved_cash"] == 10000.0
        assert s1["available_cash"] == 90000.0

        # Simulate market open execution
        opening_price = 122.0
        positions = isolated_broker.execute_pending_orders_for_ticker("NVDA", opening_price=opening_price)
        assert len(positions) == 1
        pos = positions[0]
        assert pos.ticker == "NVDA"
        assert pos.entry_price == opening_price

        # Inspect account summary after fill:
        # Soft hold must be 0 (order is FILLED, no longer PRE_MARKET_PENDING)
        # Current cash must be deducted by allocated_capital ($10,000)
        s2 = isolated_broker.get_account_summary()
        assert s2["reserved_cash"] == 0.0
        assert s2["current_cash"] == pytest.approx(90000.0, abs=0.01)
        assert s2["available_cash"] == pytest.approx(90000.0, abs=0.01)


# ============================================================================
# AREA 3: MARKET SESSION RIBBON HOLIDAY HANDLING
# ============================================================================

class TestMarketSessionHolidayHandling:
    """Probes statutory holiday handling for Indian and US exchanges."""

    @pytest.fixture(autouse=True)
    def setup_calendar(self):
        self.cal = MarketCalendarManager()
        self.tz_ist = ZoneInfo("Asia/Kolkata")
        self.tz_et = ZoneInfo("America/New_York")
        self.tz_utc = timezone.utc

    def test_nse_republic_day_statutory_holiday(self):
        """Verify NSE on Republic Day (2026-01-26, Monday) evaluates as HOLIDAY, frozen ticks, with countdown to Tuesday."""
        # 11:30 AM IST on Monday 2026-01-26 (would normally be regular trading hours)
        dt_ist = datetime(2026, 1, 26, 11, 30, 0, tzinfo=self.tz_ist)
        dt_utc = dt_ist.astimezone(self.tz_utc)

        info = self.cal.get_session_info("RELIANCE.NS", now_utc=dt_utc)

        assert info.state == MarketState.HOLIDAY
        assert info.is_open is False
        assert info.is_tradable is False
        assert info.tick_frozen is True
        assert info.holiday_name == "Republic Day"
        assert "Holiday: Republic Day" in info.reason
        assert info.next_state == MarketState.OPEN

        # Next open should be Tuesday 2026-01-27 at 09:15 IST
        expected_open_ist = datetime(2026, 1, 27, 9, 15, 0, tzinfo=self.tz_ist)
        expected_open_utc = expected_open_ist.astimezone(self.tz_utc)
        assert info.next_state_time_utc == expected_open_utc.isoformat()

        # Seconds remaining should be exactly 21h 45m = 78,300 seconds
        expected_seconds = int((expected_open_utc - dt_utc).total_seconds())
        assert info.seconds_to_next_state == expected_seconds
        assert "Opens in" in info.countdown_display

    def test_nyse_christmas_day_statutory_holiday(self):
        """Verify NYSE on Christmas Day (2026-12-25, Friday) evaluates as HOLIDAY, frozen ticks, countdown to Monday."""
        # 11:00 AM ET on Friday 2026-12-25 (would normally be regular trading hours)
        dt_et = datetime(2026, 12, 25, 11, 0, 0, tzinfo=self.tz_et)
        dt_utc = dt_et.astimezone(self.tz_utc)

        info = self.cal.get_session_info("NVDA", now_utc=dt_utc)

        assert info.state == MarketState.HOLIDAY
        assert info.is_open is False
        assert info.is_tradable is False
        assert info.tick_frozen is True
        assert info.holiday_name == "Christmas Day"
        assert "Holiday: Christmas Day" in info.reason
        assert info.next_state == MarketState.OPEN

        # Next open should be Monday 2026-12-28 at 09:30 ET (skipping Saturday and Sunday)
        expected_open_et = datetime(2026, 12, 28, 9, 30, 0, tzinfo=self.tz_et)
        expected_open_utc = expected_open_et.astimezone(self.tz_utc)
        assert info.next_state_time_utc == expected_open_utc.isoformat()

        # Seconds remaining should span Friday 11:00 ET to Monday 09:30 ET
        expected_seconds = int((expected_open_utc - dt_utc).total_seconds())
        assert info.seconds_to_next_state == expected_seconds
        assert "Opens in" in info.countdown_display

    def test_nse_christmas_day_statutory_holiday(self):
        """Verify NSE on Christmas Day (2026-12-25, Friday) also evaluates as HOLIDAY."""
        dt_ist = datetime(2026, 12, 25, 12, 0, 0, tzinfo=self.tz_ist)
        dt_utc = dt_ist.astimezone(self.tz_utc)

        info = self.cal.get_session_info("RELIANCE.NS", now_utc=dt_utc)
        assert info.state == MarketState.HOLIDAY
        assert info.holiday_name == "Christmas"
        assert info.is_open is False
        assert info.tick_frozen is True

        # Next open should be Monday 2026-12-28 at 09:15 IST
        expected_open_ist = datetime(2026, 12, 28, 9, 15, 0, tzinfo=self.tz_ist)
        expected_open_utc = expected_open_ist.astimezone(self.tz_utc)
        assert info.next_state_time_utc == expected_open_utc.isoformat()

    def test_server_api_sessions_status_returns_holiday_metadata(self, client):
        """Verify /api/sessions/status endpoint returns complete holiday metadata."""
        resp = client.get("/api/sessions/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "RELIANCE.NS" in data or "NSE_INDIA" in data
        # Check structure
        sample = next(iter(data.values()))
        assert "state" in sample
        assert "is_open" in sample
        assert "seconds_to_next_state" in sample
        assert "next_state_time_utc" in sample
        assert "local_time" in sample
        assert "exchange_tz" in sample
        assert "holiday_name" in sample
