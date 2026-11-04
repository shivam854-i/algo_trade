"""Interactive Institutional Trading & Simulated Money Cockpit for SYNAPSE-TITAN v2.0.

Run locally via:
    streamlit run app.py
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from src.backtest.engine import BacktestEngine
from src.execution.broker import PaperBroker
from src.execution.frictions import FrictionEvaluator
from src.models.gpu_acceleration import GPUManager
from src.pipeline import MarketPredictionEngine

# Page configuration
st.set_page_config(
    page_title="SYNAPSE-TITAN v2.0 | Institutional Trading & Paper Simulator",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Sleek institutional dark glassmorphic CSS styling
st.markdown(
    """
<style>
    .stApp {
        background: radial-gradient(circle at 10% 10%, #0d1117 0%, #090c10 100%);
    }
    .telemetry-banner {
        background: linear-gradient(90deg, rgba(22,27,34,0.95) 0%, rgba(13,17,23,0.95) 100%);
        border: 1px solid #30363d;
        border-left: 4px solid #00d2d3;
        border-radius: 10px;
        padding: 14px 20px;
        margin-bottom: 18px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 12px;
    }
    .metric-card {
        background: linear-gradient(145deg, #161b22 0%, #0d1117 100%);
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35);
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .metric-card:hover {
        border-color: #58a6ff;
    }
    .sim-card {
        background: linear-gradient(145deg, #131822 0%, #0b0f17 100%);
        border: 1px solid #238636;
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 16px;
    }
    .badge-buy {
        background: linear-gradient(90deg, #238636, #2ea043);
        color: white;
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.4px;
    }
    .badge-sell {
        background: linear-gradient(90deg, #da3633, #f85149);
        color: white;
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.4px;
    }
    .badge-neutral {
        background-color: #30363d;
        color: #c9d1d9;
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 600;
    }
    .gpu-pill {
        background: rgba(0, 210, 211, 0.12);
        border: 1px solid #00d2d3;
        color: #00d2d3;
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 600;
    }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def get_engine():
    return MarketPredictionEngine()


@st.cache_resource
def get_gpu_profile():
    return GPUManager().profile


def get_curr_symbol(ticker: str, jurisdiction: str) -> str:
    if jurisdiction == "FOREX":
        return ""
    elif jurisdiction == "NSE_CASH":
        return "₹"
    return "$"


def main():
    engine = get_engine()
    gpu_prof = get_gpu_profile()
    broker = PaperBroker()

    # --- SIDEBAR ---
    st.sidebar.markdown("## ⚡ SYNAPSE-TITAN `v2.0`")
    st.sidebar.caption("Audited Neuro-Causal Quantitative Engine & Simulated Money Desk")

    # Hardware status pill in sidebar
    hw_status = (
        f"🟢 {gpu_prof.device_name} ({gpu_prof.precision_mode.upper()} | {gpu_prof.total_memory_mb:.0f} MB)"
        if gpu_prof.cuda_available
        else f"🔵 {gpu_prof.device_name}"
    )
    st.sidebar.info(hw_status)

    st.sidebar.subheader("1. Asset Watchlist")
    preset_choice = st.sidebar.selectbox(
        "Load Preset Universe",
        [
            "Global Macro Multi-Asset (GC=F, EURUSD=X, NVDA, BTC-USD)",
            "Gold & Precious Metals (GC=F, SI=F, GLD)",
            "Forex FX Majors (EURUSD=X, GBPUSD=X, USDJPY=X)",
            "US Mega-Cap Tech (NVDA, AAPL, MSFT, TSLA)",
            "Indian Nifty Leaders (RELIANCE.NS, TCS.NS, INFY.NS)",
            "Commodities & Energy (GC=F, CL=F, SI=F)",
            "Crypto Majors (BTC-USD, ETH-USD, SOL-USD)",
            "Custom Selection",
        ],
    )

    preset_map = {
        "Global Macro Multi-Asset (GC=F, EURUSD=X, NVDA, BTC-USD)": "GC=F, EURUSD=X, NVDA, BTC-USD",
        "Gold & Precious Metals (GC=F, SI=F, GLD)": "GC=F, SI=F, GLD",
        "Forex FX Majors (EURUSD=X, GBPUSD=X, USDJPY=X)": "EURUSD=X, GBPUSD=X, USDJPY=X",
        "US Mega-Cap Tech (NVDA, AAPL, MSFT, TSLA)": "NVDA, AAPL, MSFT, TSLA",
        "Indian Nifty Leaders (RELIANCE.NS, TCS.NS, INFY.NS)": "RELIANCE.NS, TCS.NS, INFY.NS, HDFCBANK.NS",
        "Commodities & Energy (GC=F, CL=F, SI=F)": "GC=F, CL=F, SI=F",
        "Crypto Majors (BTC-USD, ETH-USD, SOL-USD)": "BTC-USD, ETH-USD, SOL-USD",
        "Custom Selection": "GC=F, EURUSD=X, AAPL, RELIANCE.NS",
    }
    default_tickers = preset_map.get(preset_choice, "GC=F, EURUSD=X, NVDA, BTC-USD")

    tickers_input = st.sidebar.text_input(
        "Ticker Symbols (comma-separated):", value=default_tickers
    )

    interval = st.sidebar.selectbox(
        "Timeframe / Bar Horizon",
        ["1d (Daily Swing)", "1h (Intraday)", "15m (High-Frequency)"],
        index=0,
    )
    clean_interval = interval.split(" ")[0]

    period = st.sidebar.selectbox("Lookback History", ["2y", "1y", "5y"], index=0)

    st.sidebar.divider()
    st.sidebar.subheader("2. Risk & Kelly Governance")
    kelly_choice = st.sidebar.slider(
        "Asymmetric Kelly Fraction",
        min_value=0.10,
        max_value=0.50,
        value=0.30,
        step=0.05,
        help="0.25 = Quarter Kelly, 0.30 = Institutional Default (Capped at 20% single-asset ceiling)",
    )
    engine.guardrail.kelly_c = kelly_choice

    force_refresh = st.sidebar.checkbox("Bypass Local Cache / Refresh Live Feeds", value=False)
    st.sidebar.button("🚀 Re-Scan & Forecast Universe", type="primary", use_container_width=True)

    # --- SIMULATED ACCOUNT SUMMARY IN SIDEBAR ---
    st.sidebar.divider()
    st.sidebar.subheader("3. Simulated Money Account")
    acc_sum = broker.get_account_summary()
    st.sidebar.metric(
        "Simulated Portfolio Equity",
        f"${acc_sum.get('total_equity', 100000.0):,.2f}",
        f"{acc_sum.get('total_return_pct', 0.0):+.2f}% Total Return",
    )
    st.sidebar.caption(
        f"💵 Cash: **${acc_sum.get('current_cash', 0.0):,.2f}** | "
        f"📊 Open Positions: **{acc_sum.get('open_positions_count', 0)}**"
    )

    reset_cap = st.sidebar.selectbox(
        "Reset Starting Capital",
        [100000.0, 10000.0, 50000.0, 250000.0, 1000000.0],
        format_func=lambda x: f"${x:,.0f} Simulated USD",
    )
    if st.sidebar.button("🏦 Reset Simulated Money Account", use_container_width=True):
        broker.reset_account(initial_capital=reset_cap)
        st.sidebar.success(f"Account reset to ${reset_cap:,.0f}!")
        st.rerun()

    # --- MAIN HEADER & TELEMETRY BANNER ---
    tickers = [t.strip().upper() for t in tickers_input.split(",") if t.strip()]
    if not tickers:
        st.warning("Please specify at least one valid ticker symbol in the sidebar.")
        return

    with st.spinner("Running Causal Forward-Filtering HMM, Purged High/Low Meta-Labeling & RTX 4060 TCN..."):
        analysis = engine.analyze_portfolio(
            tickers,
            period=period,
            interval=clean_interval,
            force_refresh=force_refresh,
        )

    if not analysis.single_analyses:
        st.error("No valid market data returned for the requested symbols.")
        return

    acc_sum = broker.get_account_summary()
    eq_color = "#2ed573" if acc_sum.get("total_return_pct", 0.0) >= 0 else "#ff4757"
    st.markdown(
        f"""
        <div class="telemetry-banner">
            <div>
                <h2 style="margin:0; font-size:22px;">⚡ SYNAPSE-TITAN v2.0 — Neuro-Causal Trading & Simulated Money Cockpit</h2>
                <span style="color:#8b949e; font-size:13px;">
                    Causal Forward HMM α<sub>t</sub>(j) • Purged High/Low Triple Barriers • Pinball-Loss Causal TCN • Marchenko-Pastur + Ward HRP • Almgren-Chriss Slippage
                </span>
            </div>
            <div style="display:flex; gap:14px; align-items:center;">
                <span class="gpu-pill">🎮 {gpu_prof.device_name} | CUDA {gpu_prof.cuda_runtime_version} ({gpu_prof.precision_mode.upper()})</span>
                <span style="background:#161b22; border:1px solid #30363d; padding:6px 14px; border-radius:8px; font-weight:700; color:{eq_color};">
                    💼 Sim Equity: ${acc_sum.get('total_equity', 100000.0):,.2f} ({acc_sum.get('total_return_pct', 0.0):+.2f}%)
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- TOP-LEVEL UNIVERSE OVERVIEW & ONE-CLICK TRADE CARDS ---
    st.subheader("🌐 Multi-Asset Universe & HRP Allocation Matrix")
    cols = st.columns(min(len(analysis.single_analyses), 4))

    for idx, (ticker, res) in enumerate(analysis.single_analyses.items()):
        col = cols[idx % len(cols)]
        with col:
            pred = res.meta_prediction
            regime = res.regime
            hrp_wt = analysis.hrp_portfolio_weights.get(ticker, 0.0)

            badge_class = "badge-neutral"
            if "BUY" in pred.direction_label:
                badge_class = "badge-buy"
            elif "SELL" in pred.direction_label:
                badge_class = "badge-sell"

            curr_sym = get_curr_symbol(ticker, res.market_jurisdiction)
            price_fmt = f"{res.current_price:.4f}" if res.market_jurisdiction == "FOREX" else f"{res.current_price:,.2f}"
            st.markdown(
                f"""
            <div class="metric-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h3 style="margin:0; font-size:18px;">{ticker}</h3>
                    <span class="{badge_class}">{pred.direction_label}</span>
                </div>
                <h2 style="margin:8px 0; color:#f0f6fc;">{curr_sym}{price_fmt}</h2>
                <p style="margin:2px 0; color:#8b949e; font-size:12px;">Regime: <b style="color:#c9d1d9;">{regime.name}</b></p>
                <p style="margin:2px 0; color:#8b949e; font-size:12px;">
                    Fused Conf: <b>{pred.success_probability * 100:.1f}%</b>
                    <span style="color:#00d2d3;">(TCN: {res.neural_prob * 100:.0f}%)</span>
                </p>
                <p style="margin:2px 0; color:#58a6ff; font-size:12px;">
                    Ward HRP Wt: <b>{hrp_wt * 100:.1f}%</b> | Kelly Cap: <b>{res.risk_decision.authorized_weight_pct:.1f}%</b>
                </p>
            </div>
            """,
                unsafe_allow_html=True,
            )
            trade_dir = "LONG" if pred.primary_direction >= 0 else "SHORT"
            alloc_pct = max(res.risk_decision.authorized_weight_pct, round(hrp_wt * 20.0, 1), 5.0)
            if st.button(
                f"⚡ Sim {trade_dir} {ticker} ({alloc_pct:.1f}%)",
                key=f"quick_sim_{ticker}",
                use_container_width=True,
            ):
                opened = broker.open_position(
                    ticker=ticker,
                    direction=trade_dir,
                    current_price=res.current_price,
                    target_price=pred.target_price,
                    stop_price=pred.stop_price,
                    allocation_weight_pct=alloc_pct,
                )
                if opened:
                    st.toast(f"✅ Opened Simulated {trade_dir} on {ticker} @ {curr_sym}{price_fmt}!", icon="🚀")
                    st.rerun()
                else:
                    st.error("Insufficient simulated cash for this order.")

    st.divider()

    # --- ASSET SELECTOR & KPI BAR ---
    col_sel1, col_sel2 = st.columns([2, 3])
    with col_sel1:
        selected_ticker = st.selectbox(
            "🔍 Select Asset for Deep-Dive & Order Ticket:",
            list(analysis.single_analyses.keys()),
        )
    res = analysis.single_analyses[selected_ticker]
    pred = res.meta_prediction
    regime = res.regime
    cone = res.volatility_cone
    df_ohlcv = res.recent_ohlcv
    curr_sym = get_curr_symbol(selected_ticker, res.market_jurisdiction)
    p_decimals = 4 if res.market_jurisdiction == "FOREX" else 2

    with col_sel2:
        st.info(
            f"**{selected_ticker} ({res.market_jurisdiction})** — "
            f"Optimal FracDiff Memory **`d* = {res.optimal_d_star:.2f}`** | "
            f"Round-Trip Friction + Slippage: **`{res.friction_cost_pct:.3f}%`** | "
            f"Status: **{res.risk_decision.status_message}**"
        )

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric(
        "Ensemble Signal (65% LGBM + 35% TCN)",
        pred.direction_label,
        f"Fused: {pred.success_probability * 100:.1f}% | Neural TCN: {res.neural_prob * 100:.1f}%",
    )
    kpi2.metric(
        "Profit-Taking Barrier (High/Low)",
        f"{curr_sym}{pred.target_price:,.{p_decimals}f}",
        f"{abs(pred.target_price - res.current_price) / res.current_price * 100:+.2f}% Target Excursion",
    )
    kpi3.metric(
        "Stop-Loss Barrier (Priority Wick)",
        f"{curr_sym}{pred.stop_price:,.{p_decimals}f}",
        f"{-abs(pred.stop_price - res.current_price) / res.current_price * 100:.2f}% Risk Excursion",
    )
    kpi4.metric(
        "CVaR-Kelly Authorized Allocation",
        f"{res.risk_decision.authorized_weight_pct:.1f}% of Capital",
        f"20% Hard Cap | Scalar: {res.risk_decision.sizing_scalar:.2f}x",
    )

    # --- 5 INTERACTIVE TABS ---
    tab_sim, tab_chart, tab_xai, tab_risk, tab_backtest = st.tabs(
        [
            "💼 Simulated Money Trading Desk (Paper Broker)",
            "📈 Interactive Forecast & Non-Crossing Volatility Cone",
            "🧠 Neuro-Causal XAI & RTX 4060 Telemetry",
            "🛡️ Statutory Taxes, Slippage & Microstructure Gates",
            "🧪 Causal Walk-Forward Strategy Backtest",
        ]
    )

    # =========================================================================
    # TAB 1: SIMULATED MONEY TRADING DESK & INTERACTIVE MARKET STEPPER
    # =========================================================================
    with tab_sim:
        st.markdown("### 💼 Simulated Money Trading Desk & Real-Time Forward Simulator")
        st.caption(
            "Execute simulated trades with real market prices, deduct exact statutory taxes (NSE STT/GST, SEC Sec 31) "
            "and Almgren-Chriss L2 slippage, and step the market forward bar-by-bar to test automatic Profit-Target & Stop-Loss execution."
        )

        # Refresh account summary
        summary = broker.get_account_summary()
        ac1, ac2, ac3, ac4, ac5 = st.columns(5)
        ret_val = summary.get("total_return_pct", 0.0)
        ac1.metric("Total Simulated Equity", f"${summary.get('total_equity', 0):,.2f}", f"{ret_val:+.2f}%")
        ac2.metric("Available Cash", f"${summary.get('current_cash', 0):,.2f}")
        ac3.metric("Allocated Position Margin", f"${summary.get('allocated_capital', 0):,.2f}")
        ac4.metric(
            "Open Unrealized PnL",
            f"${summary.get('unrealized_pnl', 0):+,.2f}",
            delta_color="normal",
        )
        ac5.metric(
            "Closed Realized Net PnL",
            f"${summary.get('realized_pnl', 0):+,.2f}",
            delta_color="normal",
        )

        st.markdown('<div class="sim-card">', unsafe_allow_html=True)
        st.markdown("#### 🎮 Interactive Simulation Controls & One-Click Portfolio Deployment")
        sim_c1, sim_c2, sim_c3, sim_c4, sim_c5 = st.columns(5)

        # 1. Auto-Deploy Portfolio across Watchlist
        if sim_c1.button("🤖 Auto-Deploy Watchlist Portfolio", type="primary", use_container_width=True):
            deployed_count = 0
            for tk, tk_res in analysis.single_analyses.items():
                tk_pred = tk_res.meta_prediction
                hrp_w = analysis.hrp_portfolio_weights.get(tk, 0.20)
                # Use authorized weight if active signal, else HRP-scaled test weight (8% to 18%)
                w_pct = (
                    tk_res.risk_decision.authorized_weight_pct
                    if tk_res.risk_decision.authorized_weight_pct > 0
                    else round(max(5.0, min(20.0, hrp_w * 40.0)), 1)
                )
                direction = "LONG" if tk_pred.primary_direction >= 0 else "SHORT"
                pos = broker.open_position(
                    ticker=tk,
                    direction=direction,
                    current_price=tk_res.current_price,
                    target_price=tk_pred.target_price,
                    stop_price=tk_pred.stop_price,
                    allocation_weight_pct=w_pct,
                )
                if pos is not None:
                    deployed_count += 1
            if deployed_count > 0:
                st.success(f"Deployed {deployed_count} simulated positions across your watchlist!")
                st.rerun()
            else:
                st.warning("Could not deploy positions (check available cash).")

        # 2. Step Forward 1 Simulated Bar (Realistic Volatility + Neural Drift)
        if sim_c2.button("🎲 Step +1 Market Bar (Sim Tick)", use_container_width=True):
            open_pos = broker.get_open_positions()
            if not open_pos:
                st.warning("Open at least one simulated position first to step the market forward!")
            else:
                rng = np.random.default_rng()
                sim_prices = {}
                for p in open_pos:
                    base_p = p.current_price if p.current_price > 0 else p.entry_price
                    # Use asset volatility if in analysis, else 1.2% daily step
                    if p.ticker in analysis.single_analyses:
                        tk_a = analysis.single_analyses[p.ticker]
                        bar_vol = max(tk_a.volatility_cone.expected_vol_annualized / np.sqrt(252.0), 0.008)
                        drift = 0.0015 * tk_a.meta_prediction.primary_direction
                    else:
                        bar_vol = 0.012
                        drift = 0.001
                    shock = float(rng.normal(drift, bar_vol))
                    sim_prices[p.ticker] = round(base_p * (1.0 + shock), 4)
                _, auto_closed = broker.update_and_audit_positions(sim_prices)
                if auto_closed:
                    st.toast(f"🎯 {len(auto_closed)} position(s) hit Triple-Barrier Target/Stop and closed!", icon="⚡")
                st.rerun()

        # 3. Bull Rally Stress Test (+1.5% across open positions)
        if sim_c3.button("📈 Simulate +1.5% Bull Rally", use_container_width=True):
            open_pos = broker.get_open_positions()
            if open_pos:
                sim_prices = {
                    p.ticker: round((p.current_price or p.entry_price) * 1.015, 4)
                    for p in open_pos
                }
                broker.update_and_audit_positions(sim_prices)
                st.rerun()
            else:
                st.warning("No open positions to shock.")

        # 4. Bear Crash Stress Test (-1.5% across open positions)
        if sim_c4.button("📉 Simulate -1.5% Pullback", use_container_width=True):
            open_pos = broker.get_open_positions()
            if open_pos:
                sim_prices = {
                    p.ticker: round((p.current_price or p.entry_price) * 0.985, 4)
                    for p in open_pos
                }
                broker.update_and_audit_positions(sim_prices)
                st.rerun()
            else:
                st.warning("No open positions to shock.")

        # 5. Flatten All Positions to Cash
        if sim_c5.button("🛑 Liquidate All to Cash", use_container_width=True):
            open_pos = broker.get_open_positions()
            if open_pos:
                price_map = {p.ticker: p.current_price or p.entry_price for p in open_pos}
                closed_list = broker.close_all_positions(price_map, reason="MANUAL_FLATTEN_ALL")
                st.success(f"Liquidated {len(closed_list)} position(s) to cash.")
                st.rerun()
            else:
                st.info("Portfolio is already 100% in cash.")
        st.markdown("</div>", unsafe_allow_html=True)

        # --- MANUAL / AI-ASSISTED ORDER TICKET ---
        with st.expander("📝 Place Custom Simulated Order (Pre-Filled with AI Barriers)", expanded=True):
            ord_col1, ord_col2, ord_col3, ord_col4, ord_col5 = st.columns([1.4, 1.0, 1.2, 1.2, 1.2])
            order_ticker = ord_col1.text_input("Asset Ticker", value=selected_ticker)
            default_dir_idx = 0 if pred.primary_direction >= 0 else 1
            order_dir = ord_col2.selectbox("Direction", ["LONG", "SHORT"], index=default_dir_idx)
            default_alloc = (
                float(res.risk_decision.authorized_weight_pct)
                if res.risk_decision.authorized_weight_pct >= 1.0
                else 10.0
            )
            order_alloc = ord_col3.slider(
                "Capital Allocation (%)",
                min_value=1.0,
                max_value=20.0,
                value=min(default_alloc, 20.0),
                step=0.5,
                help="Enforces the 20% institutional CVaR-Kelly single-position ceiling.",
            )

            # Calculate preview dollar notional & friction
            est_notional = summary.get("total_equity", 100000.0) * (order_alloc / 100.0)
            rt_bps = FrictionEvaluator.calculate_round_trip_friction_bps(
                order_ticker,
                is_intraday=(clean_interval != "1d"),
                reference_price=res.current_price,
                order_notional=est_notional,
            )
            est_fee_usd = est_notional * (rt_bps / 10000.0)
            ord_col4.metric("Order Notional ($)", f"${est_notional:,.2f}", f"Est. RT Fee: ${est_fee_usd:.2f} ({rt_bps:.1f} bps)")

            submit_ord = ord_col5.button("🚀 Execute Simulated Order", type="primary", use_container_width=True)
            if submit_ord:
                target_tk = order_ticker.strip().upper()
                tk_analysis = (
                    analysis.single_analyses.get(target_tk)
                    or engine.analyze_ticker(target_tk, period="1y", interval=clean_interval)
                )
                if tk_analysis:
                    p_now = tk_analysis.current_price
                    vol_now = max(tk_analysis.volatility_cone.expected_vol_annualized / np.sqrt(252.0), 0.015)
                    if order_dir == "LONG":
                        pt_p = p_now * (1.0 + 1.8 * vol_now)
                        sl_p = p_now * (1.0 - 1.25 * vol_now)
                    else:
                        pt_p = p_now * (1.0 - 1.8 * vol_now)
                        sl_p = p_now * (1.0 + 1.25 * vol_now)

                    opened_pos = broker.open_position(
                        ticker=target_tk,
                        direction=order_dir,
                        current_price=p_now,
                        target_price=round(pt_p, 4),
                        stop_price=round(sl_p, 4),
                        allocation_weight_pct=order_alloc,
                    )
                    if opened_pos:
                        st.success(
                            f"✅ Order Filled! Opened {order_dir} on {target_tk} @ {p_now:,.4f} "
                            f"(Target: {pt_p:,.4f} | Stop: {sl_p:,.4f} | Alloc: ${opened_pos.allocated_capital:,.2f})"
                        )
                        st.rerun()
                    else:
                        st.error("Order rejected: insufficient available simulated cash.")
                else:
                    st.error(f"Could not fetch live market data for {order_ticker}.")

        # --- ACTIVE OPEN POSITIONS TABLE ---
        st.markdown("#### 📊 Active Open Positions (Live Triple-Barrier Monitoring)")
        open_positions = broker.get_open_positions()
        if open_positions:
            pos_rows = []
            for p in open_positions:
                pos_rows.append(
                    {
                        "ID": p.id,
                        "Ticker": p.ticker,
                        "Side": p.direction,
                        "Entry Price": f"{p.entry_price:,.4f}" if "=X" in p.ticker else f"${p.entry_price:,.2f}",
                        "Current Sim Price": f"{p.current_price:,.4f}" if "=X" in p.ticker else f"${p.current_price:,.2f}",
                        "Profit Target": f"{p.target_price:,.4f}" if "=X" in p.ticker else f"${p.target_price:,.2f}",
                        "Stop Loss": f"{p.stop_price:,.4f}" if "=X" in p.ticker else f"${p.stop_price:,.2f}",
                        "Units / Shares": f"{p.shares:,.4f}",
                        "Allocated ($)": f"${p.allocated_capital:,.2f}",
                        "Unrealized PnL ($)": f"${p.unrealized_pnl:+,.2f}",
                        "Return (%)": f"{p.unrealized_return_pct:+.2f}%",
                        "Bars Held": p.holding_bars,
                    }
                )
            st.dataframe(pd.DataFrame(pos_rows), use_container_width=True, hide_index=True)

            col_cl1, col_cl2, col_cl3 = st.columns([2.5, 1.2, 1.3])
            pos_to_close = col_cl1.selectbox(
                "Select Open Position to Close Manually:",
                options=[p.id for p in open_positions],
                format_func=lambda pid: next(
                    f"Position #{p.id} — {p.ticker} ({p.direction}) | Unrealized: ${p.unrealized_pnl:+,.2f} ({p.unrealized_return_pct:+.2f}%)"
                    for p in open_positions
                    if p.id == pid
                ),
            )
            if col_cl2.button("🎯 Close Selected @ Current Price", use_container_width=True):
                target_p = next(p for p in open_positions if p.id == pos_to_close)
                trade_log = broker.close_position(pos_to_close, target_p.current_price, "MANUAL_UI_CLOSE")
                if trade_log:
                    st.success(f"Closed Position #{pos_to_close} | Realized Net PnL: ${trade_log.net_pnl:+,.2f}")
                    st.rerun()

            if col_cl3.button("🔄 Sync Live Market Prices", use_container_width=True):
                live_map = {}
                for p in open_positions:
                    if p.ticker in analysis.single_analyses:
                        live_map[p.ticker] = analysis.single_analyses[p.ticker].current_price
                    else:
                        tk_res = engine.analyze_ticker(p.ticker, period="3mo", interval="1d")
                        live_map[p.ticker] = tk_res.current_price if tk_res else p.current_price
                broker.update_and_audit_positions(live_map)
                st.rerun()
        else:
            st.info(
                "💡 No active open positions yet. Click **'🤖 Auto-Deploy Watchlist Portfolio'** above or any **'⚡ Sim LONG/SHORT'** button on the asset cards to start testing with simulated money!"
            )

        st.divider()

        # --- VERIFIED CLOSED TRADES LEDGER & EQUITY CURVE ---
        st.markdown("#### 📜 Verified Closed Trades Ledger & Realized Equity Curve")
        audit_metrics = broker.get_performance_audit()
        au1, au2, au3, au4 = st.columns(4)
        au1.metric("Completed Simulated Trades", audit_metrics.get("total_trades", 0))
        au2.metric("Realized Win Rate", f"{audit_metrics.get('win_rate_pct', 0.0):.1f}%")
        au3.metric("Realized Profit Factor", f"{audit_metrics.get('profit_factor', 0.0):.2f}")
        au4.metric("Total Net Realized Profit", f"${audit_metrics.get('net_profit', 0.0):+,.2f}")

        closed_trades = broker.get_closed_trades(limit=100)
        if closed_trades:
            # Plot realized equity progression across trades
            init_cap = summary.get("initial_capital", 100000.0)
            chronological_trades = list(reversed(closed_trades))
            cum_eq = [init_cap]
            labels_x = ["Start"]
            for idx_t, t in enumerate(chronological_trades, 1):
                cum_eq.append(cum_eq[-1] + t.net_pnl)
                labels_x.append(f"#{t.id} {t.ticker}")

            sim_eq_fig = go.Figure()
            sim_eq_fig.add_trace(
                go.Scatter(
                    x=labels_x,
                    y=cum_eq,
                    mode="lines+markers",
                    line=dict(color="#00d2d3", width=3),
                    fill="tozeroy",
                    fillcolor="rgba(0, 210, 211, 0.10)",
                    name="Realized Account Equity ($)",
                )
            )
            sim_eq_fig.update_layout(
                template="plotly_dark",
                height=280,
                margin=dict(l=20, r=20, t=20, b=20),
                yaxis_title="Simulated Equity ($)",
            )
            st.plotly_chart(sim_eq_fig, use_container_width=True)

            tr_data = [
                {
                    "Trade ID": t.id,
                    "Ticker": t.ticker,
                    "Side": t.direction,
                    "Entry Price": f"{t.entry_price:,.4f}" if "=X" in t.ticker else f"${t.entry_price:,.2f}",
                    "Exit Price": f"{t.exit_price:,.4f}" if "=X" in t.ticker else f"${t.exit_price:,.2f}",
                    "Gross PnL": f"${t.gross_pnl:+,.2f}",
                    "Statutory + Slippage Fee": f"${t.friction_fee:,.2f}",
                    "Net Realized PnL": f"${t.net_pnl:+,.2f}",
                    "Net Return %": f"{t.return_pct:+.2f}%",
                    "Exit Trigger": t.exit_reason.replace("_", " ").title(),
                    "Exit Time (UTC)": t.exit_time[:19].replace("T", " "),
                }
                for t in closed_trades
            ]
            st.dataframe(pd.DataFrame(tr_data), use_container_width=True, hide_index=True)
        else:
            st.caption("No closed simulated trades yet. Step the market forward or close an open position to populate the ledger.")

    # =========================================================================
    # TAB 2: INTERACTIVE FORECAST & NON-CROSSING VOLATILITY CONE
    # =========================================================================
    with tab_chart:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.07,
            row_heights=[0.74, 0.26],
            subplot_titles=(
                f"{selected_ticker} Price Action, Triple-Barriers & Cornish-Fisher Volatility Cone",
                f"Stationary Fractional Differentiation Series (d* = {res.optimal_d_star:.2f})",
            ),
        )

        # 1. Candlesticks
        fig.add_trace(
            go.Candlestick(
                x=df_ohlcv.index,
                open=df_ohlcv["Open"],
                high=df_ohlcv["High"],
                low=df_ohlcv["Low"],
                close=df_ohlcv["Close"],
                name="OHLC Price",
            ),
            row=1,
            col=1,
        )

        # 2. Forward Forecast Cone
        last_date = df_ohlcv.index[-1]
        freq = "B" if clean_interval == "1d" else "h"
        future_dates = pd.date_range(start=last_date, periods=len(cone.periods) + 1, freq=freq)[1:]

        cone_dates = [last_date] + list(future_dates)
        upper_path = [res.current_price] + cone.q90_prices
        lower_path = [res.current_price] + cone.q10_prices
        median_path = [res.current_price] + cone.q50_prices

        fig.add_trace(
            go.Scatter(
                x=cone_dates + cone_dates[::-1],
                y=upper_path + lower_path[::-1],
                fill="toself",
                fillcolor="rgba(0, 210, 211, 0.16)",
                line=dict(color="rgba(255,255,255,0)"),
                name="q10–q90 Volatility Cone",
                hoverinfo="skip",
            ),
            row=1,
            col=1,
        )

        fig.add_trace(
            go.Scatter(
                x=cone_dates,
                y=median_path,
                mode="lines+markers",
                line=dict(color="#00d2d3", width=2.5, dash="dot"),
                name="Median Trajectory (q50)",
            ),
            row=1,
            col=1,
        )

        fig.add_hline(
            y=pred.target_price,
            line_dash="dash",
            line_color="#2ed573",
            annotation_text=f"Target: {curr_sym}{pred.target_price:,.{p_decimals}f}",
            annotation_position="top right",
            row=1,
            col=1,
        )
        fig.add_hline(
            y=pred.stop_price,
            line_dash="dash",
            line_color="#ff4757",
            annotation_text=f"Stop: {curr_sym}{pred.stop_price:,.{p_decimals}f}",
            annotation_position="bottom right",
            row=1,
            col=1,
        )

        # Sub-chart: FracDiff Stationary Memory Series or Volume
        if "FracDiff_Price" in res.features_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=res.features_df.index,
                    y=res.features_df["FracDiff_Price"],
                    mode="lines",
                    line=dict(color="#a29bfe", width=1.8),
                    name=f"FracDiff (d*={res.optimal_d_star:.2f})",
                ),
                row=2,
                col=1,
            )
        else:
            fig.add_trace(
                go.Bar(
                    x=df_ohlcv.index,
                    y=df_ohlcv["Volume"],
                    name="Volume",
                    marker_color="#30363d",
                ),
                row=2,
                col=1,
            )

        fig.update_layout(
            template="plotly_dark",
            height=620,
            margin=dict(l=25, r=25, t=40, b=25),
            xaxis_rangeslider_visible=False,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)

    # =========================================================================
    # TAB 3: NEURO-CAUSAL XAI & RTX 4060 TELEMETRY
    # =========================================================================
    with tab_xai:
        col_x1, col_x2 = st.columns([3, 2])
        with col_x1:
            st.markdown("#### 🧠 LightGBM Meta-Model Feature Attribution (Top Drivers)")
            if pred.feature_importances:
                imp_df = pd.DataFrame(
                    list(pred.feature_importances.items()),
                    columns=["Feature", "Importance Weight"],
                ).sort_values("Importance Weight", ascending=True)

                fig_bar = go.Figure(
                    go.Bar(
                        x=imp_df["Importance Weight"],
                        y=imp_df["Feature"],
                        orientation="h",
                        marker_color="#58a6ff",
                    )
                )
                fig_bar.update_layout(
                    template="plotly_dark",
                    height=330,
                    margin=dict(l=20, r=20, t=20, b=20),
                    xaxis_title="Normalized Gain Contribution",
                )
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("Feature importances are calibrating across historical bars.")

        with col_x2:
            st.markdown("#### 📊 Marchenko-Pastur RMT + Ward HRP Weights")
            if analysis.hrp_portfolio_weights:
                hrp_df = pd.DataFrame(
                    list(analysis.hrp_portfolio_weights.items()),
                    columns=["Ticker", "Weight"],
                )
                fig_pie = go.Figure(
                    go.Pie(
                        labels=hrp_df["Ticker"],
                        values=hrp_df["Weight"],
                        hole=0.55,
                        textinfo="label+percent",
                    )
                )
                fig_pie.update_layout(
                    template="plotly_dark",
                    height=330,
                    margin=dict(l=20, r=20, t=20, b=20),
                    showlegend=False,
                )
                st.plotly_chart(fig_pie, use_container_width=True)

        q10_s, q50_s, q90_s = engine.neural_forecaster.forecast_tensor(df_ohlcv)
        st.markdown(
            f"""
            #### 🎮 RTX 4060 Supervised `CausalQuantileTCN` & Causal HMM Telemetry
            - **Hardware Execution Engine**: `{gpu_prof.device_name}` (`CUDA {gpu_prof.cuda_runtime_version}` | Precision: `{gpu_prof.precision_mode.upper()}` | Free VRAM: `{gpu_prof.free_memory_mb:.1f} MB`)
            - **Monotonic Non-Crossing Quantile Shocks (`Pinball Loss`)**:
              - Downside $q_{{10}}$: **`{q10_s * 100:+.2f}%`** $\le$ Median $q_{{50}}$: **`{q50_s * 100:+.2f}%`** $\le$ Upside $q_{{90}}$: **`{q90_s * 100:+.2f}%`** *(Guaranteed non-crossing via Softplus parameterization)*
            - **Ensemble Conviction Breakdown**:
              - **Supervised Causal TCN (35% Weight)**: `{res.neural_prob * 100:.1f}%`
              - **Fused Meta-Probability**: `{pred.success_probability * 100:.1f}%`
            - **Causal Forward-Filtering HMM State ($\alpha_t(j)$)**: **{regime.name}** — *{regime.description}*
            """
        )

    # =========================================================================
    # TAB 4: STATUTORY TAXES, SLIPPAGE & MICROSTRUCTURE GATES
    # =========================================================================
    with tab_risk:
        st.markdown("#### 🛡️ Holding-Period Statutory Frictions, Almgren-Chriss Slippage & Microstructure Gates")
        micro_ok, micro_msg = FrictionEvaluator.check_microstructure_execution_gate(
            selected_ticker, ohlcv_df=df_ohlcv
        )
        deliv_bps = FrictionEvaluator.calculate_round_trip_friction_bps(
            selected_ticker, is_intraday=False, reference_price=res.current_price
        )
        intra_bps = FrictionEvaluator.calculate_round_trip_friction_bps(
            selected_ticker, is_intraday=True, reference_price=res.current_price
        )
        gross_alpha = abs((pred.target_price - res.current_price) / res.current_price * 100.0)

        st.markdown(
            f"""
        | Governance Check | Evaluated Value | Institutional Requirement / Status |
        | :--- | :--- | :--- |
        | **Market Jurisdiction** | `{res.market_jurisdiction}` | Automatic Tax & Exchange Schedule |
        | **Multi-Day Delivery Round-Trip Hurdle** | `{deliv_bps:.2f} bps` (`{deliv_bps / 100:.3f}%`) | Includes Delivery STT + Stamp + GST + Almgren-Chriss Impact |
        | **Intraday Round-Trip Hurdle** | `{intra_bps:.2f} bps` (`{intra_bps / 100:.3f}%`) | Includes Intraday STT + Exchange + Almgren-Chriss Impact |
        | **Gross Expected Target Alpha** | `+{gross_alpha:.2f}%` | Must exceed **1.5x** Total Friction (`{1.5 * res.friction_cost_pct:.3f}%`) |
        | **Net Expected Alpha After Friction** | `{res.net_expected_alpha_pct:+.2f}%` | **{'✅ PASSED 1.5x HURDLE' if res.friction_hurdle_passes else '🛑 REJECTED BY 1.5x HURDLE'}** |
        | **Phase 3 Microstructure Gate (Gold/FX)** | `{micro_msg}` | **{'✅ CLEAR TO EXECUTE' if micro_ok else '🛑 MICROSTRUCTURE VETO'}** |
        """
        )
        st.info(f"🛡️ **Asymmetric CVaR-Kelly Risk Governor**: {res.risk_decision.status_message}")

    # =========================================================================
    # TAB 5: STRICTLY CAUSAL WALK-FORWARD STRATEGY BACKTEST
    # =========================================================================
    with tab_backtest:
        st.markdown(f"#### 🧪 Strictly Causal Walk-Forward Backtester: `{selected_ticker}`")
        st.caption(
            "Zero lookahead bias: calibrates FracDiff d* on warmup bars only, runs online causal forward-filtering HMM alpha_t(j), "
            "evaluates High/Low wicks with Stop-Loss priority on dual-breach bars, refits Pinball-Loss Causal TCN periodically, "
            "and deducts full holding-period statutory taxes + Almgren-Chriss slippage."
        )

        col_bt1, col_bt2, col_bt3 = st.columns([1, 1, 1])
        bt_capital = col_bt1.number_input("Starting Capital ($)", min_value=1000.0, value=10000.0, step=1000.0)
        bt_period = col_bt2.selectbox("Backtest Horizon", ["1y", "2y", "5y"], index=1)
        run_bt = col_bt3.button("🚀 Run Causal Walk-Forward Backtest", type="primary", use_container_width=True)

        bt_key = f"bt_{selected_ticker}_{bt_period}_{bt_capital}"
        if run_bt or bt_key in st.session_state:
            with st.spinner(f"Executing strictly causal walk-forward simulation on {selected_ticker}..."):
                if run_bt or bt_key not in st.session_state:
                    bt_engine = BacktestEngine(initial_capital=bt_capital, kelly_fraction=kelly_choice)
                    bt_res = bt_engine.run(selected_ticker, period=bt_period, interval=clean_interval)
                    st.session_state[bt_key] = bt_res
                else:
                    bt_res = st.session_state[bt_key]

            if bt_res is not None:
                m1, m2, m3, m4, m5 = st.columns(5)
                ret_delta = f"{bt_res.total_return_pct - bt_res.buy_hold_return_pct:+.2f}% vs B&H ({bt_res.buy_hold_return_pct:+.2f}%)"
                m1.metric("Strategy Net Return", f"{bt_res.total_return_pct:+.2f}%", ret_delta)
                m2.metric("Annual Sharpe Ratio", f"{bt_res.sharpe_ratio:.2f}", f"Sortino: {bt_res.sortino_ratio:.2f}")
                m3.metric("Max Causal Drawdown", f"{bt_res.max_drawdown_pct:.2f}%", f"Calmar: {bt_res.calmar_ratio:.2f}")
                m4.metric("Strategy Win Rate", f"{bt_res.win_rate_pct:.1f}%", f"{bt_res.winning_trades}W / {bt_res.losing_trades}L")
                m5.metric("Profit Factor", f"{bt_res.profit_factor:.2f}", f"DSR (N=10): {bt_res.deflated_sharpe * 100:.1f}%")

                col_c1, col_c2 = st.columns([3, 2])
                with col_c1:
                    eq_fig = go.Figure()
                    eq_fig.add_trace(
                        go.Scatter(
                            x=bt_res.equity_curve.index,
                            y=bt_res.equity_curve.values,
                            mode="lines",
                            line=dict(color="#00d2d3", width=2.5),
                            name="Strategy Equity ($)",
                        )
                    )
                    eq_fig.update_layout(
                        title="Cumulative Walk-Forward Portfolio Equity ($)",
                        template="plotly_dark",
                        height=350,
                        margin=dict(l=20, r=20, t=40, b=20),
                        yaxis_title="Equity ($)",
                    )
                    st.plotly_chart(eq_fig, use_container_width=True)

                with col_c2:
                    dd_fig = go.Figure()
                    dd_fig.add_trace(
                        go.Scatter(
                            x=bt_res.drawdown_series.index,
                            y=-bt_res.drawdown_series.values,
                            fill="tozeroy",
                            mode="lines",
                            line=dict(color="#ff4757", width=1.5),
                            name="Underwater Drawdown (%)",
                        )
                    )
                    dd_fig.update_layout(
                        title="Peak-to-Trough Underwater Drawdown (%)",
                        template="plotly_dark",
                        height=350,
                        margin=dict(l=20, r=20, t=40, b=20),
                        yaxis_title="Drawdown (%)",
                    )
                    st.plotly_chart(dd_fig, use_container_width=True)

                st.markdown(f"##### Completed Walk-Forward Trade Ledger ({len(bt_res.trades)} Trades)")
                if bt_res.trades:
                    trade_records = [
                        {
                            "Entry Date": tr.entry_date.strftime("%Y-%m-%d"),
                            "Exit Date": tr.exit_date.strftime("%Y-%m-%d"),
                            "Side": tr.direction,
                            "Entry Price": f"{tr.entry_price:,.4f}" if "=X" in selected_ticker else f"${tr.entry_price:,.2f}",
                            "Exit Price": f"{tr.exit_price:,.4f}" if "=X" in selected_ticker else f"${tr.exit_price:,.2f}",
                            "Net Return": f"{tr.return_pct:+.2f}%",
                            "Net PnL": f"${tr.net_pnl:+,.2f}",
                            "Exit Reason": tr.exit_reason.replace("_", " ").title(),
                            "Duration (Bars)": tr.duration_bars,
                        }
                        for tr in bt_res.trades[::-1]
                    ]
                    st.dataframe(pd.DataFrame(trade_records), use_container_width=True, hide_index=True)
                else:
                    st.info("No trades authorized during this period (Guardrails preserved 100% cash).")
            else:
                st.warning("Insufficient historical bars to execute a walk-forward backtest on this asset.")


if __name__ == "__main__":
    main()
