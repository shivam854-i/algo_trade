"""Unit and Integration Tests for Part B: Efficiency & Optimization.

Verifies:
1. Lazy import of `torch` and `lightgbm` (subprocesses confirm modules are not imported at startup).
2. Model Caching keyed by `(ticker, data_hash, config_hash)` in `MarketPredictionEngine` and models.
3. Observer Gating in `MarketObserverDaemon` on NSE trading hours (09:15-15:30 IST, Mon-Fri, excluding holidays).
4. Batch data ingestion and incremental bar append in `MarketDataDownloader`.
5. Backtest engine vectorization output remains bit-identical to baseline.
"""

from datetime import datetime, time as dt_time, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import pytest

from src.backtest.engine import BacktestEngine
from src.data.downloader import MarketDataDownloader
from src.models.gpu_acceleration import GPUManager, TorchSequenceForecaster
from src.models.meta_labeler import MetaLabelingEngine
from src.observer.monitor import MarketObserverDaemon
from src.pipeline import MarketPredictionEngine


class TestLazyImports:
    """Verifies that top-level imports do NOT eagerly pull in PyTorch or LightGBM."""

    def test_pipeline_import_does_not_load_torch(self):
        cmd = [
            sys.executable,
            "-c",
            "import sys; import src.pipeline; sys.exit(0 if 'torch' not in sys.modules else 1)",
        ]
        res = subprocess.run(cmd, capture_output=True)
        assert res.returncode == 0, "import src.pipeline eagerly imported torch!"

    def test_pipeline_import_does_not_load_lightgbm(self):
        cmd = [
            sys.executable,
            "-c",
            "import sys; import src.pipeline; sys.exit(0 if 'lightgbm' not in sys.modules else 1)",
        ]
        res = subprocess.run(cmd, capture_output=True)
        assert res.returncode == 0, "import src.pipeline eagerly imported lightgbm!"

    def test_backtest_engine_import_does_not_load_torch(self):
        cmd = [
            sys.executable,
            "-c",
            "import sys; import src.backtest.engine; sys.exit(0 if 'torch' not in sys.modules else 1)",
        ]
        res = subprocess.run(cmd, capture_output=True)
        assert res.returncode == 0, "import src.backtest.engine eagerly imported torch!"

    def test_gpu_acceleration_import_does_not_load_torch(self):
        cmd = [
            sys.executable,
            "-c",
            "import sys; import src.models.gpu_acceleration; sys.exit(0 if 'torch' not in sys.modules else 1)",
        ]
        res = subprocess.run(cmd, capture_output=True)
        assert res.returncode == 0, "import src.models.gpu_acceleration eagerly imported torch!"


class TestModelCaching:
    """Verifies model caching keyed by (ticker, data_hash, config_hash)."""

    def test_data_hash_determinism(self):
        dates = pd.date_range("2026-01-01", periods=50, freq="D", tz="UTC")
        df1 = pd.DataFrame(
            {
                "Open": np.linspace(100, 150, 50),
                "High": np.linspace(105, 155, 50),
                "Low": np.linspace(95, 145, 50),
                "Close": np.linspace(102, 152, 50),
                "Volume": np.full(50, 1000.0),
            },
            index=dates,
        )
        df2 = df1.copy()

        h1 = MarketPredictionEngine.compute_data_hash(df1)
        h2 = MarketPredictionEngine.compute_data_hash(df2)
        assert h1 == h2
        assert len(h1) == 16

        # Altering a row mutates hash
        df3 = df1.copy()
        df3.iloc[-1, df3.columns.get_loc("Close")] = 999.0
        h3 = MarketPredictionEngine.compute_data_hash(df3)
        assert h3 != h1

    def test_config_hash_determinism(self):
        engine = MarketPredictionEngine()
        cfg_hash_1 = engine.compute_config_hash()
        cfg_hash_2 = engine.compute_config_hash()
        assert cfg_hash_1 == cfg_hash_2
        assert len(cfg_hash_1) == 16

    def test_analyze_ticker_model_caching(self):
        engine = MarketPredictionEngine()
        engine.clear_model_cache()

        dates = pd.date_range("2026-01-01", periods=60, freq="D", tz="UTC")
        synthetic_df = pd.DataFrame(
            {
                "Open": np.linspace(100, 160, 60),
                "High": np.linspace(105, 165, 60),
                "Low": np.linspace(95, 155, 60),
                "Close": np.linspace(102, 162, 60),
                "Volume": np.full(60, 50000.0),
            },
            index=dates,
        )

        res1 = engine.analyze_ticker("AAPL", ohlcv_df=synthetic_df)
        assert res1 is not None
        assert len(engine._model_cache) == 1

        # Second call with identical data hits cache without refitting
        res2 = engine.analyze_ticker("AAPL", ohlcv_df=synthetic_df)
        assert res2 is not None
        assert len(engine._model_cache) == 1
        assert res1.meta_prediction.direction_label == res2.meta_prediction.direction_label
        assert res1.meta_prediction.success_probability == res2.meta_prediction.success_probability

        # Force refresh clears or bypasses cache
        res3 = engine.analyze_ticker("AAPL", ohlcv_df=synthetic_df, force_refresh=True)
        assert res3 is not None
        assert len(engine._model_cache) == 1

        # Explicit cache clearance
        engine.clear_model_cache("AAPL")
        assert len(engine._model_cache) == 0


class TestObserverGating:
    """Verifies that the market observer polls only during NSE regular trading hours."""

    def setup_method(self):
        self.daemon = MarketObserverDaemon(poll_interval_seconds=900, gate_nse=True)

    def test_weekend_gating(self):
        # Saturday Nov 7, 2026 @ 12:00 UTC
        sat_utc = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
        is_open, wait_secs, reason = self.daemon.get_nse_market_status(sat_utc)
        assert is_open is False
        assert "Weekend" in reason
        assert wait_secs > 0

    def test_statutory_holiday_gating(self):
        # Republic Day: Jan 26, 2026 (Monday)
        holiday_utc = datetime(2026, 1, 26, 5, 0, tzinfo=timezone.utc)
        is_open, wait_secs, reason = self.daemon.get_nse_market_status(holiday_utc)
        assert is_open is False
        assert "Statutory Holiday" in reason
        assert "Republic Day" in reason
        assert wait_secs > 0

    def test_overnight_pre_market_gating(self):
        # Wednesday 08:30 IST -> 03:00 UTC
        pre_utc = datetime(2026, 11, 11, 3, 0, tzinfo=timezone.utc)
        is_open, wait_secs, reason = self.daemon.get_nse_market_status(pre_utc)
        assert is_open is False
        assert "Pre-Market" in reason
        # 45 minutes until 09:15 IST = 2700 seconds
        assert wait_secs == 2700

    def test_regular_trading_hours_active(self):
        # Wednesday 11:30 IST -> 06:00 UTC
        open_utc = datetime(2026, 11, 11, 6, 0, tzinfo=timezone.utc)
        is_open, secs_to_close, reason = self.daemon.get_nse_market_status(open_utc)
        assert is_open is True
        assert "Regular Trading Session Live" in reason
        # 4 hours to 15:30 IST close = 14400 seconds
        assert secs_to_close == 14400

    def test_post_market_gating(self):
        # Wednesday 16:00 IST -> 10:30 UTC
        post_utc = datetime(2026, 11, 11, 10, 30, tzinfo=timezone.utc)
        is_open, wait_secs, reason = self.daemon.get_nse_market_status(post_utc)
        assert is_open is False
        assert "Post-Market" in reason
        assert wait_secs > 0

    def test_next_bar_sleep_alignment(self):
        # Align sleep duration to 15-minute boundary with 1s margin
        test_utc = datetime(2026, 11, 11, 6, 2, 10, tzinfo=timezone.utc)
        sleep_secs = self.daemon.get_next_bar_sleep_seconds(test_utc)
        assert 1 <= sleep_secs <= 900


class TestDownloaderBatchAndIncremental:
    """Verifies batch multi-ticker ingestion and incremental bar caching."""

    def test_incremental_bar_cache_append(self, tmp_path: Path):
        downloader = MarketDataDownloader(cache_dir=tmp_path)
        cache_file = tmp_path / "AAPL_1d_2y.csv"

        # Create historical cache ending on 2026-06-01
        dates_hist = pd.date_range("2026-05-01", periods=10, freq="D", tz="UTC")
        df_hist = pd.DataFrame(
            {
                "Open": [150.0] * 10,
                "High": [155.0] * 10,
                "Low": [145.0] * 10,
                "Close": [152.0] * 10,
                "Volume": [10000.0] * 10,
            },
            index=dates_hist,
        )
        df_hist.to_csv(cache_file)

        # Set cache mtime to 25 hours ago so TTL is expired and incremental fetch is triggered
        import time as time_mod
        old_time = time_mod.time() - 3600 * 25
        os.utime(cache_file, (old_time, old_time))

        # Mock yfinance to return new bars starting from 2026-05-10
        dates_new = pd.date_range("2026-05-10", periods=5, freq="D", tz="UTC")
        df_new = pd.DataFrame(
            {
                "Open": [160.0] * 5,
                "High": [165.0] * 5,
                "Low": [158.0] * 5,
                "Close": [162.0] * 5,
                "Volume": [20000.0] * 5,
            },
            index=dates_new,
        )

        class MockTicker:
            def __init__(self, *args, **kwargs):
                pass

            def history(self, **kwargs):
                return df_new

        import yfinance as yf
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(yf, "Ticker", MockTicker)

        try:
            combined = downloader.download_ticker("AAPL", period="2y", interval="1d")
            # Should have merged 10 initial rows + 4 unique new rows (with 2026-05-10 deduplicated)
            assert len(combined) == 14
            assert combined.index[0] == dates_hist[0]
            assert combined.index[-1] == dates_new[-1]
        finally:
            monkeypatch.undo()

    def test_batch_download_parsing(self, tmp_path: Path):
        downloader = MarketDataDownloader(cache_dir=tmp_path)

        dates = pd.date_range("2026-06-01", periods=5, freq="D", tz="UTC")
        # Build mock multi-ticker dataframe
        df_aapl = pd.DataFrame(
            {"Open": [100.0] * 5, "High": [105.0] * 5, "Low": [95.0] * 5, "Close": [102.0] * 5, "Volume": [1000.0] * 5},
            index=dates,
        )
        df_msft = pd.DataFrame(
            {"Open": [200.0] * 5, "High": [205.0] * 5, "Low": [195.0] * 5, "Close": [202.0] * 5, "Volume": [2000.0] * 5},
            index=dates,
        )
        cols = pd.MultiIndex.from_tuples(
            [("AAPL", c) for c in df_aapl.columns] + [("MSFT", c) for c in df_msft.columns],
            names=["Ticker", "Price"],
        )
        mock_batch_df = pd.DataFrame(
            np.hstack([df_aapl.values, df_msft.values]),
            index=dates,
            columns=cols,
        )

        import yfinance as yf
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(yf, "download", lambda *args, **kwargs: mock_batch_df)

        try:
            res = downloader.download_batch(["AAPL", "MSFT"], period="5d", interval="1d")
            assert "AAPL" in res
            assert "MSFT" in res
            assert len(res["AAPL"]) == 5
            assert len(res["MSFT"]) == 5
            assert list(res["AAPL"].columns) == ["Open", "High", "Low", "Close", "Volume"]
        finally:
            monkeypatch.undo()


class TestBacktestVectorizationBitIdentical:
    """Verifies that backtest metrics remain bit-identical after vectorization."""

    def test_aapl_backtest_metrics_bit_identical(self):
        engine = BacktestEngine(initial_capital=10000.0)
        res = engine.run("AAPL", period="6mo", interval="1d")
        assert res is not None

        # Verify key baseline invariants
        assert res.total_return_pct == 0.68
        assert res.final_equity == 10068.0
        assert res.buy_hold_return_pct == 5.36
        assert res.cagr_pct == 3.88
        assert res.sharpe_ratio == -0.55
        assert res.sortino_ratio == -0.61
        assert res.max_drawdown_pct == 0.16
        assert res.total_trades == 10
        assert res.winning_trades == 5
        assert res.losing_trades == 5
        assert res.win_rate_pct == 50.0
        assert res.profit_factor == 0.93

    def test_reliance_backtest_metrics_bit_identical(self):
        engine = BacktestEngine(initial_capital=10000.0)
        res = engine.run("RELIANCE.NS", period="6mo", interval="1d")
        assert res is not None

        assert res.total_return_pct == 0.75
        assert res.sharpe_ratio == 0.0
        assert res.max_drawdown_pct == 0.0
        assert res.total_trades == 0
        assert res.winning_trades == 0
        assert res.losing_trades == 0
        assert res.final_equity == 10074.88
