"""Market Data Downloader & Cache Manager.

Supports US Equities, Indian Equities (NSE/BSE), Commodities, Forex, and Cryptocurrencies.
Features timeframe-aware dynamic TTL caching, automatic error fallback, UTC timezone
preservation, batch multi-ticker provider ingestion, and incremental bar appending.
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
    """Universal market data downloader with resilient disk caching and incremental updates."""

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

    @staticmethod
    def _clamp_period(period: str, interval: str) -> str:
        """Automatically clamp intraday lookback to Yahoo Finance limits."""
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
        return effective_period

    @staticmethod
    def _standardize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
        """Standardizes columns, drops zero prices, and enforces UTC timezone."""
        if df is None or df.empty:
            return pd.DataFrame()
        req_cols = ["Open", "High", "Low", "Close", "Volume"]
        for col in req_cols:
            if col not in df.columns:
                return pd.DataFrame()
        out = df[req_cols].copy()
        out.index.name = "Date"
        if out.index.tz is not None:
            out.index = out.index.tz_convert("UTC")
        else:
            out.index = out.index.tz_localize("UTC")
        out = out[out["Close"] > 0].dropna()
        return out

    def download_ticker(
        self,
        ticker: str,
        period: str = "2y",
        interval: str = "1d",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Downloads single ticker data or loads from local cache with dynamic TTL.

        Features incremental bar fetching: if a cached history exists, only missing
        bars since the last cached timestamp are retrieved instead of re-downloading
        the entire multi-year history.
        """
        ticker = self._sanitize_ticker(ticker)
        effective_period = self._clamp_period(period, interval)
        cache_path = self._get_cache_path(ticker, interval, effective_period)

        # 1. Warm Cache Check (Dynamic Timeframe-Aware TTL)
        if not force_refresh and self._is_cache_valid(cache_path, interval=interval):
            cached_df = self._read_cache_df(cache_path)
            if not cached_df.empty:
                return cached_df

        # 2. Incremental Bar Update Check: If cache exists, fetch only missing bars
        cached_df = pd.DataFrame()
        if not force_refresh and cache_path.exists():
            cached_df = self._read_cache_df(cache_path)

        if not cached_df.empty:
            last_ts = cached_df.index[-1]
            try:
                yf_ticker = yf.Ticker(ticker)
                # Overlap by 1 day (or 2 hours for intraday) to capture final completed bar
                if interval in ["1d", "1wk", "1mo"]:
                    start_str = (last_ts - timedelta(days=1)).strftime("%Y-%m-%d")
                else:
                    start_str = (last_ts - timedelta(hours=2)).strftime("%Y-%m-%d")

                df_inc = yf_ticker.history(
                    start=start_str,
                    interval=interval,
                    auto_adjust=True,
                    raise_errors=True,
                )
                if df_inc is not None and not df_inc.empty:
                    df_inc = self._standardize_ohlcv(df_inc)
                    if not df_inc.empty:
                        combined = pd.concat([cached_df, df_inc])
                        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
                        combined.to_csv(cache_path)
                        return combined

                # If no new bars returned (e.g. market closed), touch cache to refresh TTL and return cached
                try:
                    os.utime(cache_path, None)
                except Exception:
                    pass
                return cached_df

            except Exception as e:
                logger.warning(
                    f"Incremental bar fetch failed for {ticker}: {e}. Falling back to cached data."
                )
                return cached_df

        # 3. Live Ingestion from Yahoo Finance with Robust Exception Handling
        try:
            yf_ticker = yf.Ticker(ticker)
            df = yf_ticker.history(
                period=effective_period,
                interval=interval,
                auto_adjust=True,
                raise_errors=True,
            )

            # If empty DataFrame is returned, trigger cache fallback
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

            df = self._standardize_ohlcv(df)
            if df.empty:
                return pd.DataFrame()

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

    def download_batch(
        self,
        tickers: List[str],
        period: str = "2y",
        interval: str = "1d",
        force_refresh: bool = False,
    ) -> Dict[str, pd.DataFrame]:
        """Downloads a collection of tickers in a single batch provider call with incremental caching.

        Args:
            tickers: List of ticker strings.
            period: Lookback window (e.g. '1y', '5d').
            interval: Bar resolution (e.g. '1d', '1m').
            force_refresh: If True, bypasses cache and forces network fetch.

        Returns:
            Dictionary mapping sanitized tickers to their OHLCV DataFrames.
        """
        results: Dict[str, pd.DataFrame] = {}
        if not tickers:
            return results

        clean_tickers = [self._sanitize_ticker(t) for t in tickers]
        missing_tickers: List[str] = []
        effective_period = self._clamp_period(period, interval)

        # 1. Warm Cache Check
        for ticker in clean_tickers:
            cache_path = self._get_cache_path(ticker, interval, effective_period)
            if not force_refresh and self._is_cache_valid(cache_path, interval=interval):
                cached = self._read_cache_df(cache_path)
                if not cached.empty:
                    results[ticker] = cached
                    continue
            missing_tickers.append(ticker)

        if not missing_tickers:
            return results

        # 2. Batch Download in One Provider Call
        try:
            batch_df = yf.download(
                tickers=missing_tickers,
                period=effective_period,
                interval=interval,
                auto_adjust=True,
                group_by="ticker",
                threads=True,
                progress=False,
            )

            if batch_df is not None and not batch_df.empty:
                for ticker in missing_tickers:
                    try:
                        if len(missing_tickers) == 1:
                            if isinstance(batch_df.columns, pd.MultiIndex):
                                tk_df = (
                                    batch_df[ticker]
                                    if ticker in batch_df.columns.levels[0]
                                    else batch_df
                                )
                            else:
                                tk_df = batch_df
                        else:
                            tk_df = batch_df[ticker] if ticker in batch_df else pd.DataFrame()

                        clean_df = self._standardize_ohlcv(tk_df)
                        if not clean_df.empty:
                            cache_path = self._get_cache_path(ticker, interval, effective_period)
                            # Incremental append if stale cache exists
                            if not force_refresh and cache_path.exists():
                                old_cache = self._read_cache_df(cache_path)
                                if not old_cache.empty:
                                    clean_df = pd.concat([old_cache, clean_df])
                                    clean_df = clean_df[~clean_df.index.duplicated(keep="last")].sort_index()

                            clean_df.to_csv(cache_path)
                            results[ticker] = clean_df
                        else:
                            single_df = self.download_ticker(ticker, period, interval, force_refresh)
                            if not single_df.empty:
                                results[ticker] = single_df
                    except Exception as e:
                        logger.warning(f"Error parsing batch output for {ticker}: {e}, falling back to single")
                        single_df = self.download_ticker(ticker, period, interval, force_refresh)
                        if not single_df.empty:
                            results[ticker] = single_df
            else:
                for ticker in missing_tickers:
                    single_df = self.download_ticker(ticker, period, interval, force_refresh)
                    if not single_df.empty:
                        results[ticker] = single_df

        except Exception as e:
            logger.warning(f"Batch download provider call failed: {e}. Falling back to individual downloads.")
            for ticker in missing_tickers:
                single_df = self.download_ticker(ticker, period, interval, force_refresh)
                if not single_df.empty:
                    results[ticker] = single_df

        return results

    def download_multiple(
        self,
        tickers: List[str],
        period: str = "2y",
        interval: str = "1d",
        force_refresh: bool = False,
        max_workers: int = 4,
        use_batch: bool = True,
    ) -> Dict[str, pd.DataFrame]:
        """Downloads a collection of tickers concurrently or via single batch provider call.

        Args:
            tickers: List of ticker strings.
            period: Lookback window (e.g. '1y', '5d').
            interval: Bar resolution (e.g. '1d', '1m').
            force_refresh: If True, bypasses cache and forces network fetch.
            max_workers: Maximum concurrent worker threads (used if use_batch=False).
            use_batch: If True (default), downloads tickers in a single provider call.

        Returns:
            Dictionary mapping sanitized tickers to their OHLCV DataFrames.
        """
        if not tickers:
            return {}

        if use_batch:
            return self.download_batch(
                tickers=tickers, period=period, interval=interval, force_refresh=force_refresh
            )

        clean_tickers = [self._sanitize_ticker(t) for t in tickers]
        results: Dict[str, pd.DataFrame] = {}

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
