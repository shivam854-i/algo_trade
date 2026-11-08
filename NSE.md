# NSE Cash Market Specification & Verification Blueprint

> **Strict Operational Notice**: This document details structural requirements, execution constraints, and unverified broker/exchange specifics for trading on the National Stock Exchange of India (NSE) Cash Equities segment within the algorithmic trading engine. All algorithmic executions remain restricted to virtual paper-trading simulation (`PAPER_TRADING_ONLY = True`). Live automated order generation without broker API certification and exchange algo-id approval is prohibited.

---

## 1. Executive Status & Focus

The trading engine is currently operating under an **NSE-Only Cash Market Focus** (`enabled_markets: ["NSE_CASH"]`). All other market jurisdictions (US Equities, Crypto, Forex, Commodities) are soft-disabled in the session manager, order entry gateways, and user interface.

- **Canonical Jurisdiction Identifier**: `NSE_CASH` (mapped interchangeably from `INDIAN_NSE`, `NSE`, and `INDIA`).
- **Base Currency**: `INR` (`₹`).
- **Default Asset Universe**: Nifty 50 Index Constituents (50 equities ending in `.NS`).
- **Execution Guardrails**:
  - `TokenBucketRateLimiter`: Strictly throttled to 5.0 orders/second with a burst capacity of 5.0 orders (comfortably below exchange throttling limits).
  - Algorithmic Order Type Restriction: Pure unpriced algorithmic `MARKET` orders are prohibited. Orders submitted as algorithmic market orders are automatically transformed or rejected into `LIMIT` orders with Limit Price Protection (LPP) bands to safeguard against order book vacuum execution.

---

## 2. Unverified Rules & Exchange Specifications

The following domains require formal empirical verification against official NSE circulars, exchange trading system documentation (NEAT/NEAT+ protocols), and specific broker partner APIs (e.g., Zerodha Kite Connect, Angel One SmartAPI, Upstox, or Interactive Brokers India).

> **STATUS**: **TO VERIFY WITH NSE/BROKER DOCS** — Rules must not be invented or guessed.

### 2.1. Holiday Calendar
- **Current Mock / Assumptions**:
  - Normal weekly trading days: Monday through Friday.
  - Weekend closure: Saturday and Sunday.
- **Unverified Items**:
  - **Status**: **To verify with NSE/broker docs**.
  - Annual gazetted market holiday schedule published annually by NSE (e.g., Republic Day, Independence Day, Diwali, Mahashivratri, Eid, Christmas).
  - Special and non-standard trading sessions, specifically **Diwali Muhurat Trading** (annual 1-hour evening trading window with unique auction and market timings).
  - Clearing and settlement holiday variations (trading open but settlement closed).
  - Broker holiday calendar sync mechanisms (dynamic calendar feed vs static holiday YAML/JSON table).

### 2.2. Price Bands & Circuit Filters
- **Current Mock / Assumptions**:
  - Paper broker relies on raw tick simulation without rejecting trades breaching daily limits.
- **Unverified Items**:
  - **Status**: **To verify with NSE/broker docs**.
  - **Daily Circuit Limits**: Standard non-F&O cash equities operate under fixed price bands of 2%, 5%, 10%, or 20% derived from the previous day's close (`Close[t-1]`).
  - **Dynamic Price Bands (F&O Stocks)**: Stocks with active derivative contracts (including most Nifty 50 constituents) do not have fixed statutory circuits; instead, they have dynamic operating ranges (flexing bands) starting at 10% that are dynamically relaxed by the exchange during high volatility after cooling-off periods.
  - Exchange behavior when an equity hits an upper or lower freeze band (order queueing vs order rejection).
  - Broker-specific pre-trade validation: Whether broker gateways reject limit prices outside daily bands with specific reject codes or silently queue them.

### 2.3. Tick Sizes & Price Quotation
- **Current Mock / Assumptions**:
  - Floating point prices rounded to standard 2 decimal places.
- **Unverified Items**:
  - **Status**: **To verify with NSE/broker docs**.
  - **Standard Tick Size**: NSE equity shares traditionally quote in ticks of `₹0.05` (5 paise).
  - **Sub-50 Rupee Equities**: NSE circular introduced reduced tick sizes (e.g., `₹0.01` / 1 paisa) for equities quoting below specific thresholds (e.g., under ₹100 or ₹250).
  - Validation requirement: Verification of exact tick size grid per security token from the daily master security file (`security_master` / `instruments.csv`).
  - Order price snapping: Requirement for automated algorithms to snap limit prices strictly to the valid tick increment before transmission, preventing broker rejection.

### 2.4. Intraday Square-off Timing (MIS / CNC)
- **Current Mock / Assumptions**:
  - Standard session duration policy allows `CLOSE_ALL` or `KEEP_OPEN` at the end of custom session timers.
- **Unverified Items**:
  - **Status**: **To verify with NSE/broker docs**.
  - **Product Types**: Cash delivery (`CNC` - Cash and Carry) vs intraday leveraged margin (`MIS` - Margin Intraday Square-off).
  - **Broker Square-Off Timings**: Auto-square-off of MIS positions by brokers typically occurs between `15:15 IST` and `15:25 IST` (prior to regular market close at `15:30 IST`).
  - Penalty structures: RMS (Risk Management System) liquidation charges levied by brokers for auto-square-off trades.
  - End-of-day handling: Invariant check that no MIS position remains open past broker cutoff; mandatory internal reconciliation loop at `15:10 IST`.

### 2.5. Short-Sell Rules & Borrowing Regulations
- **Current Mock / Assumptions**:
  - System permits bidirectional position simulated opening (`BUY` / `SELL`).
- **Unverified Items**:
  - **Status**: **To verify with NSE/broker docs**.
  - **No Overnight Short Selling in Cash**: SEBI and NSE regulations strictly prohibit holding overnight naked short positions in the cash equities segment. All short positions in cash shares must be intraday (MIS) and squared off before 15:30 IST.
  - **Failure to Deliver (Auction Penalties)**: An unclosed short position in cash equities goes into exchange auction on T+1, resulting in heavy financial penalties (up to 20% over market price).
  - **SLB Mechanism**: Short-selling over multiple days requires borrowing shares via the official Securities Lending and Borrowing (SLB) framework prior to sale.
  - Algo invariant: Enforce that if product is cash equity, short positions cannot transition to overnight holding under any circumstance.

### 2.6. Real-Time Data Feed Protocol & Market Depth
- **Current Mock / Assumptions**:
  - Market data polled via REST snapshots and 1-minute aggregations (yfinance / simulated streams).
- **Unverified Items**:
  - **Status**: **To verify with NSE/broker docs**.
  - **Feed Latency & Cadence**: Production deployment requires WebSocket binary streaming (e.g., Kite Connect WebSocket or Angel One SmartStream) providing Level 1 (L1 - LTP, Best Bid/Ask) and Level 2 (L2 - 5-depth order book).
  - **Tick-by-Tick (TBT) vs 1-Sec Broadcast**: NSE broadcast is batched by the exchange in 1-second intervals or delivered as raw UDP tick-by-tick for colocation.
  - Packet drop and reconnection semantics: Handling socket disconnects, sequence number gaps, and heartbeat timeouts during live market spikes.

### 2.7. Algorithmic Trading Compliance & Limit Price Protection (LPP)
- **Current Mock / Assumptions**:
  - Automated orders are converted from `MARKET` to `LIMIT` using a 1% Limit Price Protection buffer.
- **Unverified Items**:
  - **Status**: **To verify with NSE/broker docs**.
  - **Exchange Algo Approvals**: SEBI mandates that all automated order execution strategies deployed on client accounts require broker and exchange algo strategy certification, including unique strategy IDs mapped to exchange terminals.
  - **SEBI Market Order Bans**: Automated algorithmic orders placed as pure market orders have experienced regulatory clampdowns to prevent flash crashes. Exchange LPP mechanism mandates limit price protection within a defined reference range (e.g., 1.5% to 3% of the prevailing trigger price / LTP).

---

## 3. Verification Roadmap

| Domain | Action Item | Target Verification Source |
| :--- | :--- | :--- |
| **Holidays** | Parse official NSE holiday circular JSON | NSE India Clearing & Holidays circulars |
| **Circuits** | Fetch daily upper/lower bands via broker API instrument master | Broker instrument master endpoint |
| **Ticks** | Snap order limit prices to security's tick step (e.g. 0.05) | Exchange contract specification |
| **Square-Off** | Configure hard broker MIS cutoff schedule (e.g. 15:15 IST) | Broker RMS policy document |
| **Short-Selling** | Prohibit overnight `SELL` positions in cash segment | SEBI Cash Market Short-Selling regulations |
| **Data Feed** | WebSocket L2 binary packet parser with local order book | Broker WebSocket SDK documentation |
| **Rate Limit** | Enforce 5 req/s max client-side rate limiter | Broker API rate limit terms of service |
