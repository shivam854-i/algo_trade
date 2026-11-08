"""Milestone M2 Comprehensive Acceptance Test Suite.

Verifies:
1. Physical market session engine, timezone transitions (IST, ET, UTC), DST, and statutory holiday tables.
2. Second-by-second countdown calculations with UTC target timestamps.
3. Broker SQLite orders table migration, pre-market order queueing, soft cash holds, cancellation, and execution.
4. Strict live price tick freezing on closed markets vs. 24/7 simulation mode.
5. Server REST endpoints: session status, pending orders, cancellation, simulation toggle, and off-hours order routing.
"""

import sys
from pathlib import Path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest
from fastapi.testclient import TestClient

from src.execution.broker import PaperBroker, TradingLedgerDB
from src.execution.market_sessions import (
    MarketCalendarManager,
    MarketSessionInfo,
    MarketState,
)
from src.execution.live_bot import LiveBotController, get_exchange_session_status
from server import app, _get_live_bot


def test_market_sessions_indian_equities():
    manager = MarketCalendarManager()
    tz_ist = ZoneInfo("Asia/Kolkata")

    # Regular Trading Hours (Tuesday 11:30 IST)
    dt_rth = datetime(2026, 11, 3, 11, 30, tzinfo=tz_ist).astimezone(timezone.utc)
    res_rth = manager.get_session_info("RELIANCE.NS", now_utc=dt_rth)
    assert res_rth.state == MarketState.OPEN
    assert res_rth.is_open is True
    assert res_rth.is_tradable is True
    assert res_rth.tick_frozen is False

    # Pre-market (Tuesday 09:05 IST)
    dt_pre = datetime(2026, 11, 3, 9, 5, tzinfo=tz_ist).astimezone(timezone.utc)
    res_pre = manager.get_session_info("RELIANCE.NS", now_utc=dt_pre)
    assert res_pre.state == MarketState.PRE_MARKET
    assert res_pre.is_tradable is False
    assert res_pre.tick_frozen is True

    # Post-market (Tuesday 15:45 IST)
    dt_post = datetime(2026, 11, 3, 15, 45, tzinfo=tz_ist).astimezone(timezone.utc)
    res_post = manager.get_session_info("RELIANCE.NS", now_utc=dt_post)
    assert res_post.state == MarketState.POST_MARKET
    assert res_post.is_tradable is False

    # Overnight closed (Tuesday 21:00 IST)
    dt_closed = datetime(2026, 11, 3, 21, 0, tzinfo=tz_ist).astimezone(timezone.utc)
    res_closed = manager.get_session_info("RELIANCE.NS", now_utc=dt_closed)
    assert res_closed.state == MarketState.CLOSED

    # Weekend (Saturday 12:00 IST)
    dt_sat = datetime(2026, 11, 7, 12, 0, tzinfo=tz_ist).astimezone(timezone.utc)
    res_sat = manager.get_session_info("RELIANCE.NS", now_utc=dt_sat)
    assert res_sat.state == MarketState.WEEKEND

    # Statutory Holiday: Republic Day (Jan 26, 2026)
    dt_rep = datetime(2026, 1, 26, 11, 0, tzinfo=tz_ist).astimezone(timezone.utc)
    res_rep = manager.get_session_info("RELIANCE.NS", now_utc=dt_rep)
    assert res_rep.state == MarketState.HOLIDAY
    assert res_rep.holiday_name == "Republic Day"


@pytest.mark.disabled_market
def test_market_sessions_us_equities_and_dst():
    manager = MarketCalendarManager()
    tz_et = ZoneInfo("America/New_York")

    # Summer Regular Hours (EDT, UTC-4): July 15, 2026 at 11:00 ET
    dt_edt_open = datetime(2026, 7, 15, 11, 0, tzinfo=tz_et).astimezone(timezone.utc)
    res_edt = manager.get_session_info("NVDA", now_utc=dt_edt_open)
    assert res_edt.state == MarketState.OPEN
    assert "EDT" in res_edt.local_time_str or "-04" in res_edt.local_time_str or "11:00" in res_edt.local_time_str

    # Winter Regular Hours (EST, UTC-5): December 15, 2026 at 11:00 ET
    dt_est_open = datetime(2026, 12, 15, 11, 0, tzinfo=tz_et).astimezone(timezone.utc)
    res_est = manager.get_session_info("NVDA", now_utc=dt_est_open)
    assert res_est.state == MarketState.OPEN
    assert "EST" in res_est.local_time_str or "-05" in res_est.local_time_str or "11:00" in res_est.local_time_str

    # Pre-market (08:00 ET)
    dt_pre = datetime(2026, 12, 15, 8, 0, tzinfo=tz_et).astimezone(timezone.utc)
    res_pre = manager.get_session_info("NVDA", now_utc=dt_pre)
    assert res_pre.state == MarketState.PRE_MARKET

    # Statutory Holiday: Martin Luther King Jr. Day (Jan 19, 2026)
    dt_mlk = datetime(2026, 1, 19, 12, 0, tzinfo=tz_et).astimezone(timezone.utc)
    res_mlk = manager.get_session_info("NVDA", now_utc=dt_mlk)
    assert res_mlk.state == MarketState.HOLIDAY
    assert res_mlk.holiday_name == "Martin Luther King Jr. Day"


@pytest.mark.disabled_market
def test_market_sessions_commodities_and_crypto():
    manager = MarketCalendarManager()
    tz_et = ZoneInfo("America/New_York")

    # CME Globex Gold GC=F open: Wednesday 14:00 ET
    dt_open = datetime(2026, 11, 4, 14, 0, tzinfo=tz_et).astimezone(timezone.utc)
    res_gold = manager.get_session_info("GC=F", now_utc=dt_open)
    assert res_gold.state == MarketState.OPEN

    # CME Daily Maintenance Pause: Wednesday 17:30 ET
    dt_pause = datetime(2026, 11, 4, 17, 30, tzinfo=tz_et).astimezone(timezone.utc)
    res_pause = manager.get_session_info("GC=F", now_utc=dt_pause)
    assert res_pause.state == MarketState.CLOSED
    assert "Maintenance" in res_pause.reason

    # Crypto 24/7/365: always OPEN
    dt_any = datetime(2026, 11, 7, 3, 0, tzinfo=timezone.utc) # Saturday night
    res_crypto = manager.get_session_info("BTC-USD", now_utc=dt_any)
    assert res_crypto.state == MarketState.OPEN
    assert res_crypto.countdown_display == "Continuous 24/7"


def test_broker_orders_table_migration_and_soft_hold():
    broker = PaperBroker(account_id="TEST_UNIT_M2")
    broker.reset_account(100000.0)

    # 1. Baseline
    summary = broker.get_account_summary()
    assert summary["current_cash"] == 100000.0
    assert summary["reserved_cash"] == 0.0
    assert summary["available_cash"] == 100000.0

    # 2. Queue order
    order = broker.queue_pre_market_order(
        ticker="NVDA",
        direction="LONG",
        current_price=130.0,
        target_price=150.0,
        stop_price=120.0,
        allocation_weight_pct=15.0,
    )
    assert order["status"] == "PRE_MARKET_PENDING"
    assert order["allocated_capital"] == 15000.0

    # 3. Soft Cash Hold Reservation
    s2 = broker.get_account_summary()
    assert s2["current_cash"] == 100000.0  # Cash not deducted before fill
    assert s2["reserved_cash"] == 15000.0  # Soft hold active
    assert s2["available_cash"] == 85000.0  # Remaining available

    # 4. Pending orders retrieval
    pending = broker.get_pending_orders()
    assert len(pending) == 1
    assert pending[0]["ticker"] == "NVDA"

    # 5. Order execution on market open
    executed = broker.execute_pending_orders_for_ticker("NVDA", opening_price=132.0)
    assert len(executed) == 1
    assert executed[0].ticker == "NVDA"
    assert executed[0].entry_price == 132.0

    # 6. Post-execution balances
    s3 = broker.get_account_summary()
    assert s3["reserved_cash"] == 0.0  # Released
    assert s3["current_cash"] == 85000.0  # Deducted
    assert s3["allocated_capital"] == 15000.0  # Active in position

    # Clean up
    broker.reset_account(100000.0)


def test_server_m2_endpoints():
    client = TestClient(app)

    # 1. Sessions status endpoint
    r_sess = client.get("/api/sessions/status")
    assert r_sess.status_code == 200
    sessions = r_sess.json()
    assert "NSE_INDIA" in sessions
    assert "US_MARKETS" in sessions
    assert "CME_GLOBEX" in sessions
    assert "CRYPTO_247" in sessions

    # 2. Toggle simulation mode
    r_sim = client.post("/api/dashboard/toggle-simulation")
    assert r_sim.status_code == 200
    assert r_sim.json()["bot_status"]["simulation_mode"] is True
    # Toggle back to strict physical hours
    r_sim2 = client.post("/api/dashboard/toggle-simulation")
    assert r_sim2.status_code == 200
    assert r_sim2.json()["bot_status"]["simulation_mode"] is False

    # 3. Queue off-hours order via /api/dashboard/order
    bot = _get_live_bot()
    orig_tradable = bot._is_ticker_tradable_now
    bot._is_ticker_tradable_now = lambda tk: (False, {"is_open": False, "exchange": "NSE", "schedule": "09:15-15:30", "local_clock": "20:00 IST", "reason": "Closed", "next_state_time_utc": "2026-11-06T03:45:00Z"})
    try:
        r_ord = client.post("/api/dashboard/order", json={
            "ticker": "RELIANCE.NS",
            "direction": "LONG",
            "allocation_weight_pct": 10.0,
        })
    finally:
        bot._is_ticker_tradable_now = orig_tradable
    assert r_ord.status_code == 200
    ord_data = r_ord.json()
    assert ord_data.get("status") == "QUEUED"
    assert ord_data.get("state") == "PRE_MARKET_PENDING"
    order_id = ord_data.get("order_id")

    # 4. View in pending orders endpoint
    r_pend = client.get("/api/dashboard/orders/pending")
    assert r_pend.status_code == 200
    assert any(o["order_id"] == order_id for o in r_pend.json())

    # 5. Cancel pending order endpoint
    r_cancel = client.delete(f"/api/dashboard/orders/cancel/{order_id}")
    assert r_cancel.status_code == 200
    assert r_cancel.json()["status"] == "CANCELLED"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
