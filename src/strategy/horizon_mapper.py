"""Multi-Horizon Strategy Parameter Binding Module.

Dynamically maps trading horizons (1 hour, 1 day, 1 week) to quantitative model
configurations, bar intervals, lookbacks, feature spans, ATR windows, exact annualization
factors (140.2, 40.5, 15.87), TCN architectures, triple barriers, and session policies.
"""

from dataclasses import asdict, dataclass
import logging
from typing import Any, Dict, List, Optional

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
