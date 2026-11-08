"""Comprehensive Unit & End-to-End Integration Test Suite for Real-Market-Data Paper Trading.

Covers all 12 unit test categories and the full 6-step end-to-end integration pipeline
using deterministic mocked market data (zero external network dependency in CI):
1. Market-data ingestion & rate-limit / reconnection handling
2. Stale-data & missing-data rejection (never inventing prices)
3. Market-hours & NYSE early-close enforcement
4. Point-in-time causal feature calculation (no look-ahead bias)
5. Market-order fill calculation & unavailable-price rejection
6. Limit-order handling & partial fills
7. Bid/ask spread and Almgren-Chriss slippage modeling
8. Statutory commission and fee calculations
9. Gap-aware stop-loss & conservative intrabar SL/TP conflict resolution
10. Unrealized and realized P&L calculations (LONG and SHORT)
11. Position sizing, portfolio exposure limits, max concurrent positions & duplicate-order protection
12. Paper-trading-only hard safety isolation locks
13. End-to-end integration test: Ingest -> Predict -> Risk Check -> Open Virtual Position -> Update MTM P&L -> Close & Audit
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
import numpy as np
import pandas as pd
import pytest

from server import app
from src.data.provider_base import (
    AlpacaProvider,
    BaseMarketDataProvider,
    DataInterval,
    LiveQuote,
    MultiAssetDataProvider,
    SlidingWindowRateLimiter,
    YFinanceProvider,
    evaluate_quote_staleness,
)
from src.execution.auth import AuthManager
from src.execution.broker import (
     PAPER_TRADING_ONLY,
    AlpacaBrokerAdapter,
    BaseBrokerAdapter,
    MT5BrokerAdapter,
    PaperBroker,
    TradingLedgerDB,
    ZerodhaKiteAdapter,
)
from src.execution.live_bot import DEFAULT_US_EQUITIES, LiveBotController
from src.execution.market_sessions import MarketCalendarManager, MarketSessionInfo, MarketState
from src.pipeline import MarketPredictionEngine


# ==============================================================================
# Deterministic Mock Market Data Provider for CI Testing
# ==============================================================================


class MockLiveMarketDataProvider(BaseMarketDataProvider):
    """Deterministic mocked market data provider supplying US equity quotes and OHLCV bars."""

    def __init__(self, quotes: Optional[Dict[str, LiveQuote]] = None):
        super().__init__(name="MockLiveMarketDataProvider", max_staleness_seconds=60.0)
        self.is_connected = True
        self._quotes: Dict[str, LiveQuote] = quotes or {}
        self._bars: Dict[str, pd.DataFrame] = {}

    def set_quote(self, quote: LiveQuote) -> None:
        self._quotes[quote.ticker.upper()] = quote

    def set_bars(self, ticker: str, df: pd.DataFrame) -> None:
        self._bars[ticker.upper()] = df

    def is_realtime(self) -> bool:
        return True

    def get_historical_bars(
        self,
        ticker: str,
        interval: DataInterval | str = DataInterval.DAY_1,
        lookback_bars: int = 250,
        end_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        tk = ticker.strip().upper()
        if tk in self._bars:
            df = self._bars[tk]
            if end_time is not None:
                df = df[df.index <= end_time]
            return df.tail(lookback_bars).copy()
        return pd.DataFrame()

    def get_quote(self, ticker: str, market_open: Optional[bool] = None, **kwargs) -> LiveQuote:
        tk = ticker.strip().upper()
        if tk in self._quotes:
            return self._quotes[tk]
        now_utc = datetime.now(timezone.utc)
        return LiveQuote(
            ticker=tk,
            bid_price=0.0,
            ask_price=0.0,
            last_price=0.0,
            timestamp_utc=now_utc,
            received_at_utc=now_utc,
            exchange="MOCK",
            is_stale=True,
            provider_name=self.name,
            status="MISSING",
        )


def _generate_deterministic_ohlcv(
    base_price: float = 135.0,
    bars: int = 260,
    seed: int = 7,
) -> pd.DataFrame:
    """Generates a deterministic, stationary-friendly OHLCV series for unit/integration tests."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(
        end=datetime(2026, 11, 4, 20, 0, tzinfo=timezone.utc),
        periods=bars,
        freq="B",
    )
    rets = rng.normal(0.0012, 0.016, size=bars)
    close = base_price * np.cumprod(1.0 + rets)
    open_p = close * (1.0 + rng.normal(0.0, 0.003, size=bars))
    high_p = np.maximum(open_p, close) * (1.0 + np.abs(rng.normal(0.004, 0.003, size=bars)))
    low_p = np.minimum(open_p, close) * (1.0 - np.abs(rng.normal(0.004, 0.003, size=bars)))
    vol = rng.integers(15_000_000, 65_000_000, size=bars).astype(float)

    return pd.DataFrame(
        {
            "Open": open_p,
            "High": high_p,
            "Low": low_p,
            "Close": close,
            "Volume": vol,
        },
        index=dates,
    )


@pytest.fixture
def isolated_paper_broker(tmp_path: Path) -> PaperBroker:
    db_file = tmp_path / "paper_realism_test.db"
    return PaperBroker(
        account_id="PAPER_TEST",
        initial_capital=100000.0,
        db_path=db_file,
        max_concurrent_positions=3,
        max_position_exposure_pct=25.0,
        max_portfolio_exposure_pct=75.0,
    )


# ==============================================================================
# 1. Market-Data Ingestion, Rate-Limit Handling & Reconnection Tests
# ==============================================================================


class TestMarketDataIngestionAndHealth:
    @pytest.mark.disabled_market
    def test_default_us_equities_universe(self):
        """Verify the default paper-trading universe starts with NVDA, AAPL, MSFT, AMD, TSLA."""
        assert DEFAULT_US_EQUITIES == ["NVDA", "AAPL", "MSFT", "AMD", "TSLA"]

    @pytest.mark.disabled_market
    def test_alpaca_snapshot_parsing_and_env_key_isolation(self, monkeypatch):
        """Verify AlpacaProvider reads credentials from environment and parses snapshots accurately."""
        monkeypatch.delenv("ALPACA_API_KEY", raising=False)
        monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
        prov = AlpacaProvider()
        assert prov.is_connected is False

        now_utc = datetime(2026, 11, 4, 15, 30, 0, tzinfo=timezone.utc)
        sample_snapshot = {
            "latestQuote": {
                "bp": 142.48,
                "ap": 142.52,
                "bs": 400,
                "as": 300,
                "t": "2026-11-04T15:29:59Z",
            },
            "latestTrade": {
                "p": 142.50,
                "s": 100,
                "t": "2026-11-04T15:29:59Z",
            },
            "dailyBar": {
                "o": 140.00,
                "h": 143.20,
                "l": 139.80,
                "c": 142.50,
                "v": 42_500_000,
            },
            "prevDailyBar": {
                "c": 139.90,
            },
        }
        quote = prov._snapshot_to_quote("NVDA", sample_snapshot, now_utc=now_utc, lat_ms=14.2)
        assert quote.ticker == "NVDA"
        assert quote.bid_price == 142.48
        assert quote.ask_price == 142.52
        assert quote.last_price == 142.50
        assert quote.day_open == 140.00
        assert quote.day_high == 143.20
        assert quote.day_low == 139.80
        assert quote.prev_close == 139.90
        assert quote.is_valid is True
        assert quote.is_stale is False
        assert quote.spread == pytest.approx(0.04, abs=1e-4)

    def test_sliding_window_rate_limiter_and_429_backoff(self):
        """Verify rate limiter throttles bursts and honors HTTP 429 Retry-After headers."""
        limiter = SlidingWindowRateLimiter(max_requests_per_minute=3)
        t0 = 1000.0
        for i in range(3):
            ok, _ = limiter.can_proceed(t0 + i)
            assert ok is True
            limiter.record_request(t0 + i)

        ok, wait_s = limiter.can_proceed(t0 + 4.0)
        assert ok is False
        assert wait_s > 0.0

        # HTTP 429 backoff
        limiter.record_rate_limit_response(retry_after_seconds=20.0)
        ok_after_429, wait_429 = limiter.can_proceed()
        assert ok_after_429 is False
        assert wait_429 > 0.0

    def test_provider_reconnection_and_health_monitoring(self):
        """Verify automatic reconnection increments reconnect_count and clears error state."""
        prov = MockLiveMarketDataProvider()
        prov.consecutive_failures = 3
        prov.last_error = "Simulated socket timeout"
        assert prov.reconnect() is True
        assert prov.reconnect_count == 1
        assert prov.consecutive_failures == 0
        assert prov.last_error is None
        health = prov.get_health_status()
        assert health["healthy"] is True
        assert health["reconnect_count"] == 1


# ==============================================================================
# 2. Stale-Data & Missing-Data Rejection Tests
# ==============================================================================


class TestStaleAndMissingDataRejection:
    def test_evaluate_quote_staleness_open_vs_closed(self):
        now_utc = datetime(2026, 11, 4, 15, 0, 0, tzinfo=timezone.utc)
        old_quote_ts = now_utc - timedelta(minutes=25)

        # During open market hours, a 25-minute-old quote with 60s threshold is STALE
        is_stale_open, age_open = evaluate_quote_staleness(
            old_quote_ts, now_utc=now_utc, exchange_open=True, max_staleness_seconds=60.0
        )
        assert is_stale_open is True
        assert age_open == pytest.approx(1500.0, abs=1.0)

        # During closed market hours, the closing print is not a feed failure
        is_stale_closed, _ = evaluate_quote_staleness(
            old_quote_ts, now_utc=now_utc, exchange_open=False, max_staleness_seconds=60.0
        )
        assert is_stale_closed is False

    def test_broker_rejects_stale_and_unavailable_quotes(self, isolated_paper_broker: PaperBroker):
        # 1. Stale data rejection
        res_stale = isolated_paper_broker.submit_order(
            ticker="NVDA",
            direction="LONG",
            current_price=140.0,
            target_price=155.0,
            stop_price=130.0,
            is_stale=True,
            market_open=True,
        )
        assert res_stale["status"] == "REJECTED"
        assert res_stale["rejection_reason"] == "STALE_MARKET_DATA"
        assert len(isolated_paper_broker.get_open_positions()) == 0

        # 2. Unavailable / zero / NaN price rejection
        for bad_price in [0.0, -15.0, float("nan")]:
            res_bad = isolated_paper_broker.submit_order(
                ticker="AAPL",
                direction="LONG",
                current_price=bad_price,
                target_price=250.0,
                stop_price=200.0,
                is_stale=False,
                market_open=True,
            )
            assert res_bad["status"] == "REJECTED"
            assert res_bad["rejection_reason"] == "INVALID_OR_UNAVAILABLE_PRICE"
        assert len(isolated_paper_broker.get_open_positions()) == 0

    def test_live_bot_halts_new_entries_on_stale_or_missing_feed_without_inventing_prices(
        self, isolated_paper_broker: PaperBroker
    ):
        """Verify LiveBotController never invents prices and opens zero trades when feed is stale/missing."""
        now_utc = datetime.now(timezone.utc)
        stale_quote = LiveQuote(
            ticker="NVDA",
            bid_price=139.90,
            ask_price=140.10,
            last_price=140.00,
            timestamp_utc=now_utc - timedelta(hours=3),
            received_at_utc=now_utc,
            exchange="NASDAQ",
            is_stale=True,
            age_seconds=10800.0,
            provider_name="MockFeed",
            status="STALE",
        )
        missing_quote = LiveQuote(
            ticker="AAPL",
            bid_price=0.0,
            ask_price=0.0,
            last_price=0.0,
            timestamp_utc=now_utc,
            received_at_utc=now_utc,
            exchange="NASDAQ",
            is_stale=True,
            provider_name="MockFeed",
            status="MISSING",
        )
        feed = MockLiveMarketDataProvider({"NVDA": stale_quote, "AAPL": missing_quote})
        engine = MarketPredictionEngine()
        bot = LiveBotController(
            engine=engine,
            broker=isolated_paper_broker,
            data_provider=feed,
            initial_watchlist=["NVDA", "AAPL"],
        )

        # Seed analyses so we don't hit external network
        for tk, init_p in [("NVDA", 138.0), ("AAPL", 225.0)]:
            df = _generate_deterministic_ohlcv(base_price=init_p)
            bot.analyses[tk] = engine.analyze_ticker(tk, df_override=df)
            bot.base_prices[tk] = init_p
            bot.live_prices[tk] = init_p
            bot.price_series[tk] = [{"time": "09:30:00", "price": init_p, "high": init_p, "low": init_p}]

        # Force calendar open
        bot.calendar.get_session_info = lambda tk, **kw: MarketSessionInfo(
            ticker=tk,
            market_type="US_EQUITIES",
            state=MarketState.OPEN,
            is_tradable=True,
            exchange_name="NASDAQ",
            local_timezone="America/New_York",
            local_time_str="10:30:00 EDT",
            session_schedule="09:30-16:00 ET",
            reason="Regular Trading Hours",
            next_state=MarketState.POST_MARKET,
            next_state_time_utc="",
            seconds_to_next_state=18000,
            countdown_display="05h 00m 00s",
            tick_frozen=False,
        )
        bot._initialized = True

        state = bot.step_tick()
        # AAPL had a missing quote (0.0) -> price must remain at 225.0 (never invented!)
        assert bot.live_prices["AAPL"] == 225.0
        # Neither NVDA (stale) nor AAPL (missing) may open a new position
        assert len(isolated_paper_broker.get_open_positions()) == 0
        assert "AAPL" in state["data_feed_status"]["stale_tickers"]
        assert "NVDA" in state["data_feed_status"]["stale_tickers"]


# ==============================================================================
# 3. Market-Hours & NYSE Early-Close Enforcement Tests
# ==============================================================================


class TestMarketHoursEnforcement:
    @pytest.mark.disabled_market
    def test_nyse_early_close_1300_et_session_enforcement(self):
        cal = MarketCalendarManager()
        tz_et = ZoneInfo("America/New_York")

        # Day after Thanksgiving: Nov 27, 2026 (Early close at 13:00 ET)
        dt_1230 = datetime(2026, 11, 27, 12, 30, tzinfo=tz_et).astimezone(timezone.utc)
        info_open = cal.get_session_info("NVDA", now_utc=dt_1230)
        assert info_open.state == MarketState.OPEN
        assert info_open.is_tradable is True
        assert "Early Close" in info_open.reason

        # At 13:15 ET on Nov 27, 2026 -> regular session is already closed (POST_MARKET)
        dt_1315 = datetime(2026, 11, 27, 13, 15, tzinfo=tz_et).astimezone(timezone.utc)
        info_after = cal.get_session_info("NVDA", now_utc=dt_1315)
        assert info_after.state == MarketState.POST_MARKET
        assert info_after.is_tradable is False

    def test_broker_rejects_execution_outside_market_hours(self, isolated_paper_broker: PaperBroker):
        res = isolated_paper_broker.submit_order(
            ticker="MSFT",
            direction="LONG",
            current_price=420.0,
            target_price=450.0,
            stop_price=400.0,
            market_open=False,
        )
        assert res["status"] == "REJECTED"
        assert res["rejection_reason"] == "OUTSIDE_MARKET_HOURS"
        assert len(isolated_paper_broker.get_open_positions()) == 0


# ==============================================================================
# 4. Point-in-Time Causal Feature Calculation (Zero Look-Ahead Bias)
# ==============================================================================


class TestPointInTimeCausality:
    def test_point_in_time_cutoff_prevents_future_data_leakage(self):
        engine = MarketPredictionEngine()
        full_df = _generate_deterministic_ohlcv(base_price=150.0, bars=260, seed=99)

        # Inject an extreme artificial future spike in the last 10 bars
        corrupted_future_df = full_df.copy()
        corrupted_future_df.iloc[-10:, corrupted_future_df.columns.get_loc("Close")] *= 5.0
        corrupted_future_df.iloc[-10:, corrupted_future_df.columns.get_loc("High")] *= 5.0

        cutoff_ts = full_df.index[-15].to_pydatetime()

        res_clean = engine.analyze_ticker(
            "AMD",
            df_override=full_df,
            as_of_timestamp=cutoff_ts,
        )
        res_corrupted_future = engine.analyze_ticker(
            "AMD",
            df_override=corrupted_future_df,
            as_of_timestamp=cutoff_ts,
        )

        assert res_clean is not None
        assert res_corrupted_future is not None
        # Because both are evaluated strictly at `cutoff_ts` (before the last 10 bars),
        # the future 5x price spike must have ZERO effect on current_price, d*, features, or predictions!
        assert res_clean.current_price == res_corrupted_future.current_price
        assert res_clean.optimal_d_star == res_corrupted_future.optimal_d_star
        assert res_clean.meta_prediction.target_price == res_corrupted_future.meta_prediction.target_price
        assert res_clean.recent_ohlcv.index.max() <= pd.Timestamp(cutoff_ts)


# ==============================================================================
# 5, 6, 7 & 8. Market/Limit Orders, Bid/Ask Spread, Slippage, Partial Fills & Fees
# ==============================================================================


class TestOrderExecutionRealism:
    def test_bid_ask_spread_and_slippage_fill_calculation(self, isolated_paper_broker: PaperBroker):
        # LONG entry buys at Ask + positive slippage
        long_entry_fill, eff_bid, eff_ask, slip_bps = isolated_paper_broker.compute_realistic_fill_price(
            ticker="NVDA",
            direction="LONG",
            is_entry=True,
            reference_price=140.00,
            bid_price=139.95,
            ask_price=140.05,
            order_shares=100.0,
            apply_slippage=True,
        )
        assert eff_bid == 139.95
        assert eff_ask == 140.05
        assert slip_bps > 0.0
        assert long_entry_fill > eff_ask

        # SHORT entry sells at Bid - negative slippage
        short_entry_fill, _, _, _ = isolated_paper_broker.compute_realistic_fill_price(
            ticker="NVDA",
            direction="SHORT",
            is_entry=True,
            reference_price=140.00,
            bid_price=139.95,
            ask_price=140.05,
            order_shares=100.0,
            apply_slippage=True,
        )
        assert short_entry_fill < eff_bid

        # Larger order size produces greater Almgren-Chriss square-root market impact
        _, _, _, small_slip = isolated_paper_broker.compute_realistic_fill_price(
            ticker="NVDA",
            direction="LONG",
            is_entry=True,
            reference_price=140.00,
            bid_price=139.95,
            ask_price=140.05,
            order_shares=10.0,
            apply_slippage=True,
        )
        _, _, _, large_slip = isolated_paper_broker.compute_realistic_fill_price(
            ticker="NVDA",
            direction="LONG",
            is_entry=True,
            reference_price=140.00,
            bid_price=139.95,
            ask_price=140.05,
            order_shares=25_000.0,
            apply_slippage=True,
        )
        assert large_slip > small_slip

    def test_limit_order_working_and_fill_on_quote_improvement(self, isolated_paper_broker: PaperBroker):
        # Submit a LONG LIMIT order with limit_price=138.00 while Ask is 140.05 -> stays WORKING
        ord_working = isolated_paper_broker.submit_order(
            ticker="NVDA",
            direction="LONG",
            current_price=140.00,
            target_price=155.00,
            stop_price=130.00,
            order_type="LIMIT",
            limit_price=138.00,
            bid_price=139.95,
            ask_price=140.05,
            allocation_weight_pct=10.0,
        )
        assert ord_working["status"] == "WORKING"
        assert len(isolated_paper_broker.get_open_positions()) == 0
        assert isolated_paper_broker.get_account_summary()["reserved_cash"] == pytest.approx(10000.0, abs=1.0)

        # Quote Ask drops to 137.80 (<= 138.00 limit) -> working limit order fills!
        filled_positions = isolated_paper_broker.evaluate_working_orders(
            {"NVDA": {"last": 137.75, "bid": 137.70, "ask": 137.80, "is_stale": False}}
        )
        assert len(filled_positions) == 1
        assert filled_positions[0].entry_price <= 138.00
        assert isolated_paper_broker.get_account_summary()["reserved_cash"] == 0.0

    def test_partial_fill_when_order_exceeds_available_top_of_book_liquidity(
        self, isolated_paper_broker: PaperBroker
    ):
        # Order desires ~100 shares ($10,000 @ $100), but only 40 shares are available at top of book
        ord_partial = isolated_paper_broker.submit_order(
            ticker="AMD",
            direction="LONG",
            current_price=100.0,
            target_price=115.0,
            stop_price=92.0,
            order_type="MARKET",
            custom_allocated_capital=10000.0,
            bid_price=99.95,
            ask_price=100.05,
            available_liquidity_shares=40.0,
        )
        assert ord_partial["status"] == "PARTIALLY_FILLED"
        assert ord_partial["filled_shares"] == pytest.approx(40.0, rel=0.02)
        assert ord_partial["remaining_shares"] > 50.0
        positions = isolated_paper_broker.get_open_positions()
        assert len(positions) == 1
        assert positions[0].allocated_capital == pytest.approx(4000.0, abs=1.0)


# ==============================================================================
# 9 & 10. Gap-Aware Stop-Loss, Conservative Intrabar SL/TP & P&L Calculations
# ==============================================================================


class TestGapAwareStopLossAndConservativeBarriers:
    def test_gap_aware_stop_loss_fills_at_worse_gapped_open_price(
        self, isolated_paper_broker: PaperBroker
    ):
        pos = isolated_paper_broker.open_position(
            ticker="TSLA",
            direction="LONG",
            current_price=250.0,
            target_price=280.0,
            stop_price=240.0,
            custom_allocated_capital=10000.0,
        )
        assert pos is not None

        # Next session gaps down at open to $225.00 (well below $240.00 stop!)
        still_open, closed = isolated_paper_broker.update_and_audit_positions(
            {
                "TSLA": {
                    "open": 225.0,
                    "high": 228.0,
                    "low": 222.0,
                    "last": 226.0,
                    "bid": 225.9,
                    "ask": 226.1,
                }
            }
        )
        assert len(still_open) == 0
        assert len(closed) == 1
        assert closed[0].exit_reason == "STOP_LOSS"
        # Must fill at the gapped open price ($225.00), NOT the $240.00 stop level!
        assert closed[0].exit_price == 225.0
        assert closed[0].net_pnl < -900.0

    def test_conservative_intrabar_conflict_prioritizes_stop_loss_over_take_profit(
        self, isolated_paper_broker: PaperBroker
    ):
        pos = isolated_paper_broker.open_position(
            ticker="NVDA",
            direction="LONG",
            current_price=140.0,
            target_price=150.0,
            stop_price=132.0,
            custom_allocated_capital=10000.0,
        )
        assert pos is not None

        # Wide volatile candle crosses BOTH low=130.0 (<= 132.0 SL) and high=155.0 (>= 150.0 TP)
        still_open, closed = isolated_paper_broker.update_and_audit_positions(
            {
                "NVDA": {
                    "open": 140.0,
                    "high": 155.0,
                    "low": 130.0,
                    "last": 148.0,
                }
            }
        )
        assert len(still_open) == 0
        assert len(closed) == 1
        # Conservative rule: STOP_LOSS must win when both barriers are crossed in one bar
        assert closed[0].exit_reason == "STOP_LOSS"
        assert closed[0].exit_price == 132.0

    def test_short_position_unrealized_and_realized_pnl_accounting(
        self, isolated_paper_broker: PaperBroker
    ):
        pos = isolated_paper_broker.open_position(
            ticker="MSFT",
            direction="SHORT",
            current_price=400.0,
            target_price=360.0,
            stop_price=420.0,
            custom_allocated_capital=20000.0,
        )
        assert pos is not None

        # Price drops to 380.0 -> SHORT position has positive unrealized P&L
        still_open, closed = isolated_paper_broker.update_and_audit_positions({"MSFT": 380.0})
        assert len(still_open) == 1
        assert len(closed) == 0
        assert still_open[0].unrealized_pnl > 900.0

        # Price drops to 358.0 (<= 360.0 target) -> closes for PROFIT_TARGET
        still_open_2, closed_2 = isolated_paper_broker.update_and_audit_positions({"MSFT": 358.0})
        assert len(still_open_2) == 0
        assert len(closed_2) == 1
        assert closed_2[0].exit_reason == "PROFIT_TARGET"
        assert closed_2[0].net_pnl > 1900.0
        summary = isolated_paper_broker.get_account_summary()
        assert summary["realized_pnl"] == pytest.approx(closed_2[0].net_pnl, abs=0.05)
        assert summary["total_equity"] == pytest.approx(100000.0 + closed_2[0].net_pnl, abs=0.05)


# ==============================================================================
# 11. Exposure Limits, Max Concurrent Positions & Duplicate-Order Protection
# ==============================================================================


class TestExposureAndDuplicateGuardrails:
    def test_duplicate_order_and_max_concurrent_positions_protection(
        self, isolated_paper_broker: PaperBroker
    ):
        # 1. Open first position on NVDA
        r1 = isolated_paper_broker.submit_order(
            ticker="NVDA",
            direction="LONG",
            current_price=140.0,
            target_price=160.0,
            stop_price=128.0,
            allocation_weight_pct=15.0,
        )
        assert r1["status"] == "FILLED"

        # 2. Attempt duplicate order on NVDA -> REJECTED
        r_dup = isolated_paper_broker.submit_order(
            ticker="NVDA",
            direction="LONG",
            current_price=140.5,
            target_price=160.0,
            stop_price=128.0,
            allocation_weight_pct=10.0,
        )
        assert r_dup["status"] == "REJECTED"
        assert r_dup["rejection_reason"] == "DUPLICATE_ORDER_OR_POSITION"

        # 3. Fill up to max_concurrent_positions (3)
        r2 = isolated_paper_broker.submit_order(
            ticker="AAPL",
            direction="LONG",
            current_price=225.0,
            target_price=250.0,
            stop_price=210.0,
            allocation_weight_pct=15.0,
        )
        r3 = isolated_paper_broker.submit_order(
            ticker="MSFT",
            direction="LONG",
            current_price=420.0,
            target_price=460.0,
            stop_price=395.0,
            allocation_weight_pct=15.0,
        )
        assert r2["status"] == "FILLED"
        assert r3["status"] == "FILLED"

        # 4. 4th position exceeds max_concurrent_positions=3 -> REJECTED
        r4 = isolated_paper_broker.submit_order(
            ticker="AMD",
            direction="LONG",
            current_price=155.0,
            target_price=175.0,
            stop_price=142.0,
            allocation_weight_pct=15.0,
        )
        assert r4["status"] == "REJECTED"
        assert r4["rejection_reason"] == "MAX_CONCURRENT_POSITIONS_EXCEEDED"


# ==============================================================================
# 12. Paper-Only Safety Isolation Lock Verification
# ==============================================================================


class TestPaperOnlySafetyLocks:
    def test_all_external_broker_adapters_hard_disabled(self):
        assert PAPER_TRADING_ONLY is True

        with pytest.raises(PermissionError):
            BaseBrokerAdapter().submit_order("NVDA", "LONG", 10, 140.0)
        with pytest.raises(PermissionError):
            AlpacaBrokerAdapter(paper=False)
        with pytest.raises(PermissionError):
            AlpacaBrokerAdapter(paper=True).submit_order("NVDA", "LONG", 10, 140.0)
        with pytest.raises(PermissionError):
            ZerodhaKiteAdapter().submit_order("RELIANCE.NS", "LONG", 10, 1400.0)
        with pytest.raises(PermissionError):
            MT5BrokerAdapter().submit_order("EURUSD=X", "LONG", 1.0, 1.08)

    def test_auth_tiers_and_api_reject_real_money_execution(self, tmp_path: Path):
        auth = AuthManager(db_path=tmp_path / "auth_test.db")
        inst_user = auth.register_user("quant@fund.io", tier="INSTITUTIONAL")
        assert inst_user.broker_execution_enabled is False

        client = TestClient(app)
        resp = client.post(
            "/api/dashboard/order",
            json={
                "ticker": "NVDA",
                "direction": "LONG",
                "allocation_weight_pct": 10.0,
                "execution_mode": "LIVE_BROKERAGE",
            },
        )
        assert resp.status_code == 403
        assert "CRITICAL SAFETY LOCK" in resp.json()["detail"]


# ==============================================================================
# 13. End-to-End 6-Step Integration Pipeline Test
# ==============================================================================


class TestEndToEndLiveMarketPaperTradingPipeline:
    def test_full_autonomous_paper_trading_lifecycle(self, tmp_path: Path):
        """Verifies the complete 6-step pipeline:
        1. Ingest mocked market data (historical OHLCV + live Bid/Ask quotes for NVDA)
        2. Generate prediction signal via MarketPredictionEngine
        3. Pass risk & session checks
        4. Open virtual position in PaperBroker with Bid/Ask + slippage
        5. Update unrealized P&L on live quote ticks
        6. Close virtual position and record trade history & audit metrics in SQLite
        """
        # Step 1: Prepare mocked market data feed
        now_utc = datetime.now(timezone.utc)
        nvda_df = _generate_deterministic_ohlcv(base_price=135.0, bars=260, seed=21)
        last_close = float(nvda_df["Close"].iloc[-1])

        quote_t1 = LiveQuote(
            ticker="NVDA",
            bid_price=round(last_close - 0.02, 2),
            ask_price=round(last_close + 0.02, 2),
            last_price=round(last_close, 2),
            bid_size=500.0,
            ask_size=500.0,
            timestamp_utc=now_utc,
            received_at_utc=now_utc,
            exchange="NASDAQ",
            is_delayed=False,
            is_stale=False,
            age_seconds=0.2,
            latency_ms=8.5,
            provider_name="MockLiveFeed",
            day_open=round(last_close * 0.99, 2),
            day_high=round(last_close * 1.01, 2),
            day_low=round(last_close * 0.985, 2),
            prev_close=round(last_close * 0.992, 2),
            status="LIVE",
        )
        feed = MockLiveMarketDataProvider({"NVDA": quote_t1})
        feed.set_bars("NVDA", nvda_df)

        # Step 2: Run prediction engine on mocked historical bars
        engine = MarketPredictionEngine()
        analysis = engine.analyze_ticker("NVDA", df_override=nvda_df)
        assert analysis is not None
        assert analysis.ticker == "NVDA"
        assert analysis.optimal_d_star >= 0.0
        assert 0.0 <= analysis.meta_prediction.success_probability <= 1.0

        # Step 3 & 4: Initialize PaperBroker + LiveBotController and execute tick 1 (opens virtual position)
        broker = PaperBroker(
            account_id="E2E_PAPER_ACCOUNT",
            initial_capital=100000.0,
            db_path=tmp_path / "e2e_ledger.db",
        )
        bot = LiveBotController(
            engine=engine,
            broker=broker,
            data_provider=feed,
            initial_watchlist=["NVDA"],
        )
        bot.analyses["NVDA"] = analysis
        bot.base_prices["NVDA"] = last_close
        bot.live_prices["NVDA"] = last_close
        bot.price_series["NVDA"] = [{"time": "09:30:00", "price": last_close, "high": last_close, "low": last_close}]
        bot.calendar.get_session_info = lambda tk, **kw: MarketSessionInfo(
            ticker=tk,
            market_type="US_EQUITIES",
            state=MarketState.OPEN,
            is_tradable=True,
            exchange_name="NASDAQ",
            local_timezone="America/New_York",
            local_time_str="10:30:00 EDT",
            session_schedule="09:30-16:00 ET",
            reason="Regular Trading Hours",
            next_state=MarketState.POST_MARKET,
            next_state_time_utc="",
            seconds_to_next_state=18000,
            countdown_display="05h 00m 00s",
            tick_frozen=False,
        )
        bot._initialized = True

        state_t1 = bot.step_tick()
        open_positions = broker.get_open_positions()
        assert len(open_positions) == 1
        pos = open_positions[0]
        assert pos.ticker == "NVDA"
        assert pos.allocated_capital > 5000.0

        # Step 5: Advance market quote in favor of the position and verify unrealized P&L updates
        favorable_move = 1.04 if pos.direction == "LONG" else 0.96
        next_price = round(pos.entry_price * favorable_move, 2)
        quote_t2 = LiveQuote(
            ticker="NVDA",
            bid_price=round(next_price - 0.02, 2),
            ask_price=round(next_price + 0.02, 2),
            last_price=next_price,
            timestamp_utc=now_utc + timedelta(seconds=5),
            received_at_utc=now_utc + timedelta(seconds=5),
            exchange="NASDAQ",
            is_delayed=False,
            is_stale=False,
            age_seconds=0.1,
            latency_ms=7.2,
            provider_name="MockLiveFeed",
            day_open=quote_t1.day_open,
            day_high=max(quote_t1.day_high or next_price, next_price),
            day_low=min(quote_t1.day_low or next_price, next_price),
            prev_close=quote_t1.prev_close,
            status="LIVE",
        )
        feed.set_quote(quote_t2)
        bot.is_running = False  # Pause auto-entry on tick 2 so we audit the exact first trade closure
        state_t2 = bot.step_tick()

        # Step 6: If not already auto-closed by target barrier, close position and verify trade history & audit
        still_open = broker.get_open_positions()
        if still_open:
            broker.close_position(
                still_open[0].id,
                exit_price=quote_t2.bid_price if pos.direction == "LONG" else quote_t2.ask_price,
                exit_reason="E2E_TEST_TAKE_PROFIT",
                bid_price=quote_t2.bid_price,
                ask_price=quote_t2.ask_price,
                use_bid_ask=True,
            )

        closed_trades = broker.get_closed_trades()
        assert len(closed_trades) == 1
        tr = closed_trades[0]
        assert tr.ticker == "NVDA"
        assert tr.net_pnl > 0.0
        assert tr.friction_fee > 0.0

        summary = broker.get_account_summary()
        audit = broker.get_performance_audit()
        assert summary["paper_trading_only"] is True
        assert summary["total_equity"] > 100000.0
        assert summary["realized_pnl"] == pytest.approx(tr.net_pnl, abs=0.05)
        assert audit["total_trades"] == 1
        assert audit["win_rate_pct"] == 100.0
        assert audit["total_transaction_costs"] > 0.0
        assert state_t2["bot_status"]["paper_trading_only"] is True
        assert state_t2["data_feed_status"]["data_mode"] == "LIVE_MARKET_DATA"


# ==============================================================================
# 15. Stock Search & 1-Click Bot-Managed Trade Execution
# ==============================================================================


class TestStockSearchAndBotManagedTrade:
    def test_search_instruments_by_name_symbol_and_custom_ticker(self, isolated_paper_broker: PaperBroker):
        engine = MarketPredictionEngine()
        bot = LiveBotController(
            engine=engine,
            broker=isolated_paper_broker,
            initial_watchlist=["NVDA"],
        )
        nvda_df = _generate_deterministic_ohlcv(base_price=138.0, bars=260, seed=11)
        bot.analyses["NVDA"] = engine.analyze_ticker("NVDA", df_override=nvda_df)
        bot.base_prices["NVDA"] = 138.0
        bot.live_prices["NVDA"] = 138.0
        bot._initialized = True

        # 1. Search by company name ("Apple")
        apple_res = bot.search_instruments(query="Apple", category="ALL")
        assert any(r["ticker"] == "AAPL" and "Apple" in r["name"] for r in apple_res)

        # 2. Search Indian NSE equity by company name ("Reliance")
        rel_res = bot.search_instruments(query="Reliance", category="NSE")
        assert any(r["ticker"] == "RELIANCE.NS" for r in rel_res)

        # 3. Search custom unknown ticker symbol ("SNOWXYZ") offers custom lookup entry
        custom_res = bot.search_instruments(query="SNOWXYZ", category="ALL")
        assert any(r["ticker"] == "SNOWXYZ" and r.get("is_custom") is True for r in custom_res)

    def test_place_bot_managed_trade_auto_sets_barriers_and_bot_handles_exit(self, tmp_path: Path):
        now_utc = datetime.now(timezone.utc)
        pltr_df = _generate_deterministic_ohlcv(base_price=65.0, bars=260, seed=55)
        last_close = float(pltr_df["Close"].iloc[-1])

        quote_entry = LiveQuote(
            ticker="PLTR",
            bid_price=round(last_close - 0.02, 2),
            ask_price=round(last_close + 0.02, 2),
            last_price=last_close,
            timestamp_utc=now_utc,
            received_at_utc=now_utc,
            exchange="NASDAQ",
            is_delayed=False,
            is_stale=False,
            age_seconds=0.1,
            latency_ms=5.0,
            provider_name="MockLiveFeed",
            day_open=last_close,
            day_high=last_close + 0.2,
            day_low=last_close - 0.2,
            prev_close=last_close,
            status="LIVE",
        )
        feed = MockLiveMarketDataProvider({"PLTR": quote_entry})
        feed.set_bars("PLTR", pltr_df)

        engine = MarketPredictionEngine()
        broker = PaperBroker(
            account_id="BOT_TRADE_TEST",
            initial_capital=100000.0,
            db_path=tmp_path / "bot_trade.db",
        )
        bot = LiveBotController(
            engine=engine,
            broker=broker,
            data_provider=feed,
            initial_watchlist=["PLTR"],
        )
        bot.analyses["PLTR"] = engine.analyze_ticker("PLTR", df_override=pltr_df)
        bot.base_prices["PLTR"] = last_close
        bot.live_prices["PLTR"] = last_close
        bot.price_series["PLTR"] = [{"time": "09:30:00", "price": last_close, "high": last_close, "low": last_close}]
        bot.calendar.get_session_info = lambda tk, **kw: MarketSessionInfo(
            ticker=tk,
            market_type="US_EQUITIES",
            state=MarketState.OPEN,
            is_tradable=True,
            exchange_name="NASDAQ",
            local_timezone="America/New_York",
            local_time_str="10:30:00 EDT",
            session_schedule="09:30-16:00 ET",
            reason="Regular Trading Hours",
            next_state=MarketState.POST_MARKET,
            next_state_time_utc="",
            seconds_to_next_state=18000,
            countdown_display="05h 00m 00s",
            tick_frozen=False,
        )
        bot._initialized = True

        # Place a 1-click Bot Auto-Trade on PLTR
        res = bot.place_bot_managed_trade(ticker="PLTR", direction="AUTO")
        assert res["status"] == "FILLED"
        assert res["ticker"] == "PLTR"
        assert res["direction"] in ("LONG", "SHORT")
        assert res["bot_armed"] is True
        assert "PLTR" in bot.armed_tickers
        assert res["target_price"] > 0
        assert res["stop_price"] > 0

        open_pos = broker.get_open_positions()
        assert len(open_pos) == 1
        pos = open_pos[0]

        # Now feed a quote that crosses the Bot-Managed Target Price and verify the Bot automatically closes it!
        tp_cross = round(pos.target_price * (1.02 if pos.direction == "LONG" else 0.98), 2)
        quote_tp = LiveQuote(
            ticker="PLTR",
            bid_price=round(tp_cross - 0.02, 2),
            ask_price=round(tp_cross + 0.02, 2),
            last_price=tp_cross,
            timestamp_utc=now_utc + timedelta(seconds=10),
            received_at_utc=now_utc + timedelta(seconds=10),
            exchange="NASDAQ",
            is_delayed=False,
            is_stale=False,
            age_seconds=0.1,
            latency_ms=4.5,
            provider_name="MockLiveFeed",
            day_open=last_close,
            day_high=max(last_close, tp_cross),
            day_low=min(last_close, tp_cross),
            prev_close=last_close,
            status="LIVE",
        )
        feed.set_quote(quote_tp)
        bot.is_running = False  # Don't open a second position after closing the first
        bot.step_tick()

        assert len(broker.get_open_positions()) == 0
        closed = broker.get_closed_trades()
        assert len(closed) == 1
        assert closed[0].ticker == "PLTR"
        assert closed[0].net_pnl > 0

