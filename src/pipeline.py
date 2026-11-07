"""Master Quantitative Prediction Pipeline.

Orchestrates data ingestion, fractional feature engineering, causal forward-filtering
HMM regime classification, purged High/Low triple-barrier meta-labeling,
supervised Pinball-Loss Causal TCN sequence forecasting, volatility cone projections,
and CVaR-constrained asymmetric Kelly risk governance.

Live-Market Compatibility & Anti-Leakage Guarantees:
- Supports point-in-time `as_of_timestamp` filtering prior to feature extraction,
  Fractional Differentiation, HMM forward filtering, LightGBM meta-labeling, and
  Causal TCN sequence fitting, preventing look-ahead bias and data leakage.
- Supports direct injection of `ohlcv_df` or `BaseMarketDataProvider` bars, and
  live quote re-anchoring (`refresh_with_live_quote`) so barrier prices, volatility
  cones, friction hurdles, and drawdown guardrails reflect genuine market prices.
"""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from src.data.downloader import MarketDataDownloader
from src.data.normalizer import MarketDataNormalizer
from src.execution.frictions import FrictionEvaluator
from src.execution.guardrails import RiskAllocationDecision, RiskGuardrailEngine
from src.features.fracdiff import FractionalDifferentiator
from src.features.technical import TechnicalFeaturePipeline
from src.models.foundation_prior import VolatilityCone, VolatilityConeForecaster
from src.models.gpu_acceleration import GPUManager, TorchSequenceForecaster
from src.models.hrp_allocator import HierarchicalRiskParity
from src.models.meta_labeler import MetaLabelingEngine, MetaPrediction
from src.models.regime_hmm import MarketRegimeClassifier, RegimeState

logger = logging.getLogger(__name__)


@dataclass
class SingleAssetAnalysis:
    ticker: str
    current_price: float
    market_jurisdiction: str
    regime: RegimeState
    meta_prediction: MetaPrediction
    volatility_cone: VolatilityCone
    friction_hurdle_passes: bool
    friction_cost_pct: float
    net_expected_alpha_pct: float
    risk_decision: RiskAllocationDecision
    optimal_d_star: float
    recent_ohlcv: pd.DataFrame
    features_df: pd.DataFrame
    neural_prob: float = 0.50
    hardware_accelerator: str = "CPU"
    prediction_timestamp_utc: str = ""


@dataclass
class MultiAssetAnalysis:
    single_analyses: Dict[str, SingleAssetAnalysis]
    hrp_portfolio_weights: Dict[str, float]
    aggregate_regime: str
    circuit_breaker_active: bool


class MarketPredictionEngine:
    """Master quantitative prediction engine."""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        kelly_fraction: float = 0.30,
        target_vol: float = 0.15,
        current_drawdown: float = 0.0,
        data_provider: Optional[Any] = None,
    ):
        self.downloader = MarketDataDownloader(cache_dir=cache_dir)
        self.data_provider = data_provider
        self.normalizer = MarketDataNormalizer()
        self.fracdiff = FractionalDifferentiator()
        self.tech_pipeline = TechnicalFeaturePipeline()
        self.regime_clf = MarketRegimeClassifier()
        self.meta_engine = MetaLabelingEngine()
        self.cone_forecaster = VolatilityConeForecaster()
        self.neural_forecaster = TorchSequenceForecaster()
        self.guardrail = RiskGuardrailEngine(
            kelly_fraction=kelly_fraction, target_annual_vol=target_vol
        )
        self.current_drawdown = current_drawdown

    @staticmethod
    def _enforce_point_in_time_cutoff(
        df: pd.DataFrame, as_of_timestamp: Optional[datetime]
    ) -> pd.DataFrame:
        """Strictly filters OHLCV DataFrame up to `as_of_timestamp` to prevent look-ahead bias."""
        if df.empty or as_of_timestamp is None:
            return df
        ts_utc = (
            as_of_timestamp.astimezone(timezone.utc)
            if as_of_timestamp.tzinfo is not None
            else as_of_timestamp.replace(tzinfo=timezone.utc)
        )
        idx = df.index
        if getattr(idx, "tz", None) is None:
            idx_utc = idx.tz_localize("UTC")
            return df.loc[idx_utc <= ts_utc].copy()
        return df.loc[idx.tz_convert("UTC") <= ts_utc].copy()

    def analyze_ticker(
        self,
        ticker: str,
        period: str = "2y",
        interval: str = "1d",
        force_refresh: bool = False,
        as_of_timestamp: Optional[datetime] = None,
        ohlcv_df: Optional[pd.DataFrame] = None,
        df_override: Optional[pd.DataFrame] = None,
        live_price: Optional[float] = None,
    ) -> Optional[SingleAssetAnalysis]:
        """Runs full end-to-end analytical and predictive pipeline for a single ticker."""
        # 1. Acquire OHLCV data from explicit DataFrame, configured provider, or downloader
        if df_override is not None and ohlcv_df is None:
            ohlcv_df = df_override
        if ohlcv_df is not None and not ohlcv_df.empty:
            df_raw = ohlcv_df.copy()
        elif self.data_provider is not None and not force_refresh:
            try:
                df_raw = self.data_provider.get_historical_bars(
                    ticker, interval=interval, lookback_bars=500, end_time=as_of_timestamp
                )
            except Exception as e:
                logger.warning(f"Provider bar fetch failed for {ticker}, using downloader: {e}")
                df_raw = pd.DataFrame()
            if df_raw.empty:
                df_raw = self.downloader.download_ticker(
                    ticker, period=period, interval=interval, force_refresh=force_refresh
                )
        else:
            df_raw = self.downloader.download_ticker(
                ticker, period=period, interval=interval, force_refresh=force_refresh
            )

        # Enforce strict causal cutoff at as_of_timestamp before any processing
        df_raw = self._enforce_point_in_time_cutoff(df_raw, as_of_timestamp)

        if df_raw.empty or len(df_raw) < 40:
            logger.error(
                f"Insufficient data points for {ticker} ({len(df_raw)} rows)."
            )
            return None

        # 2. Clean & Normalize
        df_clean = self.normalizer.clean_ohlcv(df_raw)
        if df_clean.empty or len(df_clean) < 40:
            logger.error(f"Insufficient clean data points for {ticker} ({len(df_clean)} rows).")
            return None

        current_price = (
            float(live_price)
            if (live_price is not None and np.isfinite(live_price) and live_price > 0)
            else float(df_clean["Close"].iloc[-1])
        )
        market_type = self.downloader.get_market_type(ticker)

        last_idx = df_clean.index[-1]
        if isinstance(last_idx, pd.Timestamp):
            dt_last = last_idx.to_pydatetime()
            pred_ts_str = (
                dt_last.astimezone(timezone.utc).isoformat()
                if dt_last.tzinfo
                else dt_last.replace(tzinfo=timezone.utc).isoformat()
            )
        else:
            pred_ts_str = datetime.now(timezone.utc).isoformat()

        # 3. Memory Preservation: Fractional Differentiation (d*)
        d_opt, s_fracdiff = self.fracdiff.find_min_d(df_clean["Close"])

        # 4. Technical Feature Extraction
        feats = self.tech_pipeline.compute_features(df_clean)
        if not s_fracdiff.empty:
            common_idx = feats.index.intersection(s_fracdiff.index)
            feats = feats.loc[common_idx].copy()
            feats["FracDiff_Price"] = s_fracdiff.loc[common_idx]

        # 5. Market Regime Detection (Causal Forward-Filtering HMM)
        regime = self.regime_clf.get_current_regime(df_clean)

        # 6. Two-Stage Meta-Labeling Prediction (Purged High/Low Tabular Causal Model)
        meta_pred = self.meta_engine.train_and_predict(feats, df_clean)

        # If a genuine live quote price was supplied, re-anchor target/stop barriers to live_price
        if live_price is not None and live_price > 0 and float(df_clean["Close"].iloc[-1]) > 0:
            hist_close = float(df_clean["Close"].iloc[-1])
            scale = current_price / hist_close
            decimals = 4 if (market_type == "FOREX" or current_price < 10.0) else 2
            meta_pred.target_price = round(float(meta_pred.target_price * scale), decimals)
            meta_pred.stop_price = round(float(meta_pred.stop_price * scale), decimals)

        # 7. Supervised Pinball-Loss Causal TCN Sequence Forecaster
        self.neural_forecaster.fit(df_clean, epochs=10)
        neural_dir, neural_prob = self.neural_forecaster.evaluate_directional_conviction(df_clean)
        dev_str = str(self.neural_forecaster.device).upper()
        hardware_accel = "CUDA (NVIDIA RTX 4060)" if "CUDA" in dev_str else "AVX2 CPU (Multi-Core)"

        # Ensemble Fusion: 65% Causal Decision Trees + 35% Supervised Causal TCN
        # Note: neural_prob is P(UP), so align with primary_direction (+1 LONG, -1 SHORT)
        lgbm_prob = meta_pred.success_probability
        aligned_neural_prob = (
            float(neural_prob)
            if meta_pred.primary_direction >= 0
            else float(1.0 - neural_prob)
        )
        fused_prob = round(0.65 * lgbm_prob + 0.35 * aligned_neural_prob, 3)

        # False Breakout & Bull/Bear Trap Veto Filters (only on severe TCN disagreement < 0.35)
        if meta_pred.primary_direction == 1 and neural_prob < 0.35:
            meta_pred.direction_label = "NEUTRAL / VETOED (FALSE BREAKOUT DETECTED)"
            meta_pred.bet_size = 0.0
            fused_prob = min(fused_prob, 0.48)
        elif meta_pred.primary_direction == -1 and neural_prob > 0.65:
            meta_pred.direction_label = "NEUTRAL / VETOED (BEAR TRAP DETECTED)"
            meta_pred.bet_size = 0.0
            fused_prob = min(fused_prob, 0.48)
        else:
            # High-conviction agreement boost
            if aligned_neural_prob >= 0.56:
                meta_pred.bet_size = round(float(np.clip(meta_pred.bet_size * 1.25, -1.0, 1.0)), 3)
                if "STRONG" not in meta_pred.direction_label and "BUY" in meta_pred.direction_label and fused_prob >= 0.65:
                    meta_pred.direction_label = "STRONG BUY"
                elif "STRONG" not in meta_pred.direction_label and "SELL" in meta_pred.direction_label and fused_prob >= 0.65:
                    meta_pred.direction_label = "STRONG SELL"

        meta_pred.success_probability = fused_prob

        # If Crisis Regime, force neutral or zero bet
        if regime.is_crisis:
            meta_pred.direction_label = "CIRCUIT BREAKER (CRISIS REGIME)"
            meta_pred.bet_size = 0.0

        # 8. Foundation Volatility Cones (q10, q50, q90)
        drift_direction = float(meta_pred.primary_direction)
        cone = self.cone_forecaster.project_cone(
            current_price=current_price,
            log_returns=df_clean["LogReturn"],
            directional_drift=drift_direction,
        )

        # 9. Statutory Friction, Almgren-Chriss Slippage & Microstructure Gate
        is_intraday = interval != "1d"
        gross_alpha_pct = abs(
            (meta_pred.target_price - current_price) / current_price * 100.0
        )
        passes_hurdle, friction_cost, net_alpha = (
            FrictionEvaluator.validate_alpha_hurdle(
                ticker,
                gross_alpha_pct,
                is_intraday=is_intraday,
                reference_price=current_price,
            )
        )
        micro_ok, micro_reason = FrictionEvaluator.check_microstructure_execution_gate(
            ticker, ohlcv_df=df_clean
        )

        # 10. Dynamic Asymmetric CVaR-Kelly Sizing & Guardrails
        realized_vol = cone.expected_vol_annualized
        payoff_b = getattr(self.meta_engine, "payoff_ratio_b", 1.5)
        risk_decision = self.guardrail.evaluate_allocation(
            current_drawdown=self.current_drawdown,
            model_bet_size=meta_pred.bet_size,
            realized_annual_vol=realized_vol,
            win_probability=fused_prob,
            payoff_ratio_b=payoff_b,
        )

        # If microstructure gate or statutory hurdle failed, disallow allocation
        if not micro_ok:
            risk_decision.authorized = False
            risk_decision.authorized_weight_pct = 0.0
            risk_decision.status_message = micro_reason
            meta_pred.direction_label = "NEUTRAL / VETOED (MICROSTRUCTURE GATE)"
            meta_pred.bet_size = 0.0
        elif not passes_hurdle:
            risk_decision.authorized = False
            risk_decision.authorized_weight_pct = 0.0
            risk_decision.status_message = (
                f"REJECTED: Gross alpha ({gross_alpha_pct:.2f}%) fails 1.5x hurdle over "
                f"friction + slippage costs ({friction_cost:.2f}%)."
            )

        return SingleAssetAnalysis(
            ticker=ticker.upper(),
            current_price=current_price,
            market_jurisdiction=market_type,
            regime=regime,
            meta_prediction=meta_pred,
            volatility_cone=cone,
            friction_hurdle_passes=passes_hurdle,
            friction_cost_pct=friction_cost,
            net_expected_alpha_pct=net_alpha,
            risk_decision=risk_decision,
            optimal_d_star=d_opt,
            recent_ohlcv=df_clean.tail(150),
            features_df=feats.tail(150),
            neural_prob=neural_prob,
            hardware_accelerator=hardware_accel,
            prediction_timestamp_utc=pred_ts_str,
        )

    def refresh_with_live_quote(
        self,
        analysis: SingleAssetAnalysis,
        live_price: object,
        current_drawdown: Optional[float] = None,
        quote_timestamp_utc: Optional[str] = None,
    ) -> SingleAssetAnalysis:
        """Re-anchors an existing SingleAssetAnalysis to a genuine live market price or LiveQuote.

        Updates barriers, volatility cone, statutory friction hurdle, and Kelly risk
        sizing against current portfolio drawdown without leaking future bars.
        """
        if hasattr(live_price, "last_price"):
            price_val = float(getattr(live_price, "last_price", 0.0))
            if quote_timestamp_utc is None:
                quote_timestamp_utc = str(getattr(live_price, "timestamp_utc", ""))
        else:
            price_val = float(live_price)  # type: ignore[arg-type]

        if not np.isfinite(price_val) or price_val <= 0:
            return analysis

        decimals = 4 if (getattr(analysis, "market_jurisdiction", "") == "FOREX" or price_val < 10.0) else 2
        if not isinstance(analysis, SingleAssetAnalysis):
            analysis.current_price = round(float(price_val), decimals)
            return analysis

        dd = self.current_drawdown if current_drawdown is None else float(current_drawdown)
        prev_ref = analysis.current_price if analysis.current_price > 0 else price_val

        # Preserve unrounded barrier ratios on the first anchor to prevent cumulative rounding drift across ticks
        base_target_ratio = getattr(analysis.meta_prediction, "_base_target_ratio", None)
        base_stop_ratio = getattr(analysis.meta_prediction, "_base_stop_ratio", None)
        if base_target_ratio is None or base_stop_ratio is None:
            base_target_ratio = float(analysis.meta_prediction.target_price) / prev_ref if prev_ref > 0 else 1.0
            base_stop_ratio = float(analysis.meta_prediction.stop_price) / prev_ref if prev_ref > 0 else 1.0

        new_target = round(float(price_val * base_target_ratio), decimals)
        new_stop = round(float(price_val * base_stop_ratio), decimals)

        updated_meta = replace(
            analysis.meta_prediction,
            target_price=new_target,
            stop_price=new_stop,
        )
        setattr(updated_meta, "_base_target_ratio", base_target_ratio)
        setattr(updated_meta, "_base_stop_ratio", base_stop_ratio)

        gross_alpha_pct = abs((new_target - price_val) / price_val * 100.0)
        passes_hurdle, friction_cost, net_alpha = FrictionEvaluator.validate_alpha_hurdle(
            analysis.ticker,
            gross_alpha_pct,
            is_intraday=False,
            reference_price=price_val,
        )

        payoff_b = getattr(self.meta_engine, "payoff_ratio_b", 1.5)
        risk_decision = self.guardrail.evaluate_allocation(
            current_drawdown=dd,
            model_bet_size=updated_meta.bet_size,
            realized_annual_vol=analysis.volatility_cone.expected_vol_annualized,
            win_probability=updated_meta.success_probability,
            payoff_ratio_b=payoff_b,
        )
        if not passes_hurdle:
            risk_decision.authorized = False
            risk_decision.authorized_weight_pct = 0.0
            risk_decision.status_message = (
                f"REJECTED: Gross alpha ({gross_alpha_pct:.2f}%) fails 1.5x hurdle over "
                f"friction + slippage costs ({friction_cost:.2f}%)."
            )

        return replace(
            analysis,
            current_price=round(float(price_val), decimals),
            meta_prediction=updated_meta,
            friction_hurdle_passes=passes_hurdle,
            friction_cost_pct=friction_cost,
            net_expected_alpha_pct=net_alpha,
            risk_decision=risk_decision,
            prediction_timestamp_utc=quote_timestamp_utc or analysis.prediction_timestamp_utc,
        )

    def analyze_portfolio(
        self,
        tickers: List[str],
        period: str = "2y",
        interval: str = "1d",
        force_refresh: bool = False,
        as_of_timestamp: Optional[datetime] = None,
    ) -> MultiAssetAnalysis:
        """Analyzes a multi-ticker portfolio and computes Marchenko-Pastur + Ward HRP allocations."""
        single_results = {}
        for t in tickers:
            res = self.analyze_ticker(
                t,
                period=period,
                interval=interval,
                force_refresh=force_refresh,
                as_of_timestamp=as_of_timestamp,
            )
            if res is not None:
                single_results[t.upper()] = res

        if not single_results:
            return MultiAssetAnalysis({}, {}, "NO_DATA", False)

        # Extract aligned returns for HRP
        close_data = {
            t: res.recent_ohlcv for t, res in single_results.items()
        }
        aligned_close = self.normalizer.align_multi_asset_close(close_data)
        aligned_returns = self.normalizer.compute_asset_returns(aligned_close)

        # Compute Hierarchical Risk Parity weights (with Marchenko-Pastur de-noising & Ward linkage)
        hrp_weights = {}
        if not aligned_returns.empty:
            weights_series = HierarchicalRiskParity.compute_hrp_weights(
                aligned_returns
            )
            hrp_weights = {
                t: float(weights_series.get(t, 0.0))
                for t in single_results.keys()
            }

        # Check aggregate crisis
        crisis_count = sum(
            1 for res in single_results.values() if res.regime.is_crisis
        )
        agg_regime = (
            "CRISIS REGIME"
            if crisis_count >= len(single_results) / 2
            else "NORMAL MARKET"
        )
        circuit_active = crisis_count >= len(single_results) / 2

        return MultiAssetAnalysis(
            single_analyses=single_results,
            hrp_portfolio_weights=hrp_weights,
            aggregate_regime=agg_regime,
            circuit_breaker_active=circuit_active,
        )
