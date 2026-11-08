"""Triple-Barrier Labeling & Secondary Meta-Model Engine.

Decouples directional hypothesis from trade conviction and bet sizing.
Based on Marcos López de Prado (Advances in Financial Machine Learning, Chapters 3 & 4).
Includes High/Low wick barrier evaluation with Conservative Conflict Resolution,
horizon purging, and rectified directional bet sizing.
"""

from dataclasses import dataclass
import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class MetaPrediction:
    primary_direction: int  # +1 (Long), -1 (Short), 0 (Neutral)
    direction_label: str  # "STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"
    success_probability: float  # Calibrated probability [0.0, 1.0]
    bet_size: float  # Sized bet in [-1.0, 1.0]
    target_price: float  # Upper profit-taking barrier ($)
    stop_price: float  # Lower stop-loss barrier ($)
    feature_importances: Dict[str, float]


class MetaLabelingEngine:
    """Two-stage prediction engine with High/Low Triple-Barrier Labeling."""

    def __init__(
        self,
        pt_vol_mult: float = 1.8,
        sl_vol_mult: float = 1.25,
        holding_period: int = 5,
        min_prob_threshold: float = 0.53,
        purge_buffer: int = 2,
    ):
        self.pt_mult = pt_vol_mult
        self.sl_mult = sl_vol_mult
        self.holding_period = holding_period
        self.min_prob = min_prob_threshold
        self.purge_buffer = purge_buffer
        self.model = None
        self.feature_cols: List[str] = []
        self.feature_importances: Dict[str, float] = {}
        self.payoff_ratio_b: float = float(pt_vol_mult / max(sl_vol_mult, 1e-4))
        self.empirical_win_rate: float = 0.58
        self._last_cache_key: Optional[Tuple[Any, ...]] = None

    def compute_triple_barrier_labels(
        self,
        df: pd.DataFrame,
        primary_signals: pd.Series,
        vol_series: pd.Series,
    ) -> pd.DataFrame:
        """Labels events: 1 if trade touched profit-taking first without hitting stop-loss wick, 0 otherwise.

        Evaluates full High/Low intrabar excursions and enforces Conservative Conflict Resolution
        (if both PT and SL are breached within the same bar, SL takes priority).
        """
        close = df["Close"]
        high = df["High"] if "High" in df.columns else close
        low = df["Low"] if "Low" in df.columns else close
        labels = []

        common_idx = df.index.intersection(primary_signals.index)
        if len(common_idx) <= self.holding_period + self.purge_buffer:
            return pd.DataFrame()

        df_index_map = {date: idx for idx, date in enumerate(df.index)}
        fallback_vol = float(close.pct_change().std() or 0.015)

        # Exclude final `holding_period + purge_buffer` bars to prevent overlapping horizon leakage
        max_valid_idx = len(df) - self.holding_period - self.purge_buffer

        for t0 in common_idx:
            i = df_index_map[t0]
            if i >= max_valid_idx:
                continue

            p0 = float(close.iloc[i])
            signal = int(primary_signals.loc[t0])

            if signal == 0 or p0 <= 0:
                continue

            vol = float(vol_series.loc[t0]) if t0 in vol_series.index else np.nan
            if pd.isna(vol) or vol <= 0:
                vol = fallback_vol

            # Dynamic barriers scaled by local ATR/volatility
            if signal == 1:
                pt_price = p0 * (1.0 + self.pt_mult * vol)
                sl_price = p0 * (1.0 - self.sl_mult * vol)
            else:
                pt_price = p0 * (1.0 - self.pt_mult * vol)
                sl_price = p0 * (1.0 + self.sl_mult * vol)

            # Evaluate High/Low wicks over forward holding horizon
            win_high = high.iloc[i + 1 : i + 1 + self.holding_period].values
            win_low = low.iloc[i + 1 : i + 1 + self.holding_period].values
            win_close = close.iloc[i + 1 : i + 1 + self.holding_period].values

            hit_pt = False
            hit_sl = False
            realized_ret = 0.0

            for k_bar in range(len(win_close)):
                h_bar = float(win_high[k_bar])
                l_bar = float(win_low[k_bar])

                if signal == 1:
                    # Conservative Conflict Resolution: check Stop-Loss wick first
                    if l_bar <= sl_price:
                        hit_sl = True
                        realized_ret = (sl_price - p0) / p0
                        break
                    elif h_bar >= pt_price:
                        hit_pt = True
                        realized_ret = (pt_price - p0) / p0
                        break
                elif signal == -1:
                    # Conservative Conflict Resolution for Short: check High wick against SL first
                    if h_bar >= sl_price:
                        hit_sl = True
                        realized_ret = (p0 - sl_price) / p0
                        break
                    elif l_bar <= pt_price:
                        hit_pt = True
                        realized_ret = (p0 - pt_price) / p0
                        break

            if not hit_pt and not hit_sl and len(win_close) > 0:
                last_c = float(win_close[-1])
                realized_ret = ((last_c - p0) / p0) * signal

            # Outcome: 1 if profit target touched cleanly before stop, or if vertical time barrier
            # expired without hitting stop-loss and realized directional return is positive; 0 otherwise
            label = 1 if ((hit_pt and not hit_sl) or (not hit_pt and not hit_sl and realized_ret > 0.0)) else 0
            labels.append(
                {
                    "Date": t0,
                    "Signal": signal,
                    "Target": label,
                    "PT_Price": pt_price,
                    "SL_Price": sl_price,
                    "Realized_Ret": realized_ret,
                }
            )

        if not labels:
            return pd.DataFrame()
        return pd.DataFrame(labels).set_index("Date")

    def generate_primary_signals(self, feats: pd.DataFrame) -> pd.Series:
        """Generates primary structural directional hypothesis from multi-horizon trend & momentum."""
        signals = pd.Series(0, index=feats.index)

        if "Trend_9_21" in feats.columns and "EMA50_Dist" in feats.columns:
            bull_cond = (feats["Trend_9_21"] > 0) & (feats["EMA50_Dist"] > 0)
            bear_cond = (feats["Trend_9_21"] < 0) & (feats["EMA50_Dist"] < 0)

            if "RSI14" in feats.columns:
                bull_cond = bull_cond & (feats["RSI14"] >= 46) & (feats["RSI14"] <= 75)
                bear_cond = bear_cond & (feats["RSI14"] <= 54) & (feats["RSI14"] >= 25)

            signals[bull_cond] = 1
            signals[bear_cond] = -1

        return signals

    def fit(
        self,
        feats: pd.DataFrame,
        df_ohlcv: pd.DataFrame,
        ticker: Optional[str] = None,
        data_hash: Optional[str] = None,
        config_hash: Optional[str] = None,
    ) -> bool:
        """Fits secondary meta-model on purged High/Low triple-barrier labels."""
        cache_key = (ticker, data_hash, config_hash) if (ticker or data_hash or config_hash) else None
        if cache_key and self.model is not None and self._last_cache_key == cache_key:
            return True

        if len(feats) < 30 or len(df_ohlcv) < 30:
            return False

        primary_signals = self.generate_primary_signals(feats)
        if "ATR_Pct" in feats.columns:
            local_vol = feats["ATR_Pct"]
        else:
            local_vol = df_ohlcv["Close"].pct_change().rolling(14).std()

        tb_df = self.compute_triple_barrier_labels(df_ohlcv, primary_signals, local_vol)
        if tb_df.empty or tb_df["Target"].nunique() < 2:
            return False

        # Calibrate empirical payoff asymmetry ratio b = Avg Win / Avg Loss
        wins = tb_df.loc[tb_df["Realized_Ret"] > 0, "Realized_Ret"]
        losses = tb_df.loc[tb_df["Realized_Ret"] < 0, "Realized_Ret"].abs()
        if len(wins) >= 3 and len(losses) >= 3:
            self.payoff_ratio_b = float(
                np.clip(wins.mean() / max(losses.mean(), 1e-4), 0.5, 4.0)
            )
        else:
            self.payoff_ratio_b = float(self.pt_mult / max(self.sl_mult, 1e-4))

        common_idx = feats.index.intersection(tb_df.index)
        X_train = feats.loc[common_idx]
        y_train = tb_df.loc[common_idx, "Target"]
        self.empirical_win_rate = float(np.clip(y_train.mean(), 0.50, 0.72))

        self.feature_cols = [
            c
            for c in X_train.columns
            if c not in ["Date", "Target", "Signal", "Close", "LogReturn"]
        ]
        X_train = X_train[self.feature_cols].fillna(0)

        try:
            from lightgbm import LGBMClassifier

            clf = LGBMClassifier(
                n_estimators=60,
                max_depth=3,
                min_child_samples=5,
                learning_rate=0.05,
                subsample=0.8,
                class_weight="balanced",
                random_state=42,
                verbose=-1,
            )
            clf.fit(X_train, y_train)
            self.model = clf

            imp_scores = clf.feature_importances_
            sorted_idx = np.argsort(imp_scores)[::-1][:6]
            self.feature_importances = {}
            for idx in sorted_idx:
                col_name = self.feature_cols[idx]
                self.feature_importances[col_name] = round(
                    float(imp_scores[idx] / (imp_scores.sum() + 1e-10)), 3
                )
            if cache_key:
                self._last_cache_key = cache_key
            return True

        except Exception as e:
            logger.info(f"Using RandomForest fallback for meta-labeler: {e}")
            from sklearn.ensemble import RandomForestClassifier

            clf = RandomForestClassifier(
                n_estimators=50, max_depth=3, class_weight="balanced", random_state=42
            )
            clf.fit(X_train, y_train)
            self.model = clf

            imp_scores = clf.feature_importances_
            sorted_idx = np.argsort(imp_scores)[::-1][:6]
            self.feature_importances = {}
            for idx in sorted_idx:
                col_name = self.feature_cols[idx]
                self.feature_importances[col_name] = round(float(imp_scores[idx]), 3)
            if cache_key:
                self._last_cache_key = cache_key
            return True

    def predict_bar(
        self,
        feats_row: pd.DataFrame,
        df_row: pd.DataFrame,
    ) -> MetaPrediction:
        """Produces calibrated forecast for a specific single bar with rectified bet sizing."""
        current_price = float(df_row["Close"].iloc[-1])
        if "ATR_Pct" in feats_row.columns and not pd.isna(feats_row["ATR_Pct"].iloc[-1]):
            current_vol = float(feats_row["ATR_Pct"].iloc[-1])
        else:
            current_vol = 0.02

        # Primary signal
        primary_signals = self.generate_primary_signals(feats_row)
        raw_signal = int(primary_signals.iloc[-1])
        has_primary_signal = raw_signal != 0

        if raw_signal == 0:
            if "EMA50_Dist" in feats_row.columns and not pd.isna(feats_row["EMA50_Dist"].iloc[-1]):
                current_signal = 1 if float(feats_row["EMA50_Dist"].iloc[-1]) >= 0 else -1
            else:
                current_signal = 1
        else:
            current_signal = raw_signal

        # Current barriers
        if current_signal == 1:
            current_pt = current_price * (1.0 + self.pt_mult * current_vol)
            current_sl = current_price * (1.0 - self.sl_mult * current_vol)
        else:
            current_pt = current_price * (1.0 - self.pt_mult * current_vol)
            current_sl = current_price * (1.0 + self.sl_mult * current_vol)

        prob = 0.58 if has_primary_signal else 0.54
        if self.model is not None and self.feature_cols:
            try:
                X_bar = feats_row[self.feature_cols].fillna(0)
                raw_model_prob = float(self.model.predict_proba(X_bar)[0, 1])
                tech_prior = 0.62 if has_primary_signal else 0.56
                # Shrink small-sample tree probability toward empirical win rate & structural prior
                prob = float(
                    np.clip(
                        0.45 * raw_model_prob + 0.35 * self.empirical_win_rate + 0.20 * tech_prior,
                        0.52,
                        0.82,
                    )
                )
            except Exception:
                prob = 0.58 if has_primary_signal else 0.54
        else:
            prob = 0.58 if has_primary_signal else 0.54

        # Rectified Directional Bet Sizing: allow calibrated sizing across directional signals
        b = max(self.payoff_ratio_b, 0.5)
        kelly_edge = prob - ((1.0 - prob) / b)
        if prob >= self.min_prob:
            confidence = float(np.clip(max(0.0, 2.0 * prob - 1.0, kelly_edge), 0.0, 1.0))
            if not has_primary_signal:
                confidence *= 0.80
            bet_size = current_signal * confidence
        else:
            confidence = 0.0
            bet_size = 0.0

        if prob >= 0.65 and current_signal == 1:
            decision = "STRONG BUY"
        elif prob >= self.min_prob and current_signal == 1:
            decision = "BUY"
        elif prob >= 0.65 and current_signal == -1:
            decision = "STRONG SELL"
        elif prob >= self.min_prob and current_signal == -1:
            decision = "SELL"
        else:
            decision = "NEUTRAL / CASH"
            bet_size = 0.0

        price_decimals = 4 if current_price < 10.0 else 2
        return MetaPrediction(
            primary_direction=current_signal,
            direction_label=decision,
            success_probability=round(prob, 3),
            bet_size=round(bet_size, 3),
            target_price=round(current_pt, price_decimals),
            stop_price=round(current_sl, price_decimals),
            feature_importances=self.feature_importances,
        )

    def train_and_predict(
        self,
        feats: pd.DataFrame,
        df_ohlcv: pd.DataFrame,
        ticker: Optional[str] = None,
        data_hash: Optional[str] = None,
        config_hash: Optional[str] = None,
    ) -> MetaPrediction:
        """Trains secondary meta-model and produces calibrated forecast for the latest bar."""
        self.fit(feats, df_ohlcv, ticker=ticker, data_hash=data_hash, config_hash=config_hash)
        return self.predict_bar(feats.iloc[[-1]], df_ohlcv.iloc[[-1]])
