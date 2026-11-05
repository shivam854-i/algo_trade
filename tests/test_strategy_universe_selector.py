"""Automated unit tests for UniverseSelector (Data Quality, ADV, Spread, Volatility, Bounded Baskets)."""

from unittest.mock import MagicMock
import numpy as np
import pandas as pd
import pytest

from src.data.provider_base import LiveQuote
from src.strategy.universe_selector import (
    CandidateEvaluation,
    UniverseSelectionCriteria,
    UniverseSelectionResult,
    UniverseSelector,
)


class TestUniverseSelector:
    """Unit tests for UniverseSelector and CandidateEvaluation."""

    def _make_dummy_ohlcv(
        self,
        n_bars: int = 30,
        price: float = 100.0,
        volume: float = 100_000.0,
        volatility: float = 0.01,
    ) -> pd.DataFrame:
        """Generates synthetic OHLCV dataframe with realistic price dispersion."""
        np.random.seed(42)
        returns = np.random.normal(0.0, volatility, n_bars)
        prices = price * np.exp(np.cumsum(returns))
        highs = prices * (1.0 + np.abs(np.random.normal(0.005, 0.002, n_bars)))
        lows = prices * (1.0 - np.abs(np.random.normal(0.005, 0.002, n_bars)))
        opens = (prices + lows) / 2.0
        vols = np.full(n_bars, volume)

        df = pd.DataFrame(
            {
                "Open": opens,
                "High": highs,
                "Low": lows,
                "Close": prices,
                "Volume": vols,
            }
        )
        return df

    def test_data_quality_score(self):
        """Verifies calculation of Q_data and rejection when data quality < 0.90."""
        selector = UniverseSelector()

        # 1. Perfect data -> Q_data = 1.0
        df_clean = self._make_dummy_ohlcv(n_bars=30)
        q_clean, r_miss, r_zero = selector.evaluate_data_quality(df_clean, "US_EQUITIES")
        assert q_clean == 1.0
        assert r_miss == 0.0
        assert r_zero == 0.0

        # 2. 10% missing rows -> Q_data = 1.0 - (0.60 * 0.10) = 0.94 >= 0.90
        df_missing = df_clean.copy()
        df_missing.iloc[0:3, df_missing.columns.get_loc("Close")] = np.nan
        q_miss, r_miss, _ = selector.evaluate_data_quality(df_missing, "US_EQUITIES")
        assert q_miss == 0.94
        assert r_miss == 0.10

        # 3. 15% missing rows and 15% zero volume rows -> Q_data = 1.0 - (0.60*0.15 + 0.40*0.15) = 1.0 - 0.15 = 0.85
        df_corrupt = df_clean.copy()
        df_corrupt.iloc[0:3, df_corrupt.columns.get_loc("Close")] = np.nan
        df_corrupt.iloc[3:6, df_corrupt.columns.get_loc("Volume")] = 0.0  # 3 / 20 = 0.15 on 20 bars
        # Let's use 20 bars exactly
        df_corrupt_20 = df_clean.iloc[:20].copy()
        df_corrupt_20.iloc[0:3, df_corrupt_20.columns.get_loc("Close")] = np.nan
        df_corrupt_20.iloc[3:6, df_corrupt_20.columns.get_loc("Volume")] = 0.0
        q_bad, r_m, r_z = selector.evaluate_data_quality(df_corrupt_20, "US_EQUITIES")
        assert q_bad == 0.85
        assert r_m == 0.15
        assert r_z == 0.15

        # 4. FOREX ignores zero volume
        q_forex, _, r_z_fx = selector.evaluate_data_quality(df_corrupt_20, "FOREX")
        assert r_z_fx == 0.0
        # Only missing penalized: 1.0 - 0.15 = 0.85
        assert q_forex == 0.85

        # 5. Empty dataframe returns 0.0
        q_empty, _, _ = selector.evaluate_data_quality(pd.DataFrame(), "US_EQUITIES")
        assert q_empty == 0.0

    def test_adv_liquidity_gates(self):
        """Verifies institutional ADV thresholds across US, NSE, and Crypto."""
        selector = UniverseSelector()

        # US Equities: threshold $5,000,000 USD
        # 100 price * 60,000 vol = $6,000,000 -> Pass
        df_us_pass = self._make_dummy_ohlcv(price=100.0, volume=60_000.0)
        eval_us_pass = selector.evaluate_instrument("NVDA", df_us_pass, market_type="US_EQUITIES")
        assert "INSUFFICIENT_LIQUIDITY" not in " ".join(eval_us_pass.rejection_reasons)

        # 100 price * 40,000 vol = $4,000,000 -> Fail
        df_us_fail = self._make_dummy_ohlcv(price=100.0, volume=40_000.0)
        eval_us_fail = selector.evaluate_instrument("NVDA", df_us_fail, market_type="US_EQUITIES")
        assert any("INSUFFICIENT_LIQUIDITY" in r for r in eval_us_fail.rejection_reasons)
        assert abs(eval_us_fail.adv - 4_000_000.0) < 100_000.0
        assert eval_us_fail.adv_threshold == 5_000_000.0

        # NSE Cash: threshold ₹50,000,000 INR
        # 1,000 price * 60,000 vol = ₹60,000,000 -> Pass
        df_nse_pass = self._make_dummy_ohlcv(price=1000.0, volume=60_000.0)
        eval_nse_pass = selector.evaluate_instrument("RELIANCE.NS", df_nse_pass, market_type="INDIAN_NSE")
        assert "INSUFFICIENT_LIQUIDITY" not in " ".join(eval_nse_pass.rejection_reasons)

        # 1,000 price * 40,000 vol = ₹40,000,000 -> Fail
        df_nse_fail = self._make_dummy_ohlcv(price=1000.0, volume=40_000.0)
        eval_nse_fail = selector.evaluate_instrument("RELIANCE.NS", df_nse_fail, market_type="INDIAN_NSE")
        assert any("INSUFFICIENT_LIQUIDITY" in r for r in eval_nse_fail.rejection_reasons)

        # Crypto: threshold $10,000,000 USD
        df_crypto_pass = self._make_dummy_ohlcv(price=50_000.0, volume=250.0)  # $12.5M
        eval_crypto_pass = selector.evaluate_instrument("BTC-USD", df_crypto_pass, market_type="CRYPTO")
        assert "INSUFFICIENT_LIQUIDITY" not in " ".join(eval_crypto_pass.rejection_reasons)

        df_crypto_fail = self._make_dummy_ohlcv(price=50_000.0, volume=150.0)  # $7.5M
        eval_crypto_fail = selector.evaluate_instrument("BTC-USD", df_crypto_fail, market_type="CRYPTO")
        assert any("INSUFFICIENT_LIQUIDITY" in r for r in eval_crypto_fail.rejection_reasons)

    def test_spread_gate(self):
        """Verifies bid-ask spread gate (max 25 bps)."""
        selector = UniverseSelector()
        df = self._make_dummy_ohlcv(price=100.0, volume=100_000.0)

        # Live quote with 15 bps spread -> Pass
        # mid = 100.0, spread = 0.15 -> 15 bps
        quote_tight = LiveQuote(
            ticker="AAPL",
            bid_price=99.925,
            ask_price=100.075,
            last_price=100.0,
            volume=100000,
        )
        eval_tight = selector.evaluate_instrument("AAPL", df, live_quote=quote_tight, market_type="US_EQUITIES")
        assert "SPREAD_TOO_WIDE" not in " ".join(eval_tight.rejection_reasons)

        # Live quote with 28 bps spread -> Fail
        # mid = 100.0, spread = 0.28 -> 28 bps
        quote_wide = LiveQuote(
            ticker="AAPL",
            bid_price=99.86,
            ask_price=100.14,
            last_price=100.0,
            volume=100000,
        )
        eval_wide = selector.evaluate_instrument("AAPL", df, live_quote=quote_wide, market_type="US_EQUITIES")
        assert any("SPREAD_TOO_WIDE" in r for r in eval_wide.rejection_reasons)

    def test_volatility_tradability_bounds(self):
        """Verifies minimum tradability floor (8%) and maximum risk ceiling (100%)."""
        selector = UniverseSelector()

        # 1. Stagnant volatility (< 8%)
        # Standard deviation ~ 0.001 * 15.87 ~ 1.6% vol
        df_flat = self._make_dummy_ohlcv(price=100.0, volume=100_000.0, volatility=0.001)
        eval_flat = selector.evaluate_instrument("STAGNANT", df_flat, market_type="US_EQUITIES")
        assert any("STAGNANT_VOLATILITY" in r for r in eval_flat.rejection_reasons)

        # 2. Optimal tradability volatility (~ 25%)
        # Daily vol ~ 0.016 * 15.87 ~ 25% vol
        df_good = self._make_dummy_ohlcv(price=100.0, volume=100_000.0, volatility=0.016)
        eval_good = selector.evaluate_instrument("HEALTHY", df_good, market_type="US_EQUITIES")
        assert "VOLATILITY" not in " ".join(eval_good.rejection_reasons)

        # 3. Excessive volatility (> 100%)
        # Daily vol ~ 0.08 * 15.87 ~ 127% vol
        df_wild = self._make_dummy_ohlcv(price=100.0, volume=100_000.0, volatility=0.08)
        eval_wild = selector.evaluate_instrument("MEME", df_wild, market_type="US_EQUITIES")
        assert any("EXCESSIVE_VOLATILITY" in r for r in eval_wild.rejection_reasons)

    def test_composite_score(self):
        """Verifies composite scoring logic."""
        selector = UniverseSelector()
        score = selector.compute_composite_score(
            adv=10_000_000.0,
            adv_threshold=5_000_000.0,
            spread_bps=10.0,
            data_quality=1.0,
            annualized_vol=0.30,
        )
        assert 0.0 <= score <= 1.0
        assert score > 0.50  # Should be a strong composite score

    def test_auto_select_basket_bounding(self):
        """Verifies auto-selection returns bounded basket (3-6) and handles edge cases."""
        mock_downloader = MagicMock()

        # Return 10 candidate dataframes: first 7 good, next 3 bad ADV
        def mock_download(ticker, **kwargs):
            if ticker in ["A", "B", "C", "D", "E", "F", "G"]:
                return self._make_dummy_ohlcv(price=100.0, volume=100_000.0, volatility=0.016)
            else:
                return self._make_dummy_ohlcv(price=10.0, volume=1_000.0, volatility=0.016)

        mock_downloader.download_ticker.side_effect = mock_download
        mock_downloader.get_market_type.return_value = "US"

        candidates = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
        selector = UniverseSelector(downloader=mock_downloader)

        # Target size 5 -> returns 5
        res_5 = selector.auto_select_basket("US", target_size=5, candidate_tickers=candidates)
        assert len(res_5.selected_instruments) == 5
        assert res_5.target_size == 5
        assert res_5.passed_count == 7
        assert res_5.rejected_count == 3
        assert "Auto-selected 5" in res_5.summary_rationale

        # Target size 1 -> clamped to min 3
        res_1 = selector.auto_select_basket("US", target_size=1, candidate_tickers=candidates)
        assert len(res_1.selected_instruments) == 3
        assert res_1.target_size == 3

        # Target size 10 -> clamped to max 6
        res_10 = selector.auto_select_basket("US", target_size=10, candidate_tickers=candidates)
        assert len(res_10.selected_instruments) == 6
        assert res_10.target_size == 6

        # Zero passing candidates
        mock_downloader.download_ticker.side_effect = lambda t, **kw: self._make_dummy_ohlcv(price=1.0, volume=1.0)
        res_zero = selector.auto_select_basket("US", target_size=5, candidate_tickers=["X", "Y"])
        assert len(res_zero.selected_instruments) == 0
        assert res_zero.passed_count == 0
        assert "REJECTION: Zero candidate instruments" in res_zero.summary_rationale

    def test_serialization(self):
        """Verifies CandidateEvaluation and UniverseSelectionResult dictionary serialization."""
        eval_item = CandidateEvaluation(
            ticker="AAPL",
            market="US_EQUITIES",
            passed_all_gates=True,
            data_quality_score=1.0,
            missing_bar_ratio=0.0,
            zero_volume_ratio=0.0,
            adv=10_000_000.0,
            adv_currency="$",
            adv_threshold=5_000_000.0,
            spread_bps=5.0,
            annualized_volatility=0.25,
            composite_score=0.88,
        )
        d_eval = eval_item.to_dict()
        assert d_eval["ticker"] == "AAPL"
        assert d_eval["passed_all_gates"] is True

        result = UniverseSelectionResult(
            market="US_EQUITIES",
            target_size=5,
            selected_instruments=["AAPL"],
            evaluations={"AAPL": eval_item},
            passed_count=1,
            rejected_count=0,
            summary_rationale="Selected AAPL",
        )
        d_res = result.to_dict()
        assert d_res["market"] == "US_EQUITIES"
        assert "AAPL" in d_res["evaluations"]
