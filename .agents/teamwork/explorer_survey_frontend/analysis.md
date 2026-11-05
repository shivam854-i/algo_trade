# SYNAPSE-TITAN: Comprehensive Frontend Architecture Survey & Requirements R1/R2 Implementation Blueprint

**Document**: Frontend Survey and Technical Specification  
**Explorer**: `explorer_survey_frontend`  
**Date**: 2026-11-05  
**Target Repository**: `C:\Users\Shivam\Desktop\trade_bot\frontend`  
**Focus Requirements**: R1 (Guided Onboarding Wizard UI) & R2 (Autonomous Bot Behavior & UI Dashboard Controls)  

---

## 1. Executive Summary

This investigation conducts an exhaustive audit of the existing React/TypeScript frontend cockpit for the **SYNAPSE-TITAN** algorithmic paper-trading platform and designs the complete architectural blueprint for **Requirement R1 (Guided Onboarding Wizard UI)** and **Requirement R2 (Autonomous Bot Behavior, Session Lifecycle, and UI Dashboard Controls)**.

### Key Conclusions:
1. **Existing Frontend Health**: The current frontend is an institutional-grade, zero-GC, bounded-memory cockpit built on React 18, Vite 5, Tailwind CSS, TypeScript 5, and Lightweight Charts. Tests execute with 100% pass rates (22 tests across 4 suites in ~2.0s under Vitest), and production builds compile cleanly (`tsc && vite build` in ~2.5s). Memory footprint remains strictly bounded (< 18 MB heap under 1,000,000 streamed ticks).
2. **Current Gaps Against R1 & R2**:
   - The current UI launches directly into the main cockpit with pre-selected default tickers (e.g. `NVDA`) and default running states. It lacks a **formal session setup wizard gating flow**, allowing ad-hoc asset selection and order entry without an explicitly confirmed Trading Session configuration.
   - There is currently no persistent **Trading Session Lifecycle Model** in the frontend state machine tracking session state (`UNCONFIGURED`, `DRAFT`, `RUNNING`, `PAUSED`, `STOPPED`, `EXPIRED`), session duration countdowns, approved asset basket enforcement, or session-end position policies (`CLOSE_ALL_POSITIONS` vs. `KEEP_POSITIONS_OPEN`).
   - The Activity Feed currently parses log categories (`BOT`, `TRADE`, `PROFIT`, `STOP`, `RISK`, `SESSION`, `SYSTEM`), but lacks structured rendering for the new **`DecisionExplainer`** quantitative trade rationale (Net Expectancy, calibrated probabilities, uncertainty intervals, friction penalties).
3. **Architectural Solution**:
   - Introduce a multi-step **Guided Onboarding Wizard (`TradingSessionWizard`)** supporting 6 distinct phases: Market Selection, Instrument Selection (with manual search + UniverseSelector "Auto-select for me"), Trading Horizon Selection (differentiating holding period from session duration), Session Duration Selection (with custom duration and session-end position policy), Virtual Capital Allocation (with currency sensitivity INR vs. USD and boundary validation), and Final Confirmation.
   - Implement **Session Gating**: Autonomous bot execution and trade placement are strictly blocked until a session configuration is confirmed and launched.
   - Deploy persistent **Session Lifecycle Controls (START, PAUSE, STOP)** and an **Active Session Telemetry Bar** displaying live financial metrics in the correct currency, market regime, feed health, countdown timer, and approved basket chips.

---

## 2. Existing Frontend Codebase Audit

### 2.1 Configuration & Tooling
- **`package.json`**:
  - Name: `synapse-titan-terminal` (v2.0.0)
  - Core dependencies: `react` (18.3.1), `react-dom` (18.3.1), `lightweight-charts` (4.2.1), `lucide-react` (0.475.0).
  - Dev dependencies: `vite` (5.4.11), `typescript` (5.6.3), `tailwindcss` (3.4.17), `vitest` (2.1.8).
  - Scripts: `dev` (`vite`), `build` (`tsc && vite build`), `test` (`vitest run`).
- **`vite.config.ts`**:
  - Configures `@vitejs/plugin-react`.
  - Sets path alias `@` -> `./src`.
  - Development server runs on port 5173 with proxy `/api` -> `http://127.0.0.1:8501`.
  - Production build outputs to `dist/`, `sourcemap: false`, `chunkSizeWarningLimit: 1000`.
- **`tsconfig.json`**:
  - Target: `ES2020`, Module: `ESNext`, `moduleResolution: bundler`.
  - Strict type checking enabled (`strict: true`, `noUnusedLocals: true`, `noUnusedParameters: true`, `noFallthroughCasesInSwitch: true`).
- **`tailwind.config.js`**:
  - Custom institutional dark palette under `theme.extend.colors.titan`:
    - `bg`: `#060911`, `card`: `#0c1220`, `cardElevated`: `#111a2e`
    - `border`: `rgba(148, 163, 184, 0.12)`, `borderHover`: `rgba(56, 189, 248, 0.3)`
    - `cyan`: `#38bdf8`, `emerald`: `#10b981`, `rose`: `#f43f5e`, `amber`: `#f59e0b`

### 2.2 Component Hierarchy & Analysis
The existing UI layout in `src/App.tsx` is structured as follows:

```
App.tsx (Root Cockpit)
├── Header.tsx (Institutional Cockpit Top Navbar)
│   ├── Brand & Version ("SYNAPSE-TITAN v2.0 PRO")
│   ├── Paper Trading Badge (Virtual Account Protection)
│   ├── Market Data Feed Mode (LIVE / DELAYED / SANDBOX / STALE)
│   ├── Page Visibility Badge (ACTIVE / TAB HIDDEN)
│   ├── GPU Hardware Telemetry (RTX 4060, VRAM, Precision)
│   └── Tick Count & Manual Refresh Action
│
├── MarketSessionRibbon.tsx (Exchange Sessions Grid)
│   ├── NSE India (09:15-15:30 IST)
│   ├── NYSE / NASDAQ (09:30-16:00 ET)
│   ├── CME COMEX (23h/day Mon-Fri)
│   └── Crypto 24/7 (UTC)
│   * Dynamic 1s countdown timer with offline fallback heuristics
│
├── KpiRibbon.tsx (6 Institutional Performance Metric Cards)
│   ├── Virtual Equity ($ / Cash)
│   ├── Bot Return vs. Market Return & Sharpe
│   ├── Exposure % / Max Drawdown % / Alpha
│   ├── Unrealized MTM PnL vs Realized PnL
│   ├── Win Rate % & Profit Factor
│   └── Transaction Costs (Commissions, Spread, Slippage)
│
├── AssetSelector.tsx (Watchlist & Asset Selection Bar)
│   ├── Category Tabs (ALL, NSE, US, COMMODITY, CRYPTO, FOREX)
│   ├── Instant Client/Server Search Dropdown (Ctrl+K or "/")
│   ├── Watchlist Carousel with Real-Time Direction & Conviction
│   ├── Arming Checkboxes (toggle bot evaluation per asset)
│   └── Quick 1-Click Bot Trade Order Action
│
├── Core Cockpit Grid Layout (12-column responsive grid)
│   ├── Left Column (7/12)
│   │   ├── ChartContainer.tsx (Lightweight Charts WebGL/Canvas)
│   │   │   ├── Primary Price Line (Sky Blue)
│   │   │   ├── Target Price Barrier Line (Emerald Dashed)
│   │   │   ├── Stop Loss Barrier Line (Rose Dashed)
│   │   │   ├── Entry Price Line (Amber Dotted)
│   │   │   └── Explicit chart.remove() memory lifecycle cleanup
│   │   └── PositionsTable.tsx (Active Positions & Closed Ledger)
│   │       ├── Active Positions with dynamic Stop-to-Target visual sliders
│   │       ├── Close Position at Market & Flatten All actions
│   │       └── Closed Trades History Table with Net PnL and Friction paid
│   │
│   └── Right Column (5/12)
│       ├── OrderControls.tsx (Manual & Bot-Assisted Execution)
│       │   ├── Auto-Bot Running/Paused Toggle
│       │   ├── Strict Exchange Hours vs 24/7 Sandbox Toggle
│       │   ├── Simulation Step Tick & Reset Account buttons
│       │   ├── Direction Tabs (BUY / SELL / BOT AUTO)
│       │   ├── Limit vs Market Order Ticket with Kelly sizing presets
│       │   └── Pre-Market Pending Orders Queue
│       └── ActivityLog.tsx (Bounded Streaming Event Log)
│           ├── Bounded RingBuffer (Max 100 items)
│           ├── Category Filter Tabs (ALL, BOT, TRADE, PROFIT, RISK, SESSION)
│           ├── Robust parser for dicts, bracketed text, and raw strings
│           └── Copy logs to clipboard
│
└── Institutional Status Footer (Memory leak shield, ring buffer stats, GC monitor)
```

### 2.3 Performance & Verification Tooling
- **`src/utils/ringBuffer.ts`**: Bounded circular buffer guaranteeing $O(1)$ push/peek operations without reallocating arrays, preventing JavaScript garbage collector churn during streaming.
- **`src/hooks/usePageVisibility.ts`**: Tracks browser tab visibility via `document.hidden`. Automatically halts background intervals and network polling when minimized/inactive, eliminating background CPU/battery drain.
- **`src/hooks/useDashboardStream.ts`**: Primary polling hook (2.5s interval). Automatically steps the simulation when `bot_status.is_running` is true, or refreshes state snapshot when paused. Synchronizes incoming telemetry into pre-allocated ring buffers.
- **Automated Test Results**:
  - Vitest: 4 test files, 22 unit tests passing in 2.05s.
  - Stress scripts:
    - `stress_page_visibility.mjs`: 500 tab flapping cycles, zero interval leaks, single wake-up snapshot.
    - `stress_ring_buffer.mjs`: 1,100,000 pushes across chart and log buffers, memory remained strictly bounded at 14.68 MB (well within the 150 MB ceiling).
  - Production build: `npm run build` completed in 2.48s with zero TypeScript or bundle errors.

---

## 3. Requirement R1: Guided Onboarding Wizard UI Design

### 3.1 Architectural Principles
1. **Mandatory Gating**: The user cannot access the active trading controls or initiate autonomous bot operations until a trading session is explicitly configured, validated, and launched.
2. **Provider Awareness**: The wizard queries backend provider capabilities and feed health to disable unsupported markets dynamically (e.g. if Alpaca/IEX is down or Indian NSE feeds are offline).
3. **Separation of Concerns**: The wizard strictly distinguishes between **Trading Horizon** (the model's holding period and signal timeframe) and **Session Duration** (the wall-clock operational duration of the bot).
4. **Deterministic Validation**: All user inputs (capital, symbols, duration) are validated locally in the UI with instant feedback and validated independently on the backend prior to session creation.

### 3.2 Detailed Step-by-Step Wizard Specification

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        SYNAPSE-TITAN TRADING SESSION WIZARD                            │
├─────────────┬─────────────┬─────────────┬─────────────┬─────────────┬──────────────────┤
│ 1. Market   │ 2. Basket   │ 3. Horizon  │ 4. Duration │ 5. Capital  │ 6. Confirmation  │
│  Selection  │  Selection  │  Selection  │  & Policy   │ Allocation  │    & Launch      │
└─────────────┴─────────────┴─────────────┴─────────────┴─────────────┴──────────────────┘
```

#### Step 1: Market Selection
- **Objective**: Select the single asset market for the trading session.
- **Supported Market Cards**:
  1. **Indian Equities (NSE)**:
     - Schedule: `09:15–15:30 IST (Mon–Fri)`
     - Benchmark: `NIFTY 50 / RELIANCE.NS`
     - Base Currency: `INR (₹)`
     - Providers: `Yahoo Finance / NSE Feed`
  2. **US Equities (NYSE / NASDAQ)**:
     - Schedule: `09:30–16:00 ET (Mon–Fri)`
     - Benchmark: `S&P 500 / NVDA / AAPL`
     - Base Currency: `USD ($)`
     - Providers: `Alpaca (IEX Realtime) / Yahoo Finance`
  3. **Cryptocurrencies (24/7)**:
     - Schedule: `24/7/365 Non-Stop`
     - Benchmark: `BTC-USD / ETH-USD`
     - Base Currency: `USD ($)`
     - Providers: `Alpaca Crypto / Yahoo Finance`
  4. **Forex Majors (FX 24/5)**:
     - Schedule: `24/5 Mon 00:00 UTC – Fri 21:00 UTC`
     - Benchmark: `EUR/USD, GBP/USD, USD/JPY`
     - Base Currency: `USD ($)`
     - Providers: `Yahoo Finance FX`
  5. **Commodities (CME / COMEX / NYMEX)**:
     - Schedule: `23h/day Mon–Fri (Break 17:00–18:00 ET)`
     - Benchmark: `GC=F (Gold), CL=F (Crude Oil)`
     - Base Currency: `USD ($)`
     - Providers: `Yahoo Finance Futures`
- **UI Card Features**:
  - Market title, region, exchange clock, and feed status badge (`CONNECTED`, `DELAYED`, `OFFLINE`).
  - Unsupported or unconfigured markets are visually disabled (reduced opacity, grayscale icon) with an informational badge: *"Feed Not Configured"*.
  - Selecting a market dynamically adjusts the default currency symbol (`₹` for NSE, `$` for all others) and limits the catalog of tradable instruments in Step 2.

#### Step 2: Instrument Selection (Universe Basket)
- **Objective**: Define the approved instrument universe the autonomous bot is allowed to trade.
- **Key Invariant**: *The bot is strictly prohibited from opening trades for any instrument outside this approved basket.*
- **Features**:
  - **Manual Search Bar**: Fast type-ahead filtering by ticker or company name. Keyboard shortcut `/` to focus.
  - **Available Instruments Grid**: Filtered to the selected market. Shows symbol, name, sector, exchange, and live quote/spread if available.
  - **Basket Counter & Selected Chips**: Displays selected instruments with a 1-click removal ("x") button (e.g., `Basket (4/10): [NVDA x] [AAPL x] [MSFT x] [AMD x]`).
  - **Basket Constraints**: Minimum 1 instrument, maximum recommended 15 instruments for risk diversification.
  - **"Auto-select for me" Feature**:
    - Trigger button: *"Auto-select for me (AI Quant Universe Selector)"*
    - On click, issues request to `POST /api/sessions/recommendations` with the selected market and horizon.
    - Displays a modal or preview card showing the recommended basket along with the systematic quantitative rationale:
      - Liquidity rank, average daily volume, bid-ask spread bps.
      - Volatility profile and compatibility with the selected horizon.
      - Example rationale: *"Selected top 5 liquid US tech & index assets (NVDA, AAPL, MSFT, AMD, SPY) with spread < 3 bps and high regime alignment for intraday momentum."*
    - One-click button: *"Accept & Apply to Basket"*.

#### Step 3: Trading Horizon Selection
- **Objective**: Choose the strategy execution and holding horizon for the quantitative engine.
- **Options**:
  1. **1 Hour (High-Frequency / Scalping)**:
     - Bar Interval: `1m / 5m`
     - Typical Holding Duration: `5 to 60 minutes`
     - Characteristics: High trade frequency, tight triple-barrier stops/targets (0.4% to 1.2%), strict spread-to-volatility filters.
  2. **1 Day (Intraday Momentum / Mean-Reversion)**:
     - Bar Interval: `15m / 1h`
     - Typical Holding Duration: `2 to 8 hours`
     - Characteristics: Medium trade frequency, moderate triple-barrier stops/targets (1.5% to 3.5%), regime-guided Kelly sizing.
  3. **1 Week (Multi-Day Swing / Positional)**:
     - Bar Interval: `1h / 1d`
     - Typical Holding Duration: `1 to 5 days`
     - Characteristics: Low trade frequency, wide volatility-adjusted stops/targets (4.0% to 8.0%), macro HMM regime alignment.
- **Critical Educational Callout**:
  - The UI must prominently feature a callout box distinguishing **Trading Horizon** from **Session Duration**:
    > **⚠️ Trading Horizon ≠ Session Duration**  
    > - **Trading Horizon** dictates the model's feature window, signal bar intervals, and expected position holding duration.  
    > - **Session Duration** (configured in Step 4) specifies how long the bot software operates before halting operations.

#### Step 4: Session Duration Selection & Session-End Position Policy
- **Objective**: Specify the operational running duration for the session and how open positions are handled when the session ends.
- **Duration Presets**:
  - `1 Hour` (e.g. quick test / scalping run)
  - `4 Hours` (e.g. morning session)
  - `1 Day` (runs until exchange closing bell)
  - `1 Week` (continuous multi-day execution)
  - `Custom Duration` (numeric input in hours/minutes or target end timestamp)
  - `Manual Stop` (runs indefinitely until user explicitly clicks STOP on the dashboard)
- **Configurable Session-End Position Policy**:
  - Option A: **`CLOSE_ALL_POSITIONS` ("Flatten to Cash")**  
    *When session time expires, the engine immediately liquidates all open positions at market, books realized P&L, cancels pending orders, and converts 100% of the portfolio to cash.*
  - Option B: **`KEEP_POSITIONS_OPEN` ("Manual Management")**  
    *When session time expires, the engine halts new trade entries but keeps existing open positions intact with active stop-loss/take-profit barriers for manual trader oversight.*

#### Step 5: Virtual Capital Allocation
- **Objective**: Allocate virtual paper capital to the session.
- **Validation Rules**:
  - Strictly positive numeric amount.
  - Zero, negative, and non-numeric values are prevented with clear error hints.
  - Boundary limits:
    - **USD Markets (US, Crypto, Forex, Commodities)**: Min `$1,000` | Max `$10,000,000` | Default `$100,000`
    - **INR Markets (Indian Equities)**: Min `₹50,000` | Max `₹500,000,000` | Default `₹1,000,000`
- **UI Elements**:
  - Currency symbol prefix dynamically rendered (`$` or `₹`).
  - Quick-preset buttons:
    - USD: `$10,000`, `$50,000`, `$100,000`, `$500,000`
    - INR: `₹1,00,000`, `₹5,00,000`, `₹10,00,000`, `₹50,00,000`
  - Explanatory note: *"Virtual capital dynamically scales Kelly fractional position sizes without modifying neural confidence or model prediction outputs."*

#### Step 6: Final Confirmation Step
- **Objective**: Present a comprehensive review of all configured session parameters before launch.
- **Summary Grid**:
  - **Market**: Indian Equities / US Equities / etc. (with exchange hours & feed status)
  - **Approved Basket**: Count of selected tickers and list of symbols (e.g. `[NVDA, AAPL, MSFT, AMD]`)
  - **Trading Horizon**: 1 Hour / 1 Day / 1 Week (with signal interval explanation)
  - **Session Duration**: e.g., `4 Hours` or `Manual Stop`
  - **Session-End Policy**: `Flatten All Positions` or `Keep Positions Open`
  - **Virtual Capital**: e.g. `$100,000.00 USD` or `₹10,00,000.00 INR`
  - **Execution Mode**: `Strict Virtual Paper Trading (Zero Real-Money Risk)`
- **Actions**:
  - **"Edit" Button** on each summary card to jump back to any step.
  - **"Confirm & Launch Session" Button**:
    - Dispatches session configuration to `POST /api/sessions/create` and `POST /api/sessions/{id}/start`.
    - Displays transition animation / loader.
    - Closes wizard, enables dashboard telemetry, and unlocks cockpit controls!

---

## 4. Requirement R2: Autonomous Bot Behavior & UI Dashboard Controls Design

### 4.1 Session Gating Architecture
The frontend enforces strict gating through a centralized state machine:

```
                      ┌──────────────────────┐
                      │     UNCONFIGURED     │
                      │  (No Active Session) │
                      └──────────┬───────────┘
                                 │ User completes Wizard
                                 ▼
                      ┌──────────────────────┐
                      │     DRAFT/READY      │
                      │  (Config Confirmed)  │
                      └──────────┬───────────┘
                                 │ User clicks "START"
                                 ▼
    ┌────────────────────────────────────────────────────────┐
    │                        RUNNING                         │
    │  • Live feed telemetry streaming                       │
    │  • Opportunity scanning across approved basket only    │
    │  • Kelly allocation & paper order execution            │
    │  • Real-time countdown timer ticking                   │
    └───────────────▲────────────────────────┬───────────────┘
                    │ User clicks "RESUME"   │ User clicks "PAUSE"
                    │                        ▼
    ┌───────────────┴────────────────────────────────────────┐
    │                        PAUSED                          │
    │  • No new trade entries initiated                      │
    │  • Open positions monitored for SL/TP barriers         │
    │  • Telemetry streams live                              │
    └────────────────────────────────────────┬───────────────┘
                                             │ User clicks "STOP" or
                                             │ Duration expires
                                             ▼
                      ┌──────────────────────┐
                      │   STOPPED / EXPIRED  │
                      │  • Policy executed   │
                      │  • New session prompt│
                      └──────────────────────┘
```

- When `status === "UNCONFIGURED"`:
  - The Cockpit shows a persistent banner: *"No Active Trading Session. Complete Setup Wizard to Activate Autonomous Engine."*
  - The manual order ticket and bot execution buttons are disabled.
  - A prominent *"Launch Setup Wizard"* modal/button is presented.
- When `status === "RUNNING"`:
  - Autonomous trading is active. Order ticket restricts ticker selection strictly to the approved basket.
- When `status === "PAUSED"`:
  - New entries halted; visual badge shows `PAUSED`.
- When `status === "STOPPED"` or `status === "EXPIRED"`:
  - If policy was `CLOSE_ALL_POSITIONS`, positions are shown as closed. Telemetry displays final session summary and offers *"Start New Session"*.

### 4.2 Persistent Controls Component (`SessionControls.tsx`)
Located persistently at the top of the dashboard or in the primary control bar:
- **START / RESUME Button**:
  - Green pulse indicator when running.
  - Calls `POST /api/sessions/{id}/start` or `POST /api/sessions/{id}/resume`.
- **PAUSE Button**:
  - Amber indicator when paused.
  - Calls `POST /api/sessions/{id}/pause`.
- **STOP Button**:
  - Shows modal: *"Are you sure you want to stop session #{session_id}? Session-end policy: [Close positions / Keep open]."*
  - On confirm: calls `POST /api/sessions/{id}/stop`.
- **NEW SESSION Button**:
  - Allows opening the Wizard to configure a fresh session.

### 4.3 Active Session Telemetry Bar (`SessionTelemetryBar.tsx`)
A dedicated glass-morphism ribbon positioned immediately below the header:
- **Session Identity**: Session ID (e.g. `#SES-20261105-01`), Market badge (e.g. `US Equities`), Base Currency (`USD`).
- **Session Clock / Countdown**:
  - For preset duration: Displays remaining time with 1s countdown: `Session Closes in: 03h 41m 12s`.
  - For manual stop: Displays elapsed runtime: `Running for: 01h 14m 20s (Manual Stop)`.
- **Approved Basket Chips**:
  - Chips showing all approved tickers (e.g. `[NVDA] [AAPL] [MSFT] [AMD] [SPY]`). Clicking a chip switches the active chart and asset view.
- **Horizon & Policy Badges**:
  - Horizon: `1 Day (15m bars)`
  - End Policy: `Flatten at Expiry` or `Keep Open`
- **Financial Telemetry Grid**:
  - Starting Capital: `$100,000.00` (or `₹10,00,000.00`)
  - Available Cash: `$78,250.00`
  - Invested Capital: `$22,450.00`
  - Unrealized MTM PnL: `+$1,280.00 (+1.28%)`
  - Realized PnL: `+$620.00 (+0.62%)`
  - Total Session Equity: `$101,900.00 (+1.90%)`
- **Market Regime Badge**:
  - Displays detected regime from HMM (e.g. `BULL_TREND`, `LOW_VOL_CONSOLIDATION`, `HIGH_VOL_CRISIS`).
- **Feed Health Badge**:
  - Feed status (`LIVE`, `DELAYED`, `SANDBOX`) with average latency in milliseconds.

### 4.4 DecisionExplainer Activity Feed Integration (`ActivityLog.tsx`)
The `ActivityLog` component is upgraded to parse and display rich **`DECISION`** events:
- **New Valid Category**: `DECISION` (in addition to `BOT`, `TRADE`, `PROFIT`, `STOP`, `RISK`, `SESSION`, `SYSTEM`).
- **Filter Tab**: Added `DECISION` tab to isolate quantitative reasoning events.
- **Rendering of Decision Rationale**:
  - Green border/badge for `ACCEPTED` trades, Amber/Rose border/badge for `REJECTED` trades.
  - Formatted breakdown:
    ```
    [14:32:05] [DECISION] NVDA • LONG ACCEPTED
    Net Expectancy: +1.42% | P(Win): 63.4% vs P(Loss): 36.6% | Confidence: 78% (±4.2%)
    Friction Cost: 6.2 bps | Sizing: Kelly 12.5% ($12,500) | Regime: BULL_TREND
    Rationale: "Strong directional momentum with positive expected return exceeding friction hurdle."
    ```
    ```
    [14:35:10] [DECISION] INTC • LONG REJECTED
    Net Expectancy: -0.32% | P(Win): 46.1% vs P(Loss): 53.9% | Confidence: 41%
    Friction Cost: 9.8 bps | Sizing: 0.0% ($0) | Regime: CONSOLIDATION
    Rationale: "Negative net expectancy after friction and high spread; capital preserved in cash."
    ```

### 4.5 Strict Virtual Paper-Trading Invariant Presentation
- Top header maintains the permanent badge: `PAPER TRADING • VIRTUAL ACCOUNT`.
- All monetary amounts clearly show `(Virtual)`.
- Disclaimers indicate that real brokerage order routing is completely isolated and blocked.

---

## 5. State Management & API Integration Contracts

### 5.1 Proposed TypeScript Data Types (`src/types/index.ts`)

```typescript
export type MarketType =
  | "INDIAN_EQUITIES"
  | "US_EQUITIES"
  | "CRYPTO"
  | "FOREX"
  | "COMMODITIES";

export type TradingHorizon = "1_HOUR" | "1_DAY" | "1_WEEK";

export type SessionDuration =
  | "1_HOUR"
  | "4_HOURS"
  | "1_DAY"
  | "1_WEEK"
  | "CUSTOM"
  | "MANUAL_STOP";

export type SessionEndPolicy = "CLOSE_ALL_POSITIONS" | "KEEP_POSITIONS_OPEN";

export type SessionStatus =
  | "UNCONFIGURED"
  | "DRAFT"
  | "RUNNING"
  | "PAUSED"
  | "STOPPED"
  | "EXPIRED";

export interface TradingSessionConfig {
  session_id?: string;
  market: MarketType;
  currency: "USD" | "INR";
  currency_symbol: string;
  instruments: string[];
  horizon: TradingHorizon;
  duration: SessionDuration;
  custom_duration_minutes?: number;
  session_end_policy: SessionEndPolicy;
  virtual_capital: number;
  status: SessionStatus;
  created_at?: string;
  started_at?: string;
  expires_at?: string;
  stopped_at?: string;
}

export interface UniverseRecommendation {
  market: MarketType;
  horizon: TradingHorizon;
  recommended_instruments: string[];
  rationale: string;
  criteria: {
    min_volume: number;
    max_spread_bps: number;
    min_liquidity_rank: number;
    regime_fit: string;
  };
  instrument_details: Record<
    string,
    {
      ticker: string;
      name: string;
      avg_volume: number;
      spread_bps: number;
      volatility_pct: number;
      score: number;
      reason: string;
    }
  >;
}

export interface DecisionExplanation {
  ticker: string;
  timestamp: string;
  direction: "LONG" | "SHORT";
  action: "ACCEPTED" | "REJECTED";
  net_expectancy_pct: number;
  win_probability: number;
  loss_probability: number;
  calibrated_confidence_pct: number;
  uncertainty_interval: [number, number];
  friction_bps: number;
  kelly_allocation_pct: number;
  allocated_capital: number;
  regime: string;
  rationale: string;
}

export interface SessionTelemetry {
  session_id: string;
  status: SessionStatus;
  market: MarketType;
  currency: string;
  currency_symbol: string;
  horizon: TradingHorizon;
  duration_label: string;
  session_end_policy: SessionEndPolicy;
  started_at?: string;
  expires_at?: string;
  seconds_remaining?: number;
  elapsed_seconds?: number;
  starting_capital: number;
  current_cash: number;
  invested_equity: number;
  total_equity: number;
  unrealized_pnl: number;
  realized_pnl: number;
  session_return_pct: number;
  approved_instruments: string[];
  active_regime: string;
  feed_status: string;
  average_latency_ms: number;
}
```

### 5.2 REST API Specifications (Between Frontend & Backend R3)

| Endpoint | Method | Payload / Params | Response | Purpose |
|---|---|---|---|---|
| `/api/sessions/create` | `POST` | `TradingSessionConfig` | `{ session: TradingSessionConfig, status: "DRAFT" }` | Validates & creates session in SQLite |
| `/api/sessions/active` | `GET` | None | `{ session: TradingSessionConfig \| null, telemetry: SessionTelemetry \| null }` | Retrieves current active session snapshot |
| `/api/sessions/{id}/start` | `POST` | None | `{ status: "RUNNING", started_at: string, telemetry: SessionTelemetry }` | Begins autonomous bot execution |
| `/api/sessions/{id}/pause` | `POST` | None | `{ status: "PAUSED", telemetry: SessionTelemetry }` | Pauses entry of new orders |
| `/api/sessions/{id}/resume` | `POST` | None | `{ status: "RUNNING", telemetry: SessionTelemetry }` | Resumes autonomous execution |
| `/api/sessions/{id}/stop` | `POST` | None | `{ status: "STOPPED", stopped_at: string, policy_executed: string }` | Stops session & executes end policy |
| `/api/sessions/recommendations` | `POST` | `{ market: MarketType, horizon: TradingHorizon, count?: number }` | `UniverseRecommendation` | UniverseSelector auto-selection rationale |
| `/api/sessions/{id}/performance` | `GET` | None | `{ financial_metrics: ..., trades_count: ... }` | Complete session audit metrics |

---

## 6. Component Hierarchy & File Layout Proposal

To maintain modularity and avoid monolithic files, the new frontend components should be organized into clean directories under `frontend/src/`:

```
frontend/src/
├── components/
│   ├── wizard/
│   │   ├── TradingSessionWizard.tsx       # Main Wizard container, step controller & modal/view
│   │   ├── Step1MarketSelection.tsx       # Market cards (NSE, US, Crypto, Forex, Commodities)
│   │   ├── Step2InstrumentSelection.tsx   # Search, multi-select, chips, "Auto-select for me"
│   │   ├── Step3HorizonSelection.tsx      # 1 Hour, 1 Day, 1 Week with educational callout
│   │   ├── Step4DurationSelection.tsx     # Duration presets + custom + manual + end policy
│   │   ├── Step5CapitalAllocation.tsx     # Positive capital input, currency symbol, bounds
│   │   ├── Step6Confirmation.tsx          # Full summary review & Confirm & Launch action
│   │   └── AutoSelectModal.tsx            # UniverseSelector recommendation rationale popup
│   │
│   ├── session/
│   │   ├── SessionTelemetryBar.tsx        # Active session metrics, countdown, basket chips
│   │   ├── SessionControls.tsx            # Persistent START, PAUSE, STOP buttons & modals
│   │   └── SessionExpiryModal.tsx         # Notification when session duration ends
│   │
│   ├── Header.tsx                         # (Existing, enhanced with session status)
│   ├── MarketSessionRibbon.tsx            # (Existing)
│   ├── KpiRibbon.tsx                      # (Existing, enhanced with dynamic currency symbols)
│   ├── AssetSelector.tsx                  # (Existing, filtered by approved session basket)
│   ├── ChartContainer.tsx                 # (Existing)
│   ├── PositionsTable.tsx                 # (Existing)
│   ├── OrderControls.tsx                  # (Existing, gated by session status)
│   └── ActivityLog.tsx                    # (Existing, enhanced with DECISION category)
│
├── hooks/
│   ├── useDashboardStream.ts              # (Enhanced with session polling & actions)
│   ├── useSessionLifecycle.ts             # Dedicated hook for session countdown & state machine
│   └── usePageVisibility.ts               # (Existing)
│
├── types/
│   └── index.ts                           # (Enhanced with R1/R2 session types)
│
└── utils/
    ├── currencyFormatter.ts               # Formats numbers with correct INR (₹) or USD ($)
    └── ringBuffer.ts                      # (Existing)
```

---

## 7. Testing & Verification Strategy

### 7.1 Unit Tests (Vitest)
1. **Wizard Validation Suite (`TradingSessionWizard.test.tsx`)**:
   - Market selection sets correct base currency (`INR` for NSE, `USD` for US/Crypto/FX).
   - Instrument selection enforces non-empty basket and rejects unapproved symbols.
   - Capital validation rejects zero, negative numbers, non-numeric strings, and values exceeding boundaries.
   - Horizon selection correctly binds model intervals (1 Hour -> 5m, 1 Day -> 15m, 1 Week -> 1h).
   - Confirmation step aggregates all inputs accurately.
2. **Session Lifecycle Suite (`SessionControls.test.tsx` & `useSessionLifecycle.test.ts`)**:
   - Gating verification: cockpit buttons disabled when session is `UNCONFIGURED` or `STOPPED`.
   - Transitions between `RUNNING`, `PAUSED`, and `STOPPED` trigger appropriate callbacks and endpoints.
   - Countdown timer computes exact remaining seconds and triggers expiry callback when time reaches 0.
3. **Decision Explainer Feed Suite (`ActivityLog.test.ts`)**:
   - Verifies `DECISION` log parsing and formatting.
   - Confirms badge styling and presentation of Net Expectancy, P(Win), uncertainty bands, and plain-language explanation.

### 7.2 Build & Integration Checks
- Verify zero TypeScript compiler errors: `npm run build` (`tsc && vite build`).
- Verify zero lint/syntax issues.
- Verify memory stability: running 100,000 simulated ticks through the upgraded telemetry bar and activity log must not exceed the 150 MB heap budget.

---

## 8. Summary & Next Steps for Implementation
The frontend codebase is well-structured and ready for the implementation of R1 and R2. The architectural design specified above strictly aligns with all requirements in `ORIGINAL_REQUEST.md` and establishes clear interfaces with backend requirements R3, R4, and R5.
