"""Market Regime Detection Module (Causal Forward-Filtering HMM).

Classifies market regimes (Low-Vol Trending, Choppy Range-Bound, High-Vol Crisis)
using an online causal Forward-Filtering Hidden Markov Model with Parkinson High-Low
volatility emissions, instantaneous jump overrides, and hysteresis quarantine.
Eliminates global Viterbi lookahead bias.
"""

from dataclasses import dataclass
import logging
from typing import Dict, List, Optional, Tuple
import warnings
import numpy as np
import pandas as pd
from scipy.stats import multivariate_normal

warnings.filterwarnings("ignore")
logging.getLogger("hmmlearn").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


@dataclass
class RegimeState:
    state_id: int
    name: str
    description: str
    is_crisis: bool
    volatility_scale: float


REGIME_DEFINITIONS = {
    0: RegimeState(
        0,
        "Low-Vol Trending",
        "Stable positive drift; optimal for trend following.",
        False,
        1.0,
    ),
    1: RegimeState(
        1,
        "Choppy Range-Bound",
        "High mean-reversion; moderate volatility.",
        False,
        0.6,
    ),
    2: RegimeState(
        2,
        "High-Vol Crisis",
        "Elevated tail risk; circuit breaker protection active.",
        True,
        0.0,
    ),
}


class MarketRegimeClassifier:
    """Classifies market regimes using strictly causal forward filtering alpha_t(j)."""

    def __init__(
        self,
        n_regimes: int = 3,
        random_state: int = 42,
        crisis_enter_prob: float = 0.70,
        crisis_exit_prob: float = 0.15,
        quarantine_bars: int = 5,
    ):
        self.n_regimes = n_regimes
        self.random_state = random_state
        self.crisis_enter_prob = crisis_enter_prob
        self.crisis_exit_prob = crisis_exit_prob
        self.quarantine_bars = quarantine_bars

        self.model = None
        self.state_mapping: Dict[int, int] = {}
        self.inv_state_mapping: Dict[int, int] = {}
        self.vol_p40: float = 0.15
        self.vol_p80: float = 0.30
        self.ret_std: float = 0.015

    def _extract_feature_matrix(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Extracts causal return and dual-timescale (Close + Parkinson High-Low) volatility."""
        returns = df["Close"].pct_change().fillna(0.0).values.astype(np.float64)

        # Rolling close-to-close annualized volatility
        rolling_vol = (
            pd.Series(returns)
            .rolling(window=21, min_periods=3)
            .std()
            .bfill()
            .fillna(0.01)
            .values
            * np.sqrt(252.0)
        )

        # Parkinson High-Low range volatility (captures single-bar intraday flash crashes immediately)
        if "High" in df.columns and "Low" in df.columns:
            hl_ratio = np.log(
                np.maximum(df["High"].values.astype(np.float64), 1e-8)
                / np.maximum(df["Low"].values.astype(np.float64), 1e-8)
            )
            parkinson_bar = np.sqrt(np.maximum(hl_ratio**2 / (4.0 * np.log(2.0)), 0.0)) * np.sqrt(252.0)
            fast_parkinson = (
                pd.Series(parkinson_bar)
                .ewm(span=5, min_periods=1)
                .mean()
                .values
            )
            composite_vol = np.maximum(rolling_vol, 0.75 * fast_parkinson + 0.25 * rolling_vol)
        else:
            composite_vol = rolling_vol

        X = np.column_stack([returns, composite_vol])
        return X, returns, composite_vol

    def fit(self, df_train: pd.DataFrame) -> bool:
        """Fits HMM transition and emission parameters on a strictly historical training window."""
        if df_train.empty or len(df_train) < 30:
            return False

        X, returns, composite_vol = self._extract_feature_matrix(df_train)
        self.vol_p40 = float(np.quantile(composite_vol, 0.40))
        self.vol_p80 = float(np.quantile(composite_vol, 0.85))
        self.ret_std = max(float(np.std(returns)), 1e-4)

        try:
            from hmmlearn import hmm

            # Add tiny jitter to prevent singular covariance matrices
            rng = np.random.default_rng(self.random_state)
            X_reg = X + rng.normal(0.0, 1e-6, size=X.shape)

            model = hmm.GaussianHMM(
                n_components=self.n_regimes,
                covariance_type="diag",
                n_iter=150,
                random_state=self.random_state,
                min_covar=1e-4,
            )
            model.fit(X_reg)
            self.model = model

            # Sort states by emission volatility mean (column 1 of means_)
            state_vols = [float(model.means_[i, 1]) for i in range(self.n_regimes)]
            sorted_order = np.argsort(state_vols)
            self.state_mapping = {
                int(raw_state): int(sorted_state)
                for sorted_state, raw_state in enumerate(sorted_order)
            }
            self.inv_state_mapping = {v: k for k, v in self.state_mapping.items()}
            return True

        except Exception as e:
            logger.warning(f"hmmlearn fit fallback triggered ({e}); using causal volatility quantiles.")
            self.model = None
            return False

    def filter_causal(self, df: pd.DataFrame) -> pd.Series:
        """Runs online causal forward filtering alpha_t(j) = P(S_t = j | x_{1:t}) without future leakage.

        Enforces instantaneous jump overrides and a 5-bar hysteresis quarantine state machine.
        """
        if df.empty:
            return pd.Series(dtype=int)

        X, returns, composite_vol = self._extract_feature_matrix(df)
        n_obs = len(df)
        regimes = np.zeros(n_obs, dtype=int)

        # Prepare emission densities if HMM is fitted
        has_hmm = self.model is not None and len(self.state_mapping) == self.n_regimes
        if has_hmm:
            try:
                startprob = np.clip(self.model.startprob_, 1e-6, 1.0)
                startprob /= startprob.sum()
                transmat = np.clip(self.model.transmat_, 1e-6, 1.0)
                transmat /= transmat.sum(axis=1, keepdims=True)
                means = self.model.means_
                covars = self.model.covars_

                # Evaluate emission likelihoods B[t, k] = p(x_t | S_t = k)
                emission_probs = np.zeros((n_obs, self.n_regimes), dtype=np.float64)
                for k in range(self.n_regimes):
                    cov_k = covars[k]
                    if cov_k.ndim == 1:
                        cov_k = np.diag(np.maximum(cov_k, 1e-5))
                    elif cov_k.ndim == 2:
                        cov_k = cov_k + np.eye(cov_k.shape[0]) * 1e-5
                    emission_probs[:, k] = np.maximum(
                        multivariate_normal.pdf(X, mean=means[k], cov=cov_k, allow_singular=True),
                        1e-12,
                    )
            except Exception:
                has_hmm = False

        alpha = startprob.copy() if has_hmm else np.array([0.6, 0.3, 0.1])
        crisis_raw_idx = self.inv_state_mapping.get(2, 2) if has_hmm else 2

        in_crisis_quarantine = False
        quarantine_remaining = 0

        for t in range(n_obs):
            ret_t = returns[t]
            vol_t = composite_vol[t]

            if has_hmm:
                if t == 0:
                    alpha_prior = alpha
                else:
                    alpha_prior = alpha @ transmat
                alpha_unnorm = alpha_prior * emission_probs[t]
                denom = alpha_unnorm.sum()
                alpha = (alpha_unnorm / denom) if denom > 0 else alpha_prior

                p_crisis = float(alpha[crisis_raw_idx])
                raw_winner = int(np.argmax(alpha))
                mapped_state = self.state_mapping.get(raw_winner, 0)
            else:
                # Causal quantile fallback
                p_crisis = 0.80 if vol_t >= self.vol_p80 else (0.30 if vol_t >= self.vol_p40 else 0.05)
                mapped_state = 2 if vol_t >= self.vol_p80 else (1 if vol_t >= self.vol_p40 else 0)

            # Instantaneous tail-jump override (> 3.2x historical return std drop or extreme vol spike)
            jump_crash = (ret_t < -3.2 * self.ret_std) or (vol_t > 1.35 * self.vol_p80)

            if jump_crash or p_crisis >= self.crisis_enter_prob:
                in_crisis_quarantine = True
                quarantine_remaining = self.quarantine_bars
                regimes[t] = 2
            elif in_crisis_quarantine:
                if p_crisis <= self.crisis_exit_prob and quarantine_remaining <= 0:
                    in_crisis_quarantine = False
                    regimes[t] = min(mapped_state, 1)
                else:
                    quarantine_remaining -= 1
                    regimes[t] = 2
            else:
                regimes[t] = min(mapped_state, 1) if p_crisis < self.crisis_enter_prob else 2

        return pd.Series(regimes, index=df.index, name="Regime")

    def fit_predict(
        self, df: pd.DataFrame, calibration_bars: Optional[int] = None
    ) -> pd.Series:
        """Fits regime model on historical calibration slice and runs causal forward filter."""
        if df.empty or len(df) < 30:
            return pd.Series(0, index=df.index, name="Regime")

        if calibration_bars is not None and 30 <= calibration_bars < len(df):
            train_slice = df.iloc[:calibration_bars]
        else:
            train_slice = df

        self.fit(train_slice)
        return self.filter_causal(df)

    def get_current_regime(self, df: pd.DataFrame) -> RegimeState:
        """Determines current market regime state for the most recent observation using causal filtering."""
        if df.empty:
            return REGIME_DEFINITIONS[0]
        regime_series = self.fit_predict(df)
        current_id = int(regime_series.iloc[-1])
        return REGIME_DEFINITIONS.get(current_id, REGIME_DEFINITIONS[0])
