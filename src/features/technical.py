"""Technical Feature Engineering Pipeline.

Leak-free calculations of trend, momentum, volatility, and volume indicators.
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TechnicalFeaturePipeline:
    """Computes technical indicator feature matrix from OHLCV data."""

    @staticmethod
    def compute_features(df: pd.DataFrame) -> pd.DataFrame:
        """Generates comprehensive technical feature set.

        Requires columns: [Open, High, Low, Close, Volume]
        """
        if df.empty or len(df) < 30:
            return pd.DataFrame()

        feats = pd.DataFrame(index=df.index)
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        open_p = df["Open"]
        vol = df["Volume"]

        # 1. Price Momentum & Returns
        feats["Return_1d"] = close.pct_change(1)
        feats["Return_5d"] = close.pct_change(5)
        feats["Return_20d"] = close.pct_change(20)
        feats["LogReturn"] = np.log(close / close.shift(1))

        # 2. Moving Averages & Trend
        ema9 = close.ewm(span=9, adjust=False).mean()
        ema21 = close.ewm(span=21, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        ema200 = close.ewm(span=200, adjust=False).mean()

        feats["EMA9_Dist"] = (close - ema9) / ema9
        feats["EMA21_Dist"] = (close - ema21) / ema21
        feats["EMA50_Dist"] = (close - ema50) / ema50
        feats["Trend_9_21"] = (ema9 - ema21) / close
        feats["Trend_21_50"] = (ema21 - ema50) / close

        # Distance to 200 EMA (Long-term structural bias)
        feats["EMA200_Dist"] = (close - ema200) / ema200

        # 3. MACD (12, 26, 9)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        feats["MACD_Line"] = macd_line / close
        feats["MACD_Signal"] = macd_signal / close
        feats["MACD_Hist"] = (macd_line - macd_signal) / close

        # 4. Relative Strength Index (RSI 14)
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=14, min_periods=14).mean()
        avg_loss = loss.rolling(window=14, min_periods=14).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        feats["RSI14"] = 100.0 - (100.0 / (1.0 + rs))

        # 5. Volatility & ATR (Average True Range)
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr14 = true_range.rolling(window=14, min_periods=14).mean()

        feats["ATR14"] = atr14
        feats["ATR_Pct"] = atr14 / close  # Normalized ATR %
        feats["RealizedVol_21d"] = (
            feats["LogReturn"].rolling(window=21).std() * np.sqrt(252)
        )

        # 6. Bollinger Bands (20, 2 std)
        bb_mid = close.rolling(window=20).mean()
        bb_std = close.rolling(window=20).std()
        bb_upper = bb_mid + 2.0 * bb_std
        bb_lower = bb_mid - 2.0 * bb_std

        feats["BB_Width"] = (bb_upper - bb_lower) / bb_mid
        feats["BB_Position"] = (close - bb_lower) / (bb_upper - bb_lower + 1e-10)

        # 7. Candlestick Anatomy
        candle_range = high - low + 1e-10
        feats["Body_Ratio"] = (close - open_p).abs() / candle_range
        feats["Upper_Shadow"] = (high - np.maximum(close, open_p)) / candle_range
        feats["Lower_Shadow"] = (np.minimum(close, open_p) - low) / candle_range

        # 8. Volume Features
        vol_sma20 = vol.rolling(window=20).mean()
        feats["Volume_Ratio"] = vol / (vol_sma20 + 1e-10)

        # Drop burn-in rows
        return feats.dropna()
