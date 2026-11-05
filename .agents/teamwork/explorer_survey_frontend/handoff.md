# Frontend UI Survey & R1/R2 Architecture Handoff Report

**Agent**: `explorer_survey_frontend` (Teamwork Explorer)  
**Parent Orchestrator**: `d0b51128-456f-4a81-855c-2a488d288844`  
**Working Directory**: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\explorer_survey_frontend`  
**Date**: 2026-11-05  

---

## 1. Observation

### 1.1 Existing Frontend Stack & Configuration
- **Package Manifest** (`C:\Users\Shivam\Desktop\trade_bot\frontend\package.json`):
  - Dependencies: `react: "^18.3.1"`, `react-dom: "^18.3.1"`, `lightweight-charts: "^4.2.1"`, `lucide-react: "^0.475.0"`.
  - DevDependencies: `typescript: "^5.6.3"`, `vite: "^5.4.11"`, `vitest: "^2.1.8"`, `tailwindcss: "^3.4.17"`.
  - Scripts: `"build": "tsc && vite build"`, `"test": "vitest run"`.
- **Vite Configuration** (`C:\Users\Shivam\Desktop\trade_bot\frontend\vite.config.ts`, lines 8-21):
  - Path alias `@` resolves to `./src`.
  - Development server runs on port 5173 with proxy `/api` targeting `http://127.0.0.1:8501`.
- **Existing App & Component Hierarchy** (`C:\Users\Shivam\Desktop\trade_bot\frontend\src\App.tsx`, lines 60-192):
  - Cockpit renders `<Header>`, `<MarketSessionRibbon>`, `<KpiRibbon>`, `<AssetSelector>`, `<ChartContainer>`, `<PositionsTable>`, `<OrderControls>`, and `<ActivityLog>`.
  - State and operations are managed by `useDashboardStream.ts` (`pollIntervalMs: 2500, chartCapacity: 500, logCapacity: 100`).
- **Telemetry & Types** (`C:\Users\Shivam\Desktop\trade_bot\frontend\src\types\index.ts`):
  - Defines `BotStatus`, `DataFeedStatus`, `AccountSummary`, `AssetTelemetry`, `OpenPosition`, `ClosedTrade`, `PendingOrder`, `LogItem`, and `DashboardState`.
  - Notably absent: `TradingSessionConfig`, `SessionStatus`, `UniverseRecommendation`, `DecisionExplanation`, and `SessionTelemetry`.
- **Component Specifics Observed**:
  - `Header.tsx` (lines 61-68): Displays `PAPER TRADING • VIRTUAL ACCOUNT` badge.
  - `MarketSessionRibbon.tsx` (lines 25-66): Contains `BENCHMARK_CONFIG` for NSE, NYSE, COMEX, CRYPTO. Computes real-time 1s countdowns with offline fallback.
  - `KpiRibbon.tsx` (lines 48-150): Displays 6 KPI cards, hardcoded to USD `$` formatting.
  - `AssetSelector.tsx` (lines 39-91): Hardcoded `FALLBACK_SEARCH_CATALOG` with instant client-side autocomplete across NSE, US, CRYPTO, COMMODITIES, FOREX.
  - `ChartContainer.tsx` (lines 36-151): Implements `createChart` with explicit `chart.remove()` teardown on unmount or ticker change.
  - `PositionsTable.tsx` (lines 91-266): Renders open positions with dynamic Stop-to-Target visual sliders, close position, flatten all, and closed trades history.
  - `OrderControls.tsx` (lines 147-182): Provides `Auto-Bot: RUNNING/PAUSED` toggle, `Strict Exchange Hours` toggle, simulation `Step Tick`, `Reset Account`, and order form.
  - `ActivityLog.tsx` (lines 9-30): Supports categories `BOT`, `TRADE`, `PROFIT`, `STOP`, `RISK`, `SESSION`, `SYSTEM`. Missing `DECISION`.
  - `ringBuffer.ts`: Bounded circular buffer guaranteeing $O(1)$ operations with zero heap expansion.
  - `usePageVisibility.ts`: Subscribes to `visibilitychange` to suspend timers and canvas renders when tab is hidden.

### 1.2 Build & Test Verification Results
- **Vitest Run Command**: `cd C:\Users\Shivam\Desktop\trade_bot\frontend; npm test`
  - Output:
    ```
    RUN v2.1.9 C:/Users/Shivam/Desktop/trade_bot/frontend
    ✓ src/utils/ringBuffer.test.ts (6 tests) 5ms
    ✓ src/components/MarketSessionRibbon.test.ts (5 tests) 6ms
    ✓ src/components/ActivityLog.test.ts (7 tests) 5ms
    ✓ tests/stress_activity_log.test.tsx (4 tests) 40ms

    Test Files  4 passed (4)
         Tests  22 passed (22)
      Duration  2.05s
    ```
- **Production Build Command**: `cd C:\Users\Shivam\Desktop\trade_bot\frontend; npm run build`
  - Output:
    ```
    > synapse-titan-terminal@2.0.0 build
    > tsc && vite build
    ✓ 1609 modules transformed.
    dist/index.html                   1.18 kB │ gzip:   0.69 kB
    dist/assets/index-7UHtpM1g.css   29.04 kB │ gzip:   5.59 kB
    dist/assets/index-CdIGUnOX.js   401.54 kB │ gzip: 121.82 kB
    ✓ built in 2.48s
    ```
- **Node Stress Scripts**:
  - `node tests/stress_page_visibility.mjs`: Passed 100% green (500 cycles, 0 leaks, single snapshot resync).
  - `node tests/stress_ring_buffer.mjs`: Passed 100% green (1,100,000 pushes, bounded at 14.68 MB heap << 300 MB limit).

---

## 2. Logic Chain

1. **Premise 1 (R1 & R2 Requirements)**: `ORIGINAL_REQUEST.md` (lines 12-16, 34-48) mandates that the autonomous paper-trading engine cannot operate until the user completes and confirms a Guided Onboarding Wizard in React/TypeScript covering Market Selection, Instrument Selection (with UniverseSelector recommendation rationale), Horizon Selection (differentiating holding horizon from session duration), Session Duration Selection (with custom duration and session-end position policy), Virtual Capital Allocation (currency-sensitive, strictly positive, bounded), and Final Confirmation. Furthermore, R2 mandates persistent START, PAUSE, STOP controls, an active session telemetry display, and transparent decision explanations from `DecisionExplainer` in the activity feed.
2. **Premise 2 (Existing UI Entry State)**: From `App.tsx` (lines 35-58), the cockpit currently boots directly into an un-gated interface, auto-selecting `NVDA` and running ad-hoc polling regardless of whether any session was configured.
3. **Premise 3 (State Model Gap)**: `src/types/index.ts` lacks representation of a `TradingSessionConfig` or `SessionStatus`, meaning session parameters (duration, horizon, approved basket, end policy) are not tracked or validated in the frontend.
4. **Premise 4 (Decision Explainer Presentation Gap)**: `ActivityLog.tsx` currently filters on `['ALL', 'BOT', 'TRADE', 'PROFIT', 'RISK', 'SESSION']`, omitting the quantitative reasoning outputs (Net Expectancy, calibrated probabilities, uncertainty intervals, friction penalties) produced by `DecisionExplainer`.
5. **Deductive Conclusion**:
   - A dedicated `TradingSessionWizard` modal/overlay with 6 sequential steps must be created and integrated into `App.tsx`.
   - A session gating layer must prevent bot execution and order submission when no confirmed session is active.
   - An `activeSession` state and `SessionTelemetryBar` must be created to display real-time financial metrics, countdown timer, market regime, and approved basket chips.
   - Persistent `SessionControls` (`START`, `PAUSE`, `STOP`) must be introduced to drive session state machine transitions.
   - `ActivityLog.tsx` and `types/index.ts` must be extended with `DECISION` category support to display full quantitative explanations.

---

## 3. Caveats

1. **Backend Dependency Synchronization**: The backend FastAPI endpoints for session lifecycle (`POST /api/sessions/create`, `GET /api/sessions/active`, `POST /api/sessions/{id}/start`, `POST /api/sessions/{id}/pause`, `POST /api/sessions/{id}/stop`, `POST /api/sessions/recommendations`) are part of Requirement R3/R4, currently being designed by peer agents. The frontend design specifies the exact contract so that frontend and backend will integrate seamlessly.
2. **Provider Live Feed Availability**: While the frontend handles offline heuristics and disables unsupported market cards, real-time quote feeds for Indian Equities (NSE) depend on Yahoo Finance / NSE feed availability, while US equities can utilize Alpaca IEX or Yahoo Finance.

---

## 4. Conclusion

The existing frontend codebase provides a high-performance foundation with clean build times (< 2.5s) and zero memory leaks. 

To satisfy Requirements R1 and R2, the implementation will introduce:
1. **`src/types/index.ts`**: Addition of `TradingSessionConfig`, `MarketType`, `TradingHorizon`, `SessionDuration`, `SessionEndPolicy`, `SessionStatus`, `UniverseRecommendation`, `DecisionExplanation`, and `SessionTelemetry`.
2. **`src/components/wizard/`**:
   - `TradingSessionWizard.tsx`: Master modal and step manager.
   - `Step1MarketSelection.tsx`: Market cards (NSE, US, Crypto, Forex, Commodities) with real-time hours, feed status, and disabling unsupported markets.
   - `Step2InstrumentSelection.tsx`: Search, multi-select, chips, and "Auto-select for me" powered by `UniverseSelector`.
   - `Step3HorizonSelection.tsx`: 1 Hour, 1 Day, 1 Week with clear educational distinction between holding horizon and session duration.
   - `Step4DurationSelection.tsx`: Duration presets, custom duration, manual stop, and session-end position policy (Close all vs. Keep open).
   - `Step5CapitalAllocation.tsx`: Positive amount validation, boundary enforcement, and currency switching (INR `₹` vs. USD `$`).
   - `Step6Confirmation.tsx`: Comprehensive summary review with edit options and "Confirm & Launch" button.
3. **`src/components/session/`**:
   - `SessionTelemetryBar.tsx`: Active session telemetry, countdown clock, financial metrics, market regime, approved basket chips.
   - `SessionControls.tsx`: Persistent START, PAUSE, STOP controls with confirmation modal and policy execution.
4. **`src/components/ActivityLog.tsx`**: Upgraded with `DECISION` category parsing and formatted trade rationale.
5. **`src/App.tsx` & `useDashboardStream.ts`**: Session gating integration, blocking un-configured bot execution.

Detailed specifications and interfaces are documented in `analysis.md`.

---

## 5. Verification Method

To independently verify this survey and future implementations:
1. **Run Unit Tests**:
   ```bash
   cd C:\Users\Shivam\Desktop\trade_bot\frontend
   npm test
   ```
   *Expected*: All test suites pass cleanly (vitest).
2. **Run Production Build**:
   ```bash
   cd C:\Users\Shivam\Desktop\trade_bot\frontend
   npm run build
   ```
   *Expected*: `tsc && vite build` completes with exit code 0 and no TypeScript errors.
3. **Run Memory & Performance Tests**:
   ```bash
   cd C:\Users\Shivam\Desktop\trade_bot\frontend
   node tests/stress_page_visibility.mjs
   node tests/stress_ring_buffer.mjs
   ```
   *Expected*: 100% green pass with heap usage well below 150 MB ceiling.
4. **Inspect Analysis Specification**:
   - View `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\explorer_survey_frontend\analysis.md` for full component breakdown and API contracts.
