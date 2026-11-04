"""Market Data Normalizer & Cleaner."""

import logging
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class MarketDataNormalizer:
    """Sanitizes, aligns, and standardizes multi-asset market series."""

    @staticmethod
    def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
        """Removes zero/negative prices, sorts index, and removes duplicates."""
        if df.empty:
            return df

        df = df.copy()
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="first")]

        # Filter strictly positive prices
        price_cols = [c for c in ["Open", "High", "Low", "Close"] if c in df.columns]
        for col in price_cols:
            df = df[df[col] > 0]

        # Fix minor high/low inversion anomalies if any
        if "High" in df.columns and "Low" in df.columns:
            df["High"] = df[["Open", "High", "Close"]].max(axis=1)
            df["Low"] = df[["Open", "Low", "Close"]].min(axis=1)

        # Log returns
        df["LogReturn"] = np.log(df["Close"] / df["Close"].shift(1))
        df["Return"] = df["Close"].pct_change()
        return df

    @staticmethod
    def align_multi_asset_close(data_dict: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Extracts aligned Close prices across multiple tickers with forward fill."""
        close_series = {}
        for ticker, df in data_dict.items():
            if not df.empty and "Close" in df.columns:
                close_series[ticker] = df["Close"]

        if not close_series:
            return pd.DataFrame()

        aligned = pd.DataFrame(close_series)
        aligned = aligned.sort_index()
        aligned = aligned.ffill().dropna()
        return aligned

    @staticmethod
    def compute_asset_returns(aligned_close: pd.DataFrame) -> pd.DataFrame:
        """Computes daily/period percentage returns for aligned asset prices."""
        return aligned_close.pct_change().dropna()
