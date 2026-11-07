# ⚡ SYNAPSE-TITAN: Autonomous Trading Terminal & Quantitative Engine

An institutional-grade, multi-asset **Quantitative Observation, Volatility Forecasting, Autonomous Paper-Trading Broker, and Single-Page Web Terminal**.

SYNAPSE-TITAN replaces retail indicator strategies with empirical quantitative mathematics, combining fractional differentiation, 3-state regime switching, neural geometric pattern recognition, statutory friction deduction, and Fractional Kelly capital sizing.

---

## 🚀 Quick Start

### 1. Prerequisites & Installation
Ensure Python 3.10+ and Node.js 18+ are installed:
```bash
# 1. Install Python backend dependencies
pip install -r requirements.txt

# 2. Build the unified React 18 production frontend
cd frontend
npm install
npm run build
cd ..
```

### 2. Launch the Autonomous Trading Terminal
Start the unified FastAPI server (serves both the REST API and the React trading terminal):
```bash
python server.py
# Or directly via uvicorn:
uvicorn server:app --host 0.0.0.0 --port 8501
```
- **Web Terminal**: Open [http://localhost:8501](http://localhost:8501) in your browser.
- **Interactive OpenAPI Documentation**: Open [http://localhost:8501/docs](http://localhost:8501/docs).

### 3. CLI Walk-Forward Backtester
Backtest strategies across daily swing or intraday bars with zero lookahead bias:
```bash
# Backtest Gold Futures (GC=F) on daily bars:
python backtest.py --ticker "GC=F" --period "2y"

# Backtest Tech Equities (NVDA) on 1-hour bars:
python backtest.py --ticker "NVDA" --period "60d" --interval "1h"
```

### 4. Background Market Observer & Alert Dispatcher (Daemon)
Run continuous market scanning and alert generation without opening the UI:
```bash
# Single audit scan across active watchlist:
python monitor.py --once

# Continuous 15-minute background scanning daemon:
python monitor.py --interval 900 --min-prob 0.55
```

---

## 🏛️ Foundational Quantitative Architecture

1. **Fractional Differentiation ($d^*$ Order)**: Based on Marcos López de Prado (*AFML*, Chapter 5). Preserves long memory while guaranteeing stationarity (ADF test $p < 0.05$).
2. **Hidden Markov Model (HMM) Regimes**: Dynamically classifies markets into 3 latent regimes:
   - `State 0: Low-Vol Trending` (Momentum continuation)
   - `State 1: Choppy Range-Bound` (Barrier compression / mean-reversion)
   - `State 2: High-Vol Crisis` (Automatic circuit breaker & capital quarantine)
3. **GPU Neural Ensemble Fusion**:
   $$\text{Final Conviction} = 65\% \text{ LightGBM (Causal Trees)} + 35\% \text{ PyTorch Conv1D/Attention (3D Geometric Candle Shape)}$$
4. **Hierarchical Risk Parity (HRP)**: Tree clustering and recursive bisection with Marchenko-Pastur Random Matrix covariance de-noising.
5. **Exact Statutory Friction Deduction**: Deducts real-world jurisdiction taxes and slippage to ensure zero illusory alpha:
   - **Indian Equities**: 0.025% STT, 18% GST on turnover/brokerage, stamp duty, SEBI turnover fees.
   - **US Equities**: SEC Section 31 fees, FINRA TAF, taker exchange fees.
   - **Forex & Commodities**: Contract exchange fees and bid-ask spread hurdles.
   - **Crypto**: 4 bps taker liquidity fees.
6. **Risk Guardrails & 100% Cash Guarantee**: Fractional Kelly sizing with convex drawdown dampening. Automatically preserves 100% of capital in cash when opportunities fail to demonstrate positive Net Expectancy ($EV \le 0$).
7. **User-Controlled 6-Step Trading Session Wizard**: Guided session configuration allowing users to choose jurisdiction, approved asset baskets, holding horizons (`1h`, `1d`, `1wk`), virtual capital, and expiration policies (`CLOSE_ALL` vs `KEEP_OPEN`).

---

## 🌐 Supported Multi-Asset Universes

| Market Class | Example Tickers | Jurisdiction Profile | Supported Resolutions | Typical Friction |
| :--- | :--- | :--- | :--- | :--- |
| **US Equities** | `NVDA`, `AAPL`, `MSFT`, `TSLA`, `SPY` | `US` | `1h`, `1d` | ~2.5 bps |
| **Indian NSE/BSE** | `RELIANCE.NS`, `TCS.NS`, `INFY.NS`, `HDFCBANK.NS` | `NSE_CASH` | `1h`, `1d` | ~7.2 – 9.5 bps |
| **Cryptocurrencies** | `BTC-USD`, `ETH-USD`, `SOL-USD` | `CRYPTO` | `15m`, `1h`, `1d` | ~8.0 bps |
| **Commodities** | `GC=F` (Gold), `SI=F` (Silver), `CL=F` (Crude Oil) | `COMMODITY` | `15m`, `1h`, `1d` | ~3.0 bps |
| **Forex (FX)** | `EURUSD=X`, `GBPUSD=X`, `USDJPY=X` | `FOREX` | `15m`, `1h`, `1d` | ~1.5 bps |

---

## ⚡ Hardware Acceleration

The engine includes auto-probing hardware orchestration (`src/models/gpu_acceleration.py`):
- **CUDA Acceleration**: Automatically detects NVIDIA CUDA GPUs with Tensor Core FP16/BF16 sequence batching.
- **CPU Fallback**: Automatic, zero-configuration fallback to vectorized CPU execution for non-CUDA systems.

---

## 🐳 Docker Deployment

Run the complete stack using Docker Compose:
```bash
docker compose up -d --build
```
- **API & Trading Terminal**: Port `8000` (FastAPI backend mounting React SPA)
- **Observer Daemon**: Headless background monitoring service
- **Security**: The container runs under an unprivileged non-root user (`titan`).

---

## 📚 Technical Documentation

Comprehensive architectural papers and audit reports are consolidated in the [`docs/`](docs/) directory:

- [Technical Architecture Whitepaper](docs/SYNAPSE_TITAN_WHITEPAPER.md)
- [Quantitative Architecture Audit & Solutions](docs/SYNAPSE_TITAN_EVALUATION_AND_SOLUTIONS.md)
- [Data Ingestion Benchmarking & Paid API Guide](docs/DATA_INGESTION_AUDIT_AND_API_RECOMMENDATION.md)
- [Project Milestones & Roadmap](docs/PROJECT.md)
- [Dual-Track Testing Infrastructure](docs/TEST_INFRA.md)
- [Test Readiness Certification](docs/TEST_READY.md)

---

## 📁 Directory Layout

```text
trade_bot/
├── config/
│   └── config.yaml              # Watchlists, intervals, risk parameters, and taxes
├── data/
│   ├── alerts/                  # Real-time alert logs (alerts.json)
│   ├── cache/                   # Local disk cache for market data (auto-generated)
│   └── trading_ledger.db        # SQLite database for accounts, sessions, and trades
├── docs/                        # Consolidated architecture, roadmap, and audit documentation
├── frontend/                    # Single Consolidated UI: React 18 + TS + Tailwind + Lightweight Charts
│   ├── src/                     # React components, hooks, ring buffers, and session wizard
│   └── dist/                    # Compiled production assets served by server.py
├── src/
│   ├── backtest/                # Walk-forward backtesting engine
│   ├── data/                    # Historical data downloader & normalizer
│   ├── features/                # Fractional differencing, information bars, technical features
│   ├── models/                  # Volatility cones, GPU acceleration, HRP, LightGBM, Regime HMM
│   ├── execution/               # Paper broker, friction models, risk guardrails, session manager
│   ├── strategy/                # Trade evaluation, ranking, portfolio sizing, decision explainer
│   └── pipeline.py              # Master quantitative prediction pipeline
├── backtest.py                  # CLI walk-forward backtest runner
├── cli.py                       # High-speed terminal scanner
├── monitor.py                   # CLI background observer daemon
├── server.py                    # Unified FastAPI REST backend & React SPA host
├── Dockerfile                   # Cloud container build specification (non-root)
├── docker-compose.yml           # Container orchestration (API + Observer)
├── requirements.txt             # Core Python dependencies
└── README.md                    # Project overview & quick start
```
