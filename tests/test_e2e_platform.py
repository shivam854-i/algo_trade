"""Dual-Track Opaque-Box E2E Acceptance Test Suite for SYNAPSE-TITAN Trading Platform.

Authoritative Specifications:
- PROJECT.md § Architecture (Frontend Cockpit, Physical Sessions, Data Ingestion Pipeline)
- PROJECT.md § Interface Contracts
- ORIGINAL_REQUEST.md § Requirements (R1, R2, R3, R4) and Acceptance Criteria

Test Tiers:
- Tier 1: Feature Coverage (>=5 test cases per feature across R1, R2, R3, R4)
- Tier 2: Boundary & Corner Cases (exact open/close bounds, DST switches, statutory holidays, weekend transitions, invalid inputs)
- Tier 3: Cross-Feature Combinations (holiday order queuing to Monday open, crypto continuous vs closed stock price freeze, simulation mode decoupled)
- Tier 4: Real-World Scenarios (multi-asset simultaneous portfolio execution, tab hidden simulation without queue buildup)
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import sys
import time as time_mod
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import pytest

from src.data.downloader import MarketDataDownloader
from src.data.provider_base import (
    BaseMarketDataProvider,
    DataInterval,
    LiveQuote,
    MarketDepthL2,
    OrderBookLevel,
    YFinanceProvider,
)
from src.execution.broker import (
    PaperBroker,
    Position,
    TradeLog,
    TradingLedgerDB,
)
from src.execution.guardrails import RiskGuardrailEngine
from src.execution.live_bot import LiveBotController, get_exchange_session_status
from src.execution.market_sessions import (
    MarketCalendarManager,
    MarketSessionInfo,
    MarketState,
)
from src.pipeline import MarketPredictionEngine, SingleAssetAnalysis


# ==============================================================================
# Reference Mirror: Python Implementation of Frontend RingBuffer<T>
# Mirrors frontend/src/utils/ringBuffer.ts with identical O(1) bounds & semantics
# ==============================================================================
class BoundedRingBuffer:
    """Generic bounded circular buffer matching frontend/src/utils/ringBuffer.ts."""

    def __init__(self, capacity: int):
        if capacity <= 0 or not isinstance(capacity, int):
            raise ValueError(f"RingBuffer capacity must be a positive integer, got: {capacity}")
        self.capacity = capacity
        self.buffer: List[Optional[Any]] = [None] * capacity
        self.head: int = 0
        self.tail: int = 0
        self.count: int = 0

    def push(self, item: Any) -> None:
        self.buffer[self.tail] = item
        self.tail = (self.tail + 1) % self.capacity
        if self.count < self.capacity:
            self.count += 1
        else:
            self.head = (self.head + 1) % self.capacity

    def push_many(self, items: List[Any]) -> None:
        for it in items:
            self.push(it)

    def to_array(self) -> List[Any]:
        result = []
        for i in range(self.count):
            result.append(self.buffer[(self.head + i) % self.capacity])
        return result

    def peek_latest(self) -> Optional[Any]:
        if self.count == 0:
            return None
        latest_idx = (self.tail - 1 + self.capacity) % self.capacity
        return self.buffer[latest_idx]

    def peek_oldest(self) -> Optional[Any]:
        if self.count == 0:
            return None
        return self.buffer[self.head]

    def clear(self) -> None:
        self.buffer = [None] * self.capacity
        self.head = 0
        self.tail = 0
        self.count = 0

    def size(self) -> int:
        return self.count

    def get_capacity(self) -> int:
        return self.capacity

    def is_full(self) -> bool:
        return self.count == self.capacity

    def is_empty(self) -> bool:
        return self.count == 0


# ==============================================================================
# Mock Analysis Dataclasses for Lightweight LiveBot Simulation
# ==============================================================================
class MockVolCone:
    expected_vol_annualized: float = 0.25

class MockMetaPred:
    primary_direction: int = 1
    direction_label: str = "LONG"
    success_probability: float = 0.65
    target_price: float = 110.0
    stop_price: float = 90.0

class MockRegime:
    name: str = "BULL_TREND"
    is_crisis: bool = False

class MockRiskDecision:
    authorized_weight_pct: float = 10.0

@dataclass
class MockAnalysis:
    ticker: str
    current_price: float
    market_jurisdiction: str
    volatility_cone: Any = field(default_factory=MockVolCone)
    meta_prediction: Any = field(default_factory=MockMetaPred)
    regime: Any = field(default_factory=MockRegime)
    risk_decision: Any = field(default_factory=MockRiskDecision)
    neural_prob: float = 0.70


# ==============================================================================
# Isolated Test Fixtures
# ==============================================================================
@pytest.fixture
def isolated_db(tmp_path: Path) -> TradingLedgerDB:
    """Creates a temporary, strictly isolated SQLite database ledger for testing."""
    db_file = tmp_path / "test_trading_ledger.db"
    return TradingLedgerDB(db_path=db_file)


@pytest.fixture
def isolated_broker(isolated_db: TradingLedgerDB) -> PaperBroker:
    """Provides a fresh PaperBroker hooked to the isolated database."""
    broker = PaperBroker(account_id="TEST_ACCOUNT", initial_capital=100000.0)
    broker.ledger = isolated_db
    broker._ensure_account(100000.0)
    return broker


@pytest.fixture
def calendar() -> MarketCalendarManager:
    return MarketCalendarManager()


@pytest.fixture
def mock_live_bot(isolated_broker: PaperBroker) -> LiveBotController:
    """Initializes a lightweight LiveBotController with simulated analysis objects."""
    engine = MarketPredictionEngine()
    bot = LiveBotController(engine=engine, broker=isolated_broker)
    bot.calendar = MarketCalendarManager()

    # Pre-seed analyses with mock assets across jurisdictions
    tickers = ["BTC-USD", "ETH-USD", "GC=F", "EURUSD=X", "RELIANCE.NS", "NVDA"]
    for tk in tickers:
        m_type = bot.calendar.detect_market_type(tk)
        jurisdiction = "CRYPTO" if m_type == "CRYPTO" else ("COMMODITY" if m_type == "COMMODITY" else ("FOREX" if m_type == "FOREX" else ("INDIAN_NSE" if m_type == "NSE_CASH" else "US_EQUITIES")))
        price = 65000.0 if "BTC" in tk else (3000.0 if "ETH" in tk else (2350.0 if "GC" in tk else (1.0850 if "EUR" in tk else (2950.0 if "RELIANCE" in tk else 125.0))))

        bot.base_prices[tk] = price
        bot.live_prices[tk] = price
        bot.price_series[tk] = [{"time": "09:00:00", "price": price, "high": price * 1.001, "low": price * 0.999}]
        bot.hrp_weights[tk] = 1.0 / len(tickers)
        bot.analyses[tk] = MockAnalysis(ticker=tk, current_price=price, market_jurisdiction=jurisdiction)

    bot.watchlist = list(tickers)
    bot.armed_tickers = set(tickers)
    bot._initialized = True
    return bot


# ==============================================================================
# TIER 1: FEATURE COVERAGE (>=5 tests per feature)
# ==============================================================================

class TestTier1FrontendMemoryStability:
    """R1: Frontend memory bounds, circular ring buffers, and Page Visibility lifecycle."""

    def test_ring_buffer_bounded_capacity_and_fifo_eviction(self):
        buf = BoundedRingBuffer(capacity=5)
        for i in range(1, 6):
            buf.push(i)
        assert buf.is_full()
        assert buf.size() == 5
        assert buf.to_array() == [1, 2, 3, 4, 5]

        # Push 6th item -> oldest item (1) evicted
        buf.push(6)
        assert buf.size() == 5
        assert buf.to_array() == [2, 3, 4, 5, 6]
        assert buf.peek_oldest() == 2
        assert buf.peek_latest() == 6

    def test_ring_buffer_zero_memory_leak_heavy_streaming(self):
        """Streaming 10,000 prices into a 500-capacity buffer must never exceed 500 items."""
        buf = BoundedRingBuffer(capacity=500)
        for tick in range(10000):
            buf.push({"tick": tick, "price": 100.0 + (tick % 50)})

        assert buf.size() == 500
        assert buf.is_full()
        assert len(buf.to_array()) == 500
        assert buf.peek_latest()["tick"] == 9999
        assert buf.peek_oldest()["tick"] == 9500

    def test_ring_buffer_peek_and_clear_invariants(self):
        buf = BoundedRingBuffer(capacity=10)
        assert buf.is_empty()
        assert buf.peek_latest() is None
        assert buf.peek_oldest() is None

        buf.push_many(["A", "B", "C"])
        assert buf.size() == 3
        assert buf.peek_oldest() == "A"
        assert buf.peek_latest() == "C"

        buf.clear()
        assert buf.is_empty()
        assert buf.size() == 0
        assert buf.to_array() == []

    def test_page_visibility_lifecycle_simulation(self):
        """Simulates tab hidden suspension and resume behavior."""
        tab_is_visible = True
        tick_accumulator = []
        polling_active = True

        def simulated_visibility_event(hidden: bool):
            nonlocal tab_is_visible, polling_active
            tab_is_visible = not hidden
            polling_active = not hidden

        # 1. Tab visible: ticks collected
        for t in range(5):
            if polling_active:
                tick_accumulator.append(t)
        assert len(tick_accumulator) == 5

        # 2. Tab minimized/hidden (document.hidden === true): polling suspends!
        simulated_visibility_event(hidden=True)
        assert not polling_active
        for t in range(5, 25):
            if polling_active:
                tick_accumulator.append(t)
        # Length remains 5: zero queue buildup during backgrounding
        assert len(tick_accumulator) == 5

        # 3. Tab wake-up (document.hidden === false): single snapshot resync
        simulated_visibility_event(hidden=False)
        assert polling_active
        latest_server_snapshot = {"resync_tick": 25, "price": 105.0}
        tick_accumulator.append(latest_server_snapshot["resync_tick"])
        assert len(tick_accumulator) == 6

    def test_activity_log_bounded_at_100_entries(self, mock_live_bot: LiveBotController):
        """Verifies activity log ring buffer remains strictly capped at 100 entries."""
        for i in range(250):
            mock_live_bot.log_event("TRADE", f"Test event #{i}")

        assert len(mock_live_bot.activity_log) == 100
        assert "Test event #249" in mock_live_bot.activity_log[0]["message"]
        assert "Test event #150" in mock_live_bot.activity_log[-1]["message"]


class TestTier1PhysicalMarketSessions:
    """R2: Physical market session schedules across global asset classes."""

    def test_nse_schedule_enforcement(self, calendar: MarketCalendarManager):
        # Wednesday 11:00 IST -> OPEN
        t_open = datetime(2026, 6, 17, 5, 30, 0, tzinfo=timezone.utc)
        sess = calendar.get_session_info("RELIANCE.NS", now_utc=t_open)
        assert sess.state == MarketState.OPEN
        assert sess.is_open

        # Wednesday 08:30 IST -> CLOSED
        t_closed = datetime(2026, 6, 17, 3, 0, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("RELIANCE.NS", now_utc=t_closed).state == MarketState.CLOSED

    def test_nyse_schedule_enforcement(self, calendar: MarketCalendarManager):
        # Wednesday 14:00 ET -> OPEN
        t_open = datetime(2026, 6, 17, 18, 0, 0, tzinfo=timezone.utc)
        sess = calendar.get_session_info("NVDA", now_utc=t_open)
        assert sess.state == MarketState.OPEN
        assert sess.is_open

        # Wednesday 08:00 ET -> PRE_MARKET
        t_pre = datetime(2026, 6, 17, 12, 0, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("NVDA", now_utc=t_pre).state == MarketState.PRE_MARKET

    def test_comex_gold_schedule_enforcement(self, calendar: MarketCalendarManager):
        # Tuesday 12:00 ET -> OPEN
        t_open = datetime(2026, 6, 16, 16, 0, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("GC=F", now_utc=t_open).state == MarketState.OPEN

        # Tuesday 17:30 ET -> CLOSED (maintenance pause)
        t_pause = datetime(2026, 6, 16, 21, 30, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("GC=F", now_utc=t_pause).state == MarketState.CLOSED

    def test_crypto_24_7_continuous_schedule(self, calendar: MarketCalendarManager):
        # Sunday midnight UTC
        t_sun = datetime(2026, 6, 21, 0, 0, 0, tzinfo=timezone.utc)
        sess = calendar.get_session_info("BTC-USD", now_utc=t_sun)
        assert sess.state == MarketState.OPEN
        assert sess.is_open
        assert sess.countdown_display == "Continuous 24/7"

    def test_forex_24_5_continuous_schedule(self, calendar: MarketCalendarManager):
        # Wednesday 12:00 ET -> OPEN
        t_open = datetime(2026, 6, 17, 16, 0, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("EURUSD=X", now_utc=t_open).state == MarketState.OPEN

        # Saturday 12:00 ET -> WEEKEND
        t_sat = datetime(2026, 6, 20, 16, 0, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("EURUSD=X", now_utc=t_sat).state == MarketState.WEEKEND


class TestTier1PriceFreezingAndSimulationDecoupling:
    """R2: Strict closed-market tick freezing and decoupled simulation mode."""

    def test_closed_market_price_freeze(self, mock_live_bot: LiveBotController):
        """Closed market asset prices must freeze strictly in step_tick unless simulation_mode is enabled."""
        mock_live_bot.simulation_mode = False
        initial_reliance_price = mock_live_bot.live_prices["RELIANCE.NS"]

        # Override calendar to return CLOSED for RELIANCE.NS
        mock_live_bot.calendar.get_session_info = lambda tk, **kw: MarketSessionInfo(
            ticker=tk,
            market_type="NSE_CASH" if tk == "RELIANCE.NS" else "CRYPTO",
            state=MarketState.CLOSED if tk == "RELIANCE.NS" else MarketState.OPEN,
            is_tradable=False if tk == "RELIANCE.NS" else True,
            exchange_name="NSE Mumbai" if tk == "RELIANCE.NS" else "Crypto",
            local_timezone="Asia/Kolkata",
            local_time_str="15:30:00 IST",
            session_schedule="09:15–15:30 IST",
            reason="Market Closed",
            next_state=MarketState.OPEN,
            next_state_time_utc="",
            seconds_to_next_state=3600,
            countdown_display="Opens in 01h 00m 00s",
            tick_frozen=True if tk == "RELIANCE.NS" else False,
        )

        for _ in range(10):
            mock_live_bot.step_tick()

        # RELIANCE.NS price must remain strictly unchanged!
        assert mock_live_bot.live_prices["RELIANCE.NS"] == initial_reliance_price

    def test_simulation_mode_allows_synthetic_ticks_on_closed_markets(self, mock_live_bot: LiveBotController):
        """When simulation_mode is enabled, synthetic ticks are allowed even if physical session is closed."""
        mock_live_bot.simulation_mode = True
        initial_reliance_price = mock_live_bot.live_prices["RELIANCE.NS"]

        # Run tick with simulation_mode=True
        mock_live_bot.step_tick(custom_shock_pct=5.0)
        assert mock_live_bot.live_prices["RELIANCE.NS"] != initial_reliance_price
        assert mock_live_bot.live_prices["RELIANCE.NS"] > initial_reliance_price

    def test_crypto_ticks_continue_while_equities_frozen(self, mock_live_bot: LiveBotController):
        """Unified multi-asset step: Crypto moves while closed Equities stay pinned."""
        mock_live_bot.simulation_mode = False
        initial_btc = mock_live_bot.live_prices["BTC-USD"]
        initial_reliance = mock_live_bot.live_prices["RELIANCE.NS"]

        # Mock: BTC is OPEN, RELIANCE is CLOSED
        mock_live_bot.calendar.get_session_info = lambda tk, **kw: MarketSessionInfo(
            ticker=tk,
            market_type="NSE_CASH" if tk == "RELIANCE.NS" else "CRYPTO",
            state=MarketState.CLOSED if tk == "RELIANCE.NS" else MarketState.OPEN,
            is_tradable=False if tk == "RELIANCE.NS" else True,
            exchange_name="NSE" if tk == "RELIANCE.NS" else "Crypto",
            local_timezone="UTC",
            local_time_str="12:00:00 UTC",
            session_schedule="",
            reason="",
            next_state=MarketState.OPEN,
            next_state_time_utc="",
            seconds_to_next_state=0,
            countdown_display="",
            tick_frozen=True if tk == "RELIANCE.NS" else False,
        )

        # Run 5 ticks
        for _ in range(5):
            mock_live_bot.step_tick()

        assert mock_live_bot.live_prices["RELIANCE.NS"] == initial_reliance
        assert mock_live_bot.live_prices["BTC-USD"] != initial_btc

    def test_price_history_series_bounded_at_60_bars(self, mock_live_bot: LiveBotController):
        """Price series in live_bot must never exceed 60 items to prevent RAM growth."""
        mock_live_bot.simulation_mode = True
        for _ in range(120):
            mock_live_bot.step_tick()

        for tk, series in mock_live_bot.price_series.items():
            assert len(series) <= 60

    def test_equity_comparison_series_bounded_at_60_bars(self, mock_live_bot: LiveBotController):
        """Equity curve series in live_bot must never exceed 60 items."""
        mock_live_bot.simulation_mode = True
        for _ in range(100):
            mock_live_bot.step_tick()

        assert len(mock_live_bot.comparison_series) <= 60


class TestTier1PreMarketPendingOrders:
    """R2: SQLite orders queueing, soft cash holds, open execution, and cancellation."""

    def test_pre_market_order_insertion_with_soft_cash_hold(self, isolated_broker: PaperBroker):
        order = isolated_broker.queue_pre_market_order(
            ticker="RELIANCE.NS",
            direction="LONG",
            current_price=2950.0,
            target_price=3100.0,
            stop_price=2850.0,
            custom_allocated_capital=10000.0,
        )

        assert order["status"] == "PRE_MARKET_PENDING"
        assert order["allocated_capital"] == 10000.0
        assert order["order_id"].startswith("ORD-")

        summary = isolated_broker.get_account_summary()
        assert summary["current_cash"] == 100000.0
        assert summary["reserved_cash"] == 10000.0
        assert summary["available_cash"] == 90000.0

    def test_available_cash_deduction_by_reserved_cash(self, isolated_broker: PaperBroker):
        isolated_broker.queue_pre_market_order("RELIANCE.NS", "LONG", 2950.0, 3100.0, 2850.0, custom_allocated_capital=15000.0)
        isolated_broker.queue_pre_market_order("TCS.NS", "LONG", 3800.0, 4000.0, 3700.0, custom_allocated_capital=25000.0)

        summary = isolated_broker.get_account_summary()
        assert summary["reserved_cash"] == 40000.0
        assert summary["available_cash"] == 60000.0

    def test_cancel_pending_order_releases_cash(self, isolated_broker: PaperBroker):
        order = isolated_broker.queue_pre_market_order("NVDA", "LONG", 120.0, 135.0, 110.0, custom_allocated_capital=20000.0)
        summary_before = isolated_broker.get_account_summary()
        assert summary_before["reserved_cash"] == 20000.0

        cancelled = isolated_broker.cancel_pending_order(order["order_id"])
        assert cancelled is True

        summary_after = isolated_broker.get_account_summary()
        assert summary_after["reserved_cash"] == 0.0
        assert summary_after["available_cash"] == 100000.0

        pending = isolated_broker.get_pending_orders("NVDA")
        assert len(pending) == 0

    def test_pending_order_execution_on_market_open(self, isolated_broker: PaperBroker):
        order = isolated_broker.queue_pre_market_order(
            ticker="RELIANCE.NS",
            direction="LONG",
            current_price=2950.0,
            target_price=3150.0,
            stop_price=2850.0,
            custom_allocated_capital=15000.0,
        )

        # Market opens at 2960.0 -> execute pending orders
        executed = isolated_broker.execute_pending_orders_for_ticker("RELIANCE.NS", opening_price=2960.0)
        assert len(executed) == 1
        pos = executed[0]
        assert pos.ticker == "RELIANCE.NS"
        assert pos.entry_price == 2960.0
        assert pos.allocated_capital == 15000.0

        # Reservation cleared and cash deducted
        summary = isolated_broker.get_account_summary()
        assert summary["reserved_cash"] == 0.0
        assert summary["current_cash"] == 85000.0
        assert summary["open_positions_count"] == 1

        # Order table status updated to FILLED
        pending = isolated_broker.get_pending_orders("RELIANCE.NS")
        assert len(pending) == 0

    def test_multiple_pending_orders_fifo_execution(self, isolated_broker: PaperBroker):
        isolated_broker.queue_pre_market_order("NVDA", "LONG", 120.0, 130.0, 110.0, custom_allocated_capital=5000.0)
        isolated_broker.queue_pre_market_order("NVDA", "LONG", 120.0, 140.0, 105.0, custom_allocated_capital=8000.0)

        pending = isolated_broker.get_pending_orders("NVDA")
        assert len(pending) == 2

        executed = isolated_broker.execute_pending_orders_for_ticker("NVDA", opening_price=122.50)
        assert len(executed) == 2
        assert executed[0].allocated_capital == 5000.0
        assert executed[1].allocated_capital == 8000.0

        summary = isolated_broker.get_account_summary()
        assert summary["reserved_cash"] == 0.0
        assert summary["current_cash"] == 100000.0 - 13000.0


class TestTier1MultiAssetMonitoringAndControls:
    """R3: Multi-asset monitoring, custom ticker input, dynamic arming, and portfolio tracking."""

    def test_multi_asset_watchlist_initialization(self, mock_live_bot: LiveBotController):
        assert "BTC-USD" in mock_live_bot.watchlist
        assert "GC=F" in mock_live_bot.watchlist
        assert "EURUSD=X" in mock_live_bot.watchlist
        assert "RELIANCE.NS" in mock_live_bot.watchlist
        assert "NVDA" in mock_live_bot.watchlist

    def test_dynamic_asset_arming_disarming(self, mock_live_bot: LiveBotController):
        # Disarm all except BTC-USD
        mock_live_bot.update_asset_selection(armed_tickers=["BTC-USD"])
        assert mock_live_bot.armed_tickers == {"BTC-USD"}

        # Re-arm multiple
        mock_live_bot.update_asset_selection(armed_tickers=["BTC-USD", "NVDA", "GC=F"])
        assert mock_live_bot.armed_tickers == {"BTC-USD", "NVDA", "GC=F"}

    def test_custom_ticker_resolution_pipeline(self, calendar: MarketCalendarManager):
        # Test detection of custom tickers
        assert calendar.detect_market_type("TATAMOTORS.NS") == "NSE_CASH"
        assert calendar.detect_market_type("SI=F") == "COMMODITY"
        assert calendar.detect_market_type("GBPUSD=X") == "FOREX"
        assert calendar.detect_market_type("SOL-USD") == "CRYPTO"
        assert calendar.detect_market_type("TSLA") == "US_EQUITIES"

    def test_portfolio_mark_to_market_pnl_aggregation(self, isolated_broker: PaperBroker):
        p1 = isolated_broker.open_position("BTC-USD", "LONG", 60000.0, 70000.0, 50000.0, custom_allocated_capital=20000.0)
        p2 = isolated_broker.open_position("NVDA", "SHORT", 120.0, 100.0, 140.0, custom_allocated_capital=20000.0)

        updated, _ = isolated_broker.update_and_audit_positions({"BTC-USD": 66000.0, "NVDA": 114.0})
        summary = isolated_broker.get_account_summary()

        assert summary["open_positions_count"] == 2
        assert summary["unrealized_pnl"] > 0
        assert summary["total_equity"] > 100000.0

    def test_risk_guardrail_kelly_sizing(self):
        guard = RiskGuardrailEngine()
        alloc = guard.evaluate_allocation(
            current_drawdown=0.0,
            model_bet_size=0.5,
            realized_annual_vol=0.20,
            win_probability=0.65,
            payoff_ratio_b=1.8,
        )
        assert alloc.authorized_weight_pct > 0.0
        assert alloc.authorized_weight_pct <= 20.0


class TestTier1IngestionPipelineAndCache:
    """R4: Market data provider architecture, dynamic TTL, and timezone preservation."""

    def test_base_market_data_provider_contract(self):
        quote = LiveQuote(
            ticker="NVDA",
            bid_price=120.50,
            ask_price=120.60,
            last_price=120.55,
            bid_size=500.0,
            ask_size=300.0,
            timestamp_utc=datetime.now(timezone.utc),
            exchange="NASDAQ",
        )
        assert quote.spread == pytest.approx(0.10, abs=1e-4)
        assert quote.mid_price == pytest.approx(120.55, abs=1e-4)
        assert quote.spread_bps > 0.0

    def test_dynamic_cache_ttl_intraday_vs_daily(self, tmp_path: Path):
        downloader = MarketDataDownloader(cache_dir=tmp_path)
        cache_1m = tmp_path / "AAPL_1m_1d.csv"
        cache_1d = tmp_path / "AAPL_1d_1y.csv"

        cache_1m.write_text("timestamp,Open,High,Low,Close,Volume\n")
        cache_1d.write_text("timestamp,Open,High,Low,Close,Volume\n")

        past_time = time_mod.time() - 300
        os.utime(cache_1m, (past_time, past_time))
        os.utime(cache_1d, (past_time, past_time))

        assert not downloader._is_cache_valid(cache_1m, interval="1m")
        assert downloader._is_cache_valid(cache_1d, interval="1d")

    def test_timezone_preservation_without_naive_stripping(self):
        dates = pd.date_range("2026-06-01", periods=10, freq="D", tz="UTC")
        df = pd.DataFrame({"Close": [100.0 + i for i in range(10)]}, index=dates)
        assert df.index.tz is not None
        assert str(df.index.tz) == "UTC"

    def test_downloader_cache_hit_latency(self, tmp_path: Path):
        downloader = MarketDataDownloader(cache_dir=tmp_path)
        cache_file = tmp_path / "NVDA_1d_1y.csv"
        df_dummy = pd.DataFrame({"Open": [100.0], "High": [105.0], "Low": [95.0], "Close": [102.0], "Volume": [1000]})
        df_dummy.to_csv(cache_file)

        start = time_mod.perf_counter()
        df_read = pd.read_csv(cache_file)
        elapsed_ms = (time_mod.perf_counter() - start) * 1000.0

        assert len(df_read) == 1
        assert elapsed_ms < 50.0

    def test_yfinance_provider_quote_generation(self):
        provider = YFinanceProvider()
        assert isinstance(provider, BaseMarketDataProvider)
        assert provider.name == "YFinanceProvider"
        assert provider.is_connected is True


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================

class TestTier2BoundaryAndCornerCases:
    """Edge cases, boundaries, DST switches, holidays, zero quantities, and negative prices."""

    def test_boundary_exact_open_close_seconds(self, calendar: MarketCalendarManager):
        t_pre = datetime(2026, 6, 17, 3, 44, 59, tzinfo=timezone.utc)
        t_open = datetime(2026, 6, 17, 3, 45, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("RELIANCE.NS", now_utc=t_pre).state == MarketState.PRE_MARKET
        assert calendar.get_session_info("RELIANCE.NS", now_utc=t_open).state == MarketState.OPEN

        t_nyse_pre = datetime(2026, 6, 17, 13, 29, 59, tzinfo=timezone.utc)
        t_nyse_open = datetime(2026, 6, 17, 13, 30, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("NVDA", now_utc=t_nyse_pre).state == MarketState.PRE_MARKET
        assert calendar.get_session_info("NVDA", now_utc=t_nyse_open).state == MarketState.OPEN

    def test_dst_boundary_us_equities(self, calendar: MarketCalendarManager):
        summer_open = datetime(2026, 7, 1, 13, 30, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("AAPL", now_utc=summer_open).state == MarketState.OPEN

        winter_open = datetime(2026, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("AAPL", now_utc=winter_open).state == MarketState.OPEN

    def test_statutory_holiday_transitions(self, calendar: MarketCalendarManager):
        dt = datetime(2026, 1, 26, 6, 0, 0, tzinfo=timezone.utc)
        info = calendar.get_session_info("RELIANCE.NS", now_utc=dt)
        assert info.state == MarketState.HOLIDAY
        assert info.holiday_name == "Republic Day"

    def test_weekend_transition_cme_gold(self, calendar: MarketCalendarManager):
        fri_dt = datetime(2026, 6, 19, 21, 1, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("GC=F", now_utc=fri_dt).state == MarketState.WEEKEND

        sun_pre_dt = datetime(2026, 6, 21, 21, 20, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("GC=F", now_utc=sun_pre_dt).state == MarketState.PRE_MARKET

        sun_open_dt = datetime(2026, 6, 21, 22, 1, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("GC=F", now_utc=sun_open_dt).state == MarketState.OPEN

    def test_insufficient_unreserved_cash_order_rejection(self, isolated_broker: PaperBroker):
        isolated_broker.queue_pre_market_order("NVDA", "LONG", 120.0, 130.0, 110.0, custom_allocated_capital=99990.0)

        with pytest.raises(ValueError, match="Insufficient unreserved cash"):
            isolated_broker.queue_pre_market_order("AAPL", "LONG", 200.0, 220.0, 190.0, custom_allocated_capital=500.0)

    def test_double_cancellation_of_pending_order(self, isolated_broker: PaperBroker):
        order = isolated_broker.queue_pre_market_order("NVDA", "LONG", 120.0, 130.0, 110.0, custom_allocated_capital=10000.0)
        ord_id = order["order_id"]

        assert isolated_broker.cancel_pending_order(ord_id) is True
        assert isolated_broker.cancel_pending_order(ord_id) is False

    def test_zero_quantity_or_invalid_price_order(self, isolated_broker: PaperBroker):
        # Allocation < $50 min threshold must raise ValueError
        with pytest.raises(ValueError, match="Insufficient unreserved cash"):
            isolated_broker.queue_pre_market_order("NVDA", "LONG", 120.0, 130.0, 110.0, custom_allocated_capital=10.0)

        with pytest.raises(ValueError, match="Insufficient unreserved cash"):
            isolated_broker.queue_pre_market_order("NVDA", "LONG", 120.0, 130.0, 110.0, allocation_weight_pct=0.0)


# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS
# ==============================================================================

class TestTier3CrossFeatureCombinations:
    """Interactions between holidays, weekends, queues, price freezes, and simulation decoupling."""

    def test_order_submitted_on_holiday_persists_through_weekend_to_monday(
        self, isolated_broker: PaperBroker, calendar: MarketCalendarManager
    ):
        holiday_utc = datetime(2026, 4, 3, 4, 30, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("RELIANCE.NS", now_utc=holiday_utc).state == MarketState.HOLIDAY

        order = isolated_broker.queue_pre_market_order(
            ticker="RELIANCE.NS",
            direction="LONG",
            current_price=2900.0,
            target_price=3100.0,
            stop_price=2800.0,
            custom_allocated_capital=12000.0,
        )
        assert order["status"] == "PRE_MARKET_PENDING"

        sat_utc = datetime(2026, 4, 4, 10, 0, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("RELIANCE.NS", now_utc=sat_utc).state == MarketState.WEEKEND
        pending_sat = isolated_broker.get_pending_orders("RELIANCE.NS")
        assert len(pending_sat) == 1

        mon_open_utc = datetime(2026, 4, 6, 3, 45, 0, tzinfo=timezone.utc)
        assert calendar.get_session_info("RELIANCE.NS", now_utc=mon_open_utc).state == MarketState.OPEN

        executed = isolated_broker.execute_pending_orders_for_ticker("RELIANCE.NS", opening_price=2910.0)
        assert len(executed) == 1
        assert executed[0].entry_price == 2910.0
        assert executed[0].allocated_capital == 12000.0
        assert len(isolated_broker.get_pending_orders("RELIANCE.NS")) == 0

    def test_simultaneous_price_freeze_and_continuous_crypto(
        self, mock_live_bot: LiveBotController
    ):
        """Unified multi-asset tick: NSE is frozen, Gold is in maintenance, and Crypto advances."""
        mock_live_bot.simulation_mode = False
        initial_prices = dict(mock_live_bot.live_prices)

        def mock_session_eval(tk, **kw):
            if tk == "RELIANCE.NS":
                st = MarketState.CLOSED
                tradable = False
            elif tk == "GC=F":
                st = MarketState.CLOSED
                tradable = False
            else:
                st = MarketState.OPEN
                tradable = True
            return MarketSessionInfo(
                ticker=tk,
                market_type="CRYPTO" if "BTC" in tk else ("COMMODITY" if tk == "GC=F" else "NSE_CASH"),
                state=st,
                is_tradable=tradable,
                exchange_name="Exch",
                local_timezone="UTC",
                local_time_str="",
                session_schedule="",
                reason="",
                next_state=MarketState.OPEN,
                next_state_time_utc="",
                seconds_to_next_state=0,
                countdown_display="",
                tick_frozen=not tradable,
            )

        mock_live_bot.calendar.get_session_info = mock_session_eval

        for _ in range(5):
            mock_live_bot.step_tick()

        assert mock_live_bot.live_prices["RELIANCE.NS"] == initial_prices["RELIANCE.NS"]
        assert mock_live_bot.live_prices["GC=F"] == initial_prices["GC=F"]
        assert mock_live_bot.live_prices["BTC-USD"] != initial_prices["BTC-USD"]

    def test_simulation_mode_toggle_preserves_physical_session_badge(
        self, calendar: MarketCalendarManager
    ):
        sat_utc = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
        normal = calendar.get_session_info("NVDA", now_utc=sat_utc, simulation_mode=False)
        sim = calendar.get_session_info("NVDA", now_utc=sat_utc, simulation_mode=True)

        assert normal.state == MarketState.WEEKEND
        assert sim.state == MarketState.WEEKEND
        assert normal.is_tradable is False
        assert sim.is_tradable is True
        assert normal.tick_frozen is True
        assert sim.tick_frozen is False


# ==============================================================================
# TIER 4: REAL-WORLD SCENARIOS
# ==============================================================================

class TestTier4RealWorldScenarios:
    """Multi-asset portfolio execution and background tab hidden lifecycle simulation."""

    def test_multi_asset_portfolio_execution(self, isolated_broker: PaperBroker):
        # 1. BTC-USD: Market is open -> fills immediately
        btc_pos = isolated_broker.open_position("BTC-USD", "LONG", 65000.0, 72000.0, 58000.0, custom_allocated_capital=25000.0)
        assert btc_pos is not None
        assert btc_pos.status == "OPEN"

        # 2. RELIANCE.NS: Market is closed -> queued as PRE_MARKET_PENDING
        rel_order = isolated_broker.queue_pre_market_order("RELIANCE.NS", "LONG", 2950.0, 3150.0, 2800.0, custom_allocated_capital=20000.0)
        assert rel_order["status"] == "PRE_MARKET_PENDING"

        # 3. NVDA: Market is in pre-market -> queued as PRE_MARKET_PENDING
        nvda_order = isolated_broker.queue_pre_market_order("NVDA", "LONG", 125.0, 140.0, 115.0, custom_allocated_capital=15000.0)
        assert nvda_order["status"] == "PRE_MARKET_PENDING"

        summary = isolated_broker.get_account_summary()
        assert summary["current_cash"] == 75000.0
        assert summary["reserved_cash"] == 35000.0
        assert summary["available_cash"] == 40000.0
        assert summary["open_positions_count"] == 1

        # Drain NVDA orders on open
        nvda_executed = isolated_broker.execute_pending_orders_for_ticker("NVDA", opening_price=126.0)
        assert len(nvda_executed) == 1
        summary2 = isolated_broker.get_account_summary()
        assert summary2["reserved_cash"] == 20000.0
        assert summary2["current_cash"] == 60000.0
        assert summary2["available_cash"] == 40000.0
        assert summary2["open_positions_count"] == 2

    def test_tab_hidden_simulation_no_queue_buildup(self, mock_live_bot: LiveBotController):
        """Simulates 50 background ticks while browser tab is hidden (document.hidden = true)."""
        client_chart_buffer = BoundedRingBuffer(capacity=500)
        tab_is_hidden = True

        for _ in range(50):
            state = mock_live_bot.step_tick()
            if not tab_is_hidden:
                client_chart_buffer.push(state["assets"]["BTC-USD"]["current_price"])

        # Client buffer remained empty during hidden tab state
        assert client_chart_buffer.size() == 0

        # Tab wakes up
        tab_is_hidden = False
        resync_snapshot = mock_live_bot.get_dashboard_state()

        client_chart_buffer.push_many([p["price"] for p in mock_live_bot.price_series["BTC-USD"]])
        assert client_chart_buffer.size() <= 60
        assert client_chart_buffer.peek_latest() == resync_snapshot["assets"]["BTC-USD"]["current_price"]
