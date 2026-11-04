"""Physical Exchange Session Engine & Multi-Asset Trading Calendar.

Implements strict physical market timing schedules across:
- Indian Equities (NSE/BSE: 09:15–15:30 IST, Asia/Kolkata) with 2026/2027 statutory holiday tables.
- US Equities (NYSE/NASDAQ: 09:30–16:00 EST/EDT, America/New_York) with automatic DST transitions
  and US statutory holiday tables.
- Commodities (CME COMEX Gold GC=F, SI=F, CL=F): Sunday 18:00 to Friday 17:00 ET with daily 17:00–18:00 ET pause.
- Crypto (24/7/365 Continuous).
- Forex (24/5 ECN: Sunday 17:00 to Friday 17:00 ET).

Calculates second-by-second countdowns to next market open/close boundaries with UTC target timestamps.
"""

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


class MarketState(str, Enum):
    OPEN = "OPEN"               # Regular Trading Hours (RTH). Live ticks stream, orders execute immediately.
    PRE_MARKET = "PRE_MARKET"   # Pre-opening order collection / price discovery. Orders queue as PRE_MARKET_PENDING.
    POST_MARKET = "POST_MARKET" # Post-closing / after-hours phase. Orders queue as PRE_MARKET_PENDING.
    CLOSED = "CLOSED"           # Normal overnight off-hours. Live ticks frozen. Orders queue as PRE_MARKET_PENDING.
    WEEKEND = "WEEKEND"         # Saturday / Sunday non-trading days. Ticks frozen.
    HOLIDAY = "HOLIDAY"         # Official exchange statutory holiday. Ticks frozen.


@dataclass
class MarketSessionInfo:
    ticker: str
    market_type: str            # "NSE_CASH" | "US_EQUITIES" | "COMMODITY" | "CRYPTO" | "FOREX"
    state: MarketState          # OPEN, PRE_MARKET, POST_MARKET, CLOSED, WEEKEND, HOLIDAY
    is_tradable: bool           # True if state == OPEN or simulation_mode == True
    exchange_name: str          # "NSE Mumbai", "NYSE / NASDAQ", "CME Globex", "Crypto Spot"
    local_timezone: str         # "Asia/Kolkata", "America/New_York", "UTC"
    local_time_str: str         # e.g., "14:22:15 IST"
    session_schedule: str       # e.g., "09:15–15:30 IST"
    reason: str                 # Descriptive explanation
    next_state: MarketState     # Next scheduled state transition
    next_state_time_utc: str    # ISO 8601 UTC timestamp of boundary (e.g. "2026-11-03T03:45:00Z")
    seconds_to_next_state: int  # Integer seconds remaining until transition
    countdown_display: str      # Humanized string: "Opens in 02h 14m 35s" or "Closes in 01h 05m 12s"
    tick_frozen: bool           # True when ticks must be frozen
    holiday_name: Optional[str] = None  # Non-null if today is an exchange holiday

    @property
    def is_open(self) -> bool:
        return self.state == MarketState.OPEN

    @property
    def seconds_to_next(self) -> int:
        return self.seconds_to_next_state

    @property
    def target_time_utc(self) -> str:
        return self.next_state_time_utc

    @property
    def exchange_tz(self) -> str:
        return self.local_timezone

    @property
    def local_time(self) -> str:
        return self.local_time_str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value if isinstance(self.state, MarketState) else str(self.state)
        d["next_state"] = self.next_state.value if isinstance(self.next_state, MarketState) else str(self.next_state)
        d["is_open"] = self.is_open
        d["seconds_to_next"] = self.seconds_to_next
        d["target_time_utc"] = self.target_time_utc
        d["exchange_tz"] = self.exchange_tz
        d["local_time"] = self.local_time
        return d


class MarketCalendarManager:
    """Institutional exchange schedule and statutory holiday calendar manager."""

    def __init__(self):
        self.tz_ist = ZoneInfo("Asia/Kolkata")
        self.tz_et = ZoneInfo("America/New_York")
        self.tz_utc = timezone.utc

        # NSE Statutory Trading Holidays (2026 & 2027)
        self.nse_holidays: Dict[date, str] = {
            # 2026
            date(2026, 1, 26): "Republic Day",
            date(2026, 3, 6): "Mahashivratri",
            date(2026, 3, 25): "Holi",
            date(2026, 4, 3): "Good Friday",
            date(2026, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
            date(2026, 4, 21): "Ram Navami",
            date(2026, 5, 1): "Maharashtra Day",
            date(2026, 5, 27): "Bakri Id / Eid-ul-Adha",
            date(2026, 6, 26): "Muharram",
            date(2026, 8, 15): "Independence Day",
            date(2026, 10, 2): "Mahatma Gandhi Jayanti",
            date(2026, 10, 20): "Dussehra",
            date(2026, 11, 8): "Diwali Laxmi Pujan (Special Muhurat Trading Only)",
            date(2026, 11, 10): "Diwali Balipratipada",
            date(2026, 11, 24): "Guru Nanak Jayanti",
            date(2026, 12, 25): "Christmas",
            # 2027
            date(2027, 1, 26): "Republic Day",
            date(2027, 3, 6): "Mahashivratri",
            date(2027, 3, 22): "Holi",
            date(2027, 3, 26): "Good Friday",
            date(2027, 4, 14): "Dr. Baba Saheb Ambedkar Jayanti",
            date(2027, 4, 15): "Ram Navami",
            date(2027, 5, 1): "Maharashtra Day",
            date(2027, 5, 17): "Bakri Id / Eid-ul-Adha",
            date(2027, 6, 16): "Muharram",
            date(2027, 8, 15): "Independence Day",
            date(2027, 10, 2): "Mahatma Gandhi Jayanti",
            date(2027, 10, 9): "Dussehra",
            date(2027, 10, 29): "Diwali Laxmi Pujan",
            date(2027, 10, 31): "Diwali Balipratipada",
            date(2027, 11, 14): "Guru Nanak Jayanti",
            date(2027, 12, 25): "Christmas",
        }

        # NYSE / NASDAQ Statutory Holidays (2026 & 2027)
        self.nyse_holidays: Dict[date, str] = {
            # 2026
            date(2026, 1, 1): "New Year's Day",
            date(2026, 1, 19): "Martin Luther King Jr. Day",
            date(2026, 2, 16): "Washington's Birthday (Presidents' Day)",
            date(2026, 4, 3): "Good Friday",
            date(2026, 5, 25): "Memorial Day",
            date(2026, 6, 19): "Juneteenth National Independence Day",
            date(2026, 7, 3): "Independence Day (Observed)",
            date(2026, 9, 7): "Labor Day",
            date(2026, 11, 26): "Thanksgiving Day",
            date(2026, 12, 25): "Christmas Day",
            # 2027
            date(2027, 1, 1): "New Year's Day",
            date(2027, 1, 18): "Martin Luther King Jr. Day",
            date(2027, 2, 15): "Washington's Birthday (Presidents' Day)",
            date(2027, 3, 26): "Good Friday",
            date(2027, 5, 31): "Memorial Day",
            date(2027, 6, 18): "Juneteenth (Observed)",
            date(2027, 7, 5): "Independence Day (Observed)",
            date(2027, 9, 6): "Labor Day",
            date(2027, 11, 25): "Thanksgiving Day",
            date(2027, 12, 24): "Christmas Day (Observed)",
        }

    def detect_market_type(self, ticker: str) -> str:
        """Determines the market class / jurisdiction for a given asset symbol."""
        tk = ticker.upper()
        if tk.endswith((".NS", ".BO")) or tk.startswith(("^NSE", "^BS")):
            return "NSE_CASH"
        elif tk.endswith("=F") or tk in ["GLD", "SLV", "USO", "UNG"]:
            return "COMMODITY"
        elif tk.endswith("=X") or tk in ["DX-Y.NYB", "UUP"]:
            return "FOREX"
        elif "-USD" in tk or "-USDT" in tk or tk in ["BTC", "ETH", "SOL", "DOGE", "XRP"]:
            return "CRYPTO"
        else:
            return "US_EQUITIES"

    def get_session_info(
        self,
        ticker: str,
        now_utc: Optional[datetime] = None,
        simulation_mode: bool = False,
    ) -> MarketSessionInfo:
        """Evaluates complete market session status for `ticker` at `now_utc`."""
        if now_utc is None:
            now_utc = datetime.now(self.tz_utc)
        elif now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=self.tz_utc)
        else:
            now_utc = now_utc.astimezone(self.tz_utc)

        m_type = self.detect_market_type(ticker)

        # 1. CRYPTO: Continuous 24/7/365
        if m_type == "CRYPTO":
            return MarketSessionInfo(
                ticker=ticker,
                market_type="CRYPTO",
                state=MarketState.OPEN,
                is_tradable=True,
                exchange_name="Crypto Spot / Perpetuals",
                local_timezone="UTC",
                local_time_str=now_utc.strftime("%H:%M:%S UTC"),
                session_schedule="24/7/365 Continuous",
                reason="Continuous global trading",
                next_state=MarketState.OPEN,
                next_state_time_utc="",
                seconds_to_next_state=0,
                countdown_display="Continuous 24/7",
                tick_frozen=False,
                holiday_name=None,
            )

        # 2. INDIAN EQUITIES (NSE / BSE: Asia/Kolkata)
        if m_type == "NSE_CASH":
            return self._eval_nse(ticker, now_utc, simulation_mode)

        # 3. COMMODITIES (CME COMEX: America/New_York)
        if m_type == "COMMODITY":
            return self._eval_cme(ticker, now_utc, simulation_mode)

        # 4. FOREX (ECN 24/5: America/New_York)
        if m_type == "FOREX":
            return self._eval_forex(ticker, now_utc, simulation_mode)

        # 5. US EQUITIES (NYSE / NASDAQ: America/New_York)
        return self._eval_us_equities(ticker, now_utc, simulation_mode)

    def get_session_state(
        self,
        ticker: str,
        now_utc: Optional[datetime] = None,
        simulation_mode: bool = False,
    ) -> MarketSessionInfo:
        """Alias for get_session_info matching contract specifications."""
        return self.get_session_info(ticker, now_utc=now_utc, simulation_mode=simulation_mode)

    def _eval_nse(self, ticker: str, now_utc: datetime, sim_mode: bool) -> MarketSessionInfo:
        now_ist = now_utc.astimezone(self.tz_ist)
        today = now_ist.date()
        weekday = now_ist.weekday()  # 0=Mon .. 6=Sun
        t = now_ist.time()

        # Check Weekend (Saturday=5, Sunday=6)
        if weekday >= 5:
            days_until_mon = (7 - weekday) % 7
            next_day = today + timedelta(days=days_until_mon)
            while next_day.weekday() >= 5 or next_day in self.nse_holidays:
                next_day += timedelta(days=1)
            next_open_dt = datetime.combine(next_day, time(9, 15), tzinfo=self.tz_ist)
            return self._format_result(
                ticker=ticker,
                m_type="NSE_CASH",
                state=MarketState.WEEKEND,
                sim_mode=sim_mode,
                exch="NSE Mumbai",
                tz="Asia/Kolkata",
                clock=now_ist.strftime("%H:%M:%S IST"),
                sched="09:15–15:30 IST",
                reason="NSE Closed (Weekend — Opens Monday 09:15 IST)",
                next_s=MarketState.OPEN,
                next_dt=next_open_dt,
                now_utc=now_utc,
                holiday_name=None,
            )

        # Check Statutory Holiday
        if today in self.nse_holidays:
            h_name = self.nse_holidays[today]
            next_bus_day = today + timedelta(days=1)
            while next_bus_day.weekday() >= 5 or next_bus_day in self.nse_holidays:
                next_bus_day += timedelta(days=1)
            next_open_dt = datetime.combine(next_bus_day, time(9, 15), tzinfo=self.tz_ist)
            return self._format_result(
                ticker=ticker,
                m_type="NSE_CASH",
                state=MarketState.HOLIDAY,
                sim_mode=sim_mode,
                exch="NSE Mumbai",
                tz="Asia/Kolkata",
                clock=now_ist.strftime("%H:%M:%S IST"),
                sched="09:15–15:30 IST",
                reason=f"NSE Closed (Holiday: {h_name})",
                next_s=MarketState.OPEN,
                next_dt=next_open_dt,
                now_utc=now_utc,
                holiday_name=h_name,
            )

        # Regular weekday intraday timing:
        # 00:00 - 09:00: Overnight CLOSED
        if t < time(9, 0):
            next_pre_dt = datetime.combine(today, time(9, 0), tzinfo=self.tz_ist)
            return self._format_result(
                ticker=ticker,
                m_type="NSE_CASH",
                state=MarketState.CLOSED,
                sim_mode=sim_mode,
                exch="NSE Mumbai",
                tz="Asia/Kolkata",
                clock=now_ist.strftime("%H:%M:%S IST"),
                sched="09:15–15:30 IST",
                reason="NSE Closed (Overnight — Pre-market opens 09:00 IST)",
                next_s=MarketState.PRE_MARKET,
                next_dt=next_pre_dt,
                now_utc=now_utc,
                holiday_name=None,
            )
        # 09:00 - 09:15: PRE_MARKET (Pre-open order discovery)
        elif time(9, 0) <= t < time(9, 15):
            next_open_dt = datetime.combine(today, time(9, 15), tzinfo=self.tz_ist)
            return self._format_result(
                ticker=ticker,
                m_type="NSE_CASH",
                state=MarketState.PRE_MARKET,
                sim_mode=sim_mode,
                exch="NSE Mumbai",
                tz="Asia/Kolkata",
                clock=now_ist.strftime("%H:%M:%S IST"),
                sched="09:15–15:30 IST",
                reason="NSE Pre-Open Session (Order collection & price discovery)",
                next_s=MarketState.OPEN,
                next_dt=next_open_dt,
                now_utc=now_utc,
                holiday_name=None,
            )
        # 09:15 - 15:30: Regular Trading Hours (OPEN)
        elif time(9, 15) <= t <= time(15, 30):
            next_close_dt = datetime.combine(today, time(15, 30), tzinfo=self.tz_ist)
            return self._format_result(
                ticker=ticker,
                m_type="NSE_CASH",
                state=MarketState.OPEN,
                sim_mode=sim_mode,
                exch="NSE Mumbai",
                tz="Asia/Kolkata",
                clock=now_ist.strftime("%H:%M:%S IST"),
                sched="09:15–15:30 IST",
                reason="NSE Regular Trading Session Live",
                next_s=MarketState.POST_MARKET,
                next_dt=next_close_dt,
                now_utc=now_utc,
                holiday_name=None,
            )
        # 15:30 - 16:00: POST_MARKET
        elif time(15, 30) < t <= time(16, 0):
            next_close_dt = datetime.combine(today, time(16, 0), tzinfo=self.tz_ist)
            return self._format_result(
                ticker=ticker,
                m_type="NSE_CASH",
                state=MarketState.POST_MARKET,
                sim_mode=sim_mode,
                exch="NSE Mumbai",
                tz="Asia/Kolkata",
                clock=now_ist.strftime("%H:%M:%S IST"),
                sched="09:15–15:30 IST",
                reason="NSE Post-Market Session (Closing price determination)",
                next_s=MarketState.CLOSED,
                next_dt=next_close_dt,
                now_utc=now_utc,
                holiday_name=None,
            )
        # 16:00 - 23:59: Overnight CLOSED
        else:
            next_day = today + timedelta(days=1)
            while next_day.weekday() >= 5 or next_day in self.nse_holidays:
                next_day += timedelta(days=1)
            next_open_dt = datetime.combine(next_day, time(9, 15), tzinfo=self.tz_ist)
            return self._format_result(
                ticker=ticker,
                m_type="NSE_CASH",
                state=MarketState.CLOSED,
                sim_mode=sim_mode,
                exch="NSE Mumbai",
                tz="Asia/Kolkata",
                clock=now_ist.strftime("%H:%M:%S IST"),
                sched="09:15–15:30 IST",
                reason="NSE Closed (After-Hours — Opens next trading day 09:15 IST)",
                next_s=MarketState.OPEN,
                next_dt=next_open_dt,
                now_utc=now_utc,
                holiday_name=None,
            )

    def _eval_us_equities(self, ticker: str, now_utc: datetime, sim_mode: bool) -> MarketSessionInfo:
        now_et = now_utc.astimezone(self.tz_et)
        today = now_et.date()
        weekday = now_et.weekday()
        t = now_et.time()

        # Weekend Check
        if weekday >= 5:
            days = (7 - weekday) % 7
            next_day = today + timedelta(days=days)
            while next_day.weekday() >= 5 or next_day in self.nyse_holidays:
                next_day += timedelta(days=1)
            next_open_dt = datetime.combine(next_day, time(9, 30), tzinfo=self.tz_et)
            return self._format_result(
                ticker=ticker,
                m_type="US_EQUITIES",
                state=MarketState.WEEKEND,
                sim_mode=sim_mode,
                exch="NYSE / NASDAQ",
                tz="America/New_York",
                clock=now_et.strftime("%H:%M:%S %Z"),
                sched="09:30–16:00 ET",
                reason="US Market Closed (Weekend — Opens Monday 09:30 ET)",
                next_s=MarketState.OPEN,
                next_dt=next_open_dt,
                now_utc=now_utc,
                holiday_name=None,
            )

        # Statutory Holiday Check
        if today in self.nyse_holidays:
            h_name = self.nyse_holidays[today]
            next_d = today + timedelta(days=1)
            while next_d.weekday() >= 5 or next_d in self.nyse_holidays:
                next_d += timedelta(days=1)
            next_open_dt = datetime.combine(next_d, time(9, 30), tzinfo=self.tz_et)
            return self._format_result(
                ticker=ticker,
                m_type="US_EQUITIES",
                state=MarketState.HOLIDAY,
                sim_mode=sim_mode,
                exch="NYSE / NASDAQ",
                tz="America/New_York",
                clock=now_et.strftime("%H:%M:%S %Z"),
                sched="09:30–16:00 ET",
                reason=f"US Market Closed (Holiday: {h_name})",
                next_s=MarketState.OPEN,
                next_dt=next_open_dt,
                now_utc=now_utc,
                holiday_name=h_name,
            )

        # Intraday US Timing:
        # 00:00 - 04:00: Overnight CLOSED
        if t < time(4, 0):
            next_pre_dt = datetime.combine(today, time(4, 0), tzinfo=self.tz_et)
            return self._format_result(
                ticker=ticker,
                m_type="US_EQUITIES",
                state=MarketState.CLOSED,
                sim_mode=sim_mode,
                exch="NYSE / NASDAQ",
                tz="America/New_York",
                clock=now_et.strftime("%H:%M:%S %Z"),
                sched="09:30–16:00 ET",
                reason="US Market Closed (Overnight — Pre-market opens 04:00 ET)",
                next_s=MarketState.PRE_MARKET,
                next_dt=next_pre_dt,
                now_utc=now_utc,
                holiday_name=None,
            )
        # 04:00 - 09:30: PRE_MARKET
        elif time(4, 0) <= t < time(9, 30):
            next_open_dt = datetime.combine(today, time(9, 30), tzinfo=self.tz_et)
            return self._format_result(
                ticker=ticker,
                m_type="US_EQUITIES",
                state=MarketState.PRE_MARKET,
                sim_mode=sim_mode,
                exch="NYSE / NASDAQ",
                tz="America/New_York",
                clock=now_et.strftime("%H:%M:%S %Z"),
                sched="09:30–16:00 ET",
                reason="US Pre-Market Trading Session",
                next_s=MarketState.OPEN,
                next_dt=next_open_dt,
                now_utc=now_utc,
                holiday_name=None,
            )
        # 09:30 - 16:00: Regular Trading Hours (OPEN)
        elif time(9, 30) <= t <= time(16, 0):
            next_close_dt = datetime.combine(today, time(16, 0), tzinfo=self.tz_et)
            return self._format_result(
                ticker=ticker,
                m_type="US_EQUITIES",
                state=MarketState.OPEN,
                sim_mode=sim_mode,
                exch="NYSE / NASDAQ",
                tz="America/New_York",
                clock=now_et.strftime("%H:%M:%S %Z"),
                sched="09:30–16:00 ET",
                reason="US Regular Trading Session Live",
                next_s=MarketState.POST_MARKET,
                next_dt=next_close_dt,
                now_utc=now_utc,
                holiday_name=None,
            )
        # 16:00 - 20:00: POST_MARKET (After-Hours)
        elif time(16, 0) < t <= time(20, 0):
            next_close_dt = datetime.combine(today, time(20, 0), tzinfo=self.tz_et)
            return self._format_result(
                ticker=ticker,
                m_type="US_EQUITIES",
                state=MarketState.POST_MARKET,
                sim_mode=sim_mode,
                exch="NYSE / NASDAQ",
                tz="America/New_York",
                clock=now_et.strftime("%H:%M:%S %Z"),
                sched="09:30–16:00 ET",
                reason="US After-Hours Trading Session",
                next_s=MarketState.CLOSED,
                next_dt=next_close_dt,
                now_utc=now_utc,
                holiday_name=None,
            )
        # 20:00 - 23:59: Overnight CLOSED
        else:
            next_d = today + timedelta(days=1)
            while next_d.weekday() >= 5 or next_d in self.nyse_holidays:
                next_d += timedelta(days=1)
            next_open_dt = datetime.combine(next_d, time(9, 30), tzinfo=self.tz_et)
            return self._format_result(
                ticker=ticker,
                m_type="US_EQUITIES",
                state=MarketState.CLOSED,
                sim_mode=sim_mode,
                exch="NYSE / NASDAQ",
                tz="America/New_York",
                clock=now_et.strftime("%H:%M:%S %Z"),
                sched="09:30–16:00 ET",
                reason="US Market Closed (After-Hours — Opens next trading day 09:30 ET)",
                next_s=MarketState.OPEN,
                next_dt=next_open_dt,
                now_utc=now_utc,
                holiday_name=None,
            )

    def _eval_cme(self, ticker: str, now_utc: datetime, sim_mode: bool) -> MarketSessionInfo:
        now_et = now_utc.astimezone(self.tz_et)
        today = now_et.date()
        weekday = now_et.weekday()
        t = now_et.time()

        # Weekend: Friday 17:00 ET to Sunday 17:15 ET
        if (weekday == 4 and t >= time(17, 0)) or weekday == 5 or (weekday == 6 and t < time(17, 15)):
            days = (6 - weekday) % 7 if weekday != 6 else 0
            next_open_dt = datetime.combine(today + timedelta(days=days), time(18, 0), tzinfo=self.tz_et)
            return self._format_result(
                ticker=ticker,
                m_type="COMMODITY",
                state=MarketState.WEEKEND,
                sim_mode=sim_mode,
                exch="CME Globex",
                tz="America/New_York",
                clock=now_et.strftime("%H:%M:%S %Z"),
                sched="Sun 18:00 - Fri 17:00 ET (Daily Pause 17:00–18:00 ET)",
                reason="CME Globex Weekend Shutdown (Opens Sunday 18:00 ET)",
                next_s=MarketState.OPEN,
                next_dt=next_open_dt,
                now_utc=now_utc,
                holiday_name=None,
            )

        # Sunday Pre-Open: 17:15 - 18:00 ET
        if weekday == 6 and time(17, 15) <= t < time(18, 0):
            next_open_dt = datetime.combine(today, time(18, 0), tzinfo=self.tz_et)
            return self._format_result(
                ticker=ticker,
                m_type="COMMODITY",
                state=MarketState.PRE_MARKET,
                sim_mode=sim_mode,
                exch="CME Globex",
                tz="America/New_York",
                clock=now_et.strftime("%H:%M:%S %Z"),
                sched="Sun 18:00 - Fri 17:00 ET",
                reason="CME Globex Sunday Pre-Open Order Entry",
                next_s=MarketState.OPEN,
                next_dt=next_open_dt,
                now_utc=now_utc,
                holiday_name=None,
            )

        # Daily Maintenance Halt: Mon–Thu 17:00 - 18:00 ET
        if weekday in [0, 1, 2, 3] and time(17, 0) <= t < time(18, 0):
            next_open_dt = datetime.combine(today, time(18, 0), tzinfo=self.tz_et)
            return self._format_result(
                ticker=ticker,
                m_type="COMMODITY",
                state=MarketState.CLOSED,
                sim_mode=sim_mode,
                exch="CME Globex",
                tz="America/New_York",
                clock=now_et.strftime("%H:%M:%S %Z"),
                sched="Daily Maintenance 17:00–18:00 ET",
                reason="CME Globex Daily Maintenance Pause (Resumes 18:00 ET)",
                next_s=MarketState.OPEN,
                next_dt=next_open_dt,
                now_utc=now_utc,
                holiday_name=None,
            )

        # Active Session
        next_halt_dt = datetime.combine(today, time(17, 0), tzinfo=self.tz_et)
        if t >= time(18, 0):
            next_halt_dt = datetime.combine(today + timedelta(days=1), time(17, 0), tzinfo=self.tz_et)

        return self._format_result(
            ticker=ticker,
            m_type="COMMODITY",
            state=MarketState.OPEN,
            sim_mode=sim_mode,
            exch="CME Globex",
            tz="America/New_York",
            clock=now_et.strftime("%H:%M:%S %Z"),
            sched="23h/day Mon–Fri",
            reason="CME Globex Continuous Session Live",
            next_s=MarketState.CLOSED,
            next_dt=next_halt_dt,
            now_utc=now_utc,
            holiday_name=None,
        )

    def _eval_forex(self, ticker: str, now_utc: datetime, sim_mode: bool) -> MarketSessionInfo:
        now_et = now_utc.astimezone(self.tz_et)
        today = now_et.date()
        weekday = now_et.weekday()
        t = now_et.time()

        is_weekend = (weekday == 4 and t >= time(17, 0)) or (weekday == 5) or (weekday == 6 and t < time(17, 0))
        if is_weekend:
            days = (6 - weekday) % 7 if weekday != 6 else 0
            next_open_dt = datetime.combine(today + timedelta(days=days), time(17, 0), tzinfo=self.tz_et)
            return self._format_result(
                ticker=ticker,
                m_type="FOREX",
                state=MarketState.WEEKEND,
                sim_mode=sim_mode,
                exch="FX ECN 24/5",
                tz="America/New_York",
                clock=now_et.strftime("%H:%M:%S %Z"),
                sched="Sun 17:00 - Fri 17:00 ET",
                reason="Forex ECN Weekend Shutdown (Opens Sunday 17:00 ET)",
                next_s=MarketState.OPEN,
                next_dt=next_open_dt,
                now_utc=now_utc,
                holiday_name=None,
            )

        next_close_dt = datetime.combine(today + timedelta(days=(4 - weekday)), time(17, 0), tzinfo=self.tz_et)
        return self._format_result(
            ticker=ticker,
            m_type="FOREX",
            state=MarketState.OPEN,
            sim_mode=sim_mode,
            exch="FX ECN 24/5",
            tz="America/New_York",
            clock=now_et.strftime("%H:%M:%S %Z"),
            sched="24/5 Continuous",
            reason="Forex ECN 24/5 Live Session",
            next_s=MarketState.CLOSED,
            next_dt=next_close_dt,
            now_utc=now_utc,
            holiday_name=None,
        )

    def _format_result(
        self,
        ticker: str,
        m_type: str,
        state: MarketState,
        sim_mode: bool,
        exch: str,
        tz: str,
        clock: str,
        sched: str,
        reason: str,
        next_s: MarketState,
        next_dt: datetime,
        now_utc: datetime,
        holiday_name: Optional[str] = None,
    ) -> MarketSessionInfo:
        next_dt_utc = next_dt.astimezone(timezone.utc)
        delta_sec = max(0, int((next_dt_utc - now_utc).total_seconds()))

        hours = delta_sec // 3600
        mins = (delta_sec % 3600) // 60
        secs = delta_sec % 60
        if hours >= 24:
            days = hours // 24
            rem_h = hours % 24
            cd_str = f"{days}d {rem_h:02d}h {mins:02d}m {secs:02d}s"
        else:
            cd_str = f"{hours:02d}h {mins:02d}m {secs:02d}s"

        action = "Opens in" if state != MarketState.OPEN else "Closes in"
        countdown_display = f"{action} {cd_str}"

        is_tradable = (state == MarketState.OPEN) or sim_mode
        tick_frozen = (state != MarketState.OPEN) and (not sim_mode)

        final_reason = reason if not sim_mode else f"{reason} [SIMULATION MODE OVERRIDE]"

        return MarketSessionInfo(
            ticker=ticker,
            market_type=m_type,
            state=state,
            is_tradable=is_tradable,
            exchange_name=exch,
            local_timezone=tz,
            local_time_str=clock,
            session_schedule=sched,
            reason=final_reason,
            next_state=next_s,
            next_state_time_utc=next_dt_utc.isoformat(),
            seconds_to_next_state=delta_sec,
            countdown_display=countdown_display,
            tick_frozen=tick_frozen,
            holiday_name=holiday_name,
        )
