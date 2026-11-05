# Handoff Report: UniverseSelector & HorizonMapper (Milestone 1, Part A)

**Author**: Universe and Horizon Explorer (`teamwork_explorer`)  
**Recipient**: Lead Orchestrator & Quantitative Implementation Agents  
**Date**: November 5, 2026  
**Type**: Hard Handoff (Investigation & Specifications Complete)  
**Location**: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m1_explorer_1\handoff.md`  

---

## 1. Observation

Direct observations from inspecting `C:\Users\Shivam\Desktop\trade_bot`:

1. **Non-Existent Strategy Package**:
   - `src/` contains `backtest/`, `data/`, `execution/`, `features/`, `models/`, `observer/`, and `pipeline.py`.
   - `src/strategy/` does **not exist**. Strategy logic, universe filtering, and horizon mapping are missing as dedicated modules.

2. **Hardcoded Daily Horizon Parameters in Existing Codebase**:
   - `src/features/technical.py:81`:
     ```python
     feats["RealizedVol_21d"] = feats["LogReturn"].rolling(window=21).std() * np.sqrt(252)
     ```
   - `src/models/regime_hmm.py:92` and line 101:
     ```python
     rolling_vol = pd.Series(returns).rolling(window=21, min_periods=3).std()... * np.sqrt(252.0)
     parkinson_bar = np.sqrt(np.maximum(hl_ratio**2 / (4.0 * np.log(2.0)), 0.0)) * np.sqrt(252.0)
     ```
   - `src/pipeline.py:113-114`:
     ```python
     def analyze_ticker(self, ticker: str, period: str = "2y", interval: str = "1d", ...)
     ```
   - `src/execution/live_bot.py:992-1012`:
     ```python
     vol_bar = max(r.volatility_cone.expected_vol_annualized / np.sqrt(252.0), 0.012)
     ...
     pt_p = round(ref_entry_p * (1.0 + 1.4 * vol_bar), decimals)
     sl_p = round(ref_entry_p * (1.0 - 1.0 * vol_bar), decimals)
     ```
     Annualization is hardcoded to $\sqrt{252}$ everywhere; bar intervals are hardcoded to `"1d"` or `"1y"`; barrier multipliers are hardcoded to $1.4\times / 1.0\times$.

3. **Existing Market Catalogs and Downloader Capabilities**:
   - `src/execution/live_bot.py:47-53` defines `ASSET_CATALOG` (`"US_EQUITIES"`, `"CRYPTO"`, `"COMMODITIES"`, `"FOREX"`, `"INDIAN_NSE"`) and `SEARCHABLE_INSTRUMENTS` (lines 56–135) with 45+ instruments across markets.
   - `src/data/downloader.py:240-258` contains `get_market_type(ticker)` returning `"NSE_CASH"`, `"FOREX"`, `"COMMODITY"`, `"CRYPTO"`, or `"US"`.
   - `src/data/downloader.py:120-130` clamps Yahoo Finance lookback periods for intraday intervals:
     `5m/15m/30m` $\to$ clamped to `"60d"`, `1h` $\to$ clamped to `"730d"`, `1m/2m` $\to$ clamped to `"7d"`.
   - `src/data/provider_base.py:64-104` defines `LiveQuote` with `spread`, `spread_bps`, `mid_price`, and `is_valid`.
   - `src/execution/frictions.py:30-88` defines `PROFILES` with exact statutory schedules, slippage, and impact coefficients for `"US"`, `"NSE_CASH"`, `"CRYPTO"`, `"FOREX"`, and `"COMMODITY"`.

4. **Phase 1 & 2 Mathematical Invariants Pass**:
   - Running `Set-Location C:\Users\Shivam\Desktop\trade_bot; py tests/test_phase1_phase2_fixes.py` yielded:
     ```
     [PASS 1] FracDiff analytical lookback L*(0.25, 1e-3) = 21 bars
     [PASS 2] Causal HMM Future-Invariance (state diffs before bar 150): 0 (Expected: 0)
     [PASS 3] Triple-Barrier Dual-Breach Wick Label (Conservative Conflict Resolution): 0 (Expected: 0)
     [PASS 4] HRP RMT Diagonal Variance Preservation Error: 0.00e+00, Ward Weights Sum: 1.0001
     [PASS 5] Frictions -> NSE Delivery: 34.97 bps, NSE Intraday: 16.27 bps, US ($200): 8.15 bps
     [PASS 6] Asymmetric CVaR-Kelly -> Low-Prob (p=0.35) Weight: 0.0%, High-Prob Cap: 20.0%
     [PASS 7] Supervised TCN Pinball Loss: 0.00548, Monotonic Quantiles: q10=-0.0206 <= q50=0.0014 <= q90=0.0224
     [PASS 8] Microstructure Gates -> FX Rollover Allowed: False, Gold Sweep Allowed: False
     === ALL 8 PHASE 1, 2 & 3 MATHEMATICAL & MICROSTRUCTURE INVARIANTS VERIFIED ===
     ```

---

## 2. Logic Chain

1. **Need for `UniverseSelector` (`src/strategy/universe_selector.py`)**:
   - *Observation 1 & 3*: Setup Wizard step 2 requires auto-selecting 3 to 6 instruments based on liquidity, volume, spread, and strategy compatibility, while avoiding illiquid or broken instruments.
   - *Logic*: We establish 4 sequential hard gates:
     1. $Q_{\text{data}} \ge 0.90$ (eliminates corrupt feeds, missing bars, and frozen zero-volume trading).
     2. $\text{ADV} \ge \text{Threshold}$ ($\ge \$5\text{M}$ US, $\ge \text{₹}50\text{M}$ NSE, $\ge \$10\text{M}$ Crypto; eliminates high market impact).
     3. $\text{Spread} \le 25\text{ bps}$ (eliminates friction drag).
     4. $8.0\% \le \sigma_{\text{ann}} \le 100.0\%$ (eliminates dead money $<8\%$ and unmanageable tail risk $>100\%$).
   - Passing instruments are scored via composite ranking ($S_{\text{composite}} = 0.35 S_{\text{liq}} + 0.25 S_{\text{spread}} + 0.20 S_{\text{qual}} + 0.20 S_{\text{vol}}$), and top $K \in [3, 6]$ candidates are selected with plain-language rationales.

2. **Need for `HorizonMapper` (`src/strategy/horizon_mapper.py`)**:
   - *Observation 2*: System currently operates under daily assumptions. A 1-hour intraday trading session cannot use 1-day bars, $\sqrt{252}$ annualization, or multi-day delivery STT.
   - *Logic*: 
     - 1-hour horizon requires 5-minute bars ($390\text{ min} / 5\text{ min} = 78\text{ bars/day}$, $N = 252 \times 78 = 19,656$ bars/yr), resulting in an annualization factor of $\sqrt{19656} = \mathbf{140.2}$. Holding period is 12 bars (60 min), session-end policy is `"CLOSE_POSITIONS"`, and NSE friction is intraday STT.
     - 1-day horizon requires 1-hour bars ($6.5\text{ bars/day}$, $N = 252 \times 6.5 = 1,638$ bars/yr), resulting in an annualization factor of $\sqrt{1638} = \mathbf{40.5}$. Holding period is 7 bars.
     - 1-week horizon requires daily bars ($N = 252$ bars/yr), resulting in an annualization factor of $\sqrt{252} = \mathbf{15.87}$. Holding period is 5 bars, session-end policy is `"KEEP_OPEN"`, and NSE friction is delivery STT.
   - Binding these via an immutable `HorizonParameters` dataclass decouples model mathematics from timeframes.

---

## 3. Caveats

1. **Intraday Data Availability on Free Yahoo Feeds**:
   - Yahoo Finance limits 5-minute bars to 60 days of historical data. The downloader already enforces clamping, but `lookback_period` for 1-hour horizon must not exceed `"60d"` (we specify `"5d"` as default for 1h).
2. **Forex Tick Volume Interpretation**:
   - Certain Forex data feeds report zero or synthetic volume. In `UniverseSelector`, the zero-volume penalty is bypassed for `"FOREX"` jurisdiction, gating currency pairs strictly on price continuity and non-zero variance.
3. **Setup Wizard Session Duration vs Holding Horizon**:
   - The UI and backend must maintain strict conceptual separation: `HorizonMapper` defines the holding horizon (1h, 1d, 1wk), while `TradingSession` defines the session run duration (1h, 4h, 1d, 1wk, custom, manual stop).

---

## 4. Conclusion & Concrete Class Blueprints

### 4.1 Class Blueprint: `src/strategy/universe_selector.py`

```python
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
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from src.data.downloader import MarketDataDownloader
from src.data.provider_base import BaseMarketDataProvider, LiveQuote
from src.execution.frictions import PROFILES, FrictionEvaluator
from src.execution.live_bot import ASSET_CATALOG, SEARCHABLE_INSTRUMENTS

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
            Q_data = 1.0 - (0.60 * R_missing + 0.40 * R_zero_vol)
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
        if live_quote is not None and live_quote.is_valid and live_quote.spread_bps > 0:
            return float(live_quote.spread_bps)

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

        # 2. Spread tightness factor (linear 0 to 25 bps)
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
        market_category = self.resolve_market_category(
            market_type or self.downloader.get_market_type(ticker)
        )
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
            df = self.downloader.download_ticker(ticker, period="60d", interval="1d")
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
```

---

### 4.2 Class Blueprint: `src/strategy/horizon_mapper.py`

```python
"""Multi-Horizon Strategy Parameter Binding Module.

Dynamically maps trading horizons (1 hour, 1 day, 1 week) to quantitative model
configurations, bar intervals, lookbacks, feature spans, ATR windows, exact annualization
factors (140.2, 40.5, 15.87), TCN architectures, triple barriers, and session policies.
"""

from dataclasses import asdict, dataclass
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HorizonParameters:
    """Immutable parameter container bound to a specific trading horizon."""

    horizon_name: str  # Canonical name: "1 hour", "1 day", "1 week"
    category: str  # "INTRADAY", "DAILY", "SWING"
    bar_interval: str  # Primary execution interval: "5m", "1h", "1d"
    secondary_interval: str  # Micro-structure entry interval: "1m", "15m", "1h"
    lookback_period: str  # Historical training lookback: "5d", "60d", "2y"
    min_bars_required: int  # Minimum bar count for pipeline initialization
    feature_fast_ema: int  # Fast EMA span (9)
    feature_slow_ema: int  # Slow EMA span (21)
    feature_macro_ema: int  # Macro structural EMA span (50 or 200)
    atr_window: int  # Average True Range smoothing window (14)
    annualization_factor: float  # Exact volatility scaling: 140.2 (1h), 40.5 (1d), 15.87 (1wk)
    bars_per_day: float  # Number of bars in standard trading session: 78.0, 6.5, 1.0
    hmm_window_bars: int  # Rolling causal HMM window length
    tcn_seq_len: int  # PyTorch Causal Quantile TCN sequence length (bars)
    tcn_horizon_bars: int  # Forward prediction horizon (bars)
    pt_vol_mult: float  # Profit-taking barrier multiplier (x bar volatility)
    sl_vol_mult: float  # Stop-loss barrier multiplier (x bar volatility)
    vol_floor_bar: float  # Single-bar volatility floor to prevent zero-width barriers
    max_holding_bars: int  # Maximum holding horizon before time-expiry barrier triggers
    is_intraday_friction: bool  # True: applies intraday NSE STT; False: applies delivery STT
    default_session_end_policy: str  # "CLOSE_POSITIONS" or "KEEP_OPEN"
    quote_staleness_threshold_sec: float  # Maximum allowable quote age before halting entries
    signal_cooldown_bars: int  # Minimum bar interval between consecutive entries

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HorizonMapper:
    """Factory and registry binding quantitative strategy parameters across horizons."""

    # Exact registry matching specification
    _REGISTRY: Dict[str, HorizonParameters] = {
        "1 hour": HorizonParameters(
            horizon_name="1 hour",
            category="INTRADAY",
            bar_interval="5m",
            secondary_interval="1m",
            lookback_period="5d",
            min_bars_required=60,
            feature_fast_ema=9,
            feature_slow_ema=21,
            feature_macro_ema=50,
            atr_window=14,
            annualization_factor=140.2,  # sqrt(252 * 78) = 140.1998... -> 140.2
            bars_per_day=78.0,
            hmm_window_bars=60,
            tcn_seq_len=24,
            tcn_horizon_bars=12,  # 12 * 5m = 60 minutes = 1 hour
            pt_vol_mult=1.0,
            sl_vol_mult=0.75,
            vol_floor_bar=0.003,
            max_holding_bars=12,
            is_intraday_friction=True,
            default_session_end_policy="CLOSE_POSITIONS",
            quote_staleness_threshold_sec=60.0,
            signal_cooldown_bars=3,
        ),
        "1 day": HorizonParameters(
            horizon_name="1 day",
            category="DAILY",
            bar_interval="1h",
            secondary_interval="15m",
            lookback_period="60d",
            min_bars_required=100,
            feature_fast_ema=9,
            feature_slow_ema=21,
            feature_macro_ema=50,
            atr_window=14,
            annualization_factor=40.5,  # sqrt(252 * 6.5) = 40.472... -> 40.5
            bars_per_day=6.5,
            hmm_window_bars=120,
            tcn_seq_len=30,
            tcn_horizon_bars=7,  # ~1 trading day forward
            pt_vol_mult=1.5,
            sl_vol_mult=1.0,
            vol_floor_bar=0.008,
            max_holding_bars=7,
            is_intraday_friction=True,
            default_session_end_policy="CLOSE_POSITIONS",
            quote_staleness_threshold_sec=300.0,
            signal_cooldown_bars=2,
        ),
        "1 week": HorizonParameters(
            horizon_name="1 week",
            category="SWING",
            bar_interval="1d",
            secondary_interval="1h",
            lookback_period="2y",
            min_bars_required=150,
            feature_fast_ema=9,
            feature_slow_ema=21,
            feature_macro_ema=200,
            atr_window=14,
            annualization_factor=15.87,  # sqrt(252) = 15.8745... -> 15.87
            bars_per_day=1.0,
            hmm_window_bars=252,
            tcn_seq_len=30,
            tcn_horizon_bars=5,  # 5 trading days = 1 week forward
            pt_vol_mult=2.0,
            sl_vol_mult=1.25,
            vol_floor_bar=0.015,
            max_holding_bars=5,
            is_intraday_friction=False,
            default_session_end_policy="KEEP_OPEN",
            quote_staleness_threshold_sec=1800.0,
            signal_cooldown_bars=1,
        ),
    }

    @classmethod
    def normalize_horizon(cls, horizon: str) -> str:
        """Converts user input or API parameters to standard canonical horizon string."""
        h = horizon.strip().lower().replace("_", " ").replace("-", " ")
        if h in ["1 hour", "1h", "1hour", "intraday", "hourly"]:
            return "1 hour"
        elif h in ["1 day", "1d", "1day", "daily", "eod"]:
            return "1 day"
        elif h in ["1 week", "1wk", "1w", "1week", "swing", "weekly"]:
            return "1 week"
        raise ValueError(
            f"Unsupported trading horizon '{horizon}'. Must be one of: '1 hour', '1 day', '1 week'."
        )

    @classmethod
    def get_parameters(cls, horizon: str, market_type: str = "US") -> HorizonParameters:
        """Retrieves immutable HorizonParameters for the specified horizon."""
        canonical = cls.normalize_horizon(horizon)
        return cls._REGISTRY[canonical]

    @classmethod
    def list_supported_horizons(cls) -> List[str]:
        """Returns list of canonical supported horizon names."""
        return list(cls._REGISTRY.keys())
```

---

## 5. Verification Method

### Test Suite 1: `tests/test_strategy_universe_selector.py`
Verify the implementation handles all gates, math calculations, and basket selection:
1. `test_data_quality_score`:
   - Valid OHLCV $\to Q_{\text{data}} = 1.0$.
   - 15% NaN rows $\to Q_{\text{data}} = 1.0 - 0.60 \times 0.15 = 0.91 \ge 0.90$ (Pass).
   - 15% NaN rows and 15% zero volume rows $\to Q_{\text{data}} = 1.0 - (0.09 + 0.06) = 0.85 < 0.90$ (Fail: `LOW_DATA_QUALITY`).
2. `test_adv_liquidity_gates`:
   - US Equities: $ADV = \$6\text{M} \to$ Pass, $ADV = \$4.5\text{M} \to$ Fail (`INSUFFICIENT_LIQUIDITY`).
   - NSE Cash: $ADV = \text{₹}60\text{M} \to$ Pass, $ADV = \text{₹}40\text{M} \to$ Fail.
   - Crypto: $ADV = \$12\text{M} \to$ Pass, $ADV = \$8\text{M} \to$ Fail.
3. `test_spread_gate`:
   - LiveQuote with 15 bps spread $\to$ Pass.
   - LiveQuote with 28 bps spread $\to$ Fail (`SPREAD_TOO_WIDE`).
4. `test_volatility_tradability_bounds`:
   - $\sigma_{\text{ann}} = 5\% \to$ Fail (`STAGNANT_VOLATILITY`).
   - $\sigma_{\text{ann}} = 28\% \to$ Pass.
   - $\sigma_{\text{ann}} = 115\% \to$ Fail (`EXCESSIVE_VOLATILITY`).
5. `test_auto_select_basket_bounding`:
   - 10 passing candidates with `target_size=5` $\to$ returns exactly 5 top-ranked instruments.
   - `target_size=1` $\to$ clamped to minimum 3.
   - `target_size=10` $\to$ clamped to maximum 6.
   - Zero passing candidates $\to$ returns empty basket `[]` with full rejection logs in `evaluations`.

### Test Suite 2: `tests/test_strategy_horizon_mapper.py`
1. `test_canonical_horizon_normalization`:
   - `"1h"`, `"1hour"`, `"intraday"` $\to$ `"1 hour"`.
   - `"1d"`, `"daily"` $\to$ `"1 day"`.
   - `"1wk"`, `"weekly"` $\to$ `"1 week"`.
   - Unsupported string raises `ValueError`.
2. `test_exact_annualization_factors`:
   - `"1 hour"` $\to$ `140.2`.
   - `"1 day"` $\to$ `40.5`.
   - `"1 week"` $\to$ `15.87`.
3. `test_bar_interval_and_lookback`:
   - `"1 hour"` $\to$ `"5m"`, `"5d"`.
   - `"1 day"` $\to$ `"1h"`, `"60d"`.
   - `"1 week"` $\to$ `"1d"`, `"2y"`.
4. `test_triple_barrier_and_tcn_parameters`:
   - `"1 hour"` $\to$ `pt_vol_mult=1.0`, `sl_vol_mult=0.75`, `tcn_horizon_bars=12`, `max_holding_bars=12`.
   - `"1 day"` $\to$ `pt_vol_mult=1.5`, `sl_vol_mult=1.0`, `tcn_horizon_bars=7`, `max_holding_bars=7`.
   - `"1 week"` $\to$ `pt_vol_mult=2.0`, `sl_vol_mult=1.25`, `tcn_horizon_bars=5`, `max_holding_bars=5`.
5. `test_session_end_policy_and_friction_mode`:
   - `"1 hour"` $\to$ `default_session_end_policy="CLOSE_POSITIONS"`, `is_intraday_friction=True`.
   - `"1 day"` $\to$ `default_session_end_policy="CLOSE_POSITIONS"`, `is_intraday_friction=True`.
   - `"1 week"` $\to$ `default_session_end_policy="KEEP_OPEN"`, `is_intraday_friction=False`.

### Independent Verification Commands:
```powershell
cd C:\Users\Shivam\Desktop\trade_bot
# Baseline Phase 1 & 2 invariant check
py tests/test_phase1_phase2_fixes.py

# Run newly implemented strategy tests
py -m pytest tests/test_strategy_universe_selector.py tests/test_strategy_horizon_mapper.py -v
```

### Invalidation Conditions:
- If `UniverseSelector` recommends an instrument with ADV below the statutory threshold (e.g. $<\$5\text{M}$ for US Equities), the selection gate is invalidated.
- If `UniverseSelector` recommends an instrument with spread $>25\text{ bps}$, the spread gate is invalidated.
- If `UniverseSelector` recommends an instrument with volatility $<8\%$ or $>100\%$, the tradability gate is invalidated.
- If `HorizonMapper` returns annualization factors differing from **140.2**, **40.5**, or **15.87**, the invariant is invalidated.
- If changing virtual capital changes model predictions ($P(\text{Win})$, targets, barriers), capital invariance is invalidated.
