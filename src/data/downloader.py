"""Market Data Downloader & Cache Manager.

Supports US Equities, Indian Equities (NSE/BSE), Commodities, Forex, and Cryptocurrencies.
Features timeframe-aware dynamic TTL caching, automatic error fallback, UTC timezone
preservation, and concurrent multi-ticker ingestion.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Union
import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class MarketDataDownloader:
    """Universal market data downloader with resilient disk caching."""

    # Default timeframe-aware dynamic cache TTL mapping
    DEFAULT_TIMEFRAME_TTL: Dict[str, timedelta] = {
        "1m": timedelta(minutes=2),
        "2m": timedelta(minutes=2),
        "5m": timedelta(minutes=2),
        "15m": timedelta(minutes=15),
        "30m": timedelta(minutes=30),
        "60m": timedelta(hours=1),
        "1h": timedelta(hours=1),
        "1d": timedelta(hours=24),
        "1wk": timedelta(days=7),
        "1mo": timedelta(days=30),
    }

    def __init__(
        self,
        cache_dir: Optional[Union[str, Path]] = None,
        cache_expiry_hours: int = 4,
        ttl_map: Optional[Dict[str, timedelta]] = None,
    ):
        """Initializes the downloader with configurable cache directory and dynamic TTLs.

        Args:
            cache_dir: Directory where cached files are stored. Defaults to <repo>/data/cache.
            cache_expiry_hours: Fallback cache TTL for unspecified intervals.
            ttl_map: Optional custom timeframe-to-timedelta mapping.
        """
        if cache_dir is None:
            # Default relative to trade_bot root
            base_path = Path(__file__).resolve().parent.parent.parent
            self.cache_dir = base_path / "data" / "cache"
        else:
            self.cache_dir = Path(cache_dir)

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl = timedelta(hours=cache_expiry_hours)
        self.cache_expiry = self.default_ttl  # Preserved for backward compatibility

        self.ttl_map = dict(self.DEFAULT_TIMEFRAME_TTL)
        if ttl_map:
            self.ttl_map.update(ttl_map)

    def _sanitize_ticker(self, ticker: str) -> str:
        return ticker.strip().upper()

    def _get_cache_path(self, ticker: str, interval: str, period: str) -> Path:
        safe_name = ticker.replace("^", "IDX_").replace("=", "_").replace("/", "_")
        return self.cache_dir / f"{safe_name}_{interval}_{period}.csv"

    def _is_cache_valid(self, cache_path: Path, interval: Optional[str] = None) -> bool:
        """Evaluates whether the cache file exists and is within its dynamic TTL window."""
        if not cache_path.exists():
            return False
        try:
            mod_time = datetime.fromtimestamp(cache_path.stat().st_mtime, tz=timezone.utc)
            now_utc = datetime.now(timezone.utc)
            ttl = self.ttl_map.get(interval.lower(), self.default_ttl) if interval else self.default_ttl
            return (now_utc - mod_time) < ttl
        except Exception:
            return False

    def _read_cache_df(self, cache_path: Path) -> pd.DataFrame:
        """Safely reads a cached CSV file, validating structure and preserving UTC DatetimeIndex."""
        if not cache_path.exists():
            return pd.DataFrame()
        try:
            df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
            if df.empty or "Close" not in df.columns:
                return pd.DataFrame()

            # Preserve and enforce UTC timezone awareness across all datasets
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")

            return df
        except Exception as e:
            logger.warning(f"Error reading cache at {cache_path}: {e}")
            return pd.DataFrame()

    def download_ticker(
        self,
        ticker: str,
        period: str = "2y",
        interval: str = "1d",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Downloads single ticker data or loads from local cache with dynamic TTL.

        Returns:
            pd.DataFrame with standard columns [Open, High, Low, Close, Volume]
            and timezone-aware UTC DatetimeIndex.
        """
        ticker = self._sanitize_ticker(ticker)

        # Automatically clamp intraday lookback to Yahoo Finance limits
        effective_period = period
        if interval in ["1m", "2m"]:
            if period not in ["1d", "5d", "7d"]:
                effective_period = "7d"
        elif interval in ["5m", "15m", "30m"]:
            if period in ["3mo", "6mo", "1y", "2y", "5y", "10y", "max"]:
                effective_period = "60d"
        elif interval == "1h":
            if period in ["5y", "10y", "max"]:
                effective_period = "730d"

        cache_path = self._get_cache_path(ticker, interval, effective_period)

        # 1. Warm Cache Check (Dynamic Timeframe-Aware TTL)
        if not force_refresh and self._is_cache_valid(cache_path, interval=interval):
            cached_df = self._read_cache_df(cache_path)
            if not cached_df.empty:
                return cached_df

        # 2. Live Ingestion from Yahoo Finance with Robust Exception Handling
        try:
            yf_ticker = yf.Ticker(ticker)
            # Set raise_errors=True so network timeouts/429 errors raise exceptions rather than empty DFs
            df = yf_ticker.history(
                period=effective_period,
                interval=interval,
                auto_adjust=True,
                raise_errors=True,
            )

            # If empty DataFrame is returned (e.g. market closure, silent rejection), trigger cache fallback
            if df is None or df.empty:
                logger.warning(
                    f"No data returned from live feed for {ticker} (period={period}, interval={interval}). "
                    f"Attempting fallback to local cache."
                )
                fallback_df = self._read_cache_df(cache_path)
                if not fallback_df.empty:
                    logger.info(f"Using cached fallback data for {ticker} following empty live response.")
                    return fallback_df
                return pd.DataFrame()

            # Normalize column names
            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.index.name = "Date"

            # Preserve timezone metadata: Standardize all feeds to UTC to prevent 10.5h alignment corruption
            if df.index.tz is not None:
                df.index = df.index.tz_convert("UTC")
            else:
                df.index = df.index.tz_localize("UTC")

            # Drop invalid/zero prices
            df = df[df["Close"] > 0]
            df = df.dropna()

            # Save to disk cache
            df.to_csv(cache_path)
            return df

        except Exception as e:
            logger.error(f"Live market data fetch failed for {ticker}: {e}. Triggering fallback recovery.")
            fallback_df = self._read_cache_df(cache_path)
            if not fallback_df.empty:
                logger.info(f"Successfully recovered stale cache for {ticker} as emergency fallback.")
                return fallback_df
            return pd.DataFrame()

    def download_multiple(
        self,
        tickers: List[str],
        period: str = "2y",
        interval: str = "1d",
        force_refresh: bool = False,
        max_workers: int = 4,
    ) -> Dict[str, pd.DataFrame]:
        """Downloads a collection of tickers concurrently using a thread pool.

        Args:
            tickers: List of ticker strings.
            period: Lookback window (e.g. '1y', '5d').
            interval: Bar resolution (e.g. '1d', '1m').
            force_refresh: If True, bypasses cache and forces network fetch.
            max_workers: Maximum concurrent worker threads. Defaults to 4.

        Returns:
            Dictionary mapping sanitized tickers to their OHLCV DataFrames.
        """
        results: Dict[str, pd.DataFrame] = {}
        if not tickers:
            return results

        clean_tickers = [self._sanitize_ticker(t) for t in tickers]

        if len(clean_tickers) == 1 or max_workers <= 1:
            for clean_ticker in clean_tickers:
                df = self.download_ticker(clean_ticker, period, interval, force_refresh)
                if not df.empty:
                    results[clean_ticker] = df
            return results

        with ThreadPoolExecutor(max_workers=min(max_workers, len(clean_tickers))) as executor:
            future_to_ticker = {
                executor.submit(
                    self.download_ticker, ticker, period, interval, force_refresh
                ): ticker
                for ticker in clean_tickers
            }
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    df = future.result()
                    if not df.empty:
                        results[ticker] = df
                except Exception as exc:
                    logger.error(f"Concurrent download failed for {ticker}: {exc}")

        return results

    def get_market_type(self, ticker: str) -> str:
        """Identifies market jurisdiction based on ticker format."""
        ticker = ticker.upper()
        if (
            ticker.endswith(".NS")
            or ticker.endswith(".BO")
            or ticker.startswith("^NSE")
            or ticker.startswith("^BS")
        ):
            return "NSE_CASH"
        elif ticker.endswith("=X") or ticker in ["DX-Y.NYB", "UUP"]:
            return "FOREX"
        elif ticker.endswith("=F") or ticker in ["GLD", "SLV", "USO", "UNG"]:
            return "COMMODITY"
        elif "-USD" in ticker or "-USDT" in ticker or ticker in ["BTC", "ETH"]:
            return "CRYPTO"
        else:
            return "US"
