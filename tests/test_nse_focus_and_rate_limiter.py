"""Tests for Part A: NSE-Only Cash Market Focus, Rate Limiting, and Guardrails."""

import time
import pytest
from fastapi.testclient import TestClient

from server import app, OrderRequest
from src.config.markets import (
    NIFTY_50_TICKERS,
    get_default_universe,
    get_enabled_markets,
    get_market_for_ticker,
    is_market_enabled,
    normalize_market,
    validate_market_enabled,
)
from src.execution.guardrails import TokenBucketRateLimiter, validate_nse_order_type
from src.execution.broker import PaperBroker


client = TestClient(app)


# --------------------------------------------------------------------------
# 1. Market Configuration & Universe Tests
# --------------------------------------------------------------------------

def test_nifty_50_constituents_completeness():
    """Verify that NIFTY_50_TICKERS contains exactly 50 unique tickers ending in .NS."""
    assert len(NIFTY_50_TICKERS) == 50
    assert len(set(NIFTY_50_TICKERS)) == 50
    for ticker in NIFTY_50_TICKERS:
        assert ticker.endswith(".NS"), f"Ticker {ticker} must end with .NS"
    
    # Check default universe helper
    default_univ = get_default_universe()
    assert default_univ == NIFTY_50_TICKERS


def test_market_normalization():
    """Verify market alias normalization to canonical form."""
    assert normalize_market("INDIAN_NSE") == "NSE_CASH"
    assert normalize_market("NSE") == "NSE_CASH"
    assert normalize_market("NSE_CASH") == "NSE_CASH"
    assert normalize_market("India") == "NSE_CASH"
    
    assert normalize_market("US") == "US_EQUITIES"
    assert normalize_market("US_EQUITIES") == "US_EQUITIES"
    assert normalize_market("NYSE") == "US_EQUITIES"
    
    assert normalize_market("CRYPTO") == "CRYPTO"
    assert normalize_market("COMMODITIES") == "COMMODITIES"
    assert normalize_market("FOREX") == "FOREX"


def test_enabled_markets_state():
    """Verify that only NSE_CASH is currently enabled."""
    enabled = get_enabled_markets()
    assert "NSE_CASH" in enabled
    assert is_market_enabled("NSE_CASH") is True
    assert is_market_enabled("INDIAN_NSE") is True
    assert is_market_enabled("NSE") is True
    
    assert is_market_enabled("US_EQUITIES") is False
    assert is_market_enabled("CRYPTO") is False
    assert is_market_enabled("COMMODITIES") is False
    assert is_market_enabled("FOREX") is False


def test_validate_market_enabled_raises():
    """Verify validate_market_enabled raises ValueError with descriptive error for disabled markets."""
    # Should not raise for NSE
    validate_market_enabled("NSE_CASH")
    validate_market_enabled("INDIAN_NSE")
    
    with pytest.raises(ValueError) as excinfo:
        validate_market_enabled("US_EQUITIES")
    assert "Market 'US_EQUITIES' is disabled. Only enabled markets:" in str(excinfo.value)

    with pytest.raises(ValueError) as excinfo_crypto:
        validate_market_enabled("CRYPTO")
    assert "Market 'CRYPTO' is disabled. Only enabled markets:" in str(excinfo_crypto.value)


def test_get_market_for_ticker():
    """Verify ticker pattern to canonical market mapping."""
    assert get_market_for_ticker("RELIANCE.NS") == "NSE_CASH"
    assert get_market_for_ticker("TCS.BO") == "NSE_CASH"
    assert get_market_for_ticker("AAPL") == "US_EQUITIES"
    assert get_market_for_ticker("BTC-USD") == "CRYPTO"
    assert get_market_for_ticker("GC=F") == "COMMODITIES"
    assert get_market_for_ticker("EURUSD=X") == "FOREX"


# --------------------------------------------------------------------------
# 2. Rate Limiter Tests
# --------------------------------------------------------------------------

def test_token_bucket_rate_limiter_burst_and_refill():
    """Verify TokenBucketRateLimiter allows burst up to capacity and refills over time."""
    limiter = TokenBucketRateLimiter(rate=5.0, capacity=5.0)
    
    # Acquire 5 tokens in quick succession - all should succeed
    for _ in range(5):
        assert limiter.acquire() is True
        
    # 6th immediate request must be rejected (bucket exhausted)
    assert limiter.acquire() is False
    
    # Sleep 0.25 seconds (should replenish ~1.25 tokens, so at least 1)
    time.sleep(0.25)
    assert limiter.acquire() is True


# --------------------------------------------------------------------------
# 3. NSE Algo Market Order Prohibition Tests
# --------------------------------------------------------------------------

def test_nse_algo_market_order_conversion_to_limit():
    """Verify that algo market orders on NSE are converted to limit with price protection."""
    # Buy order: limit price = current_price * (1 + 0.01)
    converted_type, limit_price, msg = validate_nse_order_type(
        ticker="RELIANCE.NS",
        order_type="MARKET",
        direction="LONG",
        current_price=2500.0,
        convert_if_market=True,
    )
    assert converted_type == "LIMIT"
    assert limit_price == 2525.0  # 2500 * 1.01
    assert "Limit Price Protection" in msg
    
    # Sell order: limit price = current_price * (1 - 0.01)
    converted_type_sell, limit_price_sell, msg_sell = validate_nse_order_type(
        ticker="RELIANCE.NS",
        order_type="MARKET",
        direction="SHORT",
        current_price=2500.0,
        convert_if_market=True,
    )
    assert converted_type_sell == "LIMIT"
    assert limit_price_sell == 2475.0  # 2500 * 0.99
    assert "Limit Price Protection" in msg_sell


def test_nse_algo_market_order_rejection_when_configured():
    """Verify that algo market orders on NSE are rejected with ValueError when convert_if_market=False."""
    with pytest.raises(ValueError) as excinfo:
        validate_nse_order_type(
            ticker="RELIANCE.NS",
            order_type="MARKET",
            direction="LONG",
            current_price=2500.0,
            convert_if_market=False,
        )
    assert "Algorithmic MARKET orders are strictly prohibited for NSE symbol 'RELIANCE.NS'" in str(excinfo.value)


def test_nse_algo_limit_order_untouched():
    """Verify that already-limit orders on NSE pass through unchanged."""
    converted_type, limit_price, msg = validate_nse_order_type(
        ticker="RELIANCE.NS",
        order_type="LIMIT",
        direction="LONG",
        current_price=2500.0,
        limit_price=2510.0,
    )
    assert converted_type == "LIMIT"
    assert limit_price == 2510.0
    assert msg is None


# --------------------------------------------------------------------------
# 4. API Disabled Market Rejections & Enabled Success Tests
# --------------------------------------------------------------------------

def test_api_session_creation_rejects_disabled_markets():
    """Verify POST /api/sessions returns HTTP 400 when disabled markets are requested."""
    payload_us = {
        "name": "US Equities Session",
        "market": "US_EQUITIES",
        "instruments": ["NVDA", "AAPL"],
        "horizon": "1d",
        "duration_type": "FIXED",
        "duration_minutes": 240,
        "session_end_policy": "CLOSE_ALL",
        "allocated_capital": 50000.0,
        "currency": "USD",
    }
    resp = client.post("/api/sessions", json=payload_us)
    assert resp.status_code == 400
    assert "Market 'US_EQUITIES' is disabled. Only enabled markets: ['NSE_CASH']" in resp.json()["detail"]

    payload_crypto = {
        "name": "Crypto Session",
        "market": "CRYPTO",
        "instruments": ["BTC-USD"],
        "horizon": "1d",
        "duration_type": "FIXED",
        "duration_minutes": 240,
        "session_end_policy": "CLOSE_ALL",
        "allocated_capital": 50000.0,
        "currency": "USD",
    }
    resp_crypto = client.post("/api/sessions", json=payload_crypto)
    assert resp_crypto.status_code == 400
    assert "Market 'CRYPTO' is disabled. Only enabled markets: ['NSE_CASH']" in resp_crypto.json()["detail"]


def test_api_session_creation_accepts_enabled_nse():
    """Verify POST /api/sessions succeeds with HTTP 201 for enabled INDIAN_NSE market."""
    payload_nse = {
        "name": "NSE Nifty 50 Session",
        "market": "INDIAN_NSE",
        "instruments": ["RELIANCE.NS", "TCS.NS"],
        "horizon": "1d",
        "duration_type": "FIXED",
        "duration_minutes": 240,
        "session_end_policy": "CLOSE_ALL",
        "allocated_capital": 500000.0,
        "currency": "INR",
    }
    resp = client.post("/api/sessions", json=payload_nse)
    assert resp.status_code == 201
    data = resp.json()
    assert data["session"]["market"] == "INDIAN_NSE"
    assert data["session"]["currency"] == "INR"


def test_api_broker_order_rejects_disabled_market():
    """Verify POST /api/broker/order rejects disabled markets with HTTP 400."""
    payload = {
        "ticker": "AAPL",
        "side": "BUY",
        "quantity": 10,
        "order_type": "LIMIT",
        "limit_price": 150.0,
        "market": "US_EQUITIES",
    }
    resp = client.post("/api/broker/order", json=payload)
    assert resp.status_code == 400
    assert "is disabled. Only enabled markets:" in resp.json()["detail"]


def test_api_dashboard_order_rejects_disabled_market_ticker():
    """Verify POST /api/dashboard/order rejects orders on disabled market tickers with HTTP 400."""
    payload = {
        "ticker": "NVDA",
        "side": "BUY",
        "quantity": 5,
        "order_type": "LIMIT",
        "limit_price": 500.0,
    }
    resp = client.post("/api/dashboard/order", json=payload)
    assert resp.status_code == 400
    assert "Market 'US_EQUITIES' is disabled. Only enabled markets:" in resp.json()["detail"]
