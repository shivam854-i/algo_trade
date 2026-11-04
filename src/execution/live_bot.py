"""Autonomous Live Trading Bot Controller, Exchange Hours Engine & Multi-Asset Selector.

Enforces real-world exchange trading hours (NSE 09:15-15:30 IST, NYSE 09:30-16:00 EST,
CME COMEX 23/5, Forex 24/5, Crypto 24/7) with optional 24/7 Sandbox Override,
and empowers users to dynamically select which specific stocks, cryptos, commodities,
or forex pairs the bot is authorized to trade.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo
import numpy as np

from src.execution.broker import PaperBroker
from src.execution.frictions import FrictionEvaluator
from src.execution.market_sessions import (
    MarketCalendarManager,
    MarketSessionInfo,
    MarketState,
)
from src.models.gpu_acceleration import GPUManager
from src.pipeline import MarketPredictionEngine, SingleAssetAnalysis

logger = logging.getLogger(__name__)

# Global default calendar instance
_default_calendar = MarketCalendarManager()

# Curated catalog of popular multi-asset instruments for 1-click selection
ASSET_CATALOG = {
    "CRYPTO": ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD"],
    "COMMODITIES": ["GC=F", "SI=F", "CL=F"],
    "FOREX": ["EURUSD=X", "GBPUSD=X", "USDJPY=X"],
    "INDIAN_NSE": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "TATAMOTORS.NS"],
    "US_EQUITIES": ["NVDA", "AAPL", "TSLA", "MSFT", "AMD"],
}


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
    """Orchestrates live autonomous bot execution, market hours enforcement, and multi-asset selection."""

    def __init__(self, engine: MarketPredictionEngine, broker: PaperBroker):
        self.engine = engine
        self.broker = broker
        self.gpu_profile = GPUManager().profile

        # Active universe in the watchlist and the subset armed for autonomous trading
        self.watchlist: List[str] = ["BTC-USD", "ETH-USD", "GC=F", "EURUSD=X", "RELIANCE.NS", "NVDA"]
        self.armed_tickers: Set[str] = {"BTC-USD", "ETH-USD", "GC=F", "EURUSD=X", "RELIANCE.NS", "NVDA"}

        self.is_running: bool = True
        # Strictly respect real exchange hours by default (so RELIANCE.NS isn't traded before 09:15 IST!)
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
        self.price_series: Dict[str, List[Dict[str, float | str]]] = {}

        self.comparison_series: List[Dict[str, float | str]] = []
        self.activity_log: List[Dict[str, str]] = []
        self._rng = np.random.default_rng(42)
        self._initialized = False

    def log_event(self, level: str, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.activity_log.insert(
            0,
            {
                "time": ts,
                "level": level,
                "message": message,
            },
        )
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
        """Loads initial multi-asset forecasts, cleans out-of-hours positions, and seeds telemetry."""
        if self._initialized:
            return

        self.log_event(
            "BOT",
            f"Booting SYNAPSE-TITAN on {self.gpu_profile.device_name} (CUDA {self.gpu_profile.cuda_runtime_version})...",
        )
        portfolio = self.engine.analyze_portfolio(self.watchlist, period="1y", interval="1d")
        self.analyses = portfolio.single_analyses
        self.hrp_weights = portfolio.hrp_portfolio_weights

        # Close any leftover positions from closed exchanges when booting in Strict Exchange Hours mode
        if self.enforce_market_hours:
            for pos in self.broker.get_open_positions():
                tradable, sess = self._is_ticker_tradable_now(pos.ticker)
                if not tradable:
                    self.broker.close_position(pos.id, pos.entry_price, exit_reason="EXCHANGE_CLOSED_CLEANUP")

        open_pos = {p.ticker: p for p in self.broker.get_open_positions()}

        for tk, res in self.analyses.items():
            df_tail = res.recent_ohlcv.tail(45)
            decimals = 4 if res.market_jurisdiction == "FOREX" else 2
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
            curr_p = open_pos[tk].current_price if tk in open_pos else float(res.current_price)
            self.base_prices[tk] = float(res.current_price)
            self.live_prices[tk] = round(curr_p, decimals)
            hist[-1]["price"] = round(curr_p, decimals)
            self.price_series[tk] = hist

            tradable, sess = self._is_ticker_tradable_now(tk)
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
                        decimals = 4 if res.market_jurisdiction == "FOREX" else 2
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

        # Update armed set
        clean_armed = {t.strip().upper() for t in armed_tickers if t.strip().upper() in self.analyses}
        self.armed_tickers = clean_armed
        # Recompute equal/HRP weights across armed universe
        n_armed = max(len(self.armed_tickers), 1)
        for tk in self.analyses:
            self.hrp_weights[tk] = (1.0 / n_armed) if tk in self.armed_tickers else 0.0

        self.log_event(
            "BOT",
            f"Updated Bot Trading Basket ({len(self.armed_tickers)} armed): {', '.join(sorted(self.armed_tickers)) or 'NONE (Watch-Only)'}",
        )
        return self.get_dashboard_state()

    def toggle_market_hours_enforcement(self) -> Dict:
        """Toggles between Strict Real-World Exchange Hours and 24/7 Sandbox Simulation Mode."""
        self.simulation_mode = not self.simulation_mode
        self.enforce_market_hours = not self.simulation_mode
        mode_str = (
            "24/7 SANDBOX SIMULATION (All assets simulated 24/7)"
            if self.simulation_mode
            else "STRICT LIVE EXCHANGE HOURS (Closed markets frozen)"
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
        """Advances live market simulation by 1 tick for open markets and executes bot trades on armed assets."""
        if not self._initialized:
            self.initialize_market_state()

        self.tick_count += 1
        now_str = datetime.now().strftime("%H:%M:%S")
        self.last_tick_time = now_str

        # 1. Advance prices ONLY for assets whose exchange is currently OPEN (or simulation_mode is True)
        for tk, res in self.analyses.items():
            sess = self.calendar.get_session_info(tk, simulation_mode=self.simulation_mode)
            prev_state = self.last_known_market_states.get(tk)
            curr_state = sess.state
            self.last_known_market_states[tk] = curr_state

            # Detect transition to OPEN from a closed/pre-market/weekend/holiday state
            if prev_state is not None and prev_state != MarketState.OPEN and curr_state == MarketState.OPEN:
                curr_open_p = self.live_prices.get(tk, res.current_price)
                drained = self.broker.execute_pending_orders_for_ticker(tk, curr_open_p)
                if drained:
                    self.log_event(
                        "SESSION",
                        f"Market Open for {tk}: Executed {len(drained)} queued PRE_MARKET_PENDING order(s) @ {curr_open_p:.4f}.",
                    )

            if not sess.is_tradable and custom_shock_pct is None:
                # Exchange is closed and not in simulation mode -> price strictly frozen!
                continue

            decimals = 4 if res.market_jurisdiction == "FOREX" else 2
            prev_p = self.live_prices.get(tk, res.current_price)

            if custom_shock_pct is not None:
                shock = custom_shock_pct / 100.0
            else:
                ann_vol = res.volatility_cone.expected_vol_annualized
                tick_vol = max(ann_vol / np.sqrt(252.0) * 0.28, 0.0022)
                signal_dir = res.meta_prediction.primary_direction
                drift = 0.0006 * signal_dir
                shock = float(self._rng.normal(drift, tick_vol))

            new_p = max(prev_p * (1.0 + shock), 0.0001)
            self.live_prices[tk] = round(new_p, decimals)

            series = self.price_series.get(tk, [])
            series.append(
                {
                    "time": now_str,
                    "price": round(new_p, decimals),
                    "high": round(max(prev_p, new_p) * 1.001, decimals),
                    "low": round(min(prev_p, new_p) * 0.999, decimals),
                }
            )
            if len(series) > 60:
                series = series[-60:]
            self.price_series[tk] = series

        # 2. Audit open positions against updated live prices
        still_open, auto_closed = self.broker.update_and_audit_positions(self.live_prices)
        for tr in auto_closed:
            tag = "PROFIT" if tr.net_pnl >= 0 else "STOP"
            self.log_event(
                tag,
                f"Closed {tr.direction} {tr.ticker} @ {tr.exit_price:,.4f} ({tr.exit_reason}) | Net PnL: ${tr.net_pnl:+,.2f} ({tr.return_pct:+.2f}%)",
            )

        # 3. Autonomous Bot Execution: ONLY trade user-selected `armed_tickers` whose exchange is OPEN
        if self.is_running and self.armed_tickers:
            open_tickers = {p.ticker for p in still_open}
            summary = self.broker.get_account_summary()
            avail_cash = float(summary.get("current_cash", 0.0))

            # Eligible candidates: in `armed_tickers`, not already held, and exchange is currently OPEN
            candidates = []
            for tk in self.armed_tickers:
                if tk in open_tickers or tk not in self.analyses:
                    continue
                tradable, _ = self._is_ticker_tradable_now(tk)
                if tradable:
                    candidates.append((tk, self.analyses[tk]))

            candidates.sort(
                key=lambda x: abs(x[1].meta_prediction.success_probability - 0.50),
                reverse=True,
            )

            max_concurrent = min(len(self.armed_tickers), 5)
            if candidates and len(still_open) < max_concurrent and avail_cash > 5000.0:
                tk, r = candidates[0]
                curr_p = self.live_prices[tk]
                direction = "LONG" if r.meta_prediction.primary_direction >= 0 else "SHORT"
                vol_bar = max(r.volatility_cone.expected_vol_annualized / np.sqrt(252.0), 0.012)
                decimals = 4 if r.market_jurisdiction == "FOREX" else 2

                if direction == "LONG":
                    pt_p = round(curr_p * (1.0 + 1.4 * vol_bar), decimals)
                    sl_p = round(curr_p * (1.0 - 1.0 * vol_bar), decimals)
                else:
                    pt_p = round(curr_p * (1.0 - 1.4 * vol_bar), decimals)
                    sl_p = round(curr_p * (1.0 + 1.0 * vol_bar), decimals)

                alloc_pct = min(max(round(100.0 / max(len(self.armed_tickers), 2) * 0.6, 1), 8.0), 18.0)

                pos = self.broker.open_position(
                    ticker=tk,
                    direction=direction,
                    current_price=curr_p,
                    target_price=pt_p,
                    stop_price=sl_p,
                    allocation_weight_pct=alloc_pct,
                )
                if pos:
                    self.log_event(
                        "TRADE",
                        f"Bot Auto-Opened {direction} {tk} (${pos.allocated_capital:,.0f}) @ {curr_p:,.{decimals}f} | Target: {pt_p:,.{decimals}f} | Stop: {sl_p:,.{decimals}f}",
                    )

        # 4. Record Bot Equity (%) vs. Market Movement (%) point
        summary = self.broker.get_account_summary()
        bot_ret = round(float(summary.get("total_return_pct", 0.0)), 3)
        mkt_ret = round(self._compute_market_return_pct(), 3)
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
        """Resets account balance, re-anchors base prices, and clears comparison chart."""
        self.broker.reset_account(initial_capital=initial_capital)
        self.tick_count = 0
        for tk, res in self.analyses.items():
            self.base_prices[tk] = float(res.current_price)
            self.live_prices[tk] = float(res.current_price)

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
            f"Account reset to ${initial_capital:,.2f} simulated capital.",
        )
        return self.get_dashboard_state()

    def get_dashboard_state(self) -> Dict:
        """Returns complete real-time state payload for the professional web dashboard."""
        if not self._initialized:
            self.initialize_market_state()

        summary = self.broker.get_account_summary()
        open_positions = self.broker.get_open_positions()
        closed_trades = self.broker.get_closed_trades(limit=30)
        audit = self.broker.get_performance_audit()

        mkt_ret = round(self._compute_market_return_pct(), 2)
        bot_ret = round(float(summary.get("total_return_pct", 0.0)), 2)

        assets_payload = {}
        for tk, res in self.analyses.items():
            decimals = 4 if res.market_jurisdiction == "FOREX" else 2
            base_p = self.base_prices.get(tk, res.current_price)
            curr_p = self.live_prices.get(tk, res.current_price)
            move_pct = ((curr_p - base_p) / base_p * 100.0) if base_p > 0 else 0.0
            pred = res.meta_prediction
            active_pos = next((p for p in open_positions if p.ticker == tk), None)
            tradable, sess = self._is_ticker_tradable_now(tk)

            assets_payload[tk] = {
                "ticker": tk,
                "jurisdiction": res.market_jurisdiction,
                "decimals": decimals,
                "current_price": round(curr_p, decimals),
                "base_price": round(base_p, decimals),
                "move_pct": round(move_pct, 2),
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

        return {
            "bot_status": {
                "is_running": self.is_running,
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
            },
            "catalog": ASSET_CATALOG,
            "account": {
                **summary,
                "market_return_pct": mkt_ret,
                "alpha_vs_market_pct": round(bot_ret - mkt_ret, 2),
                "audit": audit,
            },
            "market_sessions": self.get_all_market_sessions(),
            "pending_orders": self.broker.get_pending_orders(),
            "comparison_series": self.comparison_series,
            "assets": assets_payload,
            "open_positions": [
                {
                    "id": p.id,
                    "ticker": p.ticker,
                    "direction": p.direction,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "target_price": p.target_price,
                    "stop_price": p.stop_price,
                    "shares": round(p.shares, 4),
                    "allocated_capital": round(p.allocated_capital, 2),
                    "unrealized_pnl": round(p.unrealized_pnl, 2),
                    "unrealized_return_pct": round(p.unrealized_return_pct, 2),
                    "holding_bars": p.holding_bars,
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
                    "net_pnl": round(t.net_pnl, 2),
                    "return_pct": round(t.return_pct, 2),
                    "friction_fee": round(t.friction_fee, 2),
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
            ("US_MARKETS", "NVDA"),
            ("CME_GLOBEX", "GC=F"),
            ("CRYPTO_247", "BTC-USD"),
        ]:
            sess = self.calendar.get_session_info(sym, simulation_mode=self.simulation_mode)
            sessions[ref] = sess.to_dict()
        return sessions
