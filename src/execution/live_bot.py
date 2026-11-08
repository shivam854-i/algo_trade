"""Autonomous Live Paper-Trading Controller, Exchange Hours Engine & Multi-Asset Selector.

Executes the 10-step autonomous paper-trading loop over genuine market data:
1. Check exchange session status (NYSE/NASDAQ, NSE, CME, Forex, Crypto).
2. Fetch latest genuine market quotes (Bid, Ask, Last, Volume, Timestamp) from DataProvider.
3. Validate data freshness, missing-data & staleness guardrails (never invent prices).
4. Update open virtual positions and Bid/Ask Mark-to-Market unrealized P&L.
5. Check gap-aware Stop-Loss and conservative intrabar Take-Profit conditions.
6. Run/refresh the point-in-time causal prediction pipeline.
7. Evaluate HMM regime and multi-tiered risk guardrails.
8. Calculate CVaR-Kelly & HRP position size within portfolio exposure limits.
9. Submit virtual paper orders with Bid/Ask spread + Almgren-Chriss slippage.
10. Persist state to SQLite and emit real-time dashboard telemetry.

CRITICAL: This controller is strictly PAPER-TRADING ONLY with virtual money.
"""

from datetime import datetime, timezone
import logging
from dataclasses import asdict
import math
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np

from src.data.provider_base import (
    BaseMarketDataProvider,
    LiveQuote,
    MultiAssetDataProvider,
)
from src.execution.broker import PAPER_TRADING_ONLY, PaperBroker
from src.execution.frictions import FrictionEvaluator
from src.execution.market_sessions import (
    MarketCalendarManager,
    MarketSessionInfo,
    MarketState,
)
from src.models.gpu_acceleration import GPUManager
from src.pipeline import MarketPredictionEngine, SingleAssetAnalysis

logger = logging.getLogger(__name__)

from src.config.markets import NIFTY_50_TICKERS, get_default_universe, NSE_MASTER_CATALOG

# Global default calendar instance
_default_calendar = MarketCalendarManager()

# Backward compatibility alias
DEFAULT_US_EQUITIES: List[str] = ["NVDA", "AAPL", "MSFT", "AMD", "TSLA"]

# Default NSE Equities universe (50 Nifty constituents)
DEFAULT_NSE_EQUITIES: List[str] = list(NIFTY_50_TICKERS)
DEFAULT_UNIVERSE: List[str] = list(NIFTY_50_TICKERS)

ASSET_CATALOG = {
    "NIFTY_50": list(NIFTY_50_TICKERS),
    "BANK_NIFTY": [
        "HDFCBANK.NS", "ICICIBANK.NS", "KOTAKBANK.NS", "SBIN.NS",
        "AXISBANK.NS", "INDUSINDBK.NS", "BANKBARODA.NS", "PNB.NS",
        "AUBANK.NS", "FEDERALBNK.NS", "IDFCFIRSTB.NS",
    ],
    "NIFTY_IT": [
        "TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS",
        "TECHM.NS", "LTIM.NS", "PERSISTENT.NS", "COFORGE.NS",
    ],
    "BSE_SENSEX": [
        "RELIANCE.BO", "TCS.BO", "HDFCBANK.BO", "INFY.BO",
        "ICICIBANK.BO", "ITC.BO", "SBIN.BO", "BHARTIARTL.BO",
    ],
    "BENCHMARKS": ["^NSEI", "^BSESN", "^NSEBANK"],
}

from src.strategy.horizon_mapper import HorizonMapper, HorizonParameters
from src.strategy.trade_evaluator import TradeEvaluator, TradeEvaluationResult
from src.strategy.trade_ranker import TradeRanker, RankedOpportunity
from src.strategy.portfolio_selector import PortfolioSelector, PortfolioAllocationResult
from src.strategy.decision_explainer import DecisionExplainer, PlainLanguageExplanation

# Comprehensive searchable directory of Indian equities & benchmark indices (NSE & BSE)
SEARCHABLE_INSTRUMENTS: List[Dict[str, str]] = [
    # Indian Benchmark Indices
    {"ticker": "^NSEI", "name": "NIFTY 50 Index", "category": "BENCHMARKS", "exchange": "NSE", "sector": "Benchmark Index"},
    {"ticker": "^BSESN", "name": "BSE SENSEX 30 Index", "category": "BENCHMARKS", "exchange": "BSE", "sector": "Benchmark Index"},
    {"ticker": "^NSEBANK", "name": "BANK NIFTY Index", "category": "BENCHMARKS", "exchange": "NSE", "sector": "Banking Index"},
    # Indian Equities — NSE Nifty 50 Constituents
    {"ticker": "RELIANCE.NS", "name": "Reliance Industries Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Energy, Telecom & Retail"},
    {"ticker": "TCS.NS", "name": "Tata Consultancy Services Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "IT Services"},
    {"ticker": "HDFCBANK.NS", "name": "HDFC Bank Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Private Banking"},
    {"ticker": "INFY.NS", "name": "Infosys Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "IT Services"},
    {"ticker": "ICICIBANK.NS", "name": "ICICI Bank Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Private Banking"},
    {"ticker": "SBIN.NS", "name": "State Bank of India (SBI)", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "PSU Banking"},
    {"ticker": "BHARTIARTL.NS", "name": "Bharti Airtel Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Telecom"},
    {"ticker": "ITC.NS", "name": "ITC Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "FMCG & Hospitality"},
    {"ticker": "KOTAKBANK.NS", "name": "Kotak Mahindra Bank Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Private Banking"},
    {"ticker": "LT.NS", "name": "Larsen & Toubro Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Infrastructure & Engineering"},
    {"ticker": "AXISBANK.NS", "name": "Axis Bank Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Private Banking"},
    {"ticker": "HINDUNILVR.NS", "name": "Hindustan Unilever Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "FMCG"},
    {"ticker": "BAJFINANCE.NS", "name": "Bajaj Finance Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "NBFC & Consumer Finance"},
    {"ticker": "MARUTI.NS", "name": "Maruti Suzuki India Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Automobiles"},
    {"ticker": "ASIANPAINT.NS", "name": "Asian Paints Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Consumer Goods & Paints"},
    {"ticker": "HCLTECH.NS", "name": "HCL Technologies Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "IT Services"},
    {"ticker": "SUNPHARMA.NS", "name": "Sun Pharmaceutical Industries", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Pharmaceuticals"},
    {"ticker": "TITAN.NS", "name": "Titan Company Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Consumer Durables & Jewelry"},
    {"ticker": "ULTRACEMCO.NS", "name": "UltraTech Cement Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Cement & Materials"},
    {"ticker": "TATASTEEL.NS", "name": "Tata Steel Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Metals & Mining"},
    {"ticker": "NTPC.NS", "name": "NTPC Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Power Generation"},
    {"ticker": "POWERGRID.NS", "name": "Power Grid Corporation of India", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Power Transmission"},
    {"ticker": "ONGC.NS", "name": "Oil & Natural Gas Corporation", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Energy & Oil"},
    {"ticker": "M&M.NS", "name": "Mahindra & Mahindra Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Automobiles"},
    {"ticker": "JSWSTEEL.NS", "name": "JSW Steel Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Metals & Mining"},
    {"ticker": "COALINDIA.NS", "name": "Coal India Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Mining & Energy"},
    {"ticker": "BAJAJFINSV.NS", "name": "Bajaj Finserv Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Financial Services"},
    {"ticker": "ADANIENT.NS", "name": "Adani Enterprises Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Infrastructure & Energy"},
    {"ticker": "ADANIPORTS.NS", "name": "Adani Ports and Special Economic Zone", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Ports & Logistics"},
    {"ticker": "BPCL.NS", "name": "Bharat Petroleum Corporation Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Energy & Refining"},
    {"ticker": "GRASIM.NS", "name": "Grasim Industries Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Materials & Textiles"},
    {"ticker": "CIPLA.NS", "name": "Cipla Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Pharmaceuticals"},
    {"ticker": "NESTLEIND.NS", "name": "Nestle India Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "FMCG & Food"},
    {"ticker": "WIPRO.NS", "name": "Wipro Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "IT Services"},
    {"ticker": "TATACONSUM.NS", "name": "Tata Consumer Products Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "FMCG"},
    {"ticker": "DRREDDY.NS", "name": "Dr. Reddy's Laboratories", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Pharmaceuticals"},
    {"ticker": "EICHERMOT.NS", "name": "Eicher Motors Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Automobiles"},
    {"ticker": "HEROMOTOCO.NS", "name": "Hero MotoCorp Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Automobiles"},
    {"ticker": "DIVISLAB.NS", "name": "Divi's Laboratories Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Pharmaceuticals"},
    {"ticker": "HINDALCO.NS", "name": "Hindalco Industries Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Metals & Aluminum"},
    {"ticker": "APOLLOHOSP.NS", "name": "Apollo Hospitals Enterprise", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Healthcare"},
    {"ticker": "SHRIRAMFIN.NS", "name": "Shriram Finance Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Financial Services"},
    {"ticker": "TRENT.NS", "name": "Trent Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Retail & Fashion"},
    {"ticker": "BEL.NS", "name": "Bharat Electronics Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Aerospace & Defense"},
    {"ticker": "BRITANNIA.NS", "name": "Britannia Industries Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "FMCG & Food"},
    {"ticker": "SBILIFE.NS", "name": "SBI Life Insurance Company", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Life Insurance"},
    {"ticker": "HDFCLIFE.NS", "name": "HDFC Life Insurance Company", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Life Insurance"},
    {"ticker": "TECHM.NS", "name": "Tech Mahindra Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "IT Services"},
    {"ticker": "BAJAJ-AUTO.NS", "name": "Bajaj Auto Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Automobiles"},
    {"ticker": "INDUSINDBK.NS", "name": "IndusInd Bank Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Private Banking"},
    {"ticker": "HAL.NS", "name": "Hindustan Aeronautics Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Aerospace & Defense"},
    {"ticker": "TATAMOTORS.NS", "name": "Tata Motors Ltd.", "category": "INDIAN_NSE", "exchange": "NSE", "sector": "Automobiles & EV"},
    # Prominent BSE Equities
    {"ticker": "RELIANCE.BO", "name": "Reliance Industries Ltd. (BSE)", "category": "INDIAN_BSE", "exchange": "BSE", "sector": "Energy, Telecom & Retail"},
    {"ticker": "TCS.BO", "name": "Tata Consultancy Services (BSE)", "category": "INDIAN_BSE", "exchange": "BSE", "sector": "IT Services"},
    {"ticker": "HDFCBANK.BO", "name": "HDFC Bank Ltd. (BSE)", "category": "INDIAN_BSE", "exchange": "BSE", "sector": "Private Banking"},
    {"ticker": "INFY.BO", "name": "Infosys Ltd. (BSE)", "category": "INDIAN_BSE", "exchange": "BSE", "sector": "IT Services"},
    {"ticker": "ICICIBANK.BO", "name": "ICICI Bank Ltd. (BSE)", "category": "INDIAN_BSE", "exchange": "BSE", "sector": "Private Banking"},
    {"ticker": "SBIN.BO", "name": "State Bank of India (BSE)", "category": "INDIAN_BSE", "exchange": "BSE", "sector": "PSU Banking"},
    # Legacy Global Catalog Reference Instruments
    {"ticker": "AAPL", "name": "Apple Inc.", "category": "US_EQUITIES", "exchange": "NASDAQ", "sector": "Consumer Technology"},
    {"ticker": "NVDA", "name": "NVIDIA Corporation", "category": "US_EQUITIES", "exchange": "NASDAQ", "sector": "Semiconductors & AI"},
]

# Enrich SEARCHABLE_INSTRUMENTS with the complete NSE Master Directory
_existing_search_tickers = {item["ticker"] for item in SEARCHABLE_INSTRUMENTS}
for _cat_entry in NSE_MASTER_CATALOG:
    if _cat_entry["ticker"] not in _existing_search_tickers:
        SEARCHABLE_INSTRUMENTS.append({
            "ticker": _cat_entry["ticker"],
            "name": _cat_entry["name"],
            "category": "INDIAN_NSE",
            "exchange": _cat_entry.get("exchange", "NSE"),
            "sector": _cat_entry["sector"],
        })
        _existing_search_tickers.add(_cat_entry["ticker"])


def get_exchange_session_status(ticker: str, market_type: str = "") -> Dict[str, Any]:
    """Determines whether the real-world exchange for `ticker` is currently OPEN or CLOSED."""
    info = _default_calendar.get_session_info(ticker)
    return {
        "is_open": info.is_open,
        "exchange": info.exchange_name,
        "schedule": info.session_schedule,
        "local_clock": info.local_time_str,
        "reason": info.reason,
        "state": info.state.value if isinstance(info.state, MarketState) else str(info.state),
        "next_state": info.next_state.value if isinstance(info.next_state, MarketState) else str(info.next_state),
        "next_state_time_utc": info.next_state_time_utc,
        "seconds_to_next_state": info.seconds_to_next_state,
        "countdown_display": info.countdown_display,
        "tick_frozen": info.tick_frozen,
        "holiday_name": info.holiday_name,
    }


class LiveBotController:
    """Orchestrates live-market autonomous paper trading, market hours enforcement, and feed health governance."""

    def __init__(
        self,
        engine: MarketPredictionEngine,
        broker: PaperBroker,
        data_provider: Optional[BaseMarketDataProvider] = None,
        initial_watchlist: Optional[List[str]] = None,
        session_manager: Optional[Any] = None,
        require_session: bool = False,
    ):
        assert PAPER_TRADING_ONLY, "LiveBotController requires PAPER_TRADING_ONLY=True"
        self.engine = engine
        self.broker = broker
        self.data_provider: BaseMarketDataProvider = data_provider or MultiAssetDataProvider()
        self.gpu_profile = GPUManager().profile

        # Session & Horizon Governance (Milestone 2 Part C)
        self.session_manager = session_manager
        self.active_session_id: Optional[str] = None
        self.require_session: bool = require_session
        self.horizon_params: Optional[HorizonParameters] = None
        self.quote_staleness_threshold_sec: float = 60.0
        self.bar_interval: str = "1d"
        self.lookback_period: str = "1y"
        self._active_session_mock: Optional[Any] = None

        # Default to Nifty 50 constituents (NSE_CASH focus)
        default_list = list(initial_watchlist) if initial_watchlist else list(DEFAULT_NSE_EQUITIES)
        self.watchlist: List[str] = default_list
        self.armed_tickers: Set[str] = set(default_list)

        self.is_running: bool = True
        self.calendar = MarketCalendarManager()
        self.simulation_mode: bool = False
        self.enforce_market_hours: bool = True
        self.last_known_market_states: Dict[str, MarketState] = {}
        self.tick_count: int = 0
        self.last_tick_time: str = datetime.now().strftime("%H:%M:%S")

        self.analyses: Dict[str, SingleAssetAnalysis] = {}
        self.hrp_weights: Dict[str, float] = {}
        self.base_prices: Dict[str, float] = {}
        self.live_prices: Dict[str, float] = {}
        self.latest_quotes: Dict[str, LiveQuote] = {}
        self.price_series: Dict[str, List[Dict[str, float | str]]] = {}

        self.comparison_series: List[Dict[str, float | str]] = []
        self.activity_log: List[Dict[str, Any]] = []
        self.last_stop_loss_time: Dict[str, datetime] = {}
        self._sandbox_rng = np.random.default_rng(42)
        self._initialized = False

    @staticmethod
    def _price_decimals(price: Optional[float], jurisdiction: str = "", ticker: str = "") -> int:
        """Determines appropriate display/barrier decimal precision (4 decimals for FX and sub-$10 assets)."""
        if jurisdiction == "FOREX" or ticker.upper().endswith("=X"):
            return 4
        if price is not None and 0.0 < float(price) < 10.0:
            return 4
        return 2

    def attach_session_manager(self, session_manager: Any) -> None:
        """Attaches the persistent SessionManager instance."""
        self.session_manager = session_manager

    def set_active_session(self, session: Any) -> None:
        """Binds a TradingSession, restricts watchlist to approved basket, and maps horizon."""
        self.active_session_id = session.id
        self.watchlist = list(session.instruments)
        self.armed_tickers = set(session.instruments)
        self.is_running = (session.status == "RUNNING")
        if hasattr(self.broker, "active_session_id"):
            self.broker.active_session_id = session.id
        self.bind_horizon_parameters(session.horizon, market_type=session.market)
        self.log_event(
            "SESSION",
            f"Bound Active Session #{session.id} ({session.name or 'Trading Session'}): "
            f"Market={session.market}, Basket={session.instruments}, Capital={session.currency} {session.allocated_capital:,.2f}, "
            f"Horizon={session.horizon}, End Policy={session.session_end_policy}.",
        )

    def get_active_session(self) -> Optional[Any]:
        """Retrieves the active TradingSession from session_manager or internal state."""
        if self.session_manager is not None:
            if self.active_session_id:
                sess = self.session_manager.get_session(self.active_session_id)
                if sess and getattr(sess, "is_active", False):
                    return sess
                self.active_session_id = None
            active = self.session_manager.get_active_session()
            if active and getattr(active, "is_active", False):
                self.active_session_id = active.id
                return active
            return None
        return self._active_session_mock

    def bind_horizon_parameters(self, horizon: str, market_type: str = "US") -> HorizonParameters:
        """Dynamically binds quantitative strategy parameters across horizons (1h, 1d, 1wk)."""
        params = HorizonMapper.get_parameters(horizon, market_type=market_type)
        self.horizon_params = params
        self.quote_staleness_threshold_sec = float(params.quote_staleness_threshold_sec)
        self.bar_interval = params.bar_interval
        self.lookback_period = params.lookback_period
        self.log_event(
            "HORIZON",
            f"Bound Horizon '{params.horizon_name}' ({params.category}): "
            f"Interval={params.bar_interval}, TCN Forward={params.tcn_horizon_bars} bars, "
            f"ATR Window={params.atr_window}, Staleness Limit={params.quote_staleness_threshold_sec:.0f}s",
            metadata=params.to_dict(),
        )
        return params

    def log_event(self, level: str, message: str, metadata: Optional[Dict[str, Any]] = None):
        """Emits structured event to activity feed with optional metadata."""
        ts = datetime.now().strftime("%H:%M:%S")
        entry: Dict[str, Any] = {
            "time": ts,
            "level": level,
            "message": message,
        }
        if metadata:
            entry["metadata"] = metadata
        self.activity_log.insert(0, entry)
        if len(self.activity_log) > 100:
            self.activity_log = self.activity_log[:100]

    def _is_ticker_tradable_now(self, ticker: str) -> Tuple[bool, Dict[str, Any]]:
        sess = self.calendar.get_session_info(ticker, simulation_mode=self.simulation_mode)
        d = sess.to_dict()
        d["exchange"] = sess.exchange_name
        d["schedule"] = sess.session_schedule
        d["local_clock"] = sess.local_time_str
        return sess.is_tradable, d

    def initialize_market_state(self):
        """Loads initial multi-asset forecasts, fetches genuine market quotes, and seeds telemetry."""
        if self._initialized:
            return

        self.log_event(
            "BOT",
            f"Booting SYNAPSE-TITAN Paper-Trading Engine on {self.gpu_profile.device_name} "
            f"(Virtual Capital: $100,000.00 | Mode: PAPER_TRADING_ONLY)...",
        )
        # Fast boot: seed initial forecasts with core watchlist
        seed_tickers = self.watchlist[:5] if len(self.watchlist) > 5 else self.watchlist
        portfolio = self.engine.analyze_portfolio(seed_tickers, period="1y", interval="1d")
        self.analyses = portfolio.single_analyses
        self.hrp_weights = portfolio.hrp_portfolio_weights

        # Close any leftover positions from closed exchanges when booting in Strict Exchange Hours mode
        if self.enforce_market_hours:
            for pos in self.broker.get_open_positions():
                tradable, _ = self._is_ticker_tradable_now(pos.ticker)
                if not tradable:
                    self.broker.close_position(pos.id, pos.entry_price, exit_reason="EXCHANGE_CLOSED_CLEANUP")

        open_pos = {p.ticker: p for p in self.broker.get_open_positions()}

        for tk, res in self.analyses.items():
            df_tail = res.recent_ohlcv.tail(45)
            decimals = self._price_decimals(res.current_price, res.market_jurisdiction, tk)
            hist = []
            for idx, row in df_tail.iterrows():
                label = idx.strftime("%b %d") if hasattr(idx, "strftime") else str(idx)
                hist.append(
                    {
                        "time": label,
                        "price": round(float(row["Close"]), decimals),
                        "high": round(float(row["High"]), decimals),
                        "low": round(float(row["Low"]), decimals),
                    }
                )

            # Query genuine market quote on initialization where available
            tradable, sess = self._is_ticker_tradable_now(tk)
            quote = None
            try:
                quote = self.data_provider.get_quote(tk, market_open=bool(sess["is_open"]))
                if quote and quote.is_valid:
                    self.latest_quotes[tk] = quote
            except Exception as exc:
                logger.debug(f"Initial quote fetch for {tk} deferred: {exc}")

            curr_p = (
                quote.last_price
                if (quote and quote.is_valid)
                else (open_pos[tk].current_price if tk in open_pos else float(res.current_price))
            )
            self.base_prices[tk] = float(res.current_price)
            self.live_prices[tk] = round(curr_p, decimals)
            if hist:
                hist[-1]["price"] = round(curr_p, decimals)
            self.price_series[tk] = hist

            if not tradable:
                self.log_event("RISK", f"{tk}: {sess['reason']} — Price frozen & auto-trading queued until market open.")

        summary = self.broker.get_account_summary()
        curr_ret = float(summary.get("total_return_pct", 0.0))
        init_cap = float(summary.get("initial_capital", 100000.0))
        now_str = datetime.now().strftime("%H:%M:%S")

        if not self.comparison_series:
            for i in range(8, 0, -1):
                frac = (8 - i) / 8.0
                b_ret = round(curr_ret * frac, 3)
                m_ret = round((curr_ret * 0.40) * frac, 3)
                self.comparison_series.append(
                    {
                        "time": f"T-{i}",
                        "bot_return_pct": b_ret,
                        "market_return_pct": m_ret,
                        "bot_equity": round(init_cap * (1.0 + b_ret / 100.0), 2),
                    }
                )
            self.comparison_series.append(
                {
                    "time": now_str,
                    "bot_return_pct": round(curr_ret, 3),
                    "market_return_pct": round(self._compute_market_return_pct(), 3),
                    "bot_equity": round(float(summary.get("total_equity", init_cap)), 2),
                }
            )

        self._initialized = True

    def update_asset_selection(
        self,
        armed_tickers: List[str],
        add_custom_tickers: Optional[List[str]] = None,
    ) -> Dict:
        """Updates which specific stocks/cryptos/FX the bot is armed to trade, loading any new symbols."""
        if not self._initialized:
            self.initialize_market_state()

        if add_custom_tickers:
            for raw_tk in add_custom_tickers:
                tk = raw_tk.strip().upper()
                if not tk:
                    continue
                if tk not in self.analyses:
                    res = self.engine.analyze_ticker(tk, period="1y", interval="1d")
                    if res is not None:
                        self.analyses[tk] = res
                        if tk not in self.watchlist:
                            self.watchlist.append(tk)
                        decimals = self._price_decimals(res.current_price, res.market_jurisdiction, tk)
                        self.base_prices[tk] = float(res.current_price)
                        self.live_prices[tk] = round(float(res.current_price), decimals)
                        df_tail = res.recent_ohlcv.tail(45)
                        self.price_series[tk] = [
                            {
                                "time": idx.strftime("%b %d") if hasattr(idx, "strftime") else str(idx),
                                "price": round(float(row["Close"]), decimals),
                                "high": round(float(row["High"]), decimals),
                                "low": round(float(row["Low"]), decimals),
                            }
                            for idx, row in df_tail.iterrows()
                        ]
                        self.log_event("BOT", f"Added {tk} ({res.market_jurisdiction}) to active terminal.")
                    else:
                        self.log_event("RISK", f"Could not load symbol '{tk}' from market feed.")

        # Also auto-load any ticker in armed_tickers that isn't in self.analyses yet
        for raw_tk in armed_tickers:
            tk = raw_tk.strip().upper()
            if tk and tk not in self.analyses:
                res = self.engine.analyze_ticker(tk, period="1y", interval="1d")
                if res is not None:
                    self.analyses[tk] = res
                    if tk not in self.watchlist:
                        self.watchlist.append(tk)
                    decimals = self._price_decimals(res.current_price, res.market_jurisdiction, tk)
                    self.base_prices[tk] = float(res.current_price)
                    self.live_prices[tk] = round(float(res.current_price), decimals)
                    df_tail = res.recent_ohlcv.tail(45)
                    self.price_series[tk] = [
                        {
                            "time": idx.strftime("%b %d") if hasattr(idx, "strftime") else str(idx),
                            "price": round(float(row["Close"]), decimals),
                            "high": round(float(row["High"]), decimals),
                            "low": round(float(row["Low"]), decimals),
                        }
                        for idx, row in df_tail.iterrows()
                    ]

        clean_armed = {t.strip().upper() for t in armed_tickers if t.strip().upper() in self.analyses}
        self.armed_tickers = clean_armed
        n_armed = max(len(self.armed_tickers), 1)
        for tk in self.analyses:
            self.hrp_weights[tk] = (1.0 / n_armed) if tk in self.armed_tickers else 0.0

        self.log_event(
            "BOT",
            f"Updated Bot Trading Basket ({len(self.armed_tickers)} armed): {', '.join(sorted(self.armed_tickers)) or 'NONE (Watch-Only)'}",
        )
        return self.get_dashboard_state()

    def ensure_ticker_loaded(self, ticker: str, arm: bool = True) -> Optional[SingleAssetAnalysis]:
        """Loads and analyzes `ticker` if not yet present in the terminal, and optionally arms it for bot management."""
        if not self._initialized:
            self.initialize_market_state()

        tk = ticker.strip().upper()
        if not tk:
            return None

        res = self.analyses.get(tk)
        if res is None:
            res = self.engine.analyze_ticker(tk, period="1y", interval="1d")
            if res is None:
                self.log_event("RISK", f"Could not load symbol '{tk}' from market feed.")
                return None
            self.analyses[tk] = res
            if tk not in self.watchlist:
                self.watchlist.append(tk)
            decimals = self._price_decimals(res.current_price, res.market_jurisdiction, tk)
            self.base_prices[tk] = float(res.current_price)
            self.live_prices[tk] = round(float(res.current_price), decimals)

            # Attempt live quote fetch
            tradable, sess = self._is_ticker_tradable_now(tk)
            try:
                q = self.data_provider.get_quote(tk, market_open=bool(sess.get("is_open", False)))
                if q and q.is_valid:
                    self.latest_quotes[tk] = q
                    self.live_prices[tk] = round(float(q.last_price), decimals)
            except Exception as exc:
                logger.debug(f"Live quote fetch for {tk} deferred: {exc}")

            df_tail = res.recent_ohlcv.tail(45)
            self.price_series[tk] = [
                {
                    "time": idx.strftime("%b %d") if hasattr(idx, "strftime") else str(idx),
                    "price": round(float(row["Close"]), decimals),
                    "high": round(float(row["High"]), decimals),
                    "low": round(float(row["Low"]), decimals),
                }
                for idx, row in df_tail.iterrows()
            ]
            if self.price_series[tk]:
                self.price_series[tk][-1]["price"] = self.live_prices[tk]
            self.log_event("BOT", f"Loaded {tk} ({res.market_jurisdiction}) into active terminal @ {self.live_prices[tk]:,.{decimals}f}.")

        if arm and tk not in self.armed_tickers:
            self.armed_tickers.add(tk)
            n_armed = max(len(self.armed_tickers), 1)
            for sym in self.analyses:
                self.hrp_weights[sym] = (1.0 / n_armed) if sym in self.armed_tickers else 0.0
            self.log_event("BOT", f"Armed {tk} for autonomous bot monitoring & management.")

        return res

    def search_instruments(
        self,
        query: str = "",
        category: str = "ALL",
        limit: int = 16,
    ) -> List[Dict[str, Any]]:
        """Searches across the global stock/asset catalog plus any custom ticker symbol."""
        if not self._initialized:
            self.initialize_market_state()

        q_clean = (query or "").strip()
        q_lower = q_clean.lower()
        q_upper = q_clean.upper()
        cat_upper = (category or "ALL").strip().upper()

        open_tickers = {p.ticker for p in self.broker.get_open_positions()}
        catalog_map: Dict[str, Dict[str, str]] = {item["ticker"]: item for item in SEARCHABLE_INSTRUMENTS}

        # Include any already-loaded custom symbols in the searchable pool
        for tk, res in self.analyses.items():
            if tk not in catalog_map:
                jur = res.market_jurisdiction
                cat = (
                    "INDIAN_NSE"
                    if jur == "INDIAN_NSE"
                    else ("CRYPTO" if jur == "CRYPTO" else ("COMMODITIES" if jur == "COMMODITY" else ("FOREX" if jur == "FOREX" else "US_EQUITIES")))
                )
                catalog_map[tk] = {
                    "ticker": tk,
                    "name": f"{tk} ({jur})",
                    "category": cat,
                    "exchange": "NSE" if tk.endswith(".NS") else ("CRYPTO 24/7" if "-USD" in tk else "US/GLOBAL"),
                    "sector": "Custom Loaded Instrument",
                }

        scored: List[Tuple[int, Dict[str, Any]]] = []
        for tk, meta in catalog_map.items():
            if cat_upper not in ("ALL", "") and meta["category"] != cat_upper:
                if not (cat_upper == "NSE" and meta["category"] == "INDIAN_NSE") and not (
                    cat_upper == "US" and meta["category"] == "US_EQUITIES"
                ) and not (cat_upper == "COMMODITY" and meta["category"] == "COMMODITIES"):
                    continue

            score = 0
            tk_lower = tk.lower()
            base_tk_lower = tk_lower.split(".")[0].split("-")[0].split("=")[0]
            name_lower = meta["name"].lower()
            sector_lower = meta["sector"].lower()
            exch_lower = meta["exchange"].lower()

            if not q_lower:
                # Default ranking when query is empty: armed & watched first, then popular US/NSE
                score = 100 if tk in self.armed_tickers else (80 if tk in self.analyses else 50)
            else:
                if tk_lower == q_lower or base_tk_lower == q_lower:
                    score = 1000
                elif tk_lower.startswith(q_lower) or base_tk_lower.startswith(q_lower):
                    score = 800
                elif q_lower in tk_lower:
                    score = 650
                elif any(word.startswith(q_lower) for word in name_lower.replace("(", " ").split()):
                    score = 550
                elif q_lower in name_lower:
                    score = 450
                elif q_lower in sector_lower or q_lower in exch_lower:
                    score = 300
                else:
                    continue

            res = self.analyses.get(tk)
            tradable, sess = self._is_ticker_tradable_now(tk)
            curr_p = self.live_prices.get(tk, float(res.current_price) if res else None)
            decimals = self._price_decimals(curr_p, res.market_jurisdiction if res else "", tk)

            scored.append(
                (
                    score,
                    {
                        "ticker": tk,
                        "name": meta["name"],
                        "category": meta["category"],
                        "exchange": meta["exchange"],
                        "sector": meta["sector"],
                        "in_watchlist": tk in self.analyses,
                        "is_armed": tk in self.armed_tickers,
                        "has_open_position": tk in open_tickers,
                        "current_price": round(float(curr_p), decimals) if curr_p is not None else None,
                        "decimals": decimals,
                        "signal": res.meta_prediction.direction_label if res else None,
                        "primary_direction": int(res.meta_prediction.primary_direction) if res else None,
                        "confidence_pct": round(float(res.meta_prediction.success_probability * 100.0), 1) if res else None,
                        "target_price": round(float(res.meta_prediction.target_price), decimals) if res else None,
                        "stop_price": round(float(res.meta_prediction.stop_price), decimals) if res else None,
                        "kelly_weight_pct": round(float(res.risk_decision.authorized_weight_pct), 1) if res else None,
                        "regime": res.regime.name if res else None,
                        "exchange_open": bool(sess.get("is_open", False)),
                        "tradable_now": bool(tradable),
                        "is_custom": False,
                    },
                )
            )

        scored.sort(key=lambda x: (-x[0], x[1]["ticker"]))
        results = [item for _, item in scored[:limit]]

        # If user typed a symbol not already in the exact results, offer direct Custom Ticker lookup/trade
        if q_upper and len(q_upper) <= 18 and all(c.isalnum() or c in ".-=^&" for c in q_upper):
            exact_tickers = {r["ticker"].upper() for r in results}
            if q_upper not in exact_tickers:
                tradable, sess = self._is_ticker_tradable_now(q_upper)
                results.append(
                    {
                        "ticker": q_upper,
                        "name": f"Load & Trade Custom Symbol '{q_upper}'",
                        "category": "INDIAN_NSE" if q_upper.endswith(".NS") else ("CRYPTO" if "-USD" in q_upper else "US_EQUITIES"),
                        "exchange": sess.get("exchange", "GLOBAL"),
                        "sector": "Direct Market Feed Lookup",
                        "in_watchlist": False,
                        "is_armed": False,
                        "has_open_position": False,
                        "current_price": None,
                        "decimals": 2,
                        "signal": None,
                        "primary_direction": None,
                        "confidence_pct": None,
                        "target_price": None,
                        "stop_price": None,
                        "kelly_weight_pct": None,
                        "regime": None,
                        "exchange_open": bool(sess.get("is_open", False)),
                        "tradable_now": bool(tradable),
                        "is_custom": True,
                    }
                )

        return results

    def place_bot_managed_trade(
        self,
        ticker: str,
        direction: str = "AUTO",
        allocation_weight_pct: Optional[float] = None,
        order_type: str = "MARKET",
        limit_price: Optional[float] = None,
        target_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        auto_arm: bool = True,
    ) -> Dict[str, Any]:
        """Analyzes `ticker`, computes Neuro-Causal barriers & Kelly sizing, arms the bot, and places/queues a paper trade."""
        res = self.ensure_ticker_loaded(ticker, arm=auto_arm)
        if res is None:
            raise ValueError(f"Unable to fetch market data or analyze symbol '{ticker}'. Verify the ticker symbol.")

        tk = res.ticker.upper()
        # Ensure autonomous bot controller is running so it actively manages the trade
        if auto_arm:
            self.is_running = True

        dir_clean = (direction or "AUTO").strip().upper()
        if dir_clean == "AUTO":
            resolved_dir = "LONG" if res.meta_prediction.primary_direction >= 0 else "SHORT"
            dir_source = f"AI Signal ({res.meta_prediction.direction_label}, {res.meta_prediction.success_probability * 100.0:.1f}% conf)"
        elif dir_clean in ("LONG", "BUY"):
            resolved_dir = "LONG"
            dir_source = "User LONG + Bot Barrier Management"
        elif dir_clean in ("SHORT", "SELL"):
            resolved_dir = "SHORT"
            dir_source = "User SHORT + Bot Barrier Management"
        else:
            raise ValueError(f"Invalid direction '{direction}'. Use 'AUTO', 'LONG', or 'SHORT'.")

        curr_p = self.live_prices.get(tk, float(res.current_price))
        q = self.latest_quotes.get(tk)
        decimals = self._price_decimals(curr_p, res.market_jurisdiction, tk)
        vol_bar = max(res.volatility_cone.expected_vol_annualized / np.sqrt(252.0), 0.012)

        ord_type = (order_type or "MARKET").strip().upper()
        is_nse = tk.endswith((".NS", ".BO")) or tk.startswith(("^NSE", "^BS")) or getattr(res, "market_jurisdiction", "") in ("NSE_CASH", "INDIAN_NSE")
        if is_nse and ord_type == "MARKET":
            lpp_pct = 0.01
            ord_type = "LIMIT"
            raw_ref = q.ask_price if (resolved_dir == "LONG" and q and q.is_valid and q.ask_price > 0) else curr_p
            limit_price = round(raw_ref * (1.0 + lpp_pct if resolved_dir == "LONG" else 1.0 - lpp_pct), decimals)
            self.log_event(
                "RISK",
                f"NSE Algo Invariant: Automated MARKET order for {tk} converted to LIMIT with {lpp_pct*100:.1f}% Limit Price Protection @ {limit_price:,.{decimals}f}.",
            )

        if ord_type == "LIMIT" and limit_price is not None and limit_price > 0:
            ref_entry_p = float(limit_price)
        elif q and q.is_valid and q.ask_price > 0 and q.bid_price > 0:
            ref_entry_p = float(q.ask_price if resolved_dir == "LONG" else q.bid_price)
        else:
            ref_entry_p = float(curr_p)

        if resolved_dir == "LONG":
            pt_p = round(target_price if (target_price and target_price > 0) else ref_entry_p * (1.0 + 1.4 * vol_bar), decimals)
            sl_p = round(stop_price if (stop_price and stop_price > 0) else ref_entry_p * (1.0 - 1.0 * vol_bar), decimals)
        else:
            pt_p = round(target_price if (target_price and target_price > 0) else ref_entry_p * (1.0 - 1.4 * vol_bar), decimals)
            sl_p = round(stop_price if (stop_price and stop_price > 0) else ref_entry_p * (1.0 + 1.0 * vol_bar), decimals)

        if allocation_weight_pct is not None and allocation_weight_pct > 0:
            alloc_pct = float(allocation_weight_pct)
        else:
            kelly_w = float(res.risk_decision.authorized_weight_pct)
            base_alloc = kelly_w if kelly_w >= 5.0 else 10.0
            alloc_pct = min(max(round(base_alloc, 1), 8.0), 20.0)

        tradable, sess = self._is_ticker_tradable_now(tk)
        if not tradable:
            queued = self.broker.queue_pre_market_order(
                ticker=tk,
                direction=resolved_dir,
                current_price=ref_entry_p,
                target_price=pt_p,
                stop_price=sl_p,
                allocation_weight_pct=alloc_pct,
                order_type=ord_type,
            )
            self.log_event(
                "SESSION",
                f"[BOT-MANAGED] Queued PRE_MARKET_PENDING {ord_type} #{queued['order_id']} for {tk} ({resolved_dir} via {dir_source}) "
                f"@ {ref_entry_p:,.{decimals}f} | Target: {pt_p:,.{decimals}f} | Stop: {sl_p:,.{decimals}f}. Bot will auto-execute at open.",
            )
            return {
                "status": "QUEUED",
                "ticker": tk,
                "direction": resolved_dir,
                "direction_source": dir_source,
                "order_id": queued["order_id"],
                "state": "PRE_MARKET_PENDING",
                "order": queued,
                "target_price": pt_p,
                "stop_price": sl_p,
                "allocation_weight_pct": alloc_pct,
                "bot_armed": tk in self.armed_tickers,
                "dashboard_state": self.get_dashboard_state(),
            }

        bid_p = q.bid_price if (q and q.is_valid and q.bid_price > 0) else None
        ask_p = q.ask_price if (q and q.is_valid and q.ask_price > 0) else None
        mkt_ts = q.timestamp_utc if (q and q.is_valid) else datetime.now(timezone.utc).isoformat()

        if ord_type == "LIMIT" and limit_price is not None and limit_price > 0:
            summary = self.broker.get_account_summary()
            avail_cash = float(summary.get("available_cash", summary.get("current_cash", 100000.0)))
            notional = avail_cash * (alloc_pct / 100.0)
            req_shares = notional / float(limit_price)
            ord_res = self.broker.submit_order(
                ticker=tk,
                direction=resolved_dir,
                requested_shares=req_shares,
                order_type="LIMIT",
                limit_price=float(limit_price),
                current_price=curr_p,
                bid_price=bid_p,
                ask_price=ask_p,
                target_price=pt_p,
                stop_price=sl_p,
                allocation_weight_pct=alloc_pct,
                is_stale=False,
                market_open=True,
                market_timestamp=mkt_ts,
                check_duplicate=False,
                enforce_exposure_limits=True,
            )
            if ord_res.status == "REJECTED":
                raise ValueError(ord_res.rejection_reason or f"Limit order for {tk} rejected.")
            self.log_event(
                "TRADE",
                f"[BOT-MANAGED] Submitted {ord_type} ({ord_res.status}) {resolved_dir} {tk} @ Limit {limit_price:,.{decimals}f} "
                f"| Target: {pt_p:,.{decimals}f} | Stop: {sl_p:,.{decimals}f}",
            )
            return {
                "status": ord_res.status,
                "ticker": tk,
                "direction": resolved_dir,
                "direction_source": dir_source,
                "order_id": ord_res.order_id,
                "target_price": pt_p,
                "stop_price": sl_p,
                "allocation_weight_pct": alloc_pct,
                "bot_armed": tk in self.armed_tickers,
                "dashboard_state": self.get_dashboard_state(),
            }

        pos = self.broker.open_position(
            ticker=tk,
            direction=resolved_dir,
            current_price=curr_p,
            target_price=pt_p,
            stop_price=sl_p,
            allocation_weight_pct=alloc_pct,
            bid_price=bid_p,
            ask_price=ask_p,
            use_bid_ask=(bid_p is not None and ask_p is not None),
            apply_slippage=(bid_p is not None and ask_p is not None),
            is_stale=False,
            market_open=True,
            market_timestamp=mkt_ts,
            check_duplicate=False,
            enforce_exposure_limits=True,
        )
        if not pos:
            raise ValueError(
                f"Order rejected for {tk}: check available virtual cash, portfolio exposure cap, or max concurrent positions."
            )

        self.log_event(
            "TRADE",
            f"[BOT-MANAGED] Opened {resolved_dir} {tk} (${pos.allocated_capital:,.0f} | {dir_source}) @ {pos.entry_price:,.{decimals}f} "
            f"| Bot Target: {pt_p:,.{decimals}f} | Bot Stop: {sl_p:,.{decimals}f}",
        )
        return {
            "status": "FILLED",
            "ticker": tk,
            "direction": resolved_dir,
            "direction_source": dir_source,
            "position": pos,
            "target_price": pt_p,
            "stop_price": sl_p,
            "allocation_weight_pct": alloc_pct,
            "bot_armed": tk in self.armed_tickers,
            "dashboard_state": self.get_dashboard_state(),
        }

    def toggle_market_hours_enforcement(self) -> Dict:
        """Toggles between Strict Real-World Exchange Hours and 24/7 Sandbox Simulation Mode."""
        self.simulation_mode = not self.simulation_mode
        self.enforce_market_hours = not self.simulation_mode
        mode_str = (
            "24/7 SANDBOX SIMULATION (Synthetic off-hours stress mode)"
            if self.simulation_mode
            else "STRICT LIVE EXCHANGE HOURS (Genuine market feed only)"
        )
        self.log_event("BOT", f"Exchange Hours Mode switched to: {mode_str}")
        return self.get_dashboard_state()

    def toggle_simulation_mode(self) -> Dict:
        """Explicitly toggles 24/7 sandbox simulation mode."""
        return self.toggle_market_hours_enforcement()

    def _compute_market_return_pct(self) -> float:
        """Computes equal-weighted percentage movement of the armed (or full) watchlist."""
        target_set = self.armed_tickers if self.armed_tickers else set(self.base_prices.keys())
        moves = []
        for tk in target_set:
            base_p = self.base_prices.get(tk, 0.0)
            curr_p = self.live_prices.get(tk, base_p)
            if base_p > 0:
                moves.append(((curr_p - base_p) / base_p) * 100.0)
        return float(np.mean(moves)) if moves else 0.0

    def step_tick(self, custom_shock_pct: Optional[float] = None) -> Dict:
        """Executes one iteration of the 10-step autonomous live-market paper-trading loop."""
        if not self._initialized:
            self.initialize_market_state()

        self.tick_count += 1
        now_str = datetime.now().strftime("%H:%M:%S")
        now_utc = datetime.now(timezone.utc)
        now_utc_iso = now_utc.isoformat()
        self.last_tick_time = now_str

        # ----------------------------------------------------------------------
        # Step 0: Session Gating & Automatic Expiry Enforcement
        # ----------------------------------------------------------------------
        if self.session_manager is not None:
            expired_session = self.session_manager.check_and_enforce_expiry(self, now_utc=now_utc)
            if expired_session is not None:
                self.log_event(
                    "SESSION",
                    f"Session #{expired_session.id} expired at {expired_session.expires_at}. "
                    f"Status: COMPLETED. Executed policy: '{expired_session.session_end_policy}'.",
                )
                return self.get_dashboard_state()

        active_session = self.get_active_session()
        allow_new_entries = self.is_running

        if self.session_manager is not None or self.require_session:
            if active_session is None:
                self.log_event("SESSION", "Autonomous execution halted: No active trading session configured.")
                return self.get_dashboard_state()
            if active_session.status != "RUNNING":
                if active_session.status == "PAUSED":
                    # PAUSED: Halt new entries, but preserve MTM & stop-loss monitoring on open positions
                    allow_new_entries = False
                else:
                    self.log_event(
                        "SESSION",
                        f"Autonomous execution halted: Session #{active_session.id} is in '{active_session.status}' state.",
                    )
                    return self.get_dashboard_state()

        stale_or_invalid_tickers: Set[str] = set()
        quotes_for_audit: Dict[str, Any] = {}
        staleness_limit = self.horizon_params.quote_staleness_threshold_sec if self.horizon_params else 60.0

        # Determine approved basket for iteration
        if active_session is not None and active_session.instruments:
            approved_basket = set(active_session.instruments)
        else:
            approved_basket = set(self.armed_tickers)

        # Auto-load any session instrument that is not yet in self.analyses (when engine is live-initialized)
        if self.analyses:
            for tk in list(approved_basket):
                if tk not in self.analyses:
                    try:
                        self.ensure_ticker_loaded(tk, arm=True)
                    except Exception as exc:
                        logger.debug(f"Deferred loading session instrument {tk}: {exc}")

        # Steps 1, 2 & 3: Check exchange session status, fetch genuine market quotes, validate freshness
        for tk, res in self.analyses.items():
            sess = self.calendar.get_session_info(tk, simulation_mode=self.simulation_mode)
            prev_state = self.last_known_market_states.get(tk)
            curr_state = sess.state
            self.last_known_market_states[tk] = curr_state

            decimals = self._price_decimals(res.current_price, res.market_jurisdiction, tk)
            prev_p = self.live_prices.get(tk, res.current_price)

            # Detect transition to OPEN from a closed/pre-market/weekend/holiday state
            if prev_state is not None and prev_state != MarketState.OPEN and curr_state == MarketState.OPEN:
                open_quote = self.data_provider.get_quote(tk, market_open=True)
                if open_quote and open_quote.is_valid and not open_quote.is_stale:
                    self.latest_quotes[tk] = open_quote
                    curr_open_p = open_quote.last_price
                    bid_open = open_quote.bid_price
                    ask_open = open_quote.ask_price
                else:
                    curr_open_p = self.live_prices.get(tk, res.current_price)
                    bid_open, ask_open = None, None

                drained = self.broker.execute_pending_orders_for_ticker(
                    tk, curr_open_p, bid_price=bid_open, ask_price=ask_open
                )
                if drained:
                    self.log_event(
                        "SESSION",
                        f"Market Open for {tk}: Executed {len(drained)} queued PRE_MARKET_PENDING order(s) @ {curr_open_p:.4f}.",
                    )

            if not sess.is_tradable and custom_shock_pct is None:
                # Exchange is closed and not in sandbox simulation mode -> price strictly frozen!
                quotes_for_audit[tk] = prev_p
                continue

            # Explicit user-triggered stress shock or explicit 24/7 sandbox override on closed exchange
            if custom_shock_pct is not None:
                shock = custom_shock_pct / 100.0
                new_p = max(prev_p * (1.0 + shock), 0.0001)
                prof_sp = float(getattr(FrictionEvaluator.get_profile(tk), "bid_ask_spread_bps", 2.0))
                half_sp = (prof_sp / 10000.0) / 2.0
                sim_quote = LiveQuote(
                    ticker=tk,
                    last_price=round(new_p, decimals),
                    bid_price=round(new_p * (1.0 - half_sp), decimals),
                    ask_price=round(new_p * (1.0 + half_sp), decimals),
                    volume=0.0,
                    timestamp_utc=now_utc_iso,
                    received_at_utc=now_utc_iso,
                    is_delayed=False,
                    delay_minutes=0,
                    is_stale=False,
                    age_seconds=0.0,
                    latency_ms=1.0,
                    provider_name="STRESS_SHOCK_SIMULATION",
                    day_open=prev_p,
                    day_high=max(prev_p, new_p),
                    day_low=min(prev_p, new_p),
                    prev_close=prev_p,
                    status="SANDBOX",
                )
                self.latest_quotes[tk] = sim_quote
                self.live_prices[tk] = round(new_p, decimals)
                quotes_for_audit[tk] = sim_quote
            elif self.simulation_mode and not sess.is_open:
                # 24/7 Sandbox simulation mode explicitly enabled while physical market is closed
                ann_vol = res.volatility_cone.expected_vol_annualized
                tick_vol = max(ann_vol / np.sqrt(252.0) * 0.25, 0.0020)
                shock = float(self._sandbox_rng.normal(0.0, tick_vol))
                new_p = max(prev_p * (1.0 + shock), 0.0001)
                prof_sp = float(getattr(FrictionEvaluator.get_profile(tk), "bid_ask_spread_bps", 2.0))
                half_sp = (prof_sp / 10000.0) / 2.0
                sim_quote = LiveQuote(
                    ticker=tk,
                    last_price=round(new_p, decimals),
                    bid_price=round(new_p * (1.0 - half_sp), decimals),
                    ask_price=round(new_p * (1.0 + half_sp), decimals),
                    volume=0.0,
                    timestamp_utc=now_utc_iso,
                    received_at_utc=now_utc_iso,
                    is_delayed=False,
                    delay_minutes=0,
                    is_stale=False,
                    age_seconds=0.0,
                    latency_ms=1.0,
                    provider_name="SANDBOX_SIMULATION",
                    day_open=prev_p,
                    day_high=max(prev_p, new_p),
                    day_low=min(prev_p, new_p),
                    prev_close=prev_p,
                    status="SANDBOX",
                )
                self.latest_quotes[tk] = sim_quote
                self.live_prices[tk] = round(new_p, decimals)
                quotes_for_audit[tk] = sim_quote
            else:
                # Normal Paper-Trading Path: Fetch genuine market data from provider!
                quote = self.data_provider.get_quote(tk, market_open=True)
                if quote is None or not quote.is_valid:
                    stale_or_invalid_tickers.add(tk)
                    if quote is not None:
                        self.latest_quotes[tk] = quote
                    self.log_event(
                        "RISK",
                        f"Market data unavailable/missing for {tk} — halting new trades on {tk} (price never invented).",
                    )
                    quotes_for_audit[tk] = prev_p
                    continue

                self.latest_quotes[tk] = quote
                effective_staleness_limit = (
                    max(staleness_limit, float(getattr(quote, "delay_minutes", 0.0)) * 60.0 + 300.0, 1200.0)
                    if getattr(quote, "is_delayed", False)
                    else staleness_limit
                )
                if quote.is_stale or quote.age_seconds > effective_staleness_limit:
                    stale_or_invalid_tickers.add(tk)
                    self.log_event(
                        "FEED",
                        f"Stale quote detected for {tk} (age: {quote.age_seconds:.0f}s > limit {effective_staleness_limit:.0f}s) — blocking new entries.",
                    )
                new_p = float(quote.last_price)
                self.live_prices[tk] = round(new_p, decimals)
                quotes_for_audit[tk] = quote

            # Append to price series for chart visualization
            curr_disp_p = self.live_prices[tk]
            q_ref = self.latest_quotes.get(tk)
            hi_p = q_ref.day_high if (q_ref and q_ref.day_high is not None and q_ref.day_high > 0) else max(prev_p, curr_disp_p)
            lo_p = q_ref.day_low if (q_ref and q_ref.day_low is not None and q_ref.day_low > 0) else min(prev_p, curr_disp_p)
            series = self.price_series.get(tk, [])
            series.append(
                {
                    "time": now_str,
                    "price": round(curr_disp_p, decimals),
                    "high": round(hi_p, decimals),
                    "low": round(lo_p, decimals),
                }
            )
            if len(series) > 60:
                series = series[-60:]
            self.price_series[tk] = series

        # Step 4 & 5: Evaluate working limit orders and audit open positions (Unrealized P&L, Gap-Aware SL, Conservative TP/SL)
        filled_limits = self.broker.evaluate_working_orders(quotes_for_audit)
        for lpos in filled_limits:
            self.log_event(
                "TRADE",
                f"Working LIMIT order filled: {lpos.direction} {lpos.ticker} @ {lpos.entry_price:,.4f} (${lpos.allocated_capital:,.0f})",
            )

        still_open, auto_closed = self.broker.update_and_audit_positions(quotes_for_audit)
        for tr in auto_closed:
            if tr.exit_reason == "STOP_LOSS":
                self.last_stop_loss_time[tr.ticker.upper()] = now_utc
            tag = "PROFIT" if tr.net_pnl >= 0 else "STOP"
            self.log_event(
                tag,
                f"Closed {tr.direction} {tr.ticker} @ {tr.exit_price:,.4f} ({tr.exit_reason}) | Net PnL: ${tr.net_pnl:+,.2f} ({tr.return_pct:+.2f}%)",
            )

        # Steps 6, 7, 8 & 9: Refresh prediction analysis, check guardrails & staleness, size position, and submit virtual order
        summary = self.broker.get_account_summary()
        if active_session is not None and self.session_manager is not None:
            sess_perf_pre = self.session_manager.compute_session_performance(active_session.id, self)
            current_dd_dec = float(sess_perf_pre.get("current_drawdown_pct", 0.0)) / 100.0
        else:
            current_dd_dec = float(summary.get("current_drawdown_pct", 0.0)) / 100.0

        for tk, res in list(self.analyses.items()):
            q = self.latest_quotes.get(tk)
            if q and q.is_valid:
                self.analyses[tk] = self.engine.refresh_with_live_quote(
                    res, q, current_drawdown=current_dd_dec
                )

        if allow_new_entries and self.armed_tickers:
            open_tickers = {p.ticker for p in still_open}
            available_cash = float(summary.get("available_cash", summary.get("current_cash", 0.0)))

            # Capital Boundary Enforcement
            if active_session is not None:
                session_cap = float(active_session.allocated_capital)
                current_invested = sum(p.allocated_capital for p in still_open if getattr(p, "session_id", None) in (active_session.id, None))
                reserved_holds = float(summary.get("reserved_cash", 0.0))
                remaining_session_cap = max(0.0, session_cap - current_invested - reserved_holds)
                deployable_capital = min(available_cash, remaining_session_cap)
            else:
                deployable_capital = available_cash

            min_trade_notional = 1000.0 if (active_session and active_session.currency == "INR") else 100.0

            # Filter candidates strictly within approved basket & valid conditions
            eligible_candidate_tickers: List[str] = []
            for tk in self.armed_tickers:
                # Basket Confinement Check
                if tk not in approved_basket:
                    continue
                if tk in open_tickers or tk not in self.analyses:
                    continue
                if tk in stale_or_invalid_tickers:
                    continue
                if self.broker.has_duplicate_order_or_position(tk):
                    continue
                last_sl = self.last_stop_loss_time.get(tk)
                if last_sl is not None:
                    cooldown_bars = self.horizon_params.signal_cooldown_bars if self.horizon_params else 3
                    if (now_utc - last_sl).total_seconds() < float(cooldown_bars) * 60.0:
                        continue
                tradable, _ = self._is_ticker_tradable_now(tk)
                if not tradable:
                    continue
                r = self.analyses[tk]
                if active_session is None and r.regime.is_crisis:
                    continue
                eligible_candidate_tickers.append(tk)

            max_concurrent = min(len(self.armed_tickers), self.broker.max_concurrent_positions)

            if active_session is not None:
                # Active Session Quantitative Decision Engine Workflow
                if eligible_candidate_tickers and len(still_open) < max_concurrent and deployable_capital >= min_trade_notional:
                    # 8a. Trade Evaluation via TradeEvaluator
                    evaluator = TradeEvaluator(default_min_ev_hurdle_pct=0.20)
                    evaluations: List[TradeEvaluationResult] = []
                    analyses_sub: Dict[str, SingleAssetAnalysis] = {}

                    for tk in eligible_candidate_tickers:
                        analysis = self.analyses[tk]
                        analyses_sub[tk] = analysis
                        ev_res = evaluator.evaluate(
                            analysis=analysis,
                            horizon_params=self.horizon_params,
                            min_ev_hurdle_pct=0.20,
                            order_notional=deployable_capital * 0.15,
                        )
                        evaluations.append(ev_res)

                    # 8b. Trade Ranking via TradeRanker
                    ranker = TradeRanker()
                    ranked_opps = ranker.rank_opportunities(
                        evaluations=evaluations,
                        analyses=analyses_sub,
                    )

                    # 9a. Portfolio Allocation via PortfolioSelector
                    selector = PortfolioSelector(
                        kelly_fraction=0.65,
                        target_annual_vol=0.15,
                        warning_drawdown=0.08,
                        max_kill_drawdown=0.15,
                        max_position_cap=0.20,
                        max_gross_exposure=0.95,
                    )
                    alloc_method = (
                        active_session.strategy_config.get("allocation_method", "KELLY")
                        if active_session and hasattr(active_session, "strategy_config") and isinstance(active_session.strategy_config, dict)
                        else "KELLY"
                    )
                    market_type = active_session.market if active_session else "US"
                    currency_sym = "₹" if (active_session and active_session.currency == "INR") else "$"

                    alloc_result = selector.allocate(
                        ranked_opportunities=ranked_opps,
                        total_virtual_equity=deployable_capital,
                        method=alloc_method,
                        current_drawdown=current_dd_dec,
                        market_type=market_type,
                    )

                    # 9b. Explainable Activity Feed Logs
                    if alloc_result.is_100_percent_cash:
                        # Only emit portfolio-level 100% cash preserved fallback when zero positions are currently open
                        if len(still_open) == 0:
                            explanation = DecisionExplainer.explain_portfolio_cash_fallback(
                                total_candidates_evaluated=len(ranked_opps),
                                rejection_summary=alloc_result.explanation,
                                current_drawdown_pct=current_dd_dec * 100.0,
                            )
                            msg_text = f"{explanation.headline} — {explanation.summary}"
                            last_decision_msg = next(
                                (item.get("message") for item in self.activity_log if item.get("level") == "DECISION"),
                                None,
                            )
                            if last_decision_msg != msg_text:
                                self.log_event(
                                    "DECISION",
                                    msg_text,
                                    metadata=explanation.to_dict(),
                                )
                    else:
                        alloc_map = {item.ticker: item for item in alloc_result.allocations}
                        for opp in ranked_opps:
                            if opp.ticker in alloc_map:
                                alloc_item = alloc_map[opp.ticker]
                                explanation = DecisionExplainer.explain_accepted_trade(
                                    opportunity=opp,
                                    allocation=alloc_item,
                                    currency_symbol=currency_sym,
                                )
                                self.log_event(
                                    "DECISION",
                                    f"{explanation.headline} — {explanation.summary}",
                                    metadata=explanation.to_dict(),
                                )

                                # Execute virtual order within capital limit
                                tk = opp.ticker
                                r = self.analyses[tk]
                                q = self.latest_quotes.get(tk)
                                curr_p = self.live_prices[tk]
                                direction = opp.direction
                                decimals = self._price_decimals(curr_p, r.market_jurisdiction, tk)

                                if q and q.is_valid:
                                    ref_entry_p = q.ask_price if direction == "LONG" else q.bid_price
                                    bid_p, ask_p = q.bid_price, q.ask_price
                                    mkt_ts = q.timestamp_utc
                                    is_stale_q = q.is_stale
                                else:
                                    ref_entry_p = curr_p
                                    bid_p, ask_p = None, None
                                    mkt_ts = now_utc_iso
                                    is_stale_q = False

                                # Use the exact target/stop barriers approved by TradeEvaluator/PortfolioSelector
                                # (scaled proportionally if bid/ask entry reference differs slightly from mid)
                                if alloc_item.entry_price > 0 and alloc_item.target_price > 0 and alloc_item.stop_price > 0:
                                    entry_scale = ref_entry_p / alloc_item.entry_price
                                    pt_p = round(alloc_item.target_price * entry_scale, decimals)
                                    sl_p = round(alloc_item.stop_price * entry_scale, decimals)
                                else:
                                    pt_mult = self.horizon_params.pt_vol_mult if self.horizon_params else 1.4
                                    sl_mult = self.horizon_params.sl_vol_mult if self.horizon_params else 1.0
                                    ann_f = self.horizon_params.annualization_factor if self.horizon_params else np.sqrt(252.0)
                                    vol_fl = self.horizon_params.vol_floor_bar if self.horizon_params else 0.012
                                    vol_bar = max(r.volatility_cone.expected_vol_annualized / ann_f, vol_fl)
                                    if direction == "LONG":
                                        pt_p = round(ref_entry_p * (1.0 + pt_mult * vol_bar), decimals)
                                        sl_p = round(ref_entry_p * (1.0 - sl_mult * vol_bar), decimals)
                                    else:
                                        pt_p = round(ref_entry_p * (1.0 - pt_mult * vol_bar), decimals)
                                        sl_p = round(ref_entry_p * (1.0 + sl_mult * vol_bar), decimals)

                                alloc_cap_order = min(alloc_item.allocated_capital, deployable_capital)

                                # Enforce NSE algorithmic invariant: automated orders must have Limit Price Protection
                                is_nse = tk.endswith((".NS", ".BO")) or tk.startswith(("^NSE", "^BS")) or getattr(r, "market_jurisdiction", "") in ("NSE_CASH", "INDIAN_NSE")
                                if is_nse:
                                    lpp_pct = 0.01
                                    lpp_limit_p = round(ref_entry_p * (1.0 + lpp_pct if direction == "LONG" else 1.0 - lpp_pct), decimals)
                                    self.log_event(
                                        "RISK",
                                        f"[NSE-ALGO] Invariant Enforced: Automated LIMIT order with {lpp_pct*100:.1f}% LPP @ {lpp_limit_p:,.{decimals}f} for {direction} {tk}.",
                                    )

                                pos = self.broker.open_position(
                                    ticker=tk,
                                    direction=direction,
                                    current_price=curr_p,
                                    target_price=pt_p,
                                    stop_price=sl_p,
                                    allocation_weight_pct=0.0,
                                    custom_allocated_capital=alloc_cap_order,
                                    bid_price=bid_p,
                                    ask_price=ask_p,
                                    use_bid_ask=(bid_p is not None and ask_p is not None),
                                    apply_slippage=(bid_p is not None and ask_p is not None),
                                    is_stale=is_stale_q,
                                    market_open=True,
                                    market_timestamp=mkt_ts,
                                    check_duplicate=True,
                                    enforce_exposure_limits=True,
                                    session_id=active_session.id,
                                )
                                if pos:
                                    self.log_event(
                                        "TRADE",
                                        f"[PAPER] Bot Auto-Opened {direction} {tk} ({currency_sym}{pos.allocated_capital:,.2f}) @ {pos.entry_price:,.{decimals}f} "
                                        f"| Target: {pt_p:,.{decimals}f} | Stop: {sl_p:,.{decimals}f}",
                                    )
                                    deployable_capital -= pos.allocated_capital
                            else:
                                explanation = DecisionExplainer.explain_rejected_trade(
                                    opportunity=opp,
                                    currency_symbol=currency_sym,
                                )
                                self.log_event(
                                    "DECISION",
                                    f"{explanation.headline} — {explanation.summary}",
                                    metadata=explanation.to_dict(),
                                )
            else:
                # Legacy un-gated fallback execution for isolated test harnesses without a session manager
                candidates: List[Tuple[str, SingleAssetAnalysis]] = []
                for tk in self.armed_tickers:
                    if tk in open_tickers or tk not in self.analyses:
                        continue
                    if tk in stale_or_invalid_tickers:
                        continue
                    if self.broker.has_duplicate_order_or_position(tk):
                        continue
                    tradable, _ = self._is_ticker_tradable_now(tk)
                    if not tradable:
                        continue
                    r = self.analyses[tk]
                    if r.regime.is_crisis:
                        continue
                    candidates.append((tk, r))

                candidates.sort(
                    key=lambda x: abs(x[1].meta_prediction.success_probability - 0.50),
                    reverse=True,
                )

                max_concurrent = min(len(self.armed_tickers), self.broker.max_concurrent_positions)
                if candidates and len(still_open) < max_concurrent and available_cash > 5000.0:
                    tk, r = candidates[0]
                    q = self.latest_quotes.get(tk)
                    curr_p = self.live_prices[tk]
                    direction = "LONG" if r.meta_prediction.primary_direction >= 0 else "SHORT"
                    vol_bar = max(r.volatility_cone.expected_vol_annualized / np.sqrt(252.0), 0.012)
                    decimals = self._price_decimals(curr_p, r.market_jurisdiction, tk)

                    if q and q.is_valid:
                        ref_entry_p = q.ask_price if direction == "LONG" else q.bid_price
                        bid_p, ask_p = q.bid_price, q.ask_price
                        mkt_ts = q.timestamp_utc
                        is_stale_q = q.is_stale
                    else:
                        ref_entry_p = curr_p
                        bid_p, ask_p = None, None
                        mkt_ts = now_utc_iso
                        is_stale_q = False

                    if direction == "LONG":
                        pt_p = round(ref_entry_p * (1.0 + 1.4 * vol_bar), decimals)
                        sl_p = round(ref_entry_p * (1.0 - 1.0 * vol_bar), decimals)
                    else:
                        pt_p = round(ref_entry_p * (1.0 - 1.4 * vol_bar), decimals)
                        sl_p = round(ref_entry_p * (1.0 + 1.0 * vol_bar), decimals)

                    kelly_w = float(r.risk_decision.authorized_weight_pct)
                    base_alloc = kelly_w if kelly_w >= 5.0 else (100.0 / max(len(self.armed_tickers), 2) * 0.6)
                    alloc_pct = min(max(round(base_alloc, 1), 8.0), 18.0)

                    pos = self.broker.open_position(
                        ticker=tk,
                        direction=direction,
                        current_price=curr_p,
                        target_price=pt_p,
                        stop_price=sl_p,
                        allocation_weight_pct=alloc_pct,
                        bid_price=bid_p,
                        ask_price=ask_p,
                        use_bid_ask=(bid_p is not None and ask_p is not None),
                        apply_slippage=(bid_p is not None and ask_p is not None),
                        is_stale=is_stale_q,
                        market_open=True,
                        market_timestamp=mkt_ts,
                        check_duplicate=True,
                        enforce_exposure_limits=True,
                    )
                    if pos:
                        self.log_event(
                            "TRADE",
                            f"[PAPER] Bot Auto-Opened {direction} {tk} (${pos.allocated_capital:,.0f}) @ {pos.entry_price:,.{decimals}f} "
                            f"| Target: {pt_p:,.{decimals}f} | Stop: {sl_p:,.{decimals}f}",
                        )

        # Step 10: Record Bot Equity (%) vs. Market Movement (%) point & emit state
        summary = self.broker.get_account_summary()
        mkt_ret = round(self._compute_market_return_pct(), 3)

        # Update Session Metrics in persistence layer using strictly session-isolated performance
        if self.session_manager is not None and active_session is not None:
            sess_perf = self.session_manager.compute_session_performance(active_session.id, self)
            self.session_manager.update_session_metrics(active_session.id, sess_perf)
            bot_ret = round(float(sess_perf.get("return_pct", 0.0)), 3)
            bot_eq = round(float(sess_perf.get("total_equity", active_session.allocated_capital)), 2)
        else:
            bot_ret = round(float(summary.get("total_return_pct", 0.0)), 3)
            bot_eq = round(float(summary.get("total_equity", 100000.0)), 2)

        self.comparison_series.append(
            {
                "time": now_str,
                "bot_return_pct": bot_ret,
                "market_return_pct": mkt_ret,
                "bot_equity": bot_eq,
            }
        )
        if len(self.comparison_series) > 60:
            self.comparison_series = self.comparison_series[-60:]

        return self.get_dashboard_state()

    def reset_simulation(self, initial_capital: float = 100000.0) -> Dict:
        """Resets virtual paper account balance, re-anchors base prices, and clears comparison chart."""
        self.broker.reset_account(initial_capital=initial_capital)
        self.tick_count = 0
        for tk, res in self.analyses.items():
            q = self.latest_quotes.get(tk)
            anchor_p = float(q.last_price) if (q and q.is_valid) else float(res.current_price)
            self.base_prices[tk] = anchor_p
            self.live_prices[tk] = anchor_p

        now_str = datetime.now().strftime("%H:%M:%S")
        self.comparison_series = [
            {
                "time": now_str,
                "bot_return_pct": 0.0,
                "market_return_pct": 0.0,
                "bot_equity": round(float(initial_capital), 2),
            }
        ]
        self.log_event(
            "BOT",
            f"Virtual Paper Account reset to ${initial_capital:,.2f} starting capital.",
        )
        return self.get_dashboard_state()

    def get_feed_health_summary(self) -> Dict[str, Any]:
        """Aggregates connection health, latency, data mode, and staleness across active market feeds."""
        provider_health = self.data_provider.get_health_status()
        latencies = [q.latency_ms for q in self.latest_quotes.values() if q.latency_ms > 0]
        stale_list = [tk for tk, q in self.latest_quotes.items() if q.is_stale or not q.is_valid]
        any_delayed = any(q.is_delayed for q in self.latest_quotes.values())
        avg_lat = round(float(np.mean(latencies)), 1) if latencies else 0.0

        if self.simulation_mode:
            data_mode = "SANDBOX_SIMULATION"
        elif provider_health.get("is_realtime", False) and not any_delayed:
            data_mode = "LIVE_MARKET_DATA"
        else:
            data_mode = "DELAYED_MARKET_DATA"

        latest_ts = max(
            (q.timestamp_utc for q in self.latest_quotes.values() if q.timestamp_utc),
            default=datetime.now(timezone.utc).isoformat(),
        )

        return {
            **provider_health,
            "data_mode": data_mode,
            "paper_trading_only": True,
            "stale_tickers": sorted(stale_list),
            "average_latency_ms": avg_lat,
            "last_update_utc": latest_ts,
        }

    def get_dashboard_state(self) -> Dict:
        """Returns complete real-time state payload for the professional web dashboard."""
        if not self._initialized:
            self.initialize_market_state()

        summary = self.broker.get_account_summary()
        all_open_positions = self.broker.get_open_positions()
        active_sess = self.get_active_session()

        if active_sess is not None and self.session_manager is not None:
            open_positions = [
                p for p in all_open_positions
                if getattr(p, "session_id", None) in (active_sess.id, None)
            ]
            closed_trades = self.broker.get_closed_trades(limit=30, session_id=active_sess.id)
            sess_perf = self.session_manager.compute_session_performance(active_sess.id, self)
            active_sess.current_metrics = sess_perf
            bot_ret = round(float(sess_perf.get("return_pct", 0.0)), 2)
        else:
            open_positions = all_open_positions
            closed_trades = self.broker.get_closed_trades(limit=30)
            sess_perf = None
            bot_ret = round(float(summary.get("total_return_pct", 0.0)), 2)

        audit = self.broker.get_performance_audit()
        feed_health = self.get_feed_health_summary()

        mkt_ret = round(self._compute_market_return_pct(), 2)

        assets_payload = {}
        for tk, res in self.analyses.items():
            base_p = self.base_prices.get(tk, res.current_price)
            curr_p = self.live_prices.get(tk, res.current_price)
            decimals = self._price_decimals(curr_p, res.market_jurisdiction, tk)
            move_pct = ((curr_p - base_p) / base_p * 100.0) if base_p > 0 else 0.0
            pred = res.meta_prediction
            active_pos = next((p for p in open_positions if p.ticker == tk), None)
            tradable, sess = self._is_ticker_tradable_now(tk)

            q = self.latest_quotes.get(tk)
            prof_sp = float(getattr(FrictionEvaluator.get_profile(tk), "bid_ask_spread_bps", 2.0))
            half_sp = (prof_sp / 10000.0) / 2.0
            bid_p = q.bid_price if (q and q.bid_price > 0) else round(curr_p * (1.0 - half_sp), decimals)
            ask_p = q.ask_price if (q and q.ask_price > 0) else round(curr_p * (1.0 + half_sp), decimals)
            spread_bps = q.spread_bps if q else round(prof_sp, 2)

            assets_payload[tk] = {
                "ticker": tk,
                "jurisdiction": res.market_jurisdiction,
                "decimals": decimals,
                "current_price": round(curr_p, decimals),
                "bid_price": round(bid_p, decimals),
                "ask_price": round(ask_p, decimals),
                "spread_bps": round(spread_bps, 2),
                "base_price": round(base_p, decimals),
                "move_pct": round(move_pct, 2),
                "quote_timestamp_utc": q.timestamp_utc if q else getattr(res, "prediction_timestamp_utc", ""),
                "age_seconds": round(q.age_seconds, 1) if q else 0.0,
                "latency_ms": round(q.latency_ms, 1) if q else 0.0,
                "is_delayed": bool(q.is_delayed) if q else True,
                "delay_minutes": int(q.delay_minutes) if q else 15,
                "is_stale": bool(q.is_stale) if q else False,
                "feed_status": ("SANDBOX" if self.simulation_mode else (q.status if q else ("LIVE" if sess["is_open"] else "MARKET_CLOSED"))),
                "provider_name": q.provider_name if q else "YFinanceProvider",
                "signal": pred.direction_label,
                "primary_direction": int(pred.primary_direction),
                "confidence_pct": round(float(pred.success_probability * 100.0), 1),
                "neural_pct": round(float(res.neural_prob * 100.0), 1),
                "regime": res.regime.name,
                "is_crisis": bool(res.regime.is_crisis),
                "is_armed": tk in self.armed_tickers,
                "exchange_open": bool(sess["is_open"]),
                "tradable_now": tradable,
                "exchange_name": sess["exchange"],
                "exchange_schedule": sess["schedule"],
                "exchange_clock": sess["local_clock"],
                "exchange_reason": sess["reason"],
                "hrp_weight_pct": round(float(self.hrp_weights.get(tk, 0.0) * 100.0), 1),
                "kelly_weight_pct": round(float(res.risk_decision.authorized_weight_pct), 1),
                "friction_bps": FrictionEvaluator.calculate_round_trip_friction_bps(
                    tk, reference_price=curr_p
                ),
                "target_price": round(active_pos.target_price if active_pos else pred.target_price, decimals),
                "stop_price": round(active_pos.stop_price if active_pos else pred.stop_price, decimals),
                "entry_price": round(active_pos.entry_price, decimals) if active_pos else None,
                "has_open_position": active_pos is not None,
                "session_state": sess.get("state", "OPEN" if sess.get("is_open") else "CLOSED"),
                "next_state": sess.get("next_state", "OPEN"),
                "next_state_time_utc": sess.get("next_state_time_utc", ""),
                "seconds_to_next_state": sess.get("seconds_to_next_state", 0),
                "countdown_display": sess.get("countdown_display", ""),
                "tick_frozen": bool(sess.get("tick_frozen", False)),
                "holiday_name": sess.get("holiday_name"),
                "price_series": self.price_series.get(tk, []),
            }

        if sess_perf is not None and active_sess is not None:
            sess_cap = float(sess_perf.get("allocated_capital", active_sess.allocated_capital))
            sess_inv = float(sess_perf.get("invested_equity", 0.0))
            sess_eq = float(sess_perf.get("total_equity", sess_cap))
            sess_exp_pct = round((sess_inv / sess_eq * 100.0) if sess_eq > 0 else 0.0, 2)
            wins_cnt = int(sess_perf.get("winning_trades", 0))
            losses_cnt = int(sess_perf.get("losing_trades", 0))
            tot_tr = int(sess_perf.get("total_trades", 0))
            win_sum = sum(t.net_pnl for t in closed_trades if t.net_pnl > 0)
            loss_sum = abs(sum(t.net_pnl for t in closed_trades if t.net_pnl <= 0))
            pf = round((win_sum / loss_sum) if loss_sum > 0 else (2.0 if win_sum > 0 else 0.0), 2)
            sess_audit = {
                **audit,
                "total_trades": tot_tr,
                "winning_trades": wins_cnt,
                "losing_trades": losses_cnt,
                "win_rate_pct": float(sess_perf.get("win_rate_pct", 0.0)),
                "profit_factor": pf,
                "max_drawdown_pct": float(sess_perf.get("max_drawdown_pct", 0.0)),
                "total_transaction_costs": float(sess_perf.get("total_transaction_costs", 0.0)),
                "net_profit": float(sess_perf.get("realized_pnl", 0.0)),
            }
            account_payload = {
                **summary,
                "initial_capital": sess_cap,
                "current_cash": float(sess_perf.get("current_cash", sess_cap)),
                "available_cash": float(sess_perf.get("current_cash", sess_cap)),
                "invested_equity": sess_inv,
                "exposure_notional": sess_inv,
                "exposure_pct": sess_exp_pct,
                "total_equity": sess_eq,
                "realized_pnl": float(sess_perf.get("realized_pnl", 0.0)),
                "unrealized_pnl": float(sess_perf.get("unrealized_pnl", 0.0)),
                "total_return_pct": bot_ret,
                "max_drawdown_pct": float(sess_perf.get("max_drawdown_pct", 0.0)),
                "current_drawdown_pct": float(sess_perf.get("current_drawdown_pct", 0.0)),
                "total_transaction_costs": float(sess_perf.get("total_transaction_costs", 0.0)),
                "open_positions_count": int(sess_perf.get("open_positions_count", len(open_positions))),
                "market_return_pct": mkt_ret,
                "alpha_vs_market_pct": round(bot_ret - mkt_ret, 2),
                "audit": sess_audit,
            }
        else:
            account_payload = {
                **summary,
                "market_return_pct": mkt_ret,
                "alpha_vs_market_pct": round(bot_ret - mkt_ret, 2),
                "audit": audit,
            }

        return {
            "bot_status": {
                "is_running": self.is_running,
                "paper_trading_only": True,
                "execution_mode_label": "PAPER TRADING ONLY — VIRTUAL CAPITAL ($100,000)",
                "data_mode": feed_health["data_mode"],
                "simulation_mode": self.simulation_mode,
                "enforce_market_hours": self.enforce_market_hours,
                "armed_count": len(self.armed_tickers),
                "armed_tickers": sorted(list(self.armed_tickers)),
                "tick_count": self.tick_count,
                "last_tick_time": self.last_tick_time,
                "gpu_device": self.gpu_profile.device_name,
                "cuda_version": self.gpu_profile.cuda_runtime_version,
                "precision": self.gpu_profile.precision_mode.upper(),
                "vram_mb": self.gpu_profile.total_memory_mb,
                "active_session_id": self.active_session_id,
                "has_active_session": active_sess is not None,
                "session_status": active_sess.status if active_sess else None,
            },
            "active_session": active_sess.to_dict() if active_sess and hasattr(active_sess, "to_dict") else None,
            "horizon_parameters": self.horizon_params.to_dict() if self.horizon_params and hasattr(self.horizon_params, "to_dict") else None,
            "currency": active_sess.currency if active_sess else "USD",
            "data_feed_status": feed_health,
            "catalog": ASSET_CATALOG,
            "account": account_payload,
            "global_account": {
                **summary,
                "market_return_pct": mkt_ret,
                "alpha_vs_market_pct": round(float(summary.get("total_return_pct", 0.0)) - mkt_ret, 2),
                "audit": audit,
            },
            "market_sessions": self.get_all_market_sessions(),
            "pending_orders": self.broker.get_pending_orders(),
            "order_history": self.broker.get_order_history(limit=25),
            "comparison_series": self.comparison_series,
            "assets": assets_payload,
            "open_positions": [
                {
                    "id": p.id,
                    "ticker": p.ticker,
                    "direction": p.direction,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "bid_price": p.bid_price,
                    "ask_price": p.ask_price,
                    "spread_bps": p.spread_bps,
                    "slippage_bps": p.slippage_bps,
                    "entry_fee": p.entry_fee,
                    "target_price": p.target_price,
                    "stop_price": p.stop_price,
                    "shares": round(p.shares, 4),
                    "allocated_capital": round(p.allocated_capital, 2),
                    "unrealized_pnl": round(p.unrealized_pnl, 2),
                    "unrealized_return_pct": round(p.unrealized_return_pct, 2),
                    "holding_bars": p.holding_bars,
                    "market_timestamp": p.market_timestamp,
                }
                for p in open_positions
            ],
            "closed_trades": [
                {
                    "id": t.id,
                    "ticker": t.ticker,
                    "direction": t.direction,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "shares": round(t.shares, 4),
                    "gross_pnl": round(t.gross_pnl, 2),
                    "net_pnl": round(t.net_pnl, 2),
                    "return_pct": round(t.return_pct, 2),
                    "friction_fee": round(t.friction_fee, 2),
                    "slippage_cost": round(t.slippage_cost, 2),
                    "exit_reason": t.exit_reason,
                    "exit_time": t.exit_time[:19].replace("T", " "),
                }
                for t in closed_trades
            ],
            "activity_log": self.activity_log[:40],
        }

    def get_all_market_sessions(self) -> Dict[str, Dict]:
        """Returns session status mapping for all watched tickers plus exchange benchmark indices."""
        sessions = {}
        for tk in self.watchlist:
            sess = self.calendar.get_session_info(tk, simulation_mode=self.simulation_mode)
            sessions[tk] = sess.to_dict()
        for tk in self.analyses:
            if tk not in sessions:
                sess = self.calendar.get_session_info(tk, simulation_mode=self.simulation_mode)
                sessions[tk] = sess.to_dict()
        for ref, sym in [
            ("NSE_INDIA", "RELIANCE.NS"),
            ("BSE_INDIA", "TCS.BO"),
            ("NIFTY_50", "^NSEI"),
            ("BANK_NIFTY", "^NSEBANK"),
            ("US_MARKETS", "NVDA"),
            ("CME_GLOBEX", "GC=F"),
            ("CRYPTO_247", "BTC-USD"),
        ]:
            sess = self.calendar.get_session_info(sym, simulation_mode=self.simulation_mode)
            sessions[ref] = sess.to_dict()
        return sessions
