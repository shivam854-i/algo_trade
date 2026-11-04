"""Information-Driven Sampling Module.

Implements Volume Bars and Dollar Bars to eliminate calendar clock distortions.
"""

from typing import Optional, Tuple
import numpy as np
import pandas as pd


class DollarBarGenerator:
    """Generates nominal dollar value sampled bars (P * V)."""

    @staticmethod
    def compute_dollar_volume(df: pd.DataFrame) -> pd.Series:
        """Calculates transacted dollar volume per bar."""
        close = df["Close"]
        vol = df["Volume"]
        return close * vol

    @classmethod
    def sample_dollar_bars(
        cls, df: pd.DataFrame, target_dollar_threshold: Optional[float] = None
    ) -> pd.DataFrame:
        """Samples bars when cumulative dollar turnover exceeds target threshold."""
        if df.empty:
            return df

        df = df.copy()
        dollar_vol = cls.compute_dollar_volume(df)

        if target_dollar_threshold is None:
            # Dynamically set threshold to average daily dollar turnover / 10
            target_dollar_threshold = float(dollar_vol.mean())

        cum_dollar = 0.0
        bar_records = []

        cur_open = None
        cur_high = -np.inf
        cur_low = np.inf
        cur_vol = 0.0
        cur_dollar = 0.0

        for idx, row in df.iterrows():
            p = row["Close"]
            v = row["Volume"]
            dv = p * v

            if cur_open is None:
                cur_open = row["Open"]

            cur_high = max(cur_high, row["High"])
            cur_low = min(cur_low, row["Low"])
            cur_vol += v
            cur_dollar += dv
            cum_dollar += dv

            if cum_dollar >= target_dollar_threshold:
                bar_records.append(
                    {
                        "Date": idx,
                        "Open": cur_open,
                        "High": cur_high,
                        "Low": cur_low,
                        "Close": p,
                        "Volume": cur_vol,
                        "DollarVolume": cur_dollar,
                    }
                )
                cum_dollar = 0.0
                cur_open = None
                cur_high = -np.inf
                cur_low = np.inf
                cur_vol = 0.0
                cur_dollar = 0.0

        if not bar_records:
            return df

        res = pd.DataFrame(bar_records).set_index("Date")
        return res
