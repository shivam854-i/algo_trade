# ⚡ SYNAPSE-TITAN: Neuro-Causal Market Prediction & SaaS Engine

An institutional-grade, multi-asset **Quantitative Observation, Volatility Forecasting, Automated Broker Execution, and SaaS Platform**.

Architected specifically for commercial deployment as a cloud SaaS platform (supporting Web, Mobile, and API clients) with local GPU acceleration on NVIDIA RTX 4000 series hardware.

---

## 🏛️ Foundational Quantitative Architecture

SYNAPSE-TITAN replaces standard retail indicator crossover bots with empirical quantitative finance:

1. **Fractional Differentiation ($d^*$ Order)**: Based on Marcos López de Prado (*AFML*, Chapter 5). Preserves memory and multi-month cyclical patterns while guaranteeing Augmented Dickey-Fuller (ADF) stationarity ($p < 0.05$).
2. **Hidden Markov Model (HMM) Regimes**: Dynamically classifies markets into 3 latent states:
   - `State 0: Low-Vol Trending` (Favorable for momentum expansion)
   - `State 1: Choppy Range-Bound` (Mean-reversion / barrier dampening)
   - `State 2: High-Vol Crisis` (Automatic emergency circuit breaker & cash preservation)
3. **GPU Neural Ensemble Fusion**:
   $$\text{Final Conviction} = 65\% \text{ LightGBM (Causal Decision Trees)} + 35\% \text{ PyTorch Conv1D/Attention (3D Geometric Candle Shape)}$$
   - Evaluates the 3D tensor trajectory of the past 60 candles across Open, High, Low, Close, Volume.
   - **False Breakout & Trap Veto**: Automatically vetoes trades if indicator signals contradict deep candle geometry.
4. **Hierarchical Risk Parity (HRP)**: Machine-learning tree clustering and recursive bisection portfolio allocation with Marchenko-Pastur Random Matrix covariance de-noising.
5. **Exact Statutory Friction Deduction**: Calculates statutory taxes on every trade to eliminate illusory alpha:
   - **Indian Equities**: 0.025% STT, 18% GST on turnover/brokerage, stamp duty, SEBI fees.
   - **US Equities**: SEC Section 31 fees, FINRA TAF, taker fees.
   - **Commodities & Forex**: Contract exchange fees and average bid-ask spread hurdle.
   - **Crypto**: Taker liquidity fees (4 bps).
6. **Risk Guardrails & Fractional Kelly Sizing**: Convex drawdown dampening, volatility scaling, and strict position constraints.
7. **Autonomous Live Paper-Trading & Execution Ledger**: SQLite-backed persistent order routing, position tracking, MTM unrealized valuation, and audit trail with pluggable adapters for **Alpaca**, **Zerodha Kite**, and **MetaTrader 5**.

---

## 🌐 Supported Multi-Asset Universes

| Market Class | Example Tickers | Jurisdiction Profile | Supported Resolutions | Typical Friction |
| :--- | :--- | :--- | :--- | :--- |
| **Commodities** | `GC=F` (Gold), `SI=F` (Silver), `CL=F` (Crude Oil) | `COMMODITY` | `15m`, `1h`, `1d` | ~3.0 bps |
| **Forex (FX)** | `EURUSD=X`, `GBPUSD=X`, `USDJPY=X` | `FOREX` | `15m`, `1h`, `1d` | ~1.5 bps |
| **US Equities** | `NVDA`, `AAPL`, `MSFT`, `TSLA`, `SPY` | `US` | `1h`, `1d` | ~2.5 bps |
| **Indian NSE/BSE** | `RELIANCE.NS`, `TCS.NS`, `INFY.NS`, `HDFCBANK.NS` | `NSE_CASH` | `1h`, `1d` | ~7.2 – 9.5 bps |
| **Cryptocurrencies** | `BTC-USD`, `ETH-USD`, `SOL-USD` | `CRYPTO` | `15m`, `1h`, `1d` | ~8.0 bps |

---

## 🚀 Execution Modes & Quick Start

### 1. Installation
Ensure Python 3.10+ is installed:
```bash
pip install -r requirements.txt
```

### 2. Modern Institutional Trading Cockpit & FastAPI Backend
Launch the high-performance unified trading cockpit (React 18 + Vite + FastAPI):
```bash
python -m uvicorn server:app --host 127.0.0.1 --port 8501 --reload
```
*Access in your browser at `http://localhost:8501`. Features:*
- 🖥️ **Leak-Free React 18 Single-Page Cockpit**: Uses $O(1)$ client ring buffers (`RingBuffer<T>`) keeping memory strictly bounded to $<30\text{ MB}$ (eliminating browser memory bloat).
- 📉 **TradingView Lightweight Charts**: Hardware-accelerated canvas charts with automatic cleanup upon unmount.
- 🕒 **Physical Market Session Timings**: Real-world operating schedules and statutory holiday calendars for **NSE/BSE (09:15–15:30 IST)**, **NYSE/NASDAQ (09:30–16:00 ET)**, **COMEX Gold (23/5)**, and **Crypto (24/7)** with live countdown clocks.
- 🔒 **Pre-Market Order Queuing**: Off-hours orders safely held in `PRE_MARKET_PENDING` with soft cash reservation, auto-executing on market open.
- ⏸️ **Tab Inactivity Auto-Pause**: Automatically halts polling and rendering when the browser tab is hidden (`document.hidden`), resuming instantly when active.
- 📡 **Data Ingestion & Paid API Guide**: Complete empirical latency and staleness analysis detailed in [`DATA_INGESTION_AUDIT_AND_API_RECOMMENDATION.md`](DATA_INGESTION_AUDIT_AND_API_RECOMMENDATION.md).

---

### 3. Interactive Analytical Web Platform (Streamlit Alternative)
Launch the standalone exploratory analytical dashboard:
```bash
streamlit run app.py
```
*Access in browser at `http://localhost:8501` (when server.py is stopped).*
- 🛡️ **Statutory Taxes & Risk**: Jurisdiction fee breakdown and Kelly sizing status.
- 🧪 **Walk-Forward Strategy Backtest**: 1-click historical audit with zero lookahead bias.
- 💼 **Live Paper-Trading & Verified Ledger**: Active position management, one-click order execution, and live PnL audit.

---

### 3. Leak-Free Walk-Forward Backtester
Backtest strategies across daily or intraday historical bars:
```bash
# Backtest Gold (GC=F) on daily swing bars:
python backtest.py --ticker "GC=F" --period "2y"

# Backtest Gold (GC=F) intraday on 1-hour bars:
python backtest.py --ticker "GC=F" --period "60d" --interval "1h"

# Backtest US Tech (NVDA):
python backtest.py --ticker "NVDA" --period "1y"

# Backtest Indian Equities (Reliance):
python backtest.py --ticker "RELIANCE.NS" --period "2y"
```

---

### 4. Background Market Observer & Alert Dispatcher (Daemon)
Runs in the background, continuously scanning watchlists and dispatching instant alerts or auto-executing orders:
```bash
# Run a single audit scan across monitored assets:
python monitor.py --once

# Run continuous observer daemon checking every 15 minutes:
python monitor.py --interval 900 --min-prob 0.55

# Enable automated order execution into the live ledger:
python monitor.py --interval 900 --auto-trade

# Monitor custom universe with Discord webhook alerts:
python monitor.py --universe "GC=F,EURUSD=X,NVDA,BTC-USD" --discord-webhook "https://discord.com/api/webhooks/..."
```

---

### 5. Production SaaS REST API Backend
Launch the high-performance FastAPI server to serve web apps, mobile apps, or SaaS subscribers:
```bash
python server.py
# Or directly via uvicorn:
uvicorn server:app --host 0.0.0.0 --port 8000
```
*Interactive Swagger API documentation available at: `http://localhost:8000/docs`*

#### SaaS Endpoints:
- `POST /api/auth/register`: Issues subscriber API keys with tier access (`FREE`, `PRO`, `INSTITUTIONAL`).
- `GET /api/auth/profile`: Returns user tier, daily quota, and authorized feature set.
- `GET /api/forecast/{ticker}`: Real-time neuro-causal prediction, neural conviction, regime, and volatility cone.
- `POST /api/scan`: Batch scanning across assets with HRP portfolio weights.
- `POST /api/backtest`: Walk-forward simulation returning trade logs and equity curve.
- `GET /api/broker/account`: Live account balance, cash, margin, and MTM PnL.
- `GET /api/broker/positions`: Active open positions.
- `POST /api/broker/order`: Submits market orders with exact friction deduction.
- `POST /api/broker/close/{position_id}`: Closes position and realizes PnL.
- `GET /api/broker/trades`: Returns verified historical trade ledger.
- `POST /api/webhook/alert`: Ingests TradingView or external bot alerts.

---

## 🧭 User-Controlled Trading Session Setup System

SYNAPSE-TITAN features a guided **6-Step Trading Session Setup Wizard** and quantitative session governance system. Before the autonomous paper-trading engine can execute trades, users explicitly configure and approve their session parameters.

### 1. Guided 6-Step Setup Wizard
1. **Market Jurisdiction**: Select between **US Equities** (`USD`), **Indian Equities** (`INR`), **Cryptocurrencies**, **Commodities**, and **Forex**. Market hours, statutory taxes, and currency adapt dynamically.
2. **Approved Basket Selection**: Select 1 to 20 instruments. Use the **Auto-select for me** feature powered by `UniverseSelector` to filter liquid candidates based on Average Daily Volume ($ADV \ge \$5\text{M}$ / $\text{₹}50\text{M}$), bid-ask spread ($\le 25\text{ bps}$), data quality ($Q \ge 0.90$), and volatility.
3. **Holding Horizon**: Binds model parameters across **1 Hour** (`5m` bars), **1 Day** (`15m`/`1h` bars), or **1 Week** (`1d` bars).
4. **Session Duration & Policy**: Choose duration presets (`1h`, `4h`, `1d`, `1wk`), custom intervals, or **Manual Stop**, with selectable end-policies (`CLOSE_ALL` liquidation vs `KEEP_OPEN` preservation).
5. **Virtual Capital Allocation**: Allocate virtual funds in local currency ($1,000 to $10,000,000). Features a strict paper-trading isolation guarantee and model invariance guarantee.
6. **Confirmation Review**: Audit parameters with one-click jump-edit links before launching.

### 2. Quantitative Universe & Opportunity Decision Engine (`src/strategy/`)
- **`UniverseSelector`**: Filters assets through quantitative gates (spread $\le 25\text{ bps}$, liquidity, missing bar ratio).
- **`TradeEvaluator`**: Computes calibrated Net Expectancy with an uncertainty margin:
  $$EV = (P_{\text{win}} - 1.0\sigma_p) \cdot E[W] - (P_{\text{loss}} + 1.0\sigma_p) \cdot E[L] - \text{Friction}$$
  Rejects trades with non-positive expectancy ($EV \le 0$).
- **`PortfolioSelector`**: Fractional Kelly & HRP allocation enforcing an absolute **100% Cash Guarantee** when opportunities lack positive expectancy.
- **`DecisionExplainer`**: Provides transparent mathematical explanations for every accepted trade, rejected trade, and cash preservation decision.

### 3. Session REST API Endpoints (`/api/sessions`)
- `GET /api/sessions/status`: Physical exchange session status, countdowns, and trading holiday tracking.
- `GET /api/sessions/active`: Returns currently active operational session (`RUNNING` or `PAUSED`).
- `POST /api/sessions/recommendations`: Quantitative candidate filtering via `UniverseSelector`.
- `GET /api/sessions`: List sessions with status and market filtering.
- `POST /api/sessions`: Creates a new session in `CREATED` state.
- `GET /api/sessions/{session_id}`: Retrieves details for a specific session.
- `PUT /api/sessions/{session_id}`: Updates mutable parameters of a `CREATED` or `PAUSED` session.
- `POST /api/sessions/{session_id}/start`: Launches a session, sets horizon parameters, and arms the bot.
- `POST /api/sessions/{session_id}/pause`: Suspends entries while preserving open positions.
- `POST /api/sessions/{session_id}/resume`: Resumes a paused session and extends the countdown timer.
- `POST /api/sessions/{session_id}/stop`: Terminates session and executes `CLOSE_ALL` / `KEEP_OPEN` policy.
- `GET /api/sessions/{session_id}/performance`: Computes isolated session KPIs, win rate, and profit factor.

---

## ⚡ Hardware Acceleration & NVIDIA RTX 4060 GPU

The engine includes auto-probing hardware orchestration (`src/models/gpu_acceleration.py`):
- **Detected Hardware**: NVIDIA GeForce RTX 4060 Laptop GPU (8,188 MiB VRAM), Driver 617.42.
- **Compute Architecture**: Ada Lovelace (Tensor Cores with native FP16 and BF16 acceleration).
- **Execution Architecture**: CPU-optimized execution by default for statistical pipelines (HMM, ADF, LightGBM) with parallel PyTorch tensor acceleration for deep sequence models and heavy multi-ticker matrix batching.

---

## 🐳 Docker & Cloud SaaS Deployment

Deploy the entire SaaS stack with Docker Compose:

```bash
docker-compose up -d --build
```
This automatically boots:
- **FastAPI REST API**: Port `8000`
- **Streamlit Web Dashboard**: Port `8501`
- **Background Observer Daemon**: Continuously scanning on a 15-minute cadence.

---

## 📁 Directory Layout

```text
trade_bot/
├── config/
│   └── config.yaml              # Watchlists, intervals, risk parameters, and taxes
├── data/
│   ├── alerts/                  # Real-time alert logs (alerts.json)
│   ├── cache/                   # Local disk cache for market data (auto-generated)
│   └── trading_ledger.db        # SQLite database for accounts, positions, and trades
├── src/
│   ├── backtest/
│   │   └── engine.py            # Walk-forward backtester & performance auditor
│   ├── data/
│   │   ├── downloader.py        # Universal historical data downloader (Equities, FX, Gold, Crypto)
│   │   └── normalizer.py        # Data sanitization, alignment, return calculator
│   ├── features/
│   │   ├── fracdiff.py          # Minimal d* memory-preserving fractional differencing
│   │   ├── information_bars.py  # Dollar and volume sampled bars
│   │   └── technical.py         # Leak-free trend, momentum & volatility features
│   ├── models/
│   │   ├── foundation_prior.py  # Forward quantile volatility cones (q10, q50, q90)
│   │   ├── gpu_acceleration.py  # NVIDIA CUDA orchestration & batch sequence forecaster
│   │   ├── hrp_allocator.py     # Hierarchical Risk Parity & Marchenko-Pastur RMT
│   │   ├── meta_labeler.py      # Two-stage meta-labeling & LightGBM secondary model
│   │   └── regime_hmm.py        # Hidden Markov Model 3-state regime classifier
│   ├── execution/
│   │   ├── auth.py              # SaaS API key auth, quotas, and subscription tiers
│   │   ├── broker.py            # Autonomous paper-trading & broker execution engine
│   │   ├── frictions.py         # Statutory fee models (Indian STT/GST, US, Forex, Crypto)
│   │   └── guardrails.py        # Fractional Kelly sizing & convex drawdown controls
│   ├── observer/
│   │   └── monitor.py           # Background observer daemon & notification dispatcher
│   └── pipeline.py              # Master quantitative prediction pipeline
├── app.py                       # Interactive Streamlit Web UI (Forecasts, Backtests, Live Ledger)
├── backtest.py                  # CLI walk-forward backtest runner
├── cli.py                       # High-speed terminal scanner
├── monitor.py                   # CLI background observer daemon
├── server.py                    # Production FastAPI REST backend for cloud SaaS
├── Dockerfile                   # Cloud container build specification
├── docker-compose.yml           # Multi-container orchestration (API + Dashboard + Daemon)
├── requirements.txt             # Python dependencies
└── README.md                    # System documentation
```
