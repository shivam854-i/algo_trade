"""Adversarial Empirical Stress-Testing Harness: Market Sessions, Order Queuing & Invariants.

Authored by challenger_r2_2 (Exchange Sessions & Orders Challenger).
Independently probes boundary seconds, DST transitions, holiday boundaries,
price tick freezing, soft cash reservation, cancellation idempotency, and open tick execution.
"""

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sqlite3
import threading
from typing import List
from zoneinfo import ZoneInfo
import numpy as np
import pytest

from src.execution.broker import PaperBroker, TradingLedgerDB
from src.execution.market_sessions import (
    MarketCalendarManager,
    MarketSessionInfo,
    MarketState,
)
from src.execution.live_bot import LiveBotController
from src.pipeline import MarketPredictionEngine


# ============================================================================
# 1. BOUNDARY TIMES & CALENDAR ADVERSARIAL STRESS TESTS
# ============================================================================

class TestAdversarialBoundaryTimes:
    """Stress tests exact boundary seconds, DST shifts, and calendar invariants."""

    @pytest.fixture(autouse=True)
    def setup_calendar(self):
        self.cal = MarketCalendarManager()
        self.tz_ist = ZoneInfo("Asia/Kolkata")
        self.tz_et = ZoneInfo("America/New_York")
        self.tz_utc = timezone.utc

    def test_nse_subsecond_and_boundary_transitions(self):
        """Tests exact second transitions for NSE: 09:14:59, 09:15:00, 15:30:00, 15:30:01, 16:00:00, 16:00:01."""
        test_day = date(2026, 4, 15)  # Wednesday (Trading Day)

        # 09:14:59 IST -> PRE_MARKET
        t1 = datetime.combine(test_day, time(9, 14, 59), tzinfo=self.tz_ist)
        s1 = self.cal.get_session_info("RELIANCE.NS", now_utc=t1)
        assert s1.state == MarketState.PRE_MARKET
        assert s1.seconds_to_next_state == 1
        assert s1.next_state == MarketState.OPEN

        # 09:15:00 IST -> OPEN
        t2 = datetime.combine(test_day, time(9, 15, 0), tzinfo=self.tz_ist)
        s2 = self.cal.get_session_info("RELIANCE.NS", now_utc=t2)
        assert s2.state == MarketState.OPEN
        assert s2.is_tradable is True
        assert s2.tick_frozen is False
        assert s2.next_state == MarketState.POST_MARKET
        # 6 hours 15 mins = 22500 seconds until 15:30
        assert s2.seconds_to_next_state == 22500

        # 15:30:00 IST -> OPEN (inclusive boundary)
        t3 = datetime.combine(test_day, time(15, 30, 0), tzinfo=self.tz_ist)
        s3 = self.cal.get_session_info("RELIANCE.NS", now_utc=t3)
        assert s3.state == MarketState.OPEN
        assert s3.seconds_to_next_state == 0

        # 15:30:01 IST -> POST_MARKET
        t4 = datetime.combine(test_day, time(15, 30, 1), tzinfo=self.tz_ist)
        s4 = self.cal.get_session_info("RELIANCE.NS", now_utc=t4)
        assert s4.state == MarketState.POST_MARKET
        assert s4.seconds_to_next_state == 1799
        assert s4.next_state == MarketState.CLOSED

        # 16:00:00 IST -> POST_MARKET (inclusive boundary)
        t5 = datetime.combine(test_day, time(16, 0, 0), tzinfo=self.tz_ist)
        s5 = self.cal.get_session_info("RELIANCE.NS", now_utc=t5)
        assert s5.state == MarketState.POST_MARKET
        assert s5.seconds_to_next_state == 0

        # 16:00:01 IST -> CLOSED (After-Hours)
        t6 = datetime.combine(test_day, time(16, 0, 1), tzinfo=self.tz_ist)
        s6 = self.cal.get_session_info("RELIANCE.NS", now_utc=t6)
        assert s6.state == MarketState.CLOSED
        assert s6.tick_frozen is True
        assert s6.next_state == MarketState.OPEN

    def test_nyse_subsecond_and_boundary_transitions(self):
        """Tests exact second transitions for NYSE: 03:59:59, 04:00:00, 09:29:59, 09:30:00, 16:00:00, 16:00:01, 20:00:00, 20:00:01."""
        test_day = date(2026, 4, 15)  # Wednesday (Trading Day)

        # 03:59:59 ET -> CLOSED
        t1 = datetime.combine(test_day, time(3, 59, 59), tzinfo=self.tz_et)
        s1 = self.cal.get_session_info("NVDA", now_utc=t1)
        assert s1.state == MarketState.CLOSED
        assert s1.seconds_to_next_state == 1
        assert s1.next_state == MarketState.PRE_MARKET

        # 04:00:00 ET -> PRE_MARKET
        t2 = datetime.combine(test_day, time(4, 0, 0), tzinfo=self.tz_et)
        s2 = self.cal.get_session_info("NVDA", now_utc=t2)
        assert s2.state == MarketState.PRE_MARKET
        assert s2.next_state == MarketState.OPEN
        assert s2.seconds_to_next_state == 5 * 3600 + 30 * 60  # 19800 seconds

        # 09:29:59 ET -> PRE_MARKET
        t3 = datetime.combine(test_day, time(9, 29, 59), tzinfo=self.tz_et)
        s3 = self.cal.get_session_info("NVDA", now_utc=t3)
        assert s3.state == MarketState.PRE_MARKET
        assert s3.seconds_to_next_state == 1

        # 09:30:00 ET -> OPEN
        t4 = datetime.combine(test_day, time(9, 30, 0), tzinfo=self.tz_et)
        s4 = self.cal.get_session_info("NVDA", now_utc=t4)
        assert s4.state == MarketState.OPEN
        assert s4.is_tradable is True
        assert s4.seconds_to_next_state == 6 * 3600 + 30 * 60  # 23400 seconds until 16:00

        # 16:00:00 ET -> OPEN (inclusive boundary)
        t5 = datetime.combine(test_day, time(16, 0, 0), tzinfo=self.tz_et)
        s5 = self.cal.get_session_info("NVDA", now_utc=t5)
        assert s5.state == MarketState.OPEN
        assert s5.seconds_to_next_state == 0

        # 16:00:01 ET -> POST_MARKET
        t6 = datetime.combine(test_day, time(16, 0, 1), tzinfo=self.tz_et)
        s6 = self.cal.get_session_info("NVDA", now_utc=t6)
        assert s6.state == MarketState.POST_MARKET
        assert s6.next_state == MarketState.CLOSED
        assert s6.seconds_to_next_state == 4 * 3600 - 1  # 14399s until 20:00

        # 20:00:00 ET -> POST_MARKET (inclusive boundary)
        t7 = datetime.combine(test_day, time(20, 0, 0), tzinfo=self.tz_et)
        s7 = self.cal.get_session_info("NVDA", now_utc=t7)
        assert s7.state == MarketState.POST_MARKET
        assert s7.seconds_to_next_state == 0

        # 20:00:01 ET -> CLOSED
        t8 = datetime.combine(test_day, time(20, 0, 1), tzinfo=self.tz_et)
        s8 = self.cal.get_session_info("NVDA", now_utc=t8)
        assert s8.state == MarketState.CLOSED
        assert s8.next_state == MarketState.OPEN

    def test_comex_gold_maintenance_break_and_reopen_exact_seconds(self):
        """Stress-tests CME COMEX Gold daily maintenance halt (17:00-18:00 ET Mon-Thu) and Sunday open."""
        # Tuesday 16:59:59 ET -> OPEN
        t_open = datetime(2026, 4, 14, 16, 59, 59, tzinfo=self.tz_et)
        s_open = self.cal.get_session_info("GC=F", now_utc=t_open)
        assert s_open.state == MarketState.OPEN
        assert s_open.seconds_to_next_state == 1
        assert s_open.next_state == MarketState.CLOSED

        # Tuesday 17:00:00 ET -> Daily Maintenance Halt (CLOSED)
        t_halt = datetime(2026, 4, 14, 17, 0, 0, tzinfo=self.tz_et)
        s_halt = self.cal.get_session_info("GC=F", now_utc=t_halt)
        assert s_halt.state == MarketState.CLOSED
        assert "Maintenance" in s_halt.reason
        assert s_halt.next_state == MarketState.OPEN
        assert s_halt.seconds_to_next_state == 3600

        # Tuesday 17:59:59 ET -> Still in Maintenance Halt
        t_halt_end = datetime(2026, 4, 14, 17, 59, 59, tzinfo=self.tz_et)
        s_halt_end = self.cal.get_session_info("GC=F", now_utc=t_halt_end)
        assert s_halt_end.state == MarketState.CLOSED
        assert s_halt_end.seconds_to_next_state == 1

        # Tuesday 18:00:00 ET -> Re-opens for next session
        t_reopen = datetime(2026, 4, 14, 18, 0, 0, tzinfo=self.tz_et)
        s_reopen = self.cal.get_session_info("GC=F", now_utc=t_reopen)
        assert s_reopen.state == MarketState.OPEN
        assert s_reopen.seconds_to_next_state == 23 * 3600  # 82800s until Wednesday 17:00

        # Friday 17:00:00 ET -> Weekend Shutdown
        t_fri_close = datetime(2026, 4, 17, 17, 0, 0, tzinfo=self.tz_et)
        s_fri_close = self.cal.get_session_info("GC=F", now_utc=t_fri_close)
        assert s_fri_close.state == MarketState.WEEKEND
        assert s_fri_close.next_state == MarketState.OPEN
        # Next open is Sunday 18:00 ET (49 hours = 176400 seconds)
        assert s_fri_close.seconds_to_next_state == 49 * 3600

        # Sunday 17:15:00 ET -> Sunday Pre-Open Order Entry
        t_sun_pre = datetime(2026, 4, 19, 17, 15, 0, tzinfo=self.tz_et)
        s_sun_pre = self.cal.get_session_info("GC=F", now_utc=t_sun_pre)
        assert s_sun_pre.state == MarketState.PRE_MARKET
        assert s_sun_pre.seconds_to_next_state == 45 * 60

        # Sunday 18:00:00 ET -> Weekly Session Open
        t_sun_open = datetime(2026, 4, 19, 18, 0, 0, tzinfo=self.tz_et)
        s_sun_open = self.cal.get_session_info("GC=F", now_utc=t_sun_open)
        assert s_sun_open.state == MarketState.OPEN

    def test_dst_transitions_us_equities_spring_and_fall(self):
        """Verifies Daylight Saving Time transition accuracy in 2026: Spring Forward (Mar 8) & Fall Back (Nov 1)."""
        # Spring 2026: Clocks forward on March 8, 2026
        # Friday Mar 6 (Winter EST: UTC-5) -> 09:30 EST is 14:30 UTC
        utc_winter = datetime(2026, 3, 6, 14, 30, 0, tzinfo=self.tz_utc)
        s_winter = self.cal.get_session_info("NVDA", now_utc=utc_winter)
        assert s_winter.state == MarketState.OPEN
        assert "09:30:00 EST" in s_winter.local_time_str

        # Monday Mar 9 (Summer EDT: UTC-4) -> 09:30 EDT is 13:30 UTC
        utc_summer = datetime(2026, 3, 9, 13, 30, 0, tzinfo=self.tz_utc)
        s_summer = self.cal.get_session_info("NVDA", now_utc=utc_summer)
        assert s_summer.state == MarketState.OPEN
        assert "09:30:00 EDT" in s_summer.local_time_str

        # Fall 2026: Clocks backward on Nov 1, 2026
        # Friday Oct 30 (Summer EDT: UTC-4) -> 09:30 EDT is 13:30 UTC
        utc_fall_edt = datetime(2026, 10, 30, 13, 30, 0, tzinfo=self.tz_utc)
        s_fall_edt = self.cal.get_session_info("AAPL", now_utc=utc_fall_edt)
        assert s_fall_edt.state == MarketState.OPEN
        assert "EDT" in s_fall_edt.local_time_str

        # Monday Nov 2 (Winter EST: UTC-5) -> 09:30 EST is 14:30 UTC
        utc_fall_est = datetime(2026, 11, 2, 14, 30, 0, tzinfo=self.tz_utc)
        s_fall_est = self.cal.get_session_info("AAPL", now_utc=utc_fall_est)
        assert s_fall_est.state == MarketState.OPEN
        assert "EST" in s_fall_est.local_time_str

    def test_comprehensive_2026_statutory_holidays_audit(self):
        """Audits all official 2026 statutory holidays for NSE and NYSE."""
        # 1. NSE Holidays (16 dates)
        nse_holidays_2026 = [
            (date(2026, 1, 26), "Republic Day"),
            (date(2026, 3, 6), "Mahashivratri"),
            (date(2026, 3, 25), "Holi"),
            (date(2026, 4, 3), "Good Friday"),
            (date(2026, 4, 14), "Dr. Baba Saheb Ambedkar Jayanti"),
            (date(2026, 4, 21), "Ram Navami"),
            (date(2026, 5, 1), "Maharashtra Day"),
            (date(2026, 5, 27), "Bakri Id / Eid-ul-Adha"),
            (date(2026, 6, 26), "Muharram"),
            (date(2026, 10, 2), "Mahatma Gandhi Jayanti"),
            (date(2026, 10, 20), "Dussehra"),
            (date(2026, 11, 10), "Diwali Balipratipada"),
            (date(2026, 11, 24), "Guru Nanak Jayanti"),
            (date(2026, 12, 25), "Christmas"),
        ]
        for h_date, h_name in nse_holidays_2026:
            dt = datetime.combine(h_date, time(11, 0), tzinfo=self.tz_ist)
            info = self.cal.get_session_info("TCS.NS", now_utc=dt)
            assert info.state == MarketState.HOLIDAY, f"Expected HOLIDAY for {h_name} on {h_date}, got {info.state}"
            assert info.holiday_name == h_name
            assert info.tick_frozen is True
            assert info.is_tradable is False

        # 2. NYSE Holidays (10 dates in 2026)
        nyse_holidays_2026 = [
            (date(2026, 1, 1), "New Year's Day"),
            (date(2026, 1, 19), "Martin Luther King Jr. Day"),
            (date(2026, 2, 16), "Washington's Birthday (Presidents' Day)"),
            (date(2026, 4, 3), "Good Friday"),
            (date(2026, 5, 25), "Memorial Day"),
            (date(2026, 6, 19), "Juneteenth National Independence Day"),
            (date(2026, 7, 3), "Independence Day (Observed)"),
            (date(2026, 9, 7), "Labor Day"),
            (date(2026, 11, 26), "Thanksgiving Day"),
            (date(2026, 12, 25), "Christmas Day"),
        ]
        for h_date, h_name in nyse_holidays_2026:
            dt = datetime.combine(h_date, time(12, 0), tzinfo=self.tz_et)
            info = self.cal.get_session_info("MSFT", now_utc=dt)
            assert info.state == MarketState.HOLIDAY, f"Expected HOLIDAY for {h_name} on {h_date}, got {info.state}"
            assert info.holiday_name == h_name
            assert info.tick_frozen is True
            assert info.is_tradable is False


# ============================================================================
# 2. PRICE TICK FREEZING & SIMULATION DECOUPLING ADVERSARIAL STRESS TESTS
# ============================================================================

class TestAdversarialPriceTickFreezing:
    """Stress tests price tick freezing when simulation mode is false vs continuous crypto."""

    @pytest.fixture
    def test_environment(self, tmp_path):
        db_path = tmp_path / "test_adversarial_ticks.db"
        broker = PaperBroker(account_id="CHALLENGER_TICK_TEST", initial_capital=100000.0)
        broker.ledger = TradingLedgerDB(db_path=db_path)
        broker._ensure_account(100000.0)

        engine = MarketPredictionEngine()
        bot = LiveBotController(engine=engine, broker=broker)

        # Seed mock analyses and base prices
        bot.watchlist = ["BTC-USD", "RELIANCE.NS", "NVDA"]
        bot.armed_tickers = {"BTC-USD", "RELIANCE.NS", "NVDA"}

        # Initialize synthetic analysis
        bot.analyses["BTC-USD"] = engine.analyze_ticker("BTC-USD", period="6mo", interval="1d")
        bot.analyses["RELIANCE.NS"] = engine.analyze_ticker("RELIANCE.NS", period="6mo", interval="1d")
        bot.analyses["NVDA"] = engine.analyze_ticker("NVDA", period="6mo", interval="1d")

        bot.live_prices["BTC-USD"] = 65000.0
        bot.base_prices["BTC-USD"] = 65000.0
        bot.price_series["BTC-USD"] = [{"time": "T-0", "price": 65000.0, "high": 65100.0, "low": 64900.0}]

        bot.live_prices["RELIANCE.NS"] = 2850.0
        bot.base_prices["RELIANCE.NS"] = 2850.0
        bot.price_series["RELIANCE.NS"] = [{"time": "T-0", "price": 2850.0, "high": 2860.0, "low": 2840.0}]

        bot.live_prices["NVDA"] = 120.0
        bot.base_prices["NVDA"] = 120.0
        bot.price_series["NVDA"] = [{"time": "T-0", "price": 120.0, "high": 121.0, "low": 119.0}]

        from src.data.provider_base import BaseMarketDataProvider, LiveQuote
        import pandas as pd

        class _MockSteppedFeed(BaseMarketDataProvider):
            def __init__(self, initial_prices):
                self._prices = dict(initial_prices)
                self._rng = np.random.default_rng(42)

            def fetch_historical_ohlcv(self, ticker, period="1y", interval="1d"):
                return pd.DataFrame()

            def get_quote(self, ticker, market_open=True):
                tk = ticker.upper()
                p = self._prices.get(tk, 100.0)
                step = float(self._rng.normal(0.0005, 0.0025))
                new_p = max(0.0001, p * (1.0 + step))
                self._prices[tk] = new_p
                now_iso = datetime.now(timezone.utc).isoformat()
                return LiveQuote(
                    ticker=tk,
                    last_price=round(new_p, 4),
                    bid_price=round(new_p * 0.9998, 4),
                    ask_price=round(new_p * 1.0002, 4),
                    volume=1000.0,
                    timestamp_utc=now_iso,
                    received_at_utc=now_iso,
                    is_delayed=False,
                    delay_minutes=0,
                    is_stale=False,
                    age_seconds=0.1,
                    latency_ms=1.0,
                    provider_name="MockSteppedFeed",
                    day_open=p,
                    day_high=max(p, new_p),
                    day_low=min(p, new_p),
                    prev_close=p,
                    status="LIVE",
                )

            def is_realtime(self) -> bool:
                return True

        bot.data_provider = _MockSteppedFeed({"BTC-USD": 65000.0, "RELIANCE.NS": 2850.0, "NVDA": 120.0})
        bot._initialized = True
        return bot

    def test_strict_price_freezing_outside_hours_over_50_ticks(self, test_environment):
        """Simulates 50 ticks outside market hours: Equities MUST freeze strictly while Crypto updates 50 times."""
        bot = test_environment
        bot.simulation_mode = False
        bot.enforce_market_hours = True

        # Mock calendar to return CLOSED for RELIANCE.NS & NVDA, OPEN for BTC-USD
        class MockCalendar:
            def get_session_info(self, ticker, simulation_mode=False):
                if ticker == "BTC-USD":
                    return MarketSessionInfo(
                        ticker=ticker, market_type="CRYPTO", state=MarketState.OPEN,
                        is_tradable=True, exchange_name="Crypto", local_timezone="UTC",
                        local_time_str="00:00:00 UTC", session_schedule="24/7",
                        reason="Open", next_state=MarketState.OPEN, next_state_time_utc="",
                        seconds_to_next_state=0, countdown_display="24/7", tick_frozen=False,
                    )
                else:
                    return MarketSessionInfo(
                        ticker=ticker, market_type="EQUITIES", state=MarketState.CLOSED,
                        is_tradable=simulation_mode, exchange_name="Closed Exch",
                        local_timezone="UTC", local_time_str="00:00:00",
                        session_schedule="Closed", reason="Exchange Closed",
                        next_state=MarketState.OPEN, next_state_time_utc="2026-04-16T09:15:00Z",
                        seconds_to_next_state=36000, countdown_display="Opens in 10h",
                        tick_frozen=not simulation_mode,
                    )

        bot.calendar = MockCalendar()

        initial_reliance_price = bot.live_prices["RELIANCE.NS"]
        initial_reliance_bars = len(bot.price_series["RELIANCE.NS"])
        initial_nvda_price = bot.live_prices["NVDA"]
        initial_nvda_bars = len(bot.price_series["NVDA"])
        initial_btc_price = bot.live_prices["BTC-USD"]
        initial_btc_bars = len(bot.price_series["BTC-USD"])

        # Execute 50 ticks
        btc_price_history = []
        for _ in range(50):
            bot.step_tick()
            btc_price_history.append(bot.live_prices["BTC-USD"])

        # Invariant 1: Closed equities prices strictly unchanged
        assert bot.live_prices["RELIANCE.NS"] == initial_reliance_price
        assert len(bot.price_series["RELIANCE.NS"]) == initial_reliance_bars
        assert bot.live_prices["NVDA"] == initial_nvda_price
        assert len(bot.price_series["NVDA"]) == initial_nvda_bars

        # Invariant 2: 24/7 Crypto price series grew by 50 points
        assert len(bot.price_series["BTC-USD"]) == min(60, initial_btc_bars + 50)
        # Price actually moved (standard deviation of steps > 0)
        assert np.std(btc_price_history) > 0.0

    def test_simulation_mode_toggle_resumes_and_refreezes_equities(self, test_environment):
        """Toggles simulation_mode on -> prices advance; toggles off -> prices freeze immediately."""
        bot = test_environment

        class MockCalendar:
            def get_session_info(self, ticker, simulation_mode=False):
                return MarketSessionInfo(
                    ticker=ticker, market_type="EQUITY", state=MarketState.CLOSED,
                    is_tradable=simulation_mode, exchange_name="Closed Exch",
                    local_timezone="UTC", local_time_str="00:00:00",
                    session_schedule="Closed", reason="Closed",
                    next_state=MarketState.OPEN, next_state_time_utc="",
                    seconds_to_next_state=3600, countdown_display="Opens in 1h",
                    tick_frozen=not simulation_mode,
                )

        bot.calendar = MockCalendar()

        # Step 1: simulation_mode = False -> frozen
        bot.simulation_mode = False
        bot.step_tick()
        assert bot.live_prices["NVDA"] == 120.0
        assert len(bot.price_series["NVDA"]) == 1

        # Step 2: toggle simulation_mode = True -> unfreezes
        bot.toggle_simulation_mode()
        assert bot.simulation_mode is True
        for _ in range(5):
            bot.step_tick()
        nvda_unfrozen_price = bot.live_prices["NVDA"]
        assert len(bot.price_series["NVDA"]) == 6  # 1 initial + 5 ticks

        # Step 3: toggle simulation_mode = False -> re-freezes
        bot.toggle_simulation_mode()
        assert bot.simulation_mode is False
        for _ in range(5):
            bot.step_tick()
        assert bot.live_prices["NVDA"] == nvda_unfrozen_price
        assert len(bot.price_series["NVDA"]) == 6  # Still 6, no new bars added!


# ============================================================================
# 3. PRE-MARKET ORDERS: SOFT CASH, CANCELLATION, IDEMPOTENCY & OPEN EXECUTION
# ============================================================================

class TestAdversarialPreMarketOrders:
    """Stress tests pre-market order mechanics, soft holds, idempotency, and open tick execution."""

    @pytest.fixture
    def isolated_broker(self, tmp_path):
        db_path = tmp_path / "test_adversarial_broker.db"
        broker = PaperBroker(account_id="CHALLENGER_ACCT_1", initial_capital=100000.0)
        broker.ledger = TradingLedgerDB(db_path=db_path)
        broker._ensure_account(100000.0)
        return broker

    def test_soft_cash_reservation_vs_ledger_balance(self, isolated_broker):
        """Verifies soft cash reservation reduces available cash but leaves ledger balance intact."""
        broker = isolated_broker

        # Initial baseline
        initial_summary = broker.get_account_summary()
        assert initial_summary["current_cash"] == 100000.0
        assert initial_summary["reserved_cash"] == 0.0
        assert initial_summary["available_cash"] == 100000.0

        # Queue buy order with $25,000 custom capital
        ord1 = broker.queue_pre_market_order(
            ticker="NVDA",
            direction="LONG",
            current_price=125.0,
            custom_allocated_capital=25000.0,
        )
        assert ord1["status"] == "PRE_MARKET_PENDING"
        assert ord1["allocated_capital"] == 25000.0

        # Verify summary invariants
        s1 = broker.get_account_summary()
        assert s1["current_cash"] == 100000.0, "Ledger balance must remain intact!"
        assert s1["reserved_cash"] == 25000.0, "Soft reservation must equal order capital"
        assert s1["available_cash"] == 75000.0, "Available cash must be deducted by reserved amount"

        # Verify database table state directly
        with broker.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT current_cash FROM accounts WHERE id = ?", (broker.account_id,))
            db_cash = cursor.fetchone()["current_cash"]
            assert db_cash == 100000.0, "SQLite accounts table must NOT be deducted before execution!"

    def test_cancellation_unreserves_cash_completely(self, isolated_broker):
        """Verifies order cancellation unreserves cash and restores available cash."""
        broker = isolated_broker
        ord1 = broker.queue_pre_market_order(
            ticker="NVDA", direction="LONG", current_price=125.0, custom_allocated_capital=30000.0
        )
        assert broker.get_account_summary()["available_cash"] == 70000.0

        # Cancel pending order
        cancelled = broker.cancel_pending_order(ord1["order_id"])
        assert cancelled is True

        # Invariants after cancellation
        s_after = broker.get_account_summary()
        assert s_after["current_cash"] == 100000.0
        assert s_after["reserved_cash"] == 0.0
        assert s_after["available_cash"] == 100000.0

        # Order status in DB is CANCELLED
        with broker.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, cancellation_reason FROM orders WHERE order_id = ?", (ord1["order_id"],))
            row = cursor.fetchone()
            assert row["status"] == "CANCELLED"
            assert row["cancellation_reason"] == "USER_CANCEL"

    def test_double_cancellation_and_idempotent_behavior(self, isolated_broker):
        """Verifies double cancellation returns False and preserves ledger invariants."""
        broker = isolated_broker
        ord1 = broker.queue_pre_market_order(
            ticker="RELIANCE.NS", direction="LONG", current_price=2800.0, custom_allocated_capital=20000.0
        )

        # First cancellation
        assert broker.cancel_pending_order(ord1["order_id"]) is True

        # Second cancellation (idempotent call)
        assert broker.cancel_pending_order(ord1["order_id"]) is False
        assert broker.cancel_pending_order(ord1["id"]) is False

        # Invariants intact
        s = broker.get_account_summary()
        assert s["current_cash"] == 100000.0
        assert s["reserved_cash"] == 0.0
        assert s["available_cash"] == 100000.0

    def test_concurrent_cancellation_race_condition(self, isolated_broker):
        """Spawns 10 concurrent threads attempting to cancel the same order simultaneously."""
        broker = isolated_broker
        ord1 = broker.queue_pre_market_order(
            ticker="NVDA", direction="LONG", current_price=125.0, custom_allocated_capital=15000.0
        )

        results = []
        def worker():
            res = broker.cancel_pending_order(ord1["order_id"])
            results.append(res)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly 1 thread must succeed, 9 must return False
        assert results.count(True) == 1
        assert results.count(False) == 9
        assert broker.get_account_summary()["reserved_cash"] == 0.0

    def test_exhaustion_of_available_cash_and_rejection(self, isolated_broker):
        """Queues orders until unreserved cash is exhausted; verifies proper rejection."""
        broker = isolated_broker

        # Queue 1: $60,000
        broker.queue_pre_market_order("NVDA", "LONG", 100.0, custom_allocated_capital=60000.0)
        # Queue 2: $39,970 (leaving $30 available)
        broker.queue_pre_market_order("AAPL", "LONG", 150.0, custom_allocated_capital=39970.0)

        assert broker.get_account_summary()["available_cash"] == 30.0

        # Attempt to queue order with < $50 available cash -> ValueError
        with pytest.raises(ValueError, match="Insufficient unreserved cash"):
            broker.queue_pre_market_order("MSFT", "LONG", 200.0, custom_allocated_capital=100.0)

    def test_cancelled_order_strictly_not_executed_on_open(self, isolated_broker):
        """Verifies cancelled orders are never executed when market opens."""
        broker = isolated_broker
        ord1 = broker.queue_pre_market_order("RELIANCE.NS", "LONG", 2800.0, custom_allocated_capital=10000.0)
        broker.cancel_pending_order(ord1["order_id"])

        # Trigger market open
        executed = broker.execute_pending_orders_for_ticker("RELIANCE.NS", opening_price=2820.0)
        assert len(executed) == 0
        assert len(broker.get_open_positions()) == 0
        assert broker.get_account_summary()["current_cash"] == 100000.0

    def test_open_tick_execution_queue_drain_and_ledger_settlement(self, isolated_broker):
        """Queues 3 orders for RELIANCE.NS, simulates market open, and verifies fill mechanics."""
        broker = isolated_broker

        ord1 = broker.queue_pre_market_order("RELIANCE.NS", "LONG", 2800.0, custom_allocated_capital=10000.0)
        ord2 = broker.queue_pre_market_order("RELIANCE.NS", "SHORT", 2800.0, custom_allocated_capital=15000.0)
        ord3 = broker.queue_pre_market_order("RELIANCE.NS", "LONG", 2800.0, custom_allocated_capital=5000.0)

        assert len(broker.get_pending_orders("RELIANCE.NS")) == 3
        assert broker.get_account_summary()["reserved_cash"] == 30000.0
        assert broker.get_account_summary()["available_cash"] == 70000.0
        assert broker.get_account_summary()["current_cash"] == 100000.0

        # Simulate Market Open @ INR 2850.00
        opening_price = 2850.0
        executed_positions = broker.execute_pending_orders_for_ticker("RELIANCE.NS", opening_price)

        # Invariant 1: Exactly 3 positions executed
        assert len(executed_positions) == 3
        assert executed_positions[0].direction == "LONG"
        assert executed_positions[1].direction == "SHORT"
        assert executed_positions[2].direction == "LONG"
        for p in executed_positions:
            assert p.entry_price == opening_price
            assert p.status == "OPEN"

        # Invariant 2: Pending order queue is now completely drained
        assert len(broker.get_pending_orders("RELIANCE.NS")) == 0

        # Invariant 3: SQLite orders table updated to FILLED
        with broker.ledger._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, status, fill_price, filled_at FROM orders WHERE ticker = 'RELIANCE.NS'")
            rows = cursor.fetchall()
            assert len(rows) == 3
            for r in rows:
                assert r["status"] == "FILLED"
                assert r["fill_price"] == opening_price
                assert r["filled_at"] is not None

        # Invariant 4: Soft cash reservation converted to actual ledger cash deduction
        summary = broker.get_account_summary()
        assert summary["reserved_cash"] == 0.0, "Reserved cash must return to 0 once filled"
        assert summary["current_cash"] == 70000.0, "Actual cash must be deducted by $30,000"
        assert summary["available_cash"] == 70000.0, "Available cash must equal current cash"
        assert summary["allocated_capital"] == 30000.0
        assert summary["open_positions_count"] == 3


# ============================================================================
# 4. CROSS-TIER INTEGRATION: LIVE BOT STEP TRANSITION FROM CLOSED TO OPEN
# ============================================================================

class TestLiveBotOpenTransitionIntegration:
    """Verifies that LiveBotController.step_tick() automatically executes pending orders on session open."""

    def test_live_bot_auto_executes_pending_order_on_session_open(self, tmp_path):
        db_path = tmp_path / "test_bot_open.db"
        broker = PaperBroker(account_id="CHALLENGER_BOT_OPEN", initial_capital=100000.0)
        broker.ledger = TradingLedgerDB(db_path=db_path)
        broker._ensure_account(100000.0)

        engine = MarketPredictionEngine()
        bot = LiveBotController(engine=engine, broker=broker)

        bot.watchlist = ["RELIANCE.NS"]
        bot.armed_tickers = {"RELIANCE.NS"}
        bot.analyses["RELIANCE.NS"] = engine.analyze_ticker("RELIANCE.NS", period="6mo", interval="1d")
        bot.live_prices["RELIANCE.NS"] = 2800.0
        bot.base_prices["RELIANCE.NS"] = 2800.0
        bot.price_series["RELIANCE.NS"] = [{"time": "T-0", "price": 2800.0, "high": 2810.0, "low": 2790.0}]

        from src.data.provider_base import BaseMarketDataProvider, LiveQuote
        class _MockRelianceOpenFeed(BaseMarketDataProvider):
            def get_quote(self, ticker, market_open=True, **kwargs):
                now_iso = datetime.now(timezone.utc).isoformat()
                return LiveQuote(
                    ticker=ticker.upper(),
                    last_price=2810.0,
                    bid_price=2809.5,
                    ask_price=2810.5,
                    timestamp_utc=now_iso,
                    received_at_utc=now_iso,
                    is_delayed=False,
                    is_stale=False,
                    provider_name="MockRelianceOpenFeed",
                    day_open=2805.0,
                    day_high=2815.0,
                    day_low=2800.0,
                    prev_close=2800.0,
                    status="LIVE",
                )

        bot.data_provider = _MockRelianceOpenFeed()
        bot._initialized = True

        # 1. Queue pre-market order while market is closed with explicit TP/SL
        queued = broker.queue_pre_market_order(
            "RELIANCE.NS", "LONG", 2800.0,
            target_price=3100.0, stop_price=2500.0,
            custom_allocated_capital=12000.0,
        )
        assert queued["status"] == "PRE_MARKET_PENDING"
        assert len(broker.get_pending_orders("RELIANCE.NS")) == 1

        # 2. Tick while CLOSED: Order stays pending, price frozen
        class ControlledCalendar:
            def __init__(self):
                self.is_market_open = False

            def get_session_info(self, ticker, simulation_mode=False):
                state = MarketState.OPEN if self.is_market_open else MarketState.CLOSED
                return MarketSessionInfo(
                    ticker=ticker, market_type="NSE_CASH", state=state,
                    is_tradable=(state == MarketState.OPEN or simulation_mode),
                    exchange_name="NSE Mumbai", local_timezone="Asia/Kolkata",
                    local_time_str="09:14:59 IST", session_schedule="09:15-15:30",
                    reason="Pre-Open" if not self.is_market_open else "Live Trading",
                    next_state=MarketState.OPEN if not self.is_market_open else MarketState.POST_MARKET,
                    next_state_time_utc="", seconds_to_next_state=1, countdown_display="Opens in 1s",
                    tick_frozen=(state != MarketState.OPEN and not simulation_mode),
                )

        ctrl_cal = ControlledCalendar()
        bot.calendar = ctrl_cal

        # Tick 1: closed -> price frozen, pending order remains
        bot.step_tick()
        assert len(broker.get_pending_orders("RELIANCE.NS")) == 1
        assert bot.live_prices["RELIANCE.NS"] == 2800.0

        # 3. Market Opens!
        ctrl_cal.is_market_open = True

        # Tick 2: open transition -> order executes automatically!
        bot.step_tick()

        # Invariants:
        assert len(broker.get_pending_orders("RELIANCE.NS")) == 0, "Queue must be drained upon open"
        positions = broker.get_open_positions()
        assert len(positions) == 1, "Position must be created"
        assert positions[0].ticker == "RELIANCE.NS"
        assert positions[0].allocated_capital == 12000.0
        assert broker.get_account_summary()["current_cash"] == 88000.0
        assert broker.get_account_summary()["reserved_cash"] == 0.0

    def test_omitted_target_price_zero_barrier_vulnerability(self, tmp_path):
        """Vulnerability probe: if target_price is omitted (default None -> 0.0), triple-barrier logic immediately closes the position."""
        db_path = tmp_path / "test_zero_barrier.db"
        broker = PaperBroker(account_id="CHALLENGER_ZERO_BARRIER", initial_capital=100000.0)
        broker.ledger = TradingLedgerDB(db_path=db_path)
        broker._ensure_account(100000.0)

        # Queue order with target_price=None (default)
        ord1 = broker.queue_pre_market_order(
            ticker="NVDA", direction="LONG", current_price=100.0,
            target_price=None, stop_price=None, custom_allocated_capital=10000.0
        )
        assert ord1["target_price"] == 0.0
        assert ord1["stop_price"] == 0.0

        # Execute at open tick @ $105.00
        positions = broker.execute_pending_orders_for_ticker("NVDA", 105.0)
        assert len(positions) == 1
        pos = positions[0]
        assert pos.target_price == 0.0

        # Audit position against market price: because target_price == 0.0, 105.0 >= 0.0 immediately triggers PROFIT_TARGET!
        still_open, closed = broker.update_and_audit_positions({"NVDA": 105.0})
        assert len(still_open) == 0, "Position was immediately closed due to target_price=0.0"
        assert len(closed) == 1
        assert closed[0].exit_reason == "PROFIT_TARGET"
        # Note: While server.py calculates pt_p/sl_p before calling broker, direct broker API calls with None trigger this edge case.

