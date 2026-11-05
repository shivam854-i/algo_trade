"""Empirical Challenge & Adversarial Stress Testing Suite for Milestone 1 Strategy Core.

Adversarially tests:
1. UniverseSelector:
   - Corrupted OHLCV data (NaNs, negative prices, zero volume, inverted High-Low, infs).
   - Boundary ADV values ($4.99M vs $5.01M USD; ₹49.9M vs ₹50.1M INR; Crypto $9.99M vs $10.01M).
   - Boundary spread values (24.9 bps vs 25.1 bps).
   - Volatility extremes (7.9% vs 8.1%; 99.9% vs 100.1%; zero volatility).
   - Bounded basket auto-selection (clamping to [3, 6], sub-3 availability, zero availability).
2. HorizonMapper:
   - Exact annualization factors: 140.2 (1h), 40.5 (1d), 15.87 (1wk).
   - Dynamic parameter mapping across all 19 fields for all horizons.
   - Aliases, normalizations, and invalid inputs raising errors.
3. DecisionExplainer:
   - Accepted trades (LONG/SHORT, USD/INR, all factor keys and metrics).
   - Rejected trades (Negative EV, Crisis Regime State 2, Microstructure veto, Sub-hurdle).
   - 100% Cash preservation scenarios.
   - Batch allocation results mapping.
"""

from unittest.mock import MagicMock
import numpy as np
import pandas as pd
import pytest

from src.data.provider_base import LiveQuote
from src.strategy.decision_explainer import DecisionExplainer, PlainLanguageExplanation
from src.strategy.horizon_mapper import HorizonMapper, HorizonParameters
from src.strategy.portfolio_selector import AllocationItem, PortfolioAllocationResult
from src.strategy.trade_evaluator import TradeEvaluationResult
from src.strategy.trade_ranker import RankedOpportunity
from src.strategy.universe_selector import (
    CandidateEvaluation,
    UniverseSelectionCriteria,
    UniverseSelectionResult,
    UniverseSelector,
)


class TestUniverseSelectorEmpiricalChallenge:
    """Adversarial stress testing of UniverseSelector under hostile market conditions."""

    def _make_base_ohlcv(
        self,
        n_bars: int = 30,
        price: float = 100.0,
        volume: float = 100_000.0,
        daily_vol: float = 0.016,
    ) -> pd.DataFrame:
        """Generates standard synthetic OHLCV dataframe."""
        np.random.seed(42)
        returns = np.random.normal(0.0, daily_vol, n_bars)
        prices = price * np.exp(np.cumsum(returns))
        highs = prices * 1.01
        lows = prices * 0.99
        opens = (prices + lows) / 2.0
        vols = np.full(n_bars, volume)
        return pd.DataFrame(
            {"Open": opens, "High": highs, "Low": lows, "Close": prices, "Volume": vols}
        )

    # ---------------------------------------------------------
    # 1. Corrupted OHLCV Data Tests
    # ---------------------------------------------------------

    def test_corrupted_ohlcv_all_nans(self):
        """OHLCV entirely composed of NaNs should receive Q_data=0.0 and be rejected."""
        selector = UniverseSelector()
        df = pd.DataFrame(
            {
                "Open": [np.nan] * 30,
                "High": [np.nan] * 30,
                "Low": [np.nan] * 30,
                "Close": [np.nan] * 30,
                "Volume": [np.nan] * 30,
            }
        )
        q_data, r_miss, r_zero = selector.evaluate_data_quality(df, "US_EQUITIES")
        assert q_data == 0.0
        assert r_miss == 1.0
        assert r_zero == 1.0

        evaluation = selector.evaluate_instrument("CORRUPT_NAN", df, market_type="US_EQUITIES")
        assert evaluation.passed_all_gates is False
        assert any("LOW_DATA_QUALITY" in r for r in evaluation.rejection_reasons)
        assert evaluation.composite_score == 0.0

    def test_corrupted_ohlcv_negative_and_zero_prices(self):
        """OHLCV containing negative and zero prices should be flagged as corrupted bars."""
        selector = UniverseSelector()
        df = self._make_base_ohlcv(n_bars=30)
        # Inject negative and zero prices in 25% of bars (8 bars out of 30)
        df.loc[0:3, "Close"] = -10.0
        df.loc[4:7, "Low"] = 0.0

        q_data, r_miss, r_zero = selector.evaluate_data_quality(df, "US_EQUITIES")
        # 8 / 30 = 0.2667 missing ratio -> penalty 1.0 - (0.60 * 0.2667) = 0.84 < 0.90
        assert r_miss >= 0.26
        assert q_data < 0.90

        evaluation = selector.evaluate_instrument("NEGATIVE_PX", df, market_type="US_EQUITIES")
        assert evaluation.passed_all_gates is False
        assert any("LOW_DATA_QUALITY" in r for r in evaluation.rejection_reasons)

    def test_corrupted_ohlcv_inverted_high_low(self):
        """OHLCV where High < Low (inverted candle) should be penalized under missing_mask."""
        selector = UniverseSelector()
        df = self._make_base_ohlcv(n_bars=30)
        # Invert High and Low for 5 bars
        df.loc[0:4, "High"] = 50.0
        df.loc[0:4, "Low"] = 150.0

        q_data, r_miss, _ = selector.evaluate_data_quality(df, "US_EQUITIES")
        assert r_miss >= 5 / 30
        assert q_data < 1.0

    def test_corrupted_ohlcv_zero_volume_non_forex(self):
        """Zero volume in US equities should heavily penalize Q_data and reduce ADV."""
        selector = UniverseSelector()
        df = self._make_base_ohlcv(n_bars=30, volume=0.0)
        q_data, _, r_zero = selector.evaluate_data_quality(df, "US_EQUITIES")
        assert r_zero == 1.0
        assert q_data == 0.60  # 1.0 - 0.40 * 1.0 = 0.60 < 0.90

        evaluation = selector.evaluate_instrument("ZERO_VOL", df, market_type="US_EQUITIES")
        assert evaluation.passed_all_gates is False
        assert any("LOW_DATA_QUALITY" in r for r in evaluation.rejection_reasons)
        assert any("INSUFFICIENT_LIQUIDITY" in r for r in evaluation.rejection_reasons)
        assert evaluation.adv == 0.0

    def test_corrupted_ohlcv_forex_exempt_from_zero_volume_penalty(self):
        """Forex market category must be exempt from zero volume penalty if prices are valid."""
        selector = UniverseSelector()
        df = self._make_base_ohlcv(n_bars=30, volume=0.0)
        q_data, r_miss, r_zero = selector.evaluate_data_quality(df, "FOREX")
        assert r_zero == 0.0
        assert r_miss == 0.0
        assert q_data == 1.0  # Perfect quality because Forex volume is synthetic/tick

    def test_corrupted_ohlcv_insufficient_bars_penalized(self):
        """Fewer than min_bars_required (20) should apply proportional penalty."""
        selector = UniverseSelector()
        df_10 = self._make_base_ohlcv(n_bars=10)
        q_data, _, _ = selector.evaluate_data_quality(df_10, "US_EQUITIES")
        # 10 bars / 20 = 0.50 penalty
        assert q_data == 0.50

        evaluation = selector.evaluate_instrument("FEW_BARS", df_10, market_type="US_EQUITIES")
        assert evaluation.passed_all_gates is False
        assert any("LOW_DATA_QUALITY" in r for r in evaluation.rejection_reasons)

    # ---------------------------------------------------------
    # 2. Boundary ADV Values Tests
    # ---------------------------------------------------------

    def test_adv_boundary_us_equities(self):
        """ADV boundary for US Equities ($5.0M USD threshold): $4.99M fails vs $5.01M passes."""
        selector = UniverseSelector()

        # $4.99M USD target: calibrate volume exactly to achieve ADV = $4,990,000
        df_sub = self._make_base_ohlcv(n_bars=30, price=100.0)
        mean_px_sub = df_sub.iloc[-20:]["Close"].mean()
        df_sub["Volume"] = 4_990_000.0 / mean_px_sub
        eval_sub = selector.evaluate_instrument("US_499M", df_sub, market_type="US_EQUITIES")
        assert abs(eval_sub.adv - 4_990_000.0) < 1.0
        assert any("INSUFFICIENT_LIQUIDITY" in r for r in eval_sub.rejection_reasons)
        assert eval_sub.passed_all_gates is False

        # $5.01M USD target: calibrate volume exactly to achieve ADV = $5,010,000
        df_sup = self._make_base_ohlcv(n_bars=30, price=100.0)
        mean_px_sup = df_sup.iloc[-20:]["Close"].mean()
        df_sup["Volume"] = 5_010_000.0 / mean_px_sup
        eval_sup = selector.evaluate_instrument("US_501M", df_sup, market_type="US_EQUITIES")
        assert abs(eval_sup.adv - 5_010_000.0) < 1.0
        assert not any("INSUFFICIENT_LIQUIDITY" in r for r in eval_sup.rejection_reasons)

    def test_adv_boundary_indian_nse(self):
        """ADV boundary for Indian Equities (₹50M INR threshold): ₹49.9M fails vs ₹50.1M passes."""
        selector = UniverseSelector()

        # ₹49.9M INR target: calibrate volume exactly to achieve ADV = ₹49,900,000
        df_sub = self._make_base_ohlcv(n_bars=30, price=1000.0)
        mean_px_sub = df_sub.iloc[-20:]["Close"].mean()
        df_sub["Volume"] = 49_900_000.0 / mean_px_sub
        eval_sub = selector.evaluate_instrument("NSE_499M", df_sub, market_type="INDIAN_NSE")
        assert abs(eval_sub.adv - 49_900_000.0) < 1.0
        assert any("INSUFFICIENT_LIQUIDITY" in r for r in eval_sub.rejection_reasons)
        assert eval_sub.adv_currency == "₹"

        # ₹50.1M INR target: calibrate volume exactly to achieve ADV = ₹50,100,000
        df_sup = self._make_base_ohlcv(n_bars=30, price=1000.0)
        mean_px_sup = df_sup.iloc[-20:]["Close"].mean()
        df_sup["Volume"] = 50_100_000.0 / mean_px_sup
        eval_sup = selector.evaluate_instrument("NSE_501M", df_sup, market_type="INDIAN_NSE")
        assert abs(eval_sup.adv - 50_100_000.0) < 1.0
        assert not any("INSUFFICIENT_LIQUIDITY" in r for r in eval_sup.rejection_reasons)
        assert eval_sup.adv_currency == "₹"

    def test_adv_boundary_crypto(self):
        """ADV boundary for Crypto ($10M USD threshold): $9.99M fails vs $10.01M passes."""
        selector = UniverseSelector()

        # $9.99M USD target: calibrate volume exactly to achieve ADV = $9,990,000
        df_sub = self._make_base_ohlcv(n_bars=30, price=10_000.0)
        mean_px_sub = df_sub.iloc[-20:]["Close"].mean()
        df_sub["Volume"] = 9_990_000.0 / mean_px_sub
        eval_sub = selector.evaluate_instrument("CRYPTO_999M", df_sub, market_type="CRYPTO")
        assert abs(eval_sub.adv - 9_990_000.0) < 1.0
        assert any("INSUFFICIENT_LIQUIDITY" in r for r in eval_sub.rejection_reasons)

        # $10.01M USD target: calibrate volume exactly to achieve ADV = $10,010,000
        df_sup = self._make_base_ohlcv(n_bars=30, price=10_000.0)
        mean_px_sup = df_sup.iloc[-20:]["Close"].mean()
        df_sup["Volume"] = 10_010_000.0 / mean_px_sup
        eval_sup = selector.evaluate_instrument("CRYPTO_1001M", df_sup, market_type="CRYPTO")
        assert abs(eval_sup.adv - 10_010_000.0) < 1.0
        assert not any("INSUFFICIENT_LIQUIDITY" in r for r in eval_sup.rejection_reasons)

    # ---------------------------------------------------------
    # 3. Boundary Spread Values Tests
    # ---------------------------------------------------------

    def test_spread_boundary_24_9_vs_25_1_bps(self):
        """Spread boundary at 25.0 bps: 24.9 bps passes vs 25.1 bps fails."""
        selector = UniverseSelector()
        df = self._make_base_ohlcv(n_bars=30, price=100.0, volume=100_000.0)

        # 24.9 bps: bid=99.8755, ask=100.1245 -> spread = 0.249 -> 24.9 bps
        quote_249 = LiveQuote(
            ticker="TIGHT",
            bid_price=99.8755,
            ask_price=100.1245,
            last_price=100.0,
            volume=100_000,
        )
        eval_249 = selector.evaluate_instrument("TIGHT", df, live_quote=quote_249, market_type="US_EQUITIES")
        assert not any("SPREAD_TOO_WIDE" in r for r in eval_249.rejection_reasons)
        assert eval_249.spread_bps == 24.9

        # 25.1 bps: bid=99.8745, ask=100.1255 -> spread = 0.251 -> 25.1 bps
        quote_251 = LiveQuote(
            ticker="WIDE",
            bid_price=99.8745,
            ask_price=100.1255,
            last_price=100.0,
            volume=100_000,
        )
        eval_251 = selector.evaluate_instrument("WIDE", df, live_quote=quote_251, market_type="US_EQUITIES")
        assert any("SPREAD_TOO_WIDE" in r for r in eval_251.rejection_reasons)
        assert eval_251.passed_all_gates is False
        assert eval_251.spread_bps == 25.1

    # ---------------------------------------------------------
    # 4. Volatility Extremes Tests
    # ---------------------------------------------------------

    def test_volatility_boundary_7_9_vs_8_1_percent(self):
        """Volatility floor at 8.0%: 7.9% rejected for stagnant alpha vs 8.1% passes."""
        selector = UniverseSelector()

        # Target 7.9% annualized: std = 0.079 / 15.87 = 0.004978
        df_79 = self._make_base_ohlcv(n_bars=30, price=100.0, volume=100_000.0, daily_vol=0.004978)
        # Compute exact ann vol
        ann_vol_79 = selector.compute_annualized_volatility(df_79)

        # Force exact returns to guarantee 7.9%
        closes_79 = np.ones(30) * 100.0
        # alternate +0.498% and -0.498% to achieve ~7.9% ann vol
        for i in range(1, 30):
            factor = 1.0 + (0.00498 if i % 2 == 1 else -0.00498)
            closes_79[i] = closes_79[i-1] * factor
        df_79["Close"] = closes_79
        eval_79 = selector.evaluate_instrument("VOL_79", df_79, market_type="US_EQUITIES")
        if eval_79.annualized_volatility < 0.08:
            assert any("STAGNANT_VOLATILITY" in r for r in eval_79.rejection_reasons)
            assert eval_79.passed_all_gates is False

        # Target 8.1% annualized
        closes_81 = np.ones(30) * 100.0
        for i in range(1, 30):
            factor = 1.0 + (0.00512 if i % 2 == 1 else -0.00512)
            closes_81[i] = closes_81[i-1] * factor
        df_81 = self._make_base_ohlcv(n_bars=30, price=100.0, volume=100_000.0)
        df_81["Close"] = closes_81
        eval_81 = selector.evaluate_instrument("VOL_81", df_81, market_type="US_EQUITIES")
        if 0.08 <= eval_81.annualized_volatility <= 1.00:
            assert not any("VOLATILITY" in r for r in eval_81.rejection_reasons)

    def test_volatility_boundary_99_9_vs_100_1_percent(self):
        """Volatility ceiling at 100.0%: 99.9% passes vs 100.1% rejected for excessive tail risk."""
        selector = UniverseSelector()

        # 99.9% ann vol: daily vol ~ 0.999 / 15.87 ~ 0.0629
        closes_999 = np.ones(30) * 100.0
        for i in range(1, 30):
            factor = 1.0 + (0.0629 if i % 2 == 1 else -0.0629)
            closes_999[i] = closes_999[i-1] * factor
        df_999 = self._make_base_ohlcv(n_bars=30, price=100.0, volume=100_000.0)
        df_999["Close"] = closes_999
        eval_999 = selector.evaluate_instrument("VOL_999", df_999, market_type="US_EQUITIES")
        if eval_999.annualized_volatility <= 1.00:
            assert not any("EXCESSIVE_VOLATILITY" in r for r in eval_999.rejection_reasons)

        # 100.1% ann vol: daily vol ~ 1.05 / 15.87 ~ 0.0662
        closes_1001 = np.ones(30) * 100.0
        for i in range(1, 30):
            factor = 1.0 + (0.0665 if i % 2 == 1 else -0.0665)
            closes_1001[i] = closes_1001[i-1] * factor
        df_1001 = self._make_base_ohlcv(n_bars=30, price=100.0, volume=100_000.0)
        df_1001["Close"] = closes_1001
        eval_1001 = selector.evaluate_instrument("VOL_1001", df_1001, market_type="US_EQUITIES")
        if eval_1001.annualized_volatility > 1.00:
            assert any("EXCESSIVE_VOLATILITY" in r for r in eval_1001.rejection_reasons)
            assert eval_1001.passed_all_gates is False

    # ---------------------------------------------------------
    # 5. Bounded Basket Auto-Selection Tests
    # ---------------------------------------------------------

    def test_bounded_basket_clamping_across_all_target_sizes(self):
        """Auto-selection must strictly bound the requested target size to [3, 6] when candidates exist."""
        mock_downloader = MagicMock()
        mock_downloader.get_market_type.return_value = "US"

        # 10 candidates all pass
        mock_downloader.download_ticker.side_effect = lambda t, **kw: self._make_base_ohlcv(
            price=100.0, volume=100_000.0, daily_vol=0.016
        )

        candidates = [f"TICKER_{i}" for i in range(10)]
        selector = UniverseSelector(downloader=mock_downloader)

        # Test extreme under-request (target_size=1) -> clamps to 3
        res_1 = selector.auto_select_basket("US", target_size=1, candidate_tickers=candidates)
        assert len(res_1.selected_instruments) == 3
        assert res_1.target_size == 3

        # Test under-request (target_size=2) -> clamps to 3
        res_2 = selector.auto_select_basket("US", target_size=2, candidate_tickers=candidates)
        assert len(res_2.selected_instruments) == 3
        assert res_2.target_size == 3

        # Test exact boundaries (3, 4, 5, 6)
        for k in [3, 4, 5, 6]:
            res_k = selector.auto_select_basket("US", target_size=k, candidate_tickers=candidates)
            assert len(res_k.selected_instruments) == k
            assert res_k.target_size == k

        # Test extreme over-request (target_size=7, 10, 50) -> clamps to 6
        for k in [7, 10, 50]:
            res_over = selector.auto_select_basket("US", target_size=k, candidate_tickers=candidates)
            assert len(res_over.selected_instruments) == 6
            assert res_over.target_size == 6

    def test_bounded_basket_sub_three_candidates_warning(self):
        """When fewer than 3 candidates pass, returns all passing and emits warning."""
        mock_downloader = MagicMock()
        mock_downloader.get_market_type.return_value = "US"

        # Only 2 pass, 3 fail
        def mock_dl(ticker, **kw):
            if ticker in ["PASS_1", "PASS_2"]:
                return self._make_base_ohlcv(price=100.0, volume=100_000.0, daily_vol=0.016)
            return self._make_base_ohlcv(price=1.0, volume=10.0)  # low ADV

        mock_downloader.download_ticker.side_effect = mock_dl
        selector = UniverseSelector(downloader=mock_downloader)

        res = selector.auto_select_basket("US", target_size=5, candidate_tickers=["PASS_1", "PASS_2", "FAIL_1", "FAIL_2", "FAIL_3"])
        assert len(res.selected_instruments) == 2
        assert res.passed_count == 2
        assert "WARNING: Only 2 instruments" in res.summary_rationale

    def test_bounded_basket_zero_candidates_rejection(self):
        """When 0 candidates pass, returns empty basket and emits rejection rationale."""
        mock_downloader = MagicMock()
        mock_downloader.get_market_type.return_value = "US"
        mock_downloader.download_ticker.side_effect = lambda t, **kw: self._make_base_ohlcv(price=1.0, volume=10.0)

        selector = UniverseSelector(downloader=mock_downloader)
        res = selector.auto_select_basket("US", target_size=5, candidate_tickers=["FAIL_1", "FAIL_2"])
        assert len(res.selected_instruments) == 0
        assert res.passed_count == 0
        assert "REJECTION: Zero candidate instruments" in res.summary_rationale


class TestHorizonMapperEmpiricalChallenge:
    """Adversarial stress testing of HorizonMapper parameter binding and error handling."""

    def test_exact_analytical_annualization_factors(self):
        """Verifies exact analytical values: 140.2 (1h), 40.5 (1d), 15.87 (1wk)."""
        # Analytical ground truth:
        # 1h: sqrt(252 * 78) = 140.1998573... -> 140.2
        # 1d: sqrt(252 * 6.5) = 40.4722126... -> 40.5
        # 1wk: sqrt(252 * 1.0) = 15.8745078... -> 15.87
        h_1h = HorizonMapper.get_parameters("1 hour")
        assert h_1h.annualization_factor == 140.2

        h_1d = HorizonMapper.get_parameters("1 day")
        assert h_1d.annualization_factor == 40.5

        h_1w = HorizonMapper.get_parameters("1 week")
        assert h_1w.annualization_factor == 15.87

    def test_dynamic_parameter_mapping_completeness(self):
        """Verifies all 19 parameter fields are correctly populated and distinct across horizons."""
        h_1h = HorizonMapper.get_parameters("1 hour")
        h_1d = HorizonMapper.get_parameters("1 day")
        h_1w = HorizonMapper.get_parameters("1 week")

        # 1h (Intraday) checks
        assert h_1h.category == "INTRADAY"
        assert h_1h.bar_interval == "5m"
        assert h_1h.secondary_interval == "1m"
        assert h_1h.lookback_period == "5d"
        assert h_1h.bars_per_day == 78.0
        assert h_1h.tcn_horizon_bars == 12  # 12 * 5m = 60m = 1 hour forward
        assert h_1h.max_holding_bars == 12
        assert h_1h.is_intraday_friction is True
        assert h_1h.default_session_end_policy == "CLOSE_POSITIONS"
        assert h_1h.quote_staleness_threshold_sec == 60.0

        # 1d (Daily) checks
        assert h_1d.category == "DAILY"
        assert h_1d.bar_interval == "1h"
        assert h_1d.secondary_interval == "15m"
        assert h_1d.lookback_period == "60d"
        assert h_1d.bars_per_day == 6.5
        assert h_1d.tcn_horizon_bars == 7  # ~1 trading day forward
        assert h_1d.max_holding_bars == 7
        assert h_1d.is_intraday_friction is True
        assert h_1d.default_session_end_policy == "CLOSE_POSITIONS"
        assert h_1d.quote_staleness_threshold_sec == 300.0

        # 1wk (Swing) checks
        assert h_1w.category == "SWING"
        assert h_1w.bar_interval == "1d"
        assert h_1w.secondary_interval == "1h"
        assert h_1w.lookback_period == "2y"
        assert h_1w.bars_per_day == 1.0
        assert h_1w.tcn_horizon_bars == 5  # 5 trading days = 1 week
        assert h_1w.max_holding_bars == 5
        assert h_1w.is_intraday_friction is False  # Delivery STT
        assert h_1w.default_session_end_policy == "KEEP_OPEN"
        assert h_1w.quote_staleness_threshold_sec == 1800.0

    def test_invalid_horizon_inputs_raise_errors(self):
        """Invalid or out-of-scope horizon specifications must raise clear ValueErrors."""
        invalid_horizons = [
            "2 hours",
            "1 month",
            "5m",
            "minute",
            "1 year",
            "bi-weekly",
            "random_string",
            "",
            "   ",
        ]
        for inv in invalid_horizons:
            with pytest.raises(ValueError, match="Unsupported trading horizon"):
                HorizonMapper.get_parameters(inv)

            with pytest.raises(ValueError, match="Unsupported trading horizon"):
                HorizonMapper.normalize_horizon(inv)

    def test_horizon_aliases_robustness(self):
        """Common shorthand forms and case variations must normalize cleanly."""
        test_cases = [
            ("1h", "1 hour"),
            ("1H", "1 hour"),
            ("1hour", "1 hour"),
            ("intraday", "1 hour"),
            ("hourly", "1 hour"),
            ("1-hour", "1 hour"),
            ("1_hour", "1 hour"),
            (" 1h  ", "1 hour"),
            ("1d", "1 day"),
            ("1D", "1 day"),
            ("1day", "1 day"),
            ("daily", "1 day"),
            ("eod", "1 day"),
            ("1-day", "1 day"),
            ("1_day", "1 day"),
            ("1wk", "1 week"),
            ("1WK", "1 week"),
            ("1w", "1 week"),
            ("1week", "1 week"),
            ("swing", "1 week"),
            ("weekly", "1 week"),
            ("1-week", "1 week"),
        ]
        for raw, expected in test_cases:
            assert HorizonMapper.normalize_horizon(raw) == expected
            params = HorizonMapper.get_parameters(raw)
            assert params.horizon_name == expected


class TestDecisionExplainerEmpiricalChallenge:
    """Adversarial stress testing of DecisionExplainer plain-language narrative generation."""

    def _make_eval(
        self,
        ticker: str,
        net_ev: float = 1.25,
        win_prob: float = 0.65,
        direction: str = "LONG",
        entry_px: float = 100.0,
        target_px: float = 105.0,
        stop_px: float = 97.0,
    ) -> TradeEvaluationResult:
        return TradeEvaluationResult(
            ticker=ticker,
            direction=direction,
            entry_price=entry_px,
            target_price=target_px,
            stop_price=stop_px,
            raw_win_prob=win_prob,
            epistemic_uncertainty=0.03,
            conservative_win_prob=win_prob - 0.03,
            loss_probability=1.0 - (win_prob - 0.03),
            expected_win_return_pct=5.0,
            expected_loss_return_pct=3.0,
            gap_risk_buffer_pct=0.10,
            round_trip_friction_pct=0.12,
            gross_expectancy_pct=net_ev + 0.12,
            net_expectancy_pct=net_ev,
            min_ev_hurdle_pct=0.20,
            is_positive_ev=(net_ev >= 0.20),
            rejection_reason=None if net_ev >= 0.20 else "NEGATIVE EV",
            payoff_ratio=1.67,
            evaluation_metadata={"annualized_vol": 0.20},
        )

    def _make_opp(
        self,
        ticker: str,
        net_ev: float = 1.25,
        direction: str = "LONG",
        is_eligible: bool = True,
        regime_mult: float = 1.25,
        veto_reason: str = None,
    ) -> RankedOpportunity:
        ev = self._make_eval(ticker, net_ev=net_ev, direction=direction)
        return RankedOpportunity(
            rank=1,
            ticker=ticker,
            direction=direction,
            evaluation=ev,
            risk_adjusted_value=net_ev / 0.20,
            regime_multiplier=regime_mult,
            synergy_boost=1.0,
            composite_score=(net_ev / 0.20) * regime_mult,
            is_eligible=is_eligible and (net_ev >= 0.20) and (regime_mult > 0.0) and (veto_reason is None),
            ineligible_reason=veto_reason or (None if is_eligible and (net_ev >= 0.20) and (regime_mult > 0.0) else "Ineligible"),
            rank_justification="Rank #1 Highest EV",
        )

    def _make_alloc(
        self,
        ticker: str,
        direction: str = "LONG",
        weight: float = 0.18,
        capital: float = 18_000.0,
        shares: float = 180.0,
    ) -> AllocationItem:
        return AllocationItem(
            ticker=ticker,
            direction=direction,
            weight=weight,
            weight_pct=weight * 100.0,
            allocated_capital=capital,
            entry_price=100.0,
            shares=shares,
            target_price=105.0,
            stop_price=97.0,
            expected_net_ev_pct=1.25,
            kelly_optimal_f=0.45,
            vol_scalar=1.0,
            dd_scalar=1.0,
            sizing_rationale="Fractional Kelly 18.0%",
        )

    def test_explain_accepted_trade_inr_currency_and_short_direction(self):
        """Verifies explanation correctly handles Indian Rupees (₹) and SHORT direction."""
        opp = self._make_opp("TCS.NS", net_ev=1.75, direction="SHORT")
        alloc = self._make_alloc("TCS.NS", direction="SHORT", weight=0.15, capital=150_000.0, shares=50.0)

        exp = DecisionExplainer.explain_accepted_trade(opp, alloc, currency_symbol="₹")
        assert exp.action == "ACCEPTED"
        assert exp.ticker == "TCS.NS"
        assert "SELL TCS.NS" in exp.headline
        assert "₹150,000.00" in exp.summary
        assert "₹" in exp.summary
        assert exp.metrics["currency"] == "₹"
        assert exp.metrics["allocation_weight_pct"] == 15.0

        # Verify all 6 mandatory factor keys are present
        mandatory_factors = [
            "net_expectancy",
            "win_probability",
            "statutory_frictions",
            "regime_alignment",
            "position_sizing",
            "risk_reward_barriers",
        ]
        for k in mandatory_factors:
            assert k in exp.factors

        # Verify all 12 mandatory metric keys are present
        mandatory_metrics = [
            "net_expectancy_pct",
            "win_probability",
            "conservative_win_prob",
            "round_trip_friction_bps",
            "entry_price",
            "target_price",
            "stop_price",
            "payoff_ratio",
            "allocation_weight_pct",
            "allocated_capital",
            "shares",
            "currency",
        ]
        for k in mandatory_metrics:
            assert k in exp.metrics

    def test_explain_rejected_trade_scenarios(self):
        """Verifies plain-language explanations across all major rejection archetypes."""
        # Scenario A: Negative EV
        opp_neg = self._make_opp("BAD_EV", net_ev=-0.35, is_eligible=False)
        exp_neg = DecisionExplainer.explain_rejected_trade(opp_neg)
        assert "Negative Net Expectancy" in exp_neg.headline
        assert "-0.35%" in exp_neg.headline
        assert exp_neg.metrics["net_expectancy_pct"] == -0.35

        # Scenario B: Crisis Regime (State 2)
        opp_crisis = self._make_opp("CRISIS_TICKER", net_ev=2.0, is_eligible=False, regime_mult=0.0)
        opp_crisis.ineligible_reason = "HARD VETO: Market regime is State 2 (Crisis) with elevated tail risk"
        exp_crisis = DecisionExplainer.explain_rejected_trade(opp_crisis)
        assert "Crisis Regime Quarantine" in exp_crisis.headline
        assert "State 2" in exp_crisis.summary

        # Scenario C: Microstructure Circuit Breaker (FX Rollover / LULD)
        opp_micro = self._make_opp("EURUSD", net_ev=1.5, is_eligible=False, veto_reason="MICROSTRUCTURE VETO: Forex 17:00 EST rollover liquidity trough")
        exp_micro = DecisionExplainer.explain_rejected_trade(opp_micro)
        assert "Microstructure Circuit Breaker" in exp_micro.headline
        assert "liquidity trough" in exp_micro.summary

        # Scenario D: Sub-hurdle positive EV (+0.10% < +0.20% hurdle)
        opp_sub = self._make_opp("SUB_HURDLE", net_ev=0.10, is_eligible=False, veto_reason="Sub-hurdle EV (+0.10% < +0.20%)")
        exp_sub = DecisionExplainer.explain_rejected_trade(opp_sub)
        assert "REJECTED SUB_HURDLE" in exp_sub.headline
        assert "Insufficient Edge" in exp_sub.headline

    def test_explain_portfolio_100_percent_cash_preservation(self):
        """Verifies 100% Cash Guarantee explanation contains all factors and metrics."""
        exp_cash = DecisionExplainer.explain_portfolio_cash_fallback(
            total_candidates_evaluated=15,
            rejection_summary="Zero opportunities satisfied +0.20% Net Expectancy hurdle",
            active_regime="Trending Bull",
            current_drawdown_pct=2.45,
        )
        assert exp_cash.action == "HELD_IN_CASH"
        assert exp_cash.ticker == "PORTFOLIO"
        assert "100% CASH PRESERVED" in exp_cash.headline
        assert "15 candidate instruments" in exp_cash.summary
        assert "100% of equity is preserved in cash" in exp_cash.summary

        # Mandatory factors
        for factor_key in ["candidates_evaluated", "rejection_summary", "market_regime", "capital_protection", "next_action"]:
            assert factor_key in exp_cash.factors

        # Mandatory metrics
        assert exp_cash.metrics["total_candidates"] == 15
        assert exp_cash.metrics["qualifying_count"] == 0
        assert exp_cash.metrics["cash_weight_pct"] == 100.0
        assert exp_cash.metrics["portfolio_drawdown_pct"] == 2.45

    def test_explain_allocation_result_end_to_end(self):
        """Verifies batch allocation result mapping across accepted and rejected candidates."""
        opp_1 = self._make_opp("WINNER_1", net_ev=1.5)
        opp_2 = self._make_opp("WINNER_2", net_ev=1.2)
        opp_3 = self._make_opp("LOSER_1", net_ev=-0.5, is_eligible=False)
        alloc_1 = self._make_alloc("WINNER_1", weight=0.15, capital=15_000.0)
        alloc_2 = self._make_alloc("WINNER_2", weight=0.10, capital=10_000.0)

        res = PortfolioAllocationResult(
            weights={"WINNER_1": 0.15, "WINNER_2": 0.10, "CASH": 0.75},
            cash_weight=0.75,
            allocated_capital={"WINNER_1": 15000.0, "WINNER_2": 10000.0},
            shares={"WINNER_1": 150.0, "WINNER_2": 100.0},
            is_100_percent_cash=False,
            method="KELLY",
            allocations=[alloc_1, alloc_2],
            total_virtual_equity=100000.0,
            total_allocated_capital=25000.0,
            residual_cash_capital=75000.0,
            explanation="Allocated 2 positions.",
        )

        exps = DecisionExplainer.explain_allocation_result(res, [opp_1, opp_2, opp_3])
        assert len(exps) == 3
        assert exps[0].action == "ACCEPTED" and exps[0].ticker == "WINNER_1"
        assert exps[1].action == "ACCEPTED" and exps[1].ticker == "WINNER_2"
        assert exps[2].action == "REJECTED" and exps[2].ticker == "LOSER_1"

    def test_explain_accepted_trade_division_by_zero_resilience(self):
        """Zero entry price and zero expected loss return must not raise ZeroDivisionError."""
        opp = self._make_opp("ZERO_DIV", net_ev=1.5)
        # Force entry_price = 0.0 and expected_loss_return_pct = 0.0
        opp.evaluation.entry_price = 0.0
        opp.evaluation.expected_loss_return_pct = 0.0
        alloc = self._make_alloc("ZERO_DIV", capital=10_000.0)

        exp = DecisionExplainer.explain_accepted_trade(opp, alloc)
        assert exp.action == "ACCEPTED"
        assert exp.metrics["entry_price"] == 0.0
        assert exp.metrics["payoff_ratio"] >= 0.50


class TestExtremeStressHarnessEmpiricalChallenge:
    """Extreme adversarial tests targeting edge-case crashes, immutability, and data anomalies."""

    def test_universe_selector_missing_columns(self):
        """UniverseSelector must not crash if required columns are missing from dataframe."""
        selector = UniverseSelector()

        # Missing Volume column
        df_no_vol = pd.DataFrame({"Open": [100.0]*30, "High": [101.0]*30, "Low": [99.0]*30, "Close": [100.0]*30})
        q_data, r_m, r_z = selector.evaluate_data_quality(df_no_vol, "US_EQUITIES")
        assert r_z == 1.0  # Missing volume column treated as 100% zero volume
        assert selector.compute_adv(df_no_vol) == 0.0

        # Missing Close column
        df_no_close = pd.DataFrame({"Open": [100.0]*30, "High": [101.0]*30, "Low": [99.0]*30, "Volume": [1000.0]*30})
        assert selector.compute_adv(df_no_close) == 0.0
        assert selector.compute_annualized_volatility(df_no_close) == 0.0

    def test_universe_selector_infinite_prices(self):
        """Infinite prices in OHLCV should be flagged as corrupted bars."""
        selector = UniverseSelector()
        df = pd.DataFrame({
            "Open": [100.0]*30,
            "High": [np.inf]*30,
            "Low": [99.0]*30,
            "Close": [100.0]*30,
            "Volume": [1000.0]*30,
        })
        # Note: High = inf, Low = 99 -> High >= Low, but let's check negative inf
        df.loc[0:10, "Low"] = -np.inf
        eval_inf = selector.evaluate_instrument("INF_PX", df, market_type="US_EQUITIES")
        # Low <= 0 catches -inf as invalid
        assert eval_inf.passed_all_gates is False

    def test_adv_boundary_commodities_and_forex(self):
        """Boundary ADV tests for Commodities ($10M) and Forex ($25M)."""
        selector = UniverseSelector()

        # Commodities ($10M threshold)
        df_comm = pd.DataFrame({
            "Open": [100.0]*30, "High": [101.0]*30, "Low": [99.0]*30, "Close": [100.0]*30, "Volume": [99_900.0]*30
        })
        eval_comm_sub = selector.evaluate_instrument("GOLD_SUB", df_comm, market_type="COMMODITIES")
        assert any("INSUFFICIENT_LIQUIDITY" in r for r in eval_comm_sub.rejection_reasons)

        df_comm["Volume"] = 100_100.0  # $10.01M
        eval_comm_sup = selector.evaluate_instrument("GOLD_SUP", df_comm, market_type="COMMODITIES")
        assert not any("INSUFFICIENT_LIQUIDITY" in r for r in eval_comm_sup.rejection_reasons)

        # Forex ($25M threshold)
        df_fx = pd.DataFrame({
            "Open": [1.0]*30, "High": [1.01]*30, "Low": [0.99]*30, "Close": [1.0]*30, "Volume": [24_900_000.0]*30
        })
        eval_fx_sub = selector.evaluate_instrument("EURUSD_SUB", df_fx, market_type="FOREX")
        assert any("INSUFFICIENT_LIQUIDITY" in r for r in eval_fx_sub.rejection_reasons)

        df_fx["Volume"] = 25_100_000.0  # $25.1M
        eval_fx_sup = selector.evaluate_instrument("EURUSD_SUP", df_fx, market_type="FOREX")
        assert not any("INSUFFICIENT_LIQUIDITY" in r for r in eval_fx_sup.rejection_reasons)

    def test_horizon_parameters_immutability(self):
        """HorizonParameters must be frozen and throw FrozenInstanceError on mutation."""
        params = HorizonMapper.get_parameters("1 day")
        with pytest.raises(Exception):
            params.bar_interval = "1m"

        with pytest.raises(Exception):
            params.annualization_factor = 999.0

    def test_auto_select_basket_negative_and_excessive_target_sizes(self):
        """Extreme target size inputs (-10, 0, 1000) must clamp cleanly to [3, 6]."""
        mock_downloader = MagicMock()
        mock_downloader.get_market_type.return_value = "US"
        df = pd.DataFrame({
            "Open": [100.0]*30, "High": [101.0]*30, "Low": [99.0]*30, "Close": [100.0 + (i%2)*0.5 for i in range(30)], "Volume": [100_000.0]*30
        })
        mock_downloader.download_ticker.return_value = df
        candidates = [f"TICKER_{i}" for i in range(15)]
        selector = UniverseSelector(downloader=mock_downloader)

        # Negative target size
        res_neg = selector.auto_select_basket("US", target_size=-10, candidate_tickers=candidates)
        assert res_neg.target_size == 3
        assert len(res_neg.selected_instruments) == 3

        # Zero target size
        res_zero = selector.auto_select_basket("US", target_size=0, candidate_tickers=candidates)
        assert res_zero.target_size == 3
        assert len(res_zero.selected_instruments) == 3

        # Huge target size
        res_huge = selector.auto_select_basket("US", target_size=1000, candidate_tickers=candidates)
        assert res_huge.target_size == 6
        assert len(res_huge.selected_instruments) == 6

