"""Quantitative Universe Selection & Opportunity Screening Engine.

Filters candidate instruments across US Equities, Indian Equities (NSE), Crypto,
Commodities, and Forex using institutional-grade data quality, liquidity, spread,
and volatility gates. Computes composite multi-factor scores and auto-selects
bounded baskets (3 to 6 instruments) with plain-language setup wizard rationales.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.data.downloader import MarketDataDownloader
from src.data.provider_base import BaseMarketDataProvider, LiveQuote
from src.execution.frictions import FrictionEvaluator
from src.execution.live_bot import ASSET_CATALOG

logger = logging.getLogger(__name__)


@dataclass
class UniverseSelectionCriteria:
    """Configurable thresholds for universe screening gates."""

    min_data_quality: float = 0.90
    min_adv_usd: float = 5_000_000.0  # $5M USD for US Equities
    min_adv_inr: float = 50_000_000.0  # ₹50M INR for NSE Cash Equities
    min_adv_crypto_usd: float = 10_000_000.0  # $10M USD for Crypto
    min_adv_commodity_usd: float = 10_000_000.0  # $10M USD for Commodities
    min_adv_forex_usd: float = 25_000_000.0  # $25M USD equivalent for Forex
    max_spread_bps: float = 25.0  # 25 basis points maximum spread
    min_annualized_vol: float = 0.08  # 8.0% minimum tradability volatility floor
    max_annualized_vol: float = 1.00  # 100.0% maximum risk volatility ceiling
    lookback_bars: int = 20  # Window for ADV and volatility estimation
    min_bars_required: int = 20
    target_basket_min: int = 3
    target_basket_max: int = 6
    default_basket_size: int = 5


@dataclass
class CandidateEvaluation:
    """Comprehensive evaluation record for a single universe candidate."""

    ticker: str
    market: str
    passed_all_gates: bool
    data_quality_score: float
    missing_bar_ratio: float
    zero_volume_ratio: float
    adv: float
    adv_currency: str
    adv_threshold: float
    spread_bps: float
    annualized_volatility: float
    composite_score: float
    rejection_reasons: List[str] = field(default_factory=list)
    pass_details: Dict[str, Any] = field(default_factory=dict)
    summary_rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UniverseSelectionResult:
    """Result of auto-selecting a bounded basket for the setup wizard."""

    market: str
    target_size: int
    selected_instruments: List[str]
    evaluations: Dict[str, CandidateEvaluation]
    passed_count: int
    rejected_count: int
    summary_rationale: str
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["evaluations"] = {k: v.to_dict() for k, v in self.evaluations.items()}
        return d


class UniverseSelector:
    """Autonomous universe screener and wizard basket recommendation engine."""

    def __init__(
        self,
        criteria: Optional[UniverseSelectionCriteria] = None,
        downloader: Optional[MarketDataDownloader] = None,
        data_provider: Optional[BaseMarketDataProvider] = None,
    ):
        self.criteria = criteria or UniverseSelectionCriteria()
        self.downloader = downloader or MarketDataDownloader()
        self.data_provider = data_provider

    def resolve_market_category(self, market: str) -> str:
        """Normalizes market identifier to canonical category."""
        m = market.strip().upper()
        if m in ["US", "US_EQUITIES", "NYSE", "NASDAQ", "AMERICA"]:
            return "US_EQUITIES"
        elif m in ["NSE", "NSE_CASH", "INDIAN_NSE", "INDIA"]:
            return "INDIAN_NSE"
        elif m in ["CRYPTO", "CRYPTOCURRENCY", "COINS"]:
            return "CRYPTO"
        elif m in ["COMMODITY", "COMMODITIES", "CME", "NYMEX", "COMEX"]:
            return "COMMODITIES"
        elif m in ["FOREX", "FX", "CURRENCY"]:
            return "FOREX"
        return "US_EQUITIES"

    def get_adv_threshold(self, market_category: str) -> Tuple[float, str]:
        """Returns (threshold_amount, currency_symbol) for the market category."""
        if market_category == "INDIAN_NSE":
            return self.criteria.min_adv_inr, "₹"
        elif market_category == "CRYPTO":
            return self.criteria.min_adv_crypto_usd, "$"
        elif market_category == "COMMODITIES":
            return self.criteria.min_adv_commodity_usd, "$"
        elif market_category == "FOREX":
            return self.criteria.min_adv_forex_usd, "$"
        else:
            return self.criteria.min_adv_usd, "$"

    def evaluate_data_quality(
        self, ohlcv_df: pd.DataFrame, market_category: str
    ) -> Tuple[float, float, float]:
        """Computes Data Quality Score Q_data, missing bar ratio, and zero volume ratio.

        Formula:
            Q_data = (1.0 - (0.60 * R_missing + 0.40 * R_zero_vol)) * penalty
        """
        if ohlcv_df.empty:
            return 0.0, 1.0, 1.0

        n_rows = len(ohlcv_df)
        if n_rows < self.criteria.min_bars_required:
            penalty = n_rows / max(self.criteria.min_bars_required, 1)
        else:
            penalty = 1.0

        required_cols = ["Open", "High", "Low", "Close"]
        missing_mask = pd.Series(False, index=ohlcv_df.index)
        for c in required_cols:
            if c in ohlcv_df.columns:
                missing_mask |= ohlcv_df[c].isna() | (ohlcv_df[c] <= 0)
            else:
                missing_mask |= True

        if "High" in ohlcv_df.columns and "Low" in ohlcv_df.columns:
            missing_mask |= ohlcv_df["High"] < ohlcv_df["Low"]

        n_missing = int(missing_mask.sum())
        r_missing = round(n_missing / max(n_rows, 1), 4)

        if market_category == "FOREX":
            r_zero_vol = 0.0
            q_data = max(0.0, 1.0 - r_missing) * penalty
        else:
            if "Volume" in ohlcv_df.columns:
                zero_vol_mask = ohlcv_df["Volume"].isna() | (ohlcv_df["Volume"] <= 0)
                n_zero_vol = int(zero_vol_mask.sum())
                r_zero_vol = round(n_zero_vol / max(n_rows, 1), 4)
            else:
                r_zero_vol = 1.0

            q_data = max(0.0, 1.0 - (0.60 * r_missing + 0.40 * r_zero_vol)) * penalty

        return round(float(q_data), 4), r_missing, r_zero_vol

    def compute_adv(self, ohlcv_df: pd.DataFrame) -> float:
        """Computes rolling Average Daily Volume (ADV) in currency units."""
        if ohlcv_df.empty or "Close" not in ohlcv_df.columns or "Volume" not in ohlcv_df.columns:
            return 0.0

        k = min(len(ohlcv_df), self.criteria.lookback_bars)
        recent = ohlcv_df.iloc[-k:]
        dollar_vol = (recent["Close"] * recent["Volume"]).fillna(0.0)
        return float(dollar_vol.mean())

    def compute_spread_bps(
        self,
        ticker: str,
        ohlcv_df: pd.DataFrame,
        live_quote: Optional[LiveQuote] = None,
    ) -> float:
        """Determines bid-ask spread in basis points using LiveQuote BBO or baseline estimation."""
        if live_quote is not None and getattr(live_quote, "is_valid", False):
            spread_bps = getattr(live_quote, "spread_bps", 0.0)
            if spread_bps > 0:
                return float(spread_bps)

        # Baseline friction spread estimation
        profile = FrictionEvaluator.get_profile(ticker)
        base_spread_bps = profile.slippage_bps * 2.0

        # Refine with recent high-low intraday noise if sufficient bars exist
        if len(ohlcv_df) >= 2 and "High" in ohlcv_df.columns and "Low" in ohlcv_df.columns:
            c = float(ohlcv_df["Close"].iloc[-1])
            h = float(ohlcv_df["High"].iloc[-1])
            l = float(ohlcv_df["Low"].iloc[-1])
            if c > 0 and h > l:
                hl_spread_est = ((h - l) / c) * 10000.0 * 0.10  # 10% of candle range as spread
                return round(float(max(base_spread_bps, min(hl_spread_est, 50.0))), 2)

        return round(float(base_spread_bps), 2)

    def compute_annualized_volatility(
        self, ohlcv_df: pd.DataFrame, annualization_factor: float = 15.87
    ) -> float:
        """Computes annualized return volatility from log returns."""
        if len(ohlcv_df) < 5 or "Close" not in ohlcv_df.columns:
            return 0.0

        closes = ohlcv_df["Close"].dropna()
        if len(closes) < 5:
            return 0.0

        log_returns = np.log(closes / closes.shift(1)).dropna()
        std_ret = float(log_returns.std())
        return round(float(std_ret * annualization_factor), 4)

    def compute_composite_score(
        self,
        adv: float,
        adv_threshold: float,
        spread_bps: float,
        data_quality: float,
        annualized_vol: float,
    ) -> float:
        """Computes composite ranking score S_composite in [0.0, 1.0].

        Formula:
            S_composite = 0.35 * S_liq + 0.25 * S_spread + 0.20 * S_qual + 0.20 * S_vol
        """
        # 1. Liquidity factor (log-scaled relative to threshold up to 20x threshold)
        if adv <= 0 or adv_threshold <= 0:
            s_liq = 0.0
        else:
            log_adv = math.log(max(adv, 1.0))
            log_thresh = math.log(max(adv_threshold, 1.0))
            log_max = math.log(max(adv_threshold * 20.0, 1.0))
            s_liq = max(0.0, min(1.0, (log_adv - log_thresh) / max(log_max - log_thresh, 1e-4)))

        # 2. Spread tightness factor (linear 0 to max_spread_bps)
        s_spread = max(0.0, min(1.0, 1.0 - (spread_bps / max(self.criteria.max_spread_bps, 1.0))))

        # 3. Data quality factor (scaled [0.90, 1.00] -> [0.0, 1.0])
        s_qual = max(0.0, min(1.0, (data_quality - 0.90) / 0.10))

        # 4. Volatility sweet-spot factor (Gaussian centered at 30% vol, std 18%)
        diff = annualized_vol - 0.30
        s_vol = math.exp(- (diff * diff) / (2.0 * 0.18 * 0.18))

        composite = 0.35 * s_liq + 0.25 * s_spread + 0.20 * s_qual + 0.20 * s_vol
        return round(float(np.clip(composite, 0.0, 1.0)), 4)

    def evaluate_instrument(
        self,
        ticker: str,
        ohlcv_df: pd.DataFrame,
        live_quote: Optional[LiveQuote] = None,
        market_type: Optional[str] = None,
    ) -> CandidateEvaluation:
        """Applies 4 institutional gates and generates candidate evaluation."""
        detected_market = market_type or self.downloader.get_market_type(ticker)
        market_category = self.resolve_market_category(detected_market)
        adv_thresh, currency_sym = self.get_adv_threshold(market_category)

        rejection_reasons: List[str] = []
        pass_details: Dict[str, Any] = {}

        # Gate 1: Data Quality
        q_data, r_missing, r_zero_vol = self.evaluate_data_quality(ohlcv_df, market_category)
        if q_data < self.criteria.min_data_quality:
            rejection_reasons.append(
                f"LOW_DATA_QUALITY: Data Quality Score {q_data:.1%} is below the "
                f"{self.criteria.min_data_quality:.1%} threshold (missing: {r_missing:.1%}, zero-volume: {r_zero_vol:.1%})."
            )
        else:
            pass_details["data_quality"] = f"Passed ({q_data:.1%})"

        # Gate 2: ADV Liquidity
        adv = self.compute_adv(ohlcv_df)
        if adv < adv_thresh:
            rejection_reasons.append(
                f"INSUFFICIENT_LIQUIDITY: ADV of {currency_sym}{adv:,.0f} is below the "
                f"{currency_sym}{adv_thresh:,.0f} institutional gate."
            )
        else:
            pass_details["adv"] = f"Passed ({currency_sym}{adv:,.0f} >= {currency_sym}{adv_thresh:,.0f})"

        # Gate 3: Spread Gate
        spread_bps = self.compute_spread_bps(ticker, ohlcv_df, live_quote)
        if spread_bps > self.criteria.max_spread_bps:
            rejection_reasons.append(
                f"SPREAD_TOO_WIDE: Bid-Ask spread of {spread_bps:.1f} bps exceeds "
                f"{self.criteria.max_spread_bps:.1f} bps maximum execution gate."
            )
        else:
            pass_details["spread"] = f"Passed ({spread_bps:.1f} bps <= {self.criteria.max_spread_bps:.1f} bps)"

        # Gate 4: Volatility Tradability Bounds
        ann_vol = self.compute_annualized_volatility(ohlcv_df)
        if ann_vol < self.criteria.min_annualized_vol:
            rejection_reasons.append(
                f"STAGNANT_VOLATILITY: Annualized volatility of {ann_vol:.1%} is below "
                f"{self.criteria.min_annualized_vol:.1%} minimum floor. Insufficient alpha to cover friction."
            )
        elif ann_vol > self.criteria.max_annualized_vol:
            rejection_reasons.append(
                f"EXCESSIVE_VOLATILITY: Annualized volatility of {ann_vol:.1%} exceeds "
                f"{self.criteria.max_annualized_vol:.1%} maximum risk ceiling. Tail risk breaks Kelly bounds."
            )
        else:
            pass_details["volatility"] = f"Passed ({ann_vol:.1%} in [{self.criteria.min_annualized_vol:.0%}, {self.criteria.max_annualized_vol:.0%}])"

        passed_all = len(rejection_reasons) == 0
        composite_score = (
            self.compute_composite_score(adv, adv_thresh, spread_bps, q_data, ann_vol)
            if passed_all
            else 0.0
        )

        # Build candidate rationale
        if passed_all:
            summary_rationale = (
                f"{ticker}: Passed all institutional gates (ADV {currency_sym}{adv:,.0f}, "
                f"spread {spread_bps:.1f} bps, vol {ann_vol:.1%}, Q_data {q_data:.1%}). "
                f"Composite score: {composite_score:.3f}."
            )
        else:
            summary_rationale = f"{ticker}: Rejected — " + "; ".join(rejection_reasons)

        return CandidateEvaluation(
            ticker=ticker,
            market=market_category,
            passed_all_gates=passed_all,
            data_quality_score=q_data,
            missing_bar_ratio=r_missing,
            zero_volume_ratio=r_zero_vol,
            adv=round(adv, 2),
            adv_currency=currency_sym,
            adv_threshold=adv_thresh,
            spread_bps=spread_bps,
            annualized_volatility=ann_vol,
            composite_score=composite_score,
            rejection_reasons=rejection_reasons,
            pass_details=pass_details,
            summary_rationale=summary_rationale,
        )

    def auto_select_basket(
        self,
        market: str,
        target_size: int = 5,
        candidate_tickers: Optional[List[str]] = None,
    ) -> UniverseSelectionResult:
        """Screens candidate pool and returns bounded recommended basket (3-6 instruments) with rationale."""
        market_category = self.resolve_market_category(market)
        k_target = max(self.criteria.target_basket_min, min(self.criteria.target_basket_max, target_size))

        # Acquire candidates
        if not candidate_tickers:
            candidate_tickers = ASSET_CATALOG.get(market_category, ASSET_CATALOG.get("US_EQUITIES", []))

        evaluations: Dict[str, CandidateEvaluation] = {}
        for ticker in candidate_tickers:
            # Download OHLCV
            try:
                df = self.downloader.download_ticker(ticker, period="60d", interval="1d")
            except Exception as e:
                logger.warning(f"Failed to download {ticker}: {e}")
                df = pd.DataFrame()

            quote = None
            if self.data_provider is not None:
                try:
                    quote = self.data_provider.get_live_quote(ticker)
                except Exception:
                    quote = None

            eval_res = self.evaluate_instrument(ticker, df, live_quote=quote, market_type=market_category)
            evaluations[ticker] = eval_res

        # Filter passing candidates
        passing = [ev for ev in evaluations.values() if ev.passed_all_gates]
        passing.sort(key=lambda x: x.composite_score, reverse=True)

        selected_instruments = [ev.ticker for ev in passing[:k_target]]

        # Construct overall setup wizard rationale
        adv_thresh, currency_sym = self.get_adv_threshold(market_category)
        if len(selected_instruments) >= self.criteria.target_basket_min:
            selected_evals = [evaluations[t] for t in selected_instruments]
            avg_adv = sum(e.adv for e in selected_evals) / len(selected_evals)
            avg_spread = sum(e.spread_bps for e in selected_evals) / len(selected_evals)
            avg_vol = sum(e.annualized_volatility for e in selected_evals) / len(selected_evals)
            summary_rationale = (
                f"Auto-selected {len(selected_instruments)} high-liquidity {market_category} instruments "
                f"({', '.join(selected_instruments)}) with mean ADV of {currency_sym}{avg_adv:,.0f}, "
                f"average spread of {avg_spread:.1f} bps, and optimal annualized volatility of {avg_vol:.1%}. "
                f"All instruments meet institutional data quality (>=90%) and execution gates."
            )
        elif len(selected_instruments) > 0:
            summary_rationale = (
                f"WARNING: Only {len(selected_instruments)} instruments ({', '.join(selected_instruments)}) "
                f"passed all risk gates, below the target of {k_target}. Market liquidity or data quality "
                f"is currently restricted."
            )
        else:
            summary_rationale = (
                f"REJECTION: Zero candidate instruments in {market_category} satisfied all institutional "
                f"liquidity, spread, data quality, and volatility gates. No trading basket can be recommended safely."
            )

        return UniverseSelectionResult(
            market=market_category,
            target_size=k_target,
            selected_instruments=selected_instruments,
            evaluations=evaluations,
            passed_count=len(passing),
            rejected_count=len(evaluations) - len(passing),
            summary_rationale=summary_rationale,
        )
