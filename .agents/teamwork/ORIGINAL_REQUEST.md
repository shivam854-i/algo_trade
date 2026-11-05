# Original User Request

## Initial Request — 2026-11-05T05:34:40Z

Build a user-controlled Trading Session Setup Wizard, session lifecycle management system, and intelligent quantitative stock selection and trade evaluation engine for the SYNAPSE-TITAN algorithmic paper-trading platform as a production enhancement. All trading, orders, accounts, and capital must remain strictly virtual using genuine market data.

Working directory: C:\Users\Shivam\Desktop\trade_bot
Integrity mode: development

## Requirements

### R1. Trading Session Setup Wizard UI and Onboarding Experience
Implement a guided onboarding wizard in React/TypeScript that users must complete before the autonomous paper-trading engine can operate. The wizard must guide users through Market Selection (restricting choices to markets supported by the configured provider/broker), Instrument Selection (with manual search, multi-select, and rule-based auto-selection with explanation), Trading Horizon Selection (1 hour, 1 day, 1 week), Session Duration Selection (with custom duration and session-end position policy), Virtual Capital Allocation (with market-appropriate currency and input validation), and a Final Confirmation step before launch.

### R2. Autonomous Bot Behavior, Session Lifecycle, and UI Dashboard Controls
The paper-trading bot must operate strictly within the user's approved session configuration, never trading unapproved instruments, exceeding virtual capital, switching horizons, or extending past session duration. Provide persistent START, PAUSE, and STOP controls on the dashboard, alongside an updated dashboard displaying session metrics, market regime, data feed status, and a transparent activity feed explaining bot decisions.

### R3. Backend Architecture, Session Management, and REST APIs
Implement a structured TradingSession configuration model, database schema migrations in SQLite, and FastAPI endpoints for session lifecycle (create, fetch, update, start, pause, resume, stop, auto-select recommendations, and performance metrics). All session parameters must be validated on the backend independently of the frontend, strictly isolating virtual paper trading from real brokerage execution and preventing trading operations without a valid active session.

### R4. Quantitative Stock Selection, Trade Evaluation, and Portfolio Decision Engine
Implement systematic universe and opportunity selection modules in `src/strategy/` (`universe_selector.py`, `trade_evaluator.py`, `trade_ranker.py`, `portfolio_selector.py`, and `decision_explainer.py`). The engine must evaluate universe candidates using data quality and liquidity for wizard auto-selection, rank opportunities by expected net value (incorporating win/loss probabilities, calibrated confidence, uncertainty bounds, and friction costs), allocate capital using Kelly/fractional Kelly or HRP with the ability to sit in cash when opportunities lack positive expectancy, and generate plain-language explanations for all actions displayed in the activity feed.

### R5. Strategy Horizon Mapping, Market Data Integration, and Virtual Execution Guardrails
Dynamically bind strategy parameters (market-data intervals, feature windows, signal frequency, HMM regime detection, TCN prediction, triple-barrier thresholds, and stop/target rules) to the chosen trading horizon, and scale position sizing with starting capital without altering model prediction outputs. Use genuine market data from configured providers—halting new entries safely if feeds become stale or unavailable rather than fabricating synthetic prices—and ensure all trading, accounts, orders, and positions remain strictly virtual.

## Verification Resources
- Discover and run existing backend test suites using pytest (via Windows `py` interpreter) in `C:\Users\Shivam\Desktop\trade_bot`.
- Run frontend build and test checks (e.g., `npm test` or `npm run build`) in `C:\Users\Shivam\Desktop\trade_bot\frontend`.
- Execute newly created unit and integration tests verifying session management, universe selection, trade evaluation, horizon mapping, capital sizing, and state transitions.

## Acceptance Criteria

### Setup Wizard & Onboarding UI
- [ ] Wizard displays supported market cards (Indian Equities, US Equities, Crypto, Forex, Commodities) showing trading hours and feed status, disabling unsupported markets.
- [ ] Instrument selection supports manual search, multi-select, removal, and an "Auto-select for me" feature powered by `UniverseSelector` that recommends a bounded basket with clear rationale based on liquidity, volume, spread, and strategy compatibility.
- [ ] Trading horizon options (1 hour, 1 day, 1 week) are selectable and explicitly differentiate holding horizon from session run duration.
- [ ] Session duration options (e.g. 1 hour, 4 hours, 1 day, 1 week, custom, manual stop) include configurable session-end policy (close open positions vs keep open for manual management).
- [ ] Virtual capital input validates positive amounts, enforces min/max boundaries, uses market-appropriate currency symbols (INR for Indian equities, USD for US equities), and prevents zero or negative balances.
- [ ] Final confirmation step displays a comprehensive summary of all configured session parameters with options to edit or confirm and launch.

### Bot Execution & Dashboard Controls
- [ ] Autonomous engine cannot start trading until the user confirms the wizard configuration.
- [ ] Bot never opens trades for instruments outside the approved session basket or beyond allocated capital.
- [ ] Dashboard provides START, PAUSE, and STOP controls that update session state reliably.
- [ ] Session expiry triggers configured session-end policy and halts new trade generation without silent extension.
- [ ] Dashboard displays active session parameters, financial metrics (starting capital, cash, invested equity, unrealized/realized P&L), market regime, feed status, and real-time decision explanations from `DecisionExplainer`.
- [ ] Trading is strictly virtual and isolated; real-money execution is completely blocked.

### Backend & API
- [ ] TradingSession database table/migration is implemented in SQLite storing session ID, market, instruments, horizon, duration, capital, currency, strategy config, risk config, status, and timestamps.
- [ ] FastAPI endpoints are functional: create session, get session, update session, start/pause/resume/stop session, get recommendations, and get performance.
- [ ] Backend validates all configuration parameters independently of frontend validation.
- [ ] Engine and order controller refuse execution without a valid active session.

### Quantitative Decision Engine
- [ ] `UniverseSelector` filters instruments based on data quality, liquidity, spread, volatility, and tradability constraints.
- [ ] `TradeEvaluator` computes Net Expectancy: P(Win) * E[Win | Win] - P(Loss) * E[Loss | Loss] - Expected Friction Cost, using calibrated probabilities and uncertainty bounds rather than naive probability ranking.
- [ ] `TradeRanker` ranks opportunities by risk-adjusted expected net value and market regime alignment.
- [ ] `PortfolioSelector` allocates capital via Kelly/fractional Kelly or HRP, allocating to cash when no opportunities meet minimum expected value thresholds.
- [ ] `DecisionExplainer` provides human-readable explanations for accepted and rejected trades.

### Strategy Horizon Mapping & Market Data
- [ ] Strategy parameters (intervals, feature windows, signal frequency, HMM, TCN, triple-barrier thresholds, stops) dynamically reflect the selected horizon (1 hour, 1 day, 1 week).
- [ ] Changing starting capital dynamically recalculates position sizing and buying power via Kelly/risk rules without changing model prediction outputs.
- [ ] Real market data provider is used; if data is stale or unavailable, new entries stop safely without generating artificial prices.

### Testing & Verification
- [ ] Automated tests verify market validation, instrument selection, horizon mapping, capital validation, position sizing, session lifecycle transitions, and data outage safeguards.
- [ ] Unit tests cover `UniverseSelector`, `TradeEvaluator`, `TradeRanker`, `PortfolioSelector`, and `DecisionExplainer` edge cases (e.g., zero positive EV trades resulting in 100% cash).
- [ ] All existing and new tests pass cleanly under the project's test runners.
