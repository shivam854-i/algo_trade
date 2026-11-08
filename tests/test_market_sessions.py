"""Institutional Verification Test Suite: Physical Exchange Sessions, Calendars & State Machine.

Authoritative Specification:
- PROJECT.md § Architecture (Physical Market Session & Order Execution Engine)
- PROJECT.md § Milestones (M2 & M4)
- ORIGINAL_REQUEST.md § Requirements (R2: Physical Market Timings & Exchange Session Enforcement)

Tests:
1. Multi-asset jurisdiction detection (NSE, NYSE, COMEX Commodities, Forex, Crypto).
2. Physical exchange session schedules (Indian Equities 09:15-15:30 IST, US Equities 09:30-16:00 ET,
   COMEX Gold 23/5, Forex 24/5, Crypto 24/7/365).
3. 6-state exchange state machine (OPEN, PRE_MARKET, POST_MARKET, CLOSED, WEEKEND, HOLIDAY).
4. Second-precision countdown computation and UTC target boundary timestamps.
5. Exact boundary second transitions (e.g., 09:14:59 vs 09:15:00 vs 15:30:00 vs 15:30:01).
6. Automatic Daylight Saving Time handling (EDT UTC-4 in summer vs EST UTC-5 in winter).
7. Statutory holiday calendar handling for NSE and NYSE (2026/2027 schedules).
8. Weekend roll-over to Monday (or Tuesday if Monday is a holiday).
9. Strict closed-market tick freezing and decoupled simulation mode override.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest

from src.execution.market_sessions import (
    MarketCalendarManager,
    MarketSessionInfo,
    MarketState,
)


@pytest.fixture
def calendar() -> MarketCalendarManager:
    """Provides a fresh instance of MarketCalendarManager for each test."""
    return MarketCalendarManager()


class TestMarketTypeDetection:
    """Verifies symbol classification across Indian Equities, US Equities, Commodities, Forex, and Crypto."""

    def test_indian_equities_detection(self, calendar: MarketCalendarManager):
        assert calendar.detect_market_type("RELIANCE.NS") == "NSE_CASH"
        assert calendar.detect_market_type("TCS.BO") == "NSE_CASH"
        assert calendar.detect_market_type("^NSEI") == "NSE_CASH"
        assert calendar.detect_market_type("^BSESN") == "NSE_CASH"
        assert calendar.detect_market_type("infy.ns") == "NSE_CASH"

    def test_us_equities_detection(self, calendar: MarketCalendarManager):
        assert calendar.detect_market_type("NVDA") == "US_EQUITIES"
        assert calendar.detect_market_type("AAPL") == "US_EQUITIES"
        assert calendar.detect_market_type("TSLA") == "US_EQUITIES"
        assert calendar.detect_market_type("msft") == "US_EQUITIES"
        assert calendar.detect_market_type("AMD") == "US_EQUITIES"

    def test_commodities_detection(self, calendar: MarketCalendarManager):
        assert calendar.detect_market_type("GC=F") == "COMMODITY"
        assert calendar.detect_market_type("SI=F") == "COMMODITY"
        assert calendar.detect_market_type("CL=F") == "COMMODITY"
        assert calendar.detect_market_type("GLD") == "COMMODITY"
        assert calendar.detect_market_type("slv") == "COMMODITY"
        assert calendar.detect_market_type("USO") == "COMMODITY"

    def test_forex_detection(self, calendar: MarketCalendarManager):
        assert calendar.detect_market_type("EURUSD=X") == "FOREX"
        assert calendar.detect_market_type("GBPUSD=X") == "FOREX"
        assert calendar.detect_market_type("USDJPY=X") == "FOREX"
        assert calendar.detect_market_type("DX-Y.NYB") == "FOREX"
        assert calendar.detect_market_type("uup") == "FOREX"

    def test_crypto_detection(self, calendar: MarketCalendarManager):
        assert calendar.detect_market_type("BTC-USD") == "CRYPTO"
        assert calendar.detect_market_type("ETH-USD") == "CRYPTO"
        assert calendar.detect_market_type("SOL-USDT") == "CRYPTO"
        assert calendar.detect_market_type("BTC") == "CRYPTO"
        assert calendar.detect_market_type("eth") == "CRYPTO"
        assert calendar.detect_market_type("DOGE") == "CRYPTO"


class TestNSEMarketSchedule:
    """Verifies Indian Equities (NSE/BSE) trading phases, timezones, and statutory calendars."""

    def test_overnight_closed_state(self, calendar: MarketCalendarManager):
        # Wednesday 04:30 IST (23:00 UTC previous day)
        now_utc = datetime(2026, 6, 16, 23, 0, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("RELIANCE.NS", now_utc=now_utc)

        assert info.state == MarketState.CLOSED
        assert not info.is_open
        assert not info.is_tradable
        assert info.tick_frozen
        assert info.next_state == MarketState.PRE_MARKET
        assert info.exchange_name == "NSE Mumbai"
        assert info.local_timezone == "Asia/Kolkata"
        assert "04:30:00 IST" in info.local_time_str

    def test_pre_market_session(self, calendar: MarketCalendarManager):
        # Wednesday 09:05:00 IST (03:35:00 UTC)
        now_utc = datetime(2026, 6, 17, 3, 35, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("RELIANCE.NS", now_utc=now_utc)

        assert info.state == MarketState.PRE_MARKET
        assert not info.is_open
        assert not info.is_tradable
        assert info.tick_frozen
        assert info.next_state == MarketState.OPEN
        assert "09:05:00 IST" in info.local_time_str
        # Target should be 09:15:00 IST today
        target_ist = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_ist)
        assert target_ist.time() == time(9, 15)
        assert info.seconds_to_next_state == 10 * 60  # 10 minutes

    def test_regular_trading_hours_open(self, calendar: MarketCalendarManager):
        # Wednesday 11:30:00 IST (06:00:00 UTC)
        now_utc = datetime(2026, 6, 17, 6, 0, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("RELIANCE.NS", now_utc=now_utc)

        assert info.state == MarketState.OPEN
        assert info.is_open
        assert info.is_tradable
        assert not info.tick_frozen
        assert info.next_state == MarketState.POST_MARKET
        # Target should be 15:30:00 IST today (4 hours = 14400 seconds)
        target_ist = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_ist)
        assert target_ist.time() == time(15, 30)
        assert info.seconds_to_next_state == 4 * 3600

    def test_post_market_session(self, calendar: MarketCalendarManager):
        # Wednesday 15:45:00 IST (10:15:00 UTC)
        now_utc = datetime(2026, 6, 17, 10, 15, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("RELIANCE.NS", now_utc=now_utc)

        assert info.state == MarketState.POST_MARKET
        assert not info.is_open
        assert not info.is_tradable
        assert info.tick_frozen
        assert info.next_state == MarketState.CLOSED
        # Target should be 16:00:00 IST today
        target_ist = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_ist)
        assert target_ist.time() == time(16, 0)
        assert info.seconds_to_next_state == 15 * 60

    def test_after_hours_closed_session(self, calendar: MarketCalendarManager):
        # Wednesday 18:00:00 IST (12:30:00 UTC)
        now_utc = datetime(2026, 6, 17, 12, 30, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("RELIANCE.NS", now_utc=now_utc)

        assert info.state == MarketState.CLOSED
        assert not info.is_open
        assert not info.is_tradable
        assert info.tick_frozen
        assert info.next_state == MarketState.OPEN
        # Next open should be Thursday 09:15:00 IST
        target_ist = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_ist)
        assert target_ist.date() == date(2026, 6, 18)
        assert target_ist.time() == time(9, 15)

    def test_weekend_transition(self, calendar: MarketCalendarManager):
        # Saturday 14:00:00 IST (08:30:00 UTC)
        now_utc = datetime(2026, 6, 20, 8, 30, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("RELIANCE.NS", now_utc=now_utc)

        assert info.state == MarketState.WEEKEND
        assert not info.is_open
        assert not info.is_tradable
        assert info.tick_frozen
        assert info.next_state == MarketState.OPEN
        # Target should be Monday 2026-06-22 09:15:00 IST
        target_ist = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_ist)
        assert target_ist.date() == date(2026, 6, 22)
        assert target_ist.time() == time(9, 15)

    def test_statutory_holiday_republic_day(self, calendar: MarketCalendarManager):
        # Monday 2026-01-26 (Republic Day in India) at 11:00:00 IST (05:30:00 UTC)
        now_utc = datetime(2026, 1, 26, 5, 30, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("RELIANCE.NS", now_utc=now_utc)

        assert info.state == MarketState.HOLIDAY
        assert not info.is_open
        assert not info.is_tradable
        assert info.tick_frozen
        assert info.holiday_name == "Republic Day"
        assert "Republic Day" in info.reason
        # Target should be Tuesday 2026-01-27 09:15:00 IST
        target_ist = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_ist)
        assert target_ist.date() == date(2026, 1, 27)
        assert target_ist.time() == time(9, 15)

    def test_statutory_holiday_independence_day_on_saturday(self, calendar: MarketCalendarManager):
        # 2026-08-15 is a Saturday. On a Saturday, weekend takes precedence in weekend check
        now_utc = datetime(2026, 8, 15, 6, 0, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("RELIANCE.NS", now_utc=now_utc)
        assert info.state == MarketState.WEEKEND
        target_ist = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_ist)
        assert target_ist.date() == date(2026, 8, 17)
        assert target_ist.time() == time(9, 15)

    def test_exact_boundary_seconds_nse(self, calendar: MarketCalendarManager):
        # Wednesday 2026-06-17
        # 1. 09:14:59 IST -> PRE_MARKET
        t_pre = datetime(2026, 6, 17, 3, 44, 59, tzinfo=timezone.utc)
        assert calendar.get_session_info("RELIANCE.NS", now_utc=t_pre).state == MarketState.PRE_MARKET

        # 2. Exactly 09:15:00 IST -> OPEN
        t_open = datetime(2026, 6, 17, 3, 45, 0, tzinfo=timezone.utc)
        s_open = calendar.get_session_info("RELIANCE.NS", now_utc=t_open)
        assert s_open.state == MarketState.OPEN
        assert s_open.is_open

        # 3. Exactly 15:30:00 IST -> OPEN (inclusive)
        t_close_inc = datetime(2026, 6, 17, 10, 0, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("RELIANCE.NS", now_utc=t_close_inc).state == MarketState.OPEN

        # 4. 15:30:01 IST -> POST_MARKET
        t_post = datetime(2026, 6, 17, 10, 0, 1, tzinfo=timezone.utc)
        assert calendar.get_session_info("RELIANCE.NS", now_utc=t_post).state == MarketState.POST_MARKET

        # 5. Exactly 16:00:00 IST -> POST_MARKET (inclusive)
        t_post_inc = datetime(2026, 6, 17, 10, 30, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("RELIANCE.NS", now_utc=t_post_inc).state == MarketState.POST_MARKET

        # 6. 16:00:01 IST -> CLOSED
        t_closed = datetime(2026, 6, 17, 10, 30, 1, tzinfo=timezone.utc)
        assert calendar.get_session_info("RELIANCE.NS", now_utc=t_closed).state == MarketState.CLOSED


@pytest.mark.disabled_market
class TestNYSEMarketSchedule:
    """Verifies US Equities (NYSE/NASDAQ) trading phases, timezones, DST, and statutory calendars."""

    def test_overnight_closed_session(self, calendar: MarketCalendarManager):
        # Wednesday 02:30 ET
        # During summer (EDT = UTC-4): 02:30 EDT is 06:30 UTC
        now_utc = datetime(2026, 6, 17, 6, 30, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("NVDA", now_utc=now_utc)

        assert info.state == MarketState.CLOSED
        assert not info.is_open
        assert not info.is_tradable
        assert info.tick_frozen
        assert info.next_state == MarketState.PRE_MARKET
        assert info.exchange_name == "NYSE / NASDAQ"
        assert info.local_timezone == "America/New_York"
        assert "02:30:00 EDT" in info.local_time_str
        target_et = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_et)
        assert target_et.time() == time(4, 0)

    def test_pre_market_session(self, calendar: MarketCalendarManager):
        # Wednesday 07:00 ET (11:00 UTC in summer)
        now_utc = datetime(2026, 6, 17, 11, 0, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("NVDA", now_utc=now_utc)

        assert info.state == MarketState.PRE_MARKET
        assert not info.is_open
        assert not info.is_tradable
        assert info.tick_frozen
        assert info.next_state == MarketState.OPEN
        assert "07:00:00 EDT" in info.local_time_str
        target_et = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_et)
        assert target_et.time() == time(9, 30)
        assert info.seconds_to_next_state == int(2.5 * 3600)

    def test_regular_trading_hours_open(self, calendar: MarketCalendarManager):
        # Wednesday 14:00 ET (18:00 UTC in summer)
        now_utc = datetime(2026, 6, 17, 18, 0, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("NVDA", now_utc=now_utc)

        assert info.state == MarketState.OPEN
        assert info.is_open
        assert info.is_tradable
        assert not info.tick_frozen
        assert info.next_state == MarketState.POST_MARKET
        target_et = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_et)
        assert target_et.time() == time(16, 0)
        assert info.seconds_to_next_state == 2 * 3600

    def test_after_hours_session(self, calendar: MarketCalendarManager):
        # Wednesday 17:30 ET (21:30 UTC in summer)
        now_utc = datetime(2026, 6, 17, 21, 30, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("NVDA", now_utc=now_utc)

        assert info.state == MarketState.POST_MARKET
        assert not info.is_open
        assert not info.is_tradable
        assert info.tick_frozen
        assert info.next_state == MarketState.CLOSED
        target_et = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_et)
        assert target_et.time() == time(20, 0)
        assert info.seconds_to_next_state == int(2.5 * 3600)

    def test_statutory_holiday_martin_luther_king_day(self, calendar: MarketCalendarManager):
        # Monday 2026-01-19 (MLK Day) at 12:00 ET (17:00 UTC in winter)
        now_utc = datetime(2026, 1, 19, 17, 0, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("AAPL", now_utc=now_utc)

        assert info.state == MarketState.HOLIDAY
        assert not info.is_open
        assert not info.is_tradable
        assert info.tick_frozen
        assert info.holiday_name == "Martin Luther King Jr. Day"
        target_et = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_et)
        assert target_et.date() == date(2026, 1, 20)
        assert target_et.time() == time(9, 30)

    def test_statutory_holiday_christmas_day(self, calendar: MarketCalendarManager):
        # Friday 2026-12-25 (Christmas Day) at 11:00 ET (16:00 UTC)
        now_utc = datetime(2026, 12, 25, 16, 0, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("AAPL", now_utc=now_utc)

        assert info.state == MarketState.HOLIDAY
        assert info.holiday_name == "Christmas Day"
        target_et = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_et)
        # Next business day is Monday 2026-12-28
        assert target_et.date() == date(2026, 12, 28)
        assert target_et.time() == time(9, 30)

    def test_exact_boundary_seconds_nyse(self, calendar: MarketCalendarManager):
        # Wednesday 2026-06-17 (EDT = UTC-4)
        # 1. 09:29:59 ET (13:29:59 UTC) -> PRE_MARKET
        t_pre = datetime(2026, 6, 17, 13, 29, 59, tzinfo=timezone.utc)
        assert calendar.get_session_info("NVDA", now_utc=t_pre).state == MarketState.PRE_MARKET

        # 2. Exactly 09:30:00 ET (13:30:00 UTC) -> OPEN
        t_open = datetime(2026, 6, 17, 13, 30, 0, tzinfo=timezone.utc)
        s_open = calendar.get_session_info("NVDA", now_utc=t_open)
        assert s_open.state == MarketState.OPEN
        assert s_open.is_open

        # 3. Exactly 16:00:00 ET (20:00:00 UTC) -> OPEN (inclusive)
        t_close_inc = datetime(2026, 6, 17, 20, 0, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("NVDA", now_utc=t_close_inc).state == MarketState.OPEN

        # 4. 16:00:01 ET (20:00:01 UTC) -> POST_MARKET
        t_post = datetime(2026, 6, 17, 20, 0, 1, tzinfo=timezone.utc)
        assert calendar.get_session_info("NVDA", now_utc=t_post).state == MarketState.POST_MARKET

        # 5. Exactly 20:00:00 ET (00:00:00 UTC next day) -> POST_MARKET (inclusive)
        t_post_inc = datetime(2026, 6, 18, 0, 0, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("NVDA", now_utc=t_post_inc).state == MarketState.POST_MARKET

        # 6. 20:00:01 ET (00:00:01 UTC next day) -> CLOSED
        t_closed = datetime(2026, 6, 18, 0, 0, 1, tzinfo=timezone.utc)
        assert calendar.get_session_info("NVDA", now_utc=t_closed).state == MarketState.CLOSED

    def test_daylight_saving_time_shift(self, calendar: MarketCalendarManager):
        """Verifies US Market Open is 13:30 UTC in Summer (EDT) and 14:30 UTC in Winter (EST)."""
        # Summer (July 15, 2026): EDT (UTC-4)
        summer_open_utc = datetime(2026, 7, 15, 13, 30, 0, tzinfo=timezone.utc)
        summer_sess = calendar.get_session_info("AAPL", now_utc=summer_open_utc)
        assert summer_sess.state == MarketState.OPEN
        assert "09:30:00 EDT" in summer_sess.local_time_str

        # 1 minute before open in summer: 13:29:00 UTC is 09:29:00 EDT (PRE_MARKET)
        summer_pre_utc = datetime(2026, 7, 15, 13, 29, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("AAPL", now_utc=summer_pre_utc).state == MarketState.PRE_MARKET

        # Winter (January 15, 2026): EST (UTC-5)
        winter_open_utc = datetime(2026, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        winter_sess = calendar.get_session_info("AAPL", now_utc=winter_open_utc)
        assert winter_sess.state == MarketState.OPEN
        assert "09:30:00 EST" in winter_sess.local_time_str

        # 1 minute before open in winter: 14:29:00 UTC is 09:29:00 EST (PRE_MARKET)
        winter_pre_utc = datetime(2026, 1, 15, 14, 29, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("AAPL", now_utc=winter_pre_utc).state == MarketState.PRE_MARKET


@pytest.mark.disabled_market
class TestCommoditiesAndForexSchedules:
    """Verifies COMEX Gold (GC=F) 23/5 and Forex 24/5 schedules."""

    def test_comex_gold_sunday_pre_open(self, calendar: MarketCalendarManager):
        # Sunday 17:30 ET (21:30 UTC in summer)
        sunday_pre_utc = datetime(2026, 6, 21, 21, 30, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("GC=F", now_utc=sunday_pre_utc)

        assert info.state == MarketState.PRE_MARKET
        assert not info.is_open
        assert not info.is_tradable
        assert info.tick_frozen
        assert info.next_state == MarketState.OPEN
        target_et = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_et)
        assert target_et.time() == time(18, 0)
        assert info.seconds_to_next_state == 30 * 60

    def test_comex_gold_active_session(self, calendar: MarketCalendarManager):
        # Tuesday 10:00 ET (14:00 UTC in summer)
        tue_utc = datetime(2026, 6, 16, 14, 0, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("GC=F", now_utc=tue_utc)

        assert info.state == MarketState.OPEN
        assert info.is_open
        assert info.is_tradable
        assert not info.tick_frozen
        assert info.next_state == MarketState.CLOSED
        target_et = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_et)
        assert target_et.time() == time(17, 0)  # Daily maintenance halt

    def test_comex_gold_daily_maintenance_pause(self, calendar: MarketCalendarManager):
        # Tuesday 17:30 ET (21:30 UTC in summer)
        halt_utc = datetime(2026, 6, 16, 21, 30, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("GC=F", now_utc=halt_utc)

        assert info.state == MarketState.CLOSED
        assert not info.is_open
        assert not info.is_tradable
        assert info.tick_frozen
        assert info.next_state == MarketState.OPEN
        target_et = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_et)
        assert target_et.time() == time(18, 0)
        assert info.seconds_to_next_state == 30 * 60

    def test_comex_gold_weekend_shutdown(self, calendar: MarketCalendarManager):
        # Friday 19:00 ET (23:00 UTC in summer)
        fri_closed_utc = datetime(2026, 6, 19, 23, 0, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("GC=F", now_utc=fri_closed_utc)

        assert info.state == MarketState.WEEKEND
        assert not info.is_open
        assert not info.is_tradable
        assert info.tick_frozen
        assert info.next_state == MarketState.OPEN
        target_et = datetime.fromisoformat(info.next_state_time_utc).astimezone(calendar.tz_et)
        assert target_et.date() == date(2026, 6, 21)  # Sunday
        assert target_et.time() == time(18, 0)

    def test_forex_24_5_open_and_weekend(self, calendar: MarketCalendarManager):
        # Tuesday 12:00 ET -> OPEN
        tue_utc = datetime(2026, 6, 16, 16, 0, 0, tzinfo=timezone.utc)
        fx_open = calendar.get_session_info("EURUSD=X", now_utc=tue_utc)
        assert fx_open.state == MarketState.OPEN
        assert fx_open.is_tradable

        # Saturday 12:00 ET -> WEEKEND
        sat_utc = datetime(2026, 6, 20, 16, 0, 0, tzinfo=timezone.utc)
        fx_weekend = calendar.get_session_info("EURUSD=X", now_utc=sat_utc)
        assert fx_weekend.state == MarketState.WEEKEND
        assert not fx_weekend.is_tradable
        target_et = datetime.fromisoformat(fx_weekend.next_state_time_utc).astimezone(calendar.tz_et)
        assert target_et.date() == date(2026, 6, 21)  # Sunday
        assert target_et.time() == time(17, 0)


@pytest.mark.disabled_market
class TestCryptoContinuousSchedule:
    """Verifies Cryptocurrencies continuous 24/7/365 state machine invariant."""

    @pytest.mark.parametrize(
        "dt_utc",
        [
            datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),     # New Year's Day
            datetime(2026, 6, 20, 3, 30, 0, tzinfo=timezone.utc),    # Saturday middle of night
            datetime(2026, 6, 21, 14, 0, 0, tzinfo=timezone.utc),    # Sunday afternoon
            datetime(2026, 12, 25, 12, 0, 0, tzinfo=timezone.utc),   # Christmas Day
            datetime(2028, 2, 29, 23, 59, 59, tzinfo=timezone.utc),  # Leap Day
        ],
    )
    def test_crypto_is_always_open(self, calendar: MarketCalendarManager, dt_utc: datetime):
        for ticker in ["BTC-USD", "ETH-USD", "SOL-USDT", "DOGE"]:
            info = calendar.get_session_info(ticker, now_utc=dt_utc)
            assert info.state == MarketState.OPEN
            assert info.is_open
            assert info.is_tradable
            assert not info.tick_frozen
            assert info.countdown_display == "Continuous 24/7"
            assert info.seconds_to_next_state == 0
            assert info.holiday_name is None


class TestSimulationModeDecoupling:
    """Verifies that enabling simulation mode decouples order tradability & ticks from physical status."""

    def test_closed_nse_stock_in_simulation_mode(self, calendar: MarketCalendarManager):
        # Sunday 12:00 UTC (Market physically closed / weekend)
        now_utc = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)

        # 1. Normal mode: physically closed, tick frozen, not tradable
        normal_sess = calendar.get_session_info("RELIANCE.NS", now_utc=now_utc, simulation_mode=False)
        assert normal_sess.state == MarketState.WEEKEND
        assert not normal_sess.is_tradable
        assert normal_sess.tick_frozen
        assert "[SIMULATION MODE OVERRIDE]" not in normal_sess.reason

        # 2. Simulation mode: state badge stays WEEKEND, but is_tradable=True and tick_frozen=False
        sim_sess = calendar.get_session_info("RELIANCE.NS", now_utc=now_utc, simulation_mode=True)
        assert sim_sess.state == MarketState.WEEKEND  # Physical badge preserved!
        assert sim_sess.is_tradable                   # Synthetic trades allowed!
        assert not sim_sess.tick_frozen               # Price ticks update!
        assert "[SIMULATION MODE OVERRIDE]" in sim_sess.reason

    @pytest.mark.disabled_market
    def test_holiday_nyse_stock_in_simulation_mode(self, calendar: MarketCalendarManager):
        # Christmas Day 2026-12-25
        now_utc = datetime(2026, 12, 25, 15, 0, 0, tzinfo=timezone.utc)
        sim_sess = calendar.get_session_info("NVDA", now_utc=now_utc, simulation_mode=True)

        assert sim_sess.state == MarketState.HOLIDAY
        assert sim_sess.holiday_name == "Christmas Day"
        assert sim_sess.is_tradable
        assert not sim_sess.tick_frozen
        assert "[SIMULATION MODE OVERRIDE]" in sim_sess.reason


class TestTelemetrySerializationAndProperties:
    """Verifies serialization contracts for REST API responses."""

    def test_market_session_info_to_dict(self, calendar: MarketCalendarManager):
        now_utc = datetime(2026, 6, 17, 6, 0, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("RELIANCE.NS", now_utc=now_utc)
        d = info.to_dict()

        assert isinstance(d, dict)
        assert d["ticker"] == "RELIANCE.NS"
        assert d["state"] == "OPEN"
        assert d["next_state"] == "POST_MARKET"
        assert d["is_open"] is True
        assert d["seconds_to_next"] == 4 * 3600
        assert d["exchange_tz"] == "Asia/Kolkata"
        assert "11:30:00 IST" in d["local_time"]
        assert "target_time_utc" in d
        assert d["tick_frozen"] is False
