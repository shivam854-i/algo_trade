"""Market Jurisdiction Configuration and Governance Helpers.

Enforces market enablement, canonical normalization, and provides the default
Nifty 50 and Indian equity constituent universes for the Indian equity focus.
Exclusively supports Indian Equities (NSE and BSE) in INR (₹).
"""

from pathlib import Path
from typing import List, Optional
import yaml

# Official, complete 50 constituents of the Nifty 50 index with .NS suffix
NIFTY_50_TICKERS: List[str] = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
    "BHARTIARTL.NS",
    "ITC.NS",
    "KOTAKBANK.NS",
    "LT.NS",
    "AXISBANK.NS",
    "HINDUNILVR.NS",
    "BAJFINANCE.NS",
    "MARUTI.NS",
    "ASIANPAINT.NS",
    "HCLTECH.NS",
    "SUNPHARMA.NS",
    "TITAN.NS",
    "ULTRACEMCO.NS",
    "TATASTEEL.NS",
    "NTPC.NS",
    "POWERGRID.NS",
    "ONGC.NS",
    "M&M.NS",
    "JSWSTEEL.NS",
    "COALINDIA.NS",
    "BAJAJFINSV.NS",
    "ADANIENT.NS",
    "ADANIPORTS.NS",
    "BPCL.NS",
    "GRASIM.NS",
    "CIPLA.NS",
    "NESTLEIND.NS",
    "WIPRO.NS",
    "TATACONSUM.NS",
    "DRREDDY.NS",
    "EICHERMOT.NS",
    "HEROMOTOCO.NS",
    "DIVISLAB.NS",
    "HINDALCO.NS",
    "APOLLOHOSP.NS",
    "SHRIRAMFIN.NS",
    "TRENT.NS",
    "BEL.NS",
    "BRITANNIA.NS",
    "SBILIFE.NS",
    "HDFCLIFE.NS",
    "TECHM.NS",
    "BAJAJ-AUTO.NS",
    "INDUSINDBK.NS",
]

# Prominent BSE 30 Sensex constituents with .BO suffix
BSE_SENSEX_TICKERS: List[str] = [
    "RELIANCE.BO",
    "TCS.BO",
    "HDFCBANK.BO",
    "INFY.BO",
    "ICICIBANK.BO",
    "SBIN.BO",
    "BHARTIARTL.BO",
    "ITC.BO",
    "KOTAKBANK.BO",
    "LT.BO",
    "AXISBANK.BO",
    "HINDUNILVR.BO",
    "BAJFINANCE.BO",
    "MARUTI.BO",
    "ASIANPAINT.BO",
]

# Canonical Indian market benchmarks
INDIAN_BENCHMARKS: List[str] = [
    "^NSEI",       # Nifty 50
    "^BSESN",      # BSE Sensex
    "^NSEBANK",    # Nifty Bank
]


def normalize_market(market_str: str) -> str:
    """Normalizes market identifier strings into canonical form.

    Maps INDIAN_NSE, NSE, NSE_CASH, and INDIA equivalently to NSE_CASH.
    Maps INDIAN_BSE, BSE, BSE_CASH to BSE_CASH.
    Maps US, US_EQUITIES, NYSE, NASDAQ to US_EQUITIES.
    Maps CRYPTO, CRYPTOCURRENCY to CRYPTO.
    Maps COMMODITY, COMMODITIES, CME to COMMODITIES.
    Maps FOREX, FX to FOREX.
    """
    if not market_str or not isinstance(market_str, str):
        return ""
    norm = market_str.strip().upper()
    if norm in ("INDIAN_NSE", "NSE", "NSE_CASH", "INDIA", "INDIAN_EQUITIES", "EQUITIES"):
        return "NSE_CASH"
    if norm in ("INDIAN_BSE", "BSE", "BSE_CASH"):
        return "BSE_CASH"
    if norm in ("US", "US_EQUITIES", "NYSE", "NASDAQ"):
        return "US_EQUITIES"
    if norm in ("CRYPTO", "CRYPTOCURRENCY"):
        return "CRYPTO"
    if norm in ("COMMODITY", "COMMODITIES", "CME"):
        return "COMMODITIES"
    if norm in ("FOREX", "FX"):
        return "FOREX"
    return norm


def get_market_for_ticker(ticker: str) -> str:
    """Infers canonical market jurisdiction from ticker symbol pattern."""
    if not ticker or not isinstance(ticker, str):
        return "US_EQUITIES"
    tk = ticker.strip().upper()
    if tk.endswith((".NS", ".BO")) or tk.startswith(("^NSE", "^BS")):
        return "NSE_CASH"
    if tk.endswith("=F") or tk in ("GLD", "SLV", "USO", "UNG"):
        return "COMMODITIES"
    if tk.endswith("=X") or tk in ("DX-Y.NYB", "UUP"):
        return "FOREX"
    if "-USD" in tk or "-USDT" in tk or tk in ("BTC", "ETH", "SOL", "DOGE", "XRP"):
        return "CRYPTO"
    return "US_EQUITIES"


def get_enabled_markets() -> List[str]:
    """Reads enabled markets from config/config.yaml or falls back to ['NSE_CASH']."""
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "config.yaml"
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and "enabled_markets" in data:
                    return [normalize_market(m) for m in data["enabled_markets"] if m]
        except Exception:
            pass
    return ["NSE_CASH"]


def is_market_enabled(market_str: str) -> bool:
    """Checks whether the given market (or ticker market) is currently enabled."""
    norm = normalize_market(market_str)
    enabled = get_enabled_markets()
    return norm in enabled


def validate_market_enabled(market_str: str) -> None:
    """Validates that a market is enabled; raises ValueError if disabled."""
    norm = normalize_market(market_str)
    enabled = get_enabled_markets()
    if norm not in enabled:
        raise ValueError(
            f"Market '{market_str}' is disabled. Only enabled markets: {enabled}"
        )


def get_default_universe() -> List[str]:
    """Returns the default asset universe (Nifty 50 constituents)."""
    return list(NIFTY_50_TICKERS)

