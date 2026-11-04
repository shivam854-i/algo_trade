"""Foundation Volatility Cone & Quantile Surface Forecaster.

Computes forward multi-horizon probabilistic bounds (q10, q50, q90)
to establish dynamic Value-at-Risk (VaR) cones and expected trajectories.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd


@dataclass
class VolatilityCone:
    periods: List[int]
    q10_prices: List[float]  # Lower 10th percentile bound
    q50_prices: List[float]  # Median expected path
    q90_prices: List[float]  # Upper 90th percentile bound
    expected_vol_annualized: float
    forward_skew: float


class VolatilityConeForecaster:
    """Projects forward quantile cones using heavy-tailed empirical diffusion."""

    def __init__(self, horizons: int = 5):
        self.horizons = horizons

    def project_cone(
        self,
        current_price: float,
        log_returns: pd.Series,
        directional_drift: float = 0.0,
    ) -> VolatilityCone:
        """Projects multi-step forward quantiles (q10, q50, q90)."""
        clean_rets = log_returns.dropna()
        if len(clean_rets) < 20:
            sigma_daily = 0.015
            skewness = 0.0
        else:
            sigma_daily = float(clean_rets.tail(30).std())
            skewness = float(clean_rets.tail(60).skew())

        # If zero or nan, apply default
        if pd.isna(sigma_daily) or sigma_daily <= 0:
            sigma_daily = 0.015
        if pd.isna(skewness):
            skewness = 0.0

        periods = list(range(1, self.horizons + 1))
        q10_prices = []
        q50_prices = []
        q90_prices = []

        # Student-t / heavy-tailed critical z-values (approx. 1.35 for q10/q90 in finance)
        z_90 = 1.35 + 0.15 * skewness
        z_10 = -1.35 + 0.15 * skewness

        drift_daily = directional_drift * (sigma_daily * 0.25)

        for h in periods:
            vol_h = sigma_daily * np.sqrt(h)
            expected_drift = drift_daily * h

            p_median = current_price * np.exp(expected_drift)
            p_upper = current_price * np.exp(expected_drift + z_90 * vol_h)
            p_lower = current_price * np.exp(expected_drift + z_10 * vol_h)

            q50_prices.append(round(float(p_median), 2))
            q90_prices.append(round(float(p_upper), 2))
            q10_prices.append(round(float(p_lower), 2))

        return VolatilityCone(
            periods=periods,
            q10_prices=q10_prices,
            q50_prices=q50_prices,
            q90_prices=q90_prices,
            expected_vol_annualized=round(sigma_daily * np.sqrt(252), 4),
            forward_skew=round(skewness, 3),
        )
