"""High-Performance SaaS REST API Backend for SYNAPSE-TITAN.

Exposes institutional-grade market prediction, multi-asset scanning,
quantile volatility forecasting, and walk-forward backtesting endpoints
to cloud web frontends (React / Next.js / Vue / mobile apps).
"""

from contextlib import asynccontextmanager
from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.backtest.engine import BacktestEngine
from src.execution.auth import AuthManager, UserTierProfile
from src.execution.broker import PaperBroker
from src.execution.frictions import FrictionEvaluator
from src.execution.live_bot import LiveBotController
from src.pipeline import MarketPredictionEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("synapse_api")

# Initialize managers
auth_manager = AuthManager()
broker_engine = PaperBroker()

# Initialize global prediction engine & live bot controller
engine: Optional[MarketPredictionEngine] = None
backtest_engine: Optional[BacktestEngine] = None
live_bot: Optional[LiveBotController] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, backtest_engine, live_bot
    logger.info("Initializing SYNAPSE-TITAN Neuro-Causal Engine...")
    engine = MarketPredictionEngine()
    backtest_engine = BacktestEngine()
    live_bot = LiveBotController(engine=engine, broker=broker_engine)
    live_bot.initialize_market_state()
    logger.info("Engine and Autonomous Bot Controller warmed up and ready.")
    yield
    logger.info("Shutting down SYNAPSE-TITAN API.")


app = FastAPI(
    title="SYNAPSE-TITAN API",
    description="Institutional-Grade Multi-Asset Market Prediction & Risk Governance Engine",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for cloud web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- Request / Response Schemas ----------------- #


class RegisterRequest(BaseModel):
    email: str = Field(..., description="Subscriber email address")
    tier: str = Field(default="PRO", description="Subscription tier: FREE, PRO, or INSTITUTIONAL")


class OrderRequest(BaseModel):
    ticker: str = Field(..., description="Asset symbol, e.g. GC=F or NVDA")
    direction: str = Field(default="LONG", description="LONG or SHORT")
    allocation_weight_pct: float = Field(default=10.0, description="Capital allocation percentage")
    order_type: Optional[str] = Field(default="MARKET", description="MARKET or LIMIT")
    limit_price: Optional[float] = Field(default=None, description="Limit price for LIMIT orders")
    target_price: Optional[float] = Field(default=None, description="Custom target price (optional)")
    stop_price: Optional[float] = Field(default=None, description="Custom stop price (optional)")


class WebhookAlertRequest(BaseModel):
    ticker: str = Field(..., description="Asset symbol, e.g. GC=F")
    action: str = Field(..., description="BUY, SELL, or CLOSE")
    price: Optional[float] = Field(default=None, description="Execution price")
    secret: Optional[str] = Field(default=None, description="Webhook shared secret")


class ScanRequest(BaseModel):
    tickers: List[str] = Field(
        default=["GC=F", "EURUSD=X", "NVDA", "AAPL", "RELIANCE.NS", "BTC-USD"],
        description="List of asset symbols across any market class",
    )
    period: str = Field(default="1y", description="Lookback window (e.g. 6mo, 1y, 2y)")
    interval: str = Field(default="1d", description="Resolution (e.g. 15m, 1h, 1d)")


class BacktestRequest(BaseModel):
    ticker: str = Field(..., description="Asset ticker symbol, e.g. GC=F or NVDA")
    period: str = Field(default="2y", description="Backtest lookback period")
    interval: str = Field(default="1d", description="Bar interval")
    initial_capital: float = Field(default=10000.0, description="Starting cash")
    kelly_fraction: float = Field(default=0.35, description="Fractional Kelly multiplier")
    target_vol: float = Field(default=0.15, description="Target annualized volatility (e.g. 0.15 = 15%)")


def get_current_user(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None),
) -> UserTierProfile:
    """Validates API Key from header or query param. Defaults to demo Pro tier if omitted."""
    key = x_api_key or api_key or "synapse_demo_pro_key_2026"
    user = auth_manager.get_user_by_key(key)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key. Please provide a valid 'X-API-Key' header or register at /api/auth/register",
        )
    if user.requests_today > user.daily_quota:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily quota exceeded for {user.tier} tier ({user.daily_quota} req/day). Upgrade to Pro/Institutional.",
        )
    return user


# ----------------- Endpoints ----------------- #


def _get_live_bot() -> LiveBotController:
    global engine, live_bot
    if engine is None:
        engine = MarketPredictionEngine()
    if live_bot is None:
        live_bot = LiveBotController(engine=engine, broker=broker_engine)
        live_bot.initialize_market_state()
    return live_bot


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
def serve_dashboard():
    """Serves the interactive SYNAPSE-TITAN Autonomous Trading Terminal UI."""
    dist_html = Path(__file__).resolve().parent / "frontend" / "dist" / "index.html"
    if dist_html.exists():
        return FileResponse(str(dist_html), media_type="text/html")
    html_path = Path(__file__).resolve().parent / "static" / "index.html"
    if html_path.exists():
        return FileResponse(str(html_path), media_type="text/html")
    return HTMLResponse("<h1>SYNAPSE-TITAN API ONLINE</h1>")


@app.get("/api/health", tags=["System"])
def root():
    """System health check, version, and hardware capabilities."""
    import torch

    cuda_available = torch.cuda.is_available()
    device_name = torch.cuda.get_device_name(0) if cuda_available else "CPU (Host Processor)"
    vram_mb = (
        round(torch.cuda.get_device_properties(0).total_memory / (1024**2), 1)
        if cuda_available
        else 0
    )

    return {
        "engine": "SYNAPSE-TITAN",
        "version": "1.0.0",
        "status": "ONLINE",
        "server_time": datetime.utcnow().isoformat(),
        "hardware": {
            "cuda_available": cuda_available,
            "device": device_name,
            "vram_mb": vram_mb,
            "torch_version": torch.__version__,
        },
        "asset_classes": [
            "US_EQUITIES",
            "INDIAN_NSE",
            "COMMODITIES",
            "FOREX",
            "CRYPTOCURRENCIES",
        ],
    }


@app.get("/api/universes", tags=["Market Data"])
def get_preset_universes():
    """Returns curated multi-asset watchlists ready for one-click scanning."""
    return {
        "US_TECH": ["NVDA", "AAPL", "MSFT", "TSLA", "GOOGL"],
        "PRECIOUS_METALS": ["GC=F", "SI=F", "GLD", "SLV"],
        "ENERGY_COMMODITIES": ["CL=F", "NG=F", "USO"],
        "FOREX_MAJORS": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X"],
        "INDIAN_EQUITIES": ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS"],
        "CRYPTO_MAJORS": ["BTC-USD", "ETH-USD", "SOL-USD"],
        "GLOBAL_MACRO": ["GC=F", "EURUSD=X", "SPY", "BTC-USD", "TLT"],
    }


@app.get("/api/forecast/{ticker}", tags=["Prediction"])
def get_ticker_forecast(
    ticker: str,
    period: str = Query("1y", description="Lookback window"),
    interval: str = Query("1d", description="Bar interval"),
):
    """Executes single-asset neuro-causal analysis, volatility cone forecast, and risk governance."""
    global engine
    if engine is None:
        engine = MarketPredictionEngine()

    try:
        res = engine.analyze_ticker(ticker, period=period, interval=interval)
    except Exception as e:
        logger.error(f"Analysis failed for {ticker}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze {ticker}: {str(e)}",
        )

    pred = res.meta_prediction
    regime = res.regime
    cone = res.volatility_cone

    # Serialize cone quantiles
    cone_data = {
        "periods": cone.periods,
        "q10_prices": [round(float(p), 2) for p in cone.q10_prices],
        "q50_prices": [round(float(p), 2) for p in cone.q50_prices],
        "q90_prices": [round(float(p), 2) for p in cone.q90_prices],
        "expected_vol_annualized": round(float(cone.expected_vol_annualized), 4),
        "forward_skew": round(float(cone.forward_skew), 4),
    }

    return {
        "ticker": res.ticker,
        "current_price": round(res.current_price, 2),
        "jurisdiction": res.market_jurisdiction,
        "timestamp": datetime.utcnow().isoformat(),
        "memory_preservation": {
            "optimal_d_star": round(float(res.optimal_d_star), 2),
            "stationarity_verified": True,
        },
        "market_regime": {
            "state_id": int(regime.state_id),
            "name": str(regime.name),
            "description": str(regime.description),
            "circuit_breaker_active": bool(regime.is_crisis),
            "volatility_scale": float(regime.volatility_scale),
        },
        "meta_prediction": {
            "primary_direction": int(pred.primary_direction),
            "signal": str(pred.direction_label),
            "success_probability": round(float(pred.success_probability), 3),
            "bet_size_score": round(float(pred.bet_size), 3),
            "target_price": round(float(pred.target_price), 2),
            "stop_price": round(float(pred.stop_price), 2),
            "expected_upside_pct": round(
                float(((pred.target_price - res.current_price) / res.current_price) * 100.0), 2
            ),
            "feature_importances": {k: float(v) for k, v in pred.feature_importances.items()},
        },
        "volatility_cone": cone_data,
        "neural_ensemble": {
            "neural_conviction_prob": round(float(res.neural_prob), 3),
            "fused_probability": round(float(pred.success_probability), 3),
            "hardware_accelerator": res.hardware_accelerator,
        },
        "risk_governance": {
            "friction_cost_pct": round(float(res.friction_cost_pct), 2),
            "net_expected_alpha_pct": round(float(res.net_expected_alpha_pct), 2),
            "hurdle_cleared": bool(res.friction_hurdle_passes),
            "authorized_trade": bool(res.risk_decision.authorized),
            "authorized_weight_pct": round(float(res.risk_decision.authorized_weight_pct), 2),
            "sizing_scalar": round(float(res.risk_decision.sizing_scalar), 2),
            "status_message": str(res.risk_decision.status_message),
        },
    }


@app.post("/api/scan", tags=["Prediction"])
def scan_universe(req: ScanRequest):
    """Batch scans a multi-asset universe and computes HRP portfolio diversification weights."""
    global engine
    if engine is None:
        engine = MarketPredictionEngine()

    try:
        portfolio_analysis = engine.analyze_portfolio(
            req.tickers, period=req.period, interval=req.interval
        )
    except Exception as e:
        logger.error(f"Universe scan failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Universe scan failed: {str(e)}",
        )

    summary_list = []
    for ticker, single in portfolio_analysis.single_analyses.items():
        summary_list.append(
            {
                "ticker": ticker,
                "current_price": round(float(single.current_price), 2),
                "jurisdiction": str(single.market_jurisdiction),
                "regime": str(single.regime.name),
                "signal": str(single.meta_prediction.direction_label),
                "confidence_pct": round(float(single.meta_prediction.success_probability * 100.0), 1),
                "target_price": round(float(single.meta_prediction.target_price), 2),
                "stop_price": round(float(single.meta_prediction.stop_price), 2),
                "net_alpha_pct": round(float(single.net_expected_alpha_pct), 2),
                "friction_cost_pct": round(float(single.friction_cost_pct), 2),
                "hurdle_cleared": bool(single.friction_hurdle_passes),
                "single_kelly_pct": round(float(single.risk_decision.authorized_weight_pct), 1),
                "hrp_portfolio_weight_pct": round(
                    float(portfolio_analysis.hrp_portfolio_weights.get(ticker, 0.0) * 100.0), 1
                ),
            }
        )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "aggregate_regime": str(portfolio_analysis.aggregate_regime),
        "circuit_breaker_active": bool(portfolio_analysis.circuit_breaker_active),
        "total_assets": len(summary_list),
        "assets": summary_list,
        "hrp_portfolio_weights": {
            k: round(float(v * 100.0), 2)
            for k, v in portfolio_analysis.hrp_portfolio_weights.items()
        },
    }


@app.post("/api/backtest", tags=["Backtesting"])
def run_backtest(req: BacktestRequest):
    """Executes a leak-free walk-forward backtest simulation with statutory friction deduction."""
    engine_bt = BacktestEngine(
        initial_capital=req.initial_capital,
        kelly_fraction=req.kelly_fraction,
        target_vol=req.target_vol,
    )

    res = engine_bt.run(ticker=req.ticker, period=req.period, interval=req.interval)
    if res is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient historical data to backtest {req.ticker} over period {req.period}",
        )

    # Format trades
    trade_list = [
        {
            "entry_date": tr.entry_date.strftime("%Y-%m-%d"),
            "exit_date": tr.exit_date.strftime("%Y-%m-%d"),
            "ticker": tr.ticker,
            "direction": tr.direction,
            "entry_price": tr.entry_price,
            "exit_price": tr.exit_price,
            "return_pct": tr.return_pct,
            "net_pnl": tr.net_pnl,
            "exit_reason": tr.exit_reason,
            "duration_bars": tr.duration_bars,
        }
        for tr in res.trades
    ]

    # Format equity curve sample (downsample if very large)
    eq_curve = [
        {"date": str(idx)[:10], "equity": round(val, 2)}
        for idx, val in res.equity_curve.items()
    ]

    return {
        "ticker": res.ticker,
        "period": res.period,
        "interval": res.interval,
        "jurisdiction": res.jurisdiction,
        "initial_capital": res.initial_capital,
        "final_equity": res.final_equity,
        "total_return_pct": res.total_return_pct,
        "buy_hold_return_pct": res.buy_hold_return_pct,
        "cagr_pct": res.cagr_pct,
        "sharpe_ratio": res.sharpe_ratio,
        "sortino_ratio": res.sortino_ratio,
        "max_drawdown_pct": res.max_drawdown_pct,
        "calmar_ratio": res.calmar_ratio,
        "win_rate_pct": res.win_rate_pct,
        "profit_factor": res.profit_factor,
        "total_trades": res.total_trades,
        "winning_trades": res.winning_trades,
        "losing_trades": res.losing_trades,
        "avg_trade_return_pct": res.avg_trade_return_pct,
        "deflated_sharpe_ratio_pct": round(res.deflated_sharpe * 100.0, 1),
        "trades": trade_list,
        "equity_curve": eq_curve,
    }


@app.get("/api/alerts", tags=["Alerts"])
def get_recent_alerts(limit: int = Query(50, description="Max alerts to retrieve")):
    """Returns the latest market signals dispatched by the background observer."""
    alerts_file = Path("data/alerts/alerts.json")
    if not alerts_file.exists():
        return {"total": 0, "alerts": []}

    try:
        with open(alerts_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"total": len(data), "alerts": data[:limit]}
    except Exception as e:
        logger.error(f"Failed to read alerts: {e}")
        return {"total": 0, "alerts": []}


# ----------------- Authentication & Subscriber Endpoints ----------------- #


@app.post("/api/auth/register", tags=["Authentication"])
def register_subscriber(req: RegisterRequest):
    """Registers a new subscriber and issues their secret API key."""
    try:
        user = auth_manager.register_user(req.email, req.tier)
        return {
            "status": "SUCCESS",
            "message": f"Successfully registered subscriber under {user.tier} tier.",
            "user_id": user.user_id,
            "email": user.email,
            "api_key": user.api_key,
            "tier": user.tier,
            "daily_quota": user.daily_quota,
            "allowed_intervals": user.allowed_intervals,
            "broker_execution_enabled": user.broker_execution_enabled,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {str(e)}",
        )


@app.get("/api/auth/profile", tags=["Authentication"])
def get_user_profile(user: UserTierProfile = Depends(get_current_user)):
    """Returns the caller's active tier, remaining requests, and authorized features."""
    return {
        "user_id": user.user_id,
        "email": user.email,
        "tier": user.tier,
        "requests_today": user.requests_today,
        "daily_quota": user.daily_quota,
        "quota_remaining": max(0, user.daily_quota - user.requests_today),
        "allowed_intervals": user.allowed_intervals,
        "broker_execution_enabled": user.broker_execution_enabled,
    }


# ----------------- Live Paper-Trading & Broker Execution Endpoints ----------------- #


@app.get("/api/broker/account", tags=["Broker Execution"])
def get_broker_account(user: UserTierProfile = Depends(get_current_user)):
    """Returns the live paper / live broker account balance, equity, and MTM PnL."""
    return broker_engine.get_account_summary()


@app.get("/api/broker/positions", tags=["Broker Execution"])
def get_broker_positions(user: UserTierProfile = Depends(get_current_user)):
    """Returns all currently open positions with live entry, target, and stop prices."""
    positions = broker_engine.get_open_positions()
    return {
        "total_open": len(positions),
        "positions": [
            {
                "id": p.id,
                "ticker": p.ticker,
                "direction": p.direction,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "shares": round(p.shares, 4),
                "allocated_capital": round(p.allocated_capital, 2),
                "target_price": round(p.target_price, 2),
                "stop_price": round(p.stop_price, 2),
                "unrealized_pnl": round(p.unrealized_pnl, 2),
                "unrealized_return_pct": round(p.unrealized_return_pct, 2),
                "entry_time": p.entry_time,
                "holding_bars": p.holding_bars,
            }
            for p in positions
        ],
    }


@app.post("/api/broker/order", tags=["Broker Execution"])
def submit_broker_order(
    req: OrderRequest, user: UserTierProfile = Depends(get_current_user)
):
    """Executes a new market order, allocating capital with exact friction deduction."""
    global engine
    if engine is None:
        engine = MarketPredictionEngine()

    analysis = engine.analyze_ticker(req.ticker, period="1y", interval="1d")
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to fetch current market price for {req.ticker}",
        )

    curr_p = analysis.current_price
    order_type = (req.order_type or "MARKET").upper()
    exec_p = req.limit_price if (order_type == "LIMIT" and req.limit_price is not None and req.limit_price > 0) else curr_p
    target_p = req.target_price or analysis.meta_prediction.target_price
    stop_p = req.stop_price or analysis.meta_prediction.stop_price

    pos = broker_engine.open_position(
        ticker=req.ticker,
        direction=req.direction.upper(),
        current_price=exec_p,
        target_price=target_p,
        stop_price=stop_p,
        allocation_weight_pct=req.allocation_weight_pct,
    )

    if not pos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order rejected: insufficient cash or below minimum trade size.",
        )

    return {
        "status": "FILLED",
        "position_id": pos.id,
        "ticker": pos.ticker,
        "direction": pos.direction,
        "entry_price": pos.entry_price,
        "shares": round(pos.shares, 4),
        "allocated_capital": round(pos.allocated_capital, 2),
        "target_price": round(pos.target_price, 2),
        "stop_price": round(pos.stop_price, 2),
        "timestamp": pos.entry_time,
    }


@app.post("/api/broker/close/{position_id}", tags=["Broker Execution"])
def close_broker_position(
    position_id: int, user: UserTierProfile = Depends(get_current_user)
):
    """Manually closes an active open position and realizes PnL."""
    global engine
    if engine is None:
        engine = MarketPredictionEngine()

    positions = broker_engine.get_open_positions()
    matched = [p for p in positions if p.id == position_id]
    if not matched:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Open position with ID {position_id} not found.",
        )

    pos = matched[0]
    analysis = engine.analyze_ticker(pos.ticker, period="1y", interval="1d")
    curr_p = analysis.current_price if analysis else pos.entry_price

    trade = broker_engine.close_position(
        position_id=position_id, exit_price=curr_p, exit_reason="MANUAL_API_CLOSE"
    )

    if not trade:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to close position.",
        )

    return {
        "status": "CLOSED",
        "trade_id": trade.id,
        "ticker": trade.ticker,
        "direction": trade.direction,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "net_pnl": trade.net_pnl,
        "return_pct": trade.return_pct,
        "friction_fee": trade.friction_fee,
        "exit_reason": trade.exit_reason,
        "exit_time": trade.exit_time,
    }


@app.get("/api/broker/trades", tags=["Broker Execution"])
def get_broker_trades(
    limit: int = Query(50, description="Max closed trades to retrieve"),
    user: UserTierProfile = Depends(get_current_user),
):
    """Returns verified historical trades and execution performance audit."""
    trades = broker_engine.get_closed_trades(limit=limit)
    audit = broker_engine.get_performance_audit()
    return {
        "audit": audit,
        "total_retrieved": len(trades),
        "trades": [
            {
                "id": t.id,
                "ticker": t.ticker,
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "shares": t.shares,
                "net_pnl": t.net_pnl,
                "return_pct": t.return_pct,
                "friction_fee": t.friction_fee,
                "exit_reason": t.exit_reason,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
            }
            for t in trades
        ],
    }


@app.post("/api/webhook/alert", tags=["Webhooks"])
def receive_webhook_alert(req: WebhookAlertRequest):
    """Receives incoming alerts from external services (e.g. TradingView / Cron) and routes orders."""
    bot = _get_live_bot()
    tk = req.ticker.upper()
    action = req.action.upper()

    if action in ["BUY", "SELL"]:
        direction = "LONG" if action == "BUY" else "SHORT"
        analysis = bot.analyses.get(tk)
        if not analysis:
            analysis = bot.engine.analyze_ticker(tk, period="1y", interval="1d")
            if not analysis:
                return {"status": "ERROR", "message": f"Unable to fetch price for {tk}"}
            bot.analyses[tk] = analysis
            bot.live_prices[tk] = analysis.current_price
            bot.base_prices[tk] = analysis.current_price

        curr_p = req.price or bot.live_prices.get(tk, analysis.current_price)
        tradable, sess = bot._is_ticker_tradable_now(tk)

        if not tradable:
            try:
                queued = bot.broker.queue_pre_market_order(
                    ticker=tk,
                    direction=direction,
                    current_price=curr_p,
                    target_price=analysis.meta_prediction.target_price,
                    stop_price=analysis.meta_prediction.stop_price,
                    allocation_weight_pct=10.0,
                )
                bot.log_event(
                    "SESSION",
                    f"Webhook alert queued as PRE_MARKET_PENDING order #{queued['order_id']} for {tk} ({direction}). Scheduled execution at open.",
                )
                return {"status": "QUEUED", "order_id": queued["order_id"], "state": "PRE_MARKET_PENDING", "order": queued}
            except Exception as e:
                return {"status": "ERROR", "message": str(e)}

        pos = bot.broker.open_position(
            ticker=tk,
            direction=direction,
            current_price=curr_p,
            target_price=analysis.meta_prediction.target_price,
            stop_price=analysis.meta_prediction.stop_price,
            allocation_weight_pct=10.0,
        )
        return {"status": "EXECUTED", "position_id": pos.id if pos else None}

    return {"status": "IGNORED", "message": f"Action '{action}' does not trigger an order."}


class AssetSelectionRequest(BaseModel):
    armed_tickers: List[str] = Field(default=[], description="List of symbols armed for autonomous bot trading")
    add_custom_tickers: Optional[List[str]] = Field(default=None, description="Optional new symbols to load into terminal")


# ----------------- Interactive Real-Time Dashboard Endpoints ----------------- #


@app.get("/api/dashboard/state", tags=["Dashboard"])
def get_dashboard_state():
    """Returns real-time bot status, Market vs. Bot performance series, watchlist, and positions."""
    bot = _get_live_bot()
    return bot.get_dashboard_state()


@app.get("/api/sessions/status", tags=["Sessions"])
def get_sessions_status():
    """Returns complete physical exchange session states, countdowns, and statutory holiday statuses."""
    bot = _get_live_bot()
    return bot.get_all_market_sessions()


@app.get("/api/dashboard/orders/pending", tags=["Dashboard"])
def get_pending_orders():
    """Returns all queued PRE_MARKET_PENDING orders awaiting physical exchange open."""
    bot = _get_live_bot()
    return bot.broker.get_pending_orders()


@app.delete("/api/dashboard/orders/cancel/{order_id}", tags=["Dashboard"])
@app.post("/api/dashboard/orders/cancel/{order_id}", tags=["Dashboard"])
def cancel_pending_order(order_id: str):
    """Cancels a queued pre-market order and immediately releases reserved cash hold."""
    bot = _get_live_bot()
    success = bot.broker.cancel_pending_order(order_id)
    if success:
        bot.log_event("SESSION", f"Cancelled queued pending order #{order_id}. Capital unreserved.")
    return {
        "status": "CANCELLED" if success else "NOT_FOUND",
        "order_id": order_id,
        "dashboard_state": bot.get_dashboard_state(),
    }


@app.post("/api/dashboard/select-assets", tags=["Dashboard"])
def update_dashboard_asset_selection(req: AssetSelectionRequest):
    """Updates which specific stocks, cryptos, commodities, or FX pairs the bot is armed to trade."""
    bot = _get_live_bot()
    return bot.update_asset_selection(
        armed_tickers=req.armed_tickers,
        add_custom_tickers=req.add_custom_tickers,
    )


@app.post("/api/dashboard/toggle-hours", tags=["Dashboard"])
def toggle_dashboard_market_hours():
    """Toggles between Strict Real-World Exchange Hours and 24/7 Sandbox Simulation Mode."""
    bot = _get_live_bot()
    return bot.toggle_market_hours_enforcement()


@app.post("/api/dashboard/toggle-simulation", tags=["Dashboard"])
def toggle_dashboard_simulation():
    """Explicitly toggles between Strict Physical Market Hours and 24/7 Sandbox Override."""
    bot = _get_live_bot()
    return bot.toggle_simulation_mode()


@app.post("/api/dashboard/step", tags=["Dashboard"])
def step_dashboard_tick(shock_pct: Optional[float] = Query(None)):
    """Advances the live market simulation by 1 tick, updates MTM PnL, and runs autonomous bot trades."""
    bot = _get_live_bot()
    return bot.step_tick(custom_shock_pct=shock_pct)


@app.post("/api/dashboard/toggle", tags=["Dashboard"])
def toggle_bot_running():
    """Starts or pauses the autonomous trading bot."""
    bot = _get_live_bot()
    bot.is_running = not bot.is_running
    bot.log_event(
        "BOT",
        f"Autonomous Bot switched to {'RUNNING (Auto-Trading Active)' if bot.is_running else 'PAUSED (Manual Standby)'}.",
    )
    return bot.get_dashboard_state()


@app.post("/api/dashboard/order", tags=["Dashboard"])
def dashboard_manual_order(req: OrderRequest):
    """Places an order from the terminal; queues as PRE_MARKET_PENDING if physical exchange is closed."""
    bot = _get_live_bot()
    tk = req.ticker.upper()
    curr_p = bot.live_prices.get(tk)
    if curr_p is None:
        analysis = bot.engine.analyze_ticker(tk, period="1y", interval="1d")
        if not analysis:
            raise HTTPException(status_code=400, detail=f"Unknown ticker {tk}")
        curr_p = analysis.current_price
        bot.analyses[tk] = analysis
        bot.live_prices[tk] = curr_p
        bot.base_prices[tk] = curr_p

    res = bot.analyses.get(tk)
    vol_bar = max(res.volatility_cone.expected_vol_annualized / np.sqrt(252.0), 0.012) if res else 0.015
    decimals = 4 if (res and res.market_jurisdiction == "FOREX") else 2
    direction = req.direction.upper()
    order_type = (req.order_type or "MARKET").upper()
    limit_p = req.limit_price

    # Reference execution price for target/stop calculation and order allocation
    exec_p = limit_p if (order_type == "LIMIT" and limit_p is not None and limit_p > 0) else curr_p

    pt_p = req.target_price or round(exec_p * (1.0 + 1.4 * vol_bar if direction == "LONG" else 1.0 - 1.4 * vol_bar), decimals)
    sl_p = req.stop_price or round(exec_p * (1.0 - 1.0 * vol_bar if direction == "LONG" else 1.0 + 1.0 * vol_bar), decimals)

    tradable, sess = bot._is_ticker_tradable_now(tk)
    if not tradable:
        # Off-hours submission: queue order safely as PRE_MARKET_PENDING with soft cash hold
        try:
            queued = bot.broker.queue_pre_market_order(
                ticker=tk,
                direction=direction,
                current_price=exec_p,
                target_price=pt_p,
                stop_price=sl_p,
                allocation_weight_pct=req.allocation_weight_pct,
                order_type=order_type,
            )
            bot.log_event(
                "SESSION",
                f"Queued PRE_MARKET_PENDING {order_type} order #{queued['order_id']} for {tk} ({direction}) @ {exec_p:,.{decimals}f}. Scheduled execution at market open ({sess.get('next_state_time_utc')}).",
            )
            return {
                "status": "QUEUED",
                "order_id": queued["order_id"],
                "state": "PRE_MARKET_PENDING",
                "order": queued,
                "dashboard_state": bot.get_dashboard_state(),
            }
        except ValueError as err:
            bot.log_event("RISK", f"Pre-market order rejected for {tk}: {str(err)}")
            raise HTTPException(status_code=400, detail=str(err))

    # Market is open or in simulation mode: execute immediately
    pos = bot.broker.open_position(
        ticker=tk,
        direction=direction,
        current_price=exec_p,
        target_price=pt_p,
        stop_price=sl_p,
        allocation_weight_pct=req.allocation_weight_pct,
    )
    if pos:
        bot.log_event(
            "TRADE",
            f"Manual Order Filled: {direction} {tk} (${pos.allocated_capital:,.0f}) @ {exec_p:,.{decimals}f} | Target: {pt_p:,.{decimals}f} | Stop: {sl_p:,.{decimals}f}",
        )
    return {
        "status": "FILLED",
        "position": pos,
        "dashboard_state": bot.get_dashboard_state(),
    }


@app.post("/api/dashboard/close/{position_id}", tags=["Dashboard"])
def dashboard_close_position(position_id: int):
    """Closes a specific open simulated position at its current live price."""
    bot = _get_live_bot()
    open_pos = bot.broker.get_open_positions()
    matched = [p for p in open_pos if p.id == position_id]
    if matched:
        p = matched[0]
        exit_p = bot.live_prices.get(p.ticker, p.current_price or p.entry_price)
        tr = bot.broker.close_position(position_id, exit_p, exit_reason="MANUAL_CLOSE")
        if tr:
            bot.log_event(
                "PROFIT" if tr.net_pnl >= 0 else "STOP",
                f"Manually Closed {tr.direction} {tr.ticker} @ {tr.exit_price:,.4f} | Net PnL: ${tr.net_pnl:+,.2f} ({tr.return_pct:+.2f}%)",
            )
    return bot.get_dashboard_state()


@app.post("/api/dashboard/flatten", tags=["Dashboard"])
def dashboard_flatten_all():
    """Liquidates all open simulated positions to cash."""
    bot = _get_live_bot()
    closed = bot.broker.close_all_positions(bot.live_prices, reason="FLATTEN_ALL")
    bot.log_event("BOT", f"Liquidated all ({len(closed)}) open positions to cash.")
    return bot.get_dashboard_state()


@app.post("/api/dashboard/reset", tags=["Dashboard"])
def dashboard_reset_account():
    """Resets the simulated account to $100,000.00."""
    bot = _get_live_bot()
    return bot.reset_simulation(initial_capital=100000.0)


# ----------------- Frontend Static Files Mounting ----------------- #
frontend_dist = Path(__file__).resolve().parent / "frontend" / "dist"
if frontend_dist.exists():
    try:
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend-dist")
        logger.info(f"Mounted frontend/dist at /")
    except Exception as e:
        logger.warning(f"Could not mount frontend/dist: {e}")


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8501, reload=False)
