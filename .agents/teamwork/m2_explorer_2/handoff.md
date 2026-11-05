# Handoff Report: FastAPI Endpoints & Independent Backend Validation (Milestone 2 Part B)

**Module**: SYNAPSE-TITAN REST Gateway & Session Lifecycle Management  
**Author**: FastAPI Endpoints & Validation Explorer (`teamwork_explorer`)  
**Target Repository**: `C:\Users\Shivam\Desktop\trade_bot`  
**Working Directory**: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\m2_explorer_2`  
**Date**: 2026-11-05  

---

## 1. Observation

Direct observations and evidence from the codebase investigation:

1. **Existing Route Architecture in `server.py`**:
   - `server.py:726-731`: An existing endpoint `@app.get("/api/sessions/status", tags=["Sessions"])` returns physical exchange session statuses (`bot.get_all_market_sessions()`).
   - `server.py:712-962`: Interactive dashboard endpoints currently handle manual orders (`/api/dashboard/order`), asset selection (`/api/dashboard/select-assets`), simulation toggle (`/api/dashboard/toggle-simulation`), step ticks (`/api/dashboard/step`), and liquidation (`/api/dashboard/flatten`).
   - `server.py:827-836`: `toggle_bot_running()` toggles `bot.is_running` directly without any active session gating, duration tracking, or approved basket enforcement.
   - `server.py:16-19`: Imports FastAPI components: `Depends, FastAPI, Header, HTTPException, Query, status`, `BaseModel, Field` from `pydantic`. Pydantic version is `2.13.3` (confirmed via `py -c "import pydantic; print(pydantic.__version__)"`).

2. **Existing Test Suite Verification**:
   - `tests/test_milestone_m2_sessions.py:177`: Explicitly tests physical session status:
     ```python
     r_sess = client.get("/api/sessions/status")
     assert r_sess.status_code == 200
     sessions = r_sess.json()
     assert "NSE_INDIA" in sessions
     ```
   - Running `cd C:\Users\Shivam\Desktop\trade_bot; py -m pytest tests/test_milestone_m2_sessions.py` passes 5 of 5 tests cleanly in 16.28 seconds.

3. **UniverseSelector Basket Recommendation Engine (`src/strategy/universe_selector.py`)**:
   - `src/strategy/universe_selector.py:360-433`: `UniverseSelector.auto_select_basket(market: str, target_size: int = 5, candidate_tickers: Optional[List[str]] = None) -> UniverseSelectionResult`.
   - `UniverseSelectionResult` contains `to_dict()` returning `market`, `target_size`, `selected_instruments`, `evaluations`, `passed_count`, `rejected_count`, `summary_rationale`, and `timestamp_utc`.
   - Candidate evaluations enforce 4 gates: Data Quality ($Q_{\text{data}} \ge 0.90$), ADV Liquidity ($\ge \$5\text{M}$ USD or $\ge \text{₹}50\text{M}$ INR), Bid-Ask Spread ($\le 25\text{ bps}$), and Tradability Volatility ($8\%-100\%$).

4. **Market Detection & Catalog (`src/execution/market_sessions.py`, `src/execution/live_bot.py`)**:
   - `src/execution/market_sessions.py:162-175`: `MarketCalendarManager.detect_market_type(ticker)` classifies:
     - `.NS` / `.BO` -> `"NSE_CASH"`
     - `=F` or `GLD, SLV, USO, UNG` -> `"COMMODITY"`
     - `=X` or `DX-Y.NYB, UUP` -> `"FOREX"`
     - `-USD` / `-USDT` or `BTC, ETH, SOL, DOGE, XRP` -> `"CRYPTO"`
     - standard tickers -> `"US_EQUITIES"`
   - `src/execution/live_bot.py:47-53`: `ASSET_CATALOG` contains pre-curated baskets for `US_EQUITIES`, `CRYPTO`, `COMMODITIES`, `FOREX`, `INDIAN_NSE`.

5. **Peer Explorer Alignment**:
   - `m2_explorer_1` is specifying `TradingSession` dataclass and SQLite schema migrations in `src/execution/session_manager.py` and `src/execution/broker.py`.
   - `m2_explorer_3` is specifying autonomous execution loop gating and expiry enforcement in `src/execution/live_bot.py`.

---

## 2. Logic Chain

From the observations above, the implementation design follows this deductive sequence:

1. **Route Precedence Prevents Collision** (Supported by Observations 1 & 2):
   - In FastAPI, routes registered with dynamic parameters (e.g. `/api/sessions/{session_id}`) will match any URL segment. If declared before static routes, a request to `/api/sessions/status` or `/api/sessions/active` would match `{session_id} = "status"`, calling the session lookup instead of the physical exchange endpoint.
   - Therefore, declaring static routes (`/api/sessions/status`, `/api/sessions/active`, `/api/sessions/recommendations`, `/api/sessions`) **before** parameterized routes (`/api/sessions/{session_id}`, `/start`, `/pause`, `/resume`, `/stop`, `/performance`), combined with a reserved-subpath guard, completely prevents route shadowing and protects all existing tests.

2. **Decoupled Backend Validation Enforces Safety** (Supported by Observations 1 & 4):
   - The setup wizard frontend will validate inputs, but client-side validation cannot protect the engine against direct API calls or script attacks.
   - Independent backend validation must strictly enforce:
     - Positive capital bounded to $[1,000, 10,000,000]$.
     - Currency isolation (`INR` for `INDIAN_NSE`, `USD` for `US_EQUITIES`, `CRYPTO`, `FOREX`, `COMMODITIES`).
     - Jurisdiction containment (mapping detected `NSE_CASH` to `INDIAN_NSE`, `COMMODITY` to `COMMODITIES`, etc., and rejecting out-of-market tickers like `AAPL` in an `INDIAN_NSE` session).
     - Separation of holding horizon (`1h`, `1d`, `1wk`) from session run duration (`FIXED`, `CUSTOM`, `MANUAL_STOP`) with $\le 10,080$ minutes ceiling.
     - Session-end policy in `["CLOSE_ALL", "KEEP_OPEN"]`.

3. **Lifecycle State Machine Governance** (Supported by Observations 1 & 5):
   - Sessions can only be updated in `CREATED` or `PAUSED` state (409 Conflict if modified while `RUNNING` or `STOPPED`).
   - Starting a session arms the bot with approved instruments, allocates capital in `broker`, dynamically sets strategy parameters for the chosen horizon, and sets `bot.is_running = True`.
   - If another session is already `RUNNING`, starting a new one must be rejected with 409 Conflict.
   - Pausing halts new trade generation (`bot.is_running = False`) while keeping positions open.
   - Resuming calculates the elapsed pause duration and extends `expires_at` accordingly.
   - Stopping halts trading, calculates final metrics, and triggers the configured `session_end_policy` (`CLOSE_ALL` flattens positions; `KEEP_OPEN` preserves them).

4. **Quantitative Wizard Recommendation Integration** (Supported by Observation 3):
   - `POST /api/sessions/recommendations` directly queries `UniverseSelector.auto_select_basket` with the requested market and target size (3 to 6).
   - This returns the quantitative gate results, composite scores, and plain-language summary rationales required by Wizard Step 2.

---

## 3. Caveats

1. **SessionManager Dependency**: The endpoints call `SessionManager` methods (`create_session`, `get_active_session`, `get_session`, `list_sessions`, `update_session`, `start_session`, `pause_session`, `resume_session`, `stop_session`, `compute_session_performance`). The worker implementing Milestone 2 must ensure `src/execution/session_manager.py` is implemented first (or simultaneously) using the blueprint from `m2_explorer_1`.
2. **Asynchronous Bot Loop vs Synchronous Endpoints**: The endpoints in `server.py` are synchronous (`def`) or async (`async def`). In FastAPI, standard `def` functions run in the default thread pool, which avoids blocking the async event loop during SQLite ledger reads and `UniverseSelector` data fetches.
3. **Multi-Currency Accounting**: The broker maintains virtual account balances in the session's currency (`USD` or `INR`). Cross-currency conversion is not needed because a single session trades strictly within its assigned market currency.

---

## 4. Conclusion & Actionable Code Blueprints

### 4.1 Route Registration Order in `server.py`
Place all new schemas and endpoints into `server.py` in this exact sequence:

```
# [Lines 1-725: Existing imports, models, lifespan, prediction endpoints]

# ----------------- Milestone 2: Trading Session Schemas & Endpoints ----------------- #
# 1. Pydantic Schemas (SessionCreateRequest, SessionUpdateRequest, SessionStopRequest, RecommendationRequest, Response Schemas)
# 2. Independent Validation Functions (validate_capital_and_currency, validate_instruments_jurisdiction, validate_duration_and_horizon)
# 3. GET /api/sessions/status (Existing line 726 - PRESERVED AS IS)
# 4. GET /api/sessions/active (Returns active session or {"session": null})
# 5. POST /api/sessions/recommendations (Wizard auto-select basket)
# 6. GET /api/sessions (List sessions with filters)
# 7. POST /api/sessions (Create session with validation)
# 8. GET /api/sessions/{session_id} (Fetch session by ID)
# 9. PUT /api/sessions/{session_id} (Update session in CREATED/PAUSED state)
# 10. POST /api/sessions/{session_id}/start (Start session & arm bot)
# 11. POST /api/sessions/{session_id}/pause (Pause session & halt new entries)
# 12. POST /api/sessions/{session_id}/resume (Resume session & adjust expiry)
# 13. POST /api/sessions/{session_id}/stop (Stop session & trigger end policy)
# 14. GET /api/sessions/{session_id}/performance (Financial KPIs & P&L)
```

### 4.2 Complete Pydantic Schemas & Validation Code

```python
# ----------------- Session Pydantic Request / Response Schemas ----------------- #

class SessionCreateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=120, description="Optional user-assigned session name")
    market: str = Field(..., description="Target market: US_EQUITIES, INDIAN_NSE, CRYPTO, COMMODITIES, FOREX")
    instruments: List[str] = Field(..., min_length=1, max_length=20, description="List of approved asset tickers")
    horizon: str = Field(default="1d", description="Holding horizon: '1h', '1d', or '1wk'")
    duration_type: str = Field(default="FIXED", description="Duration type: FIXED, CUSTOM, or MANUAL_STOP")
    duration_minutes: Optional[int] = Field(None, description="Session run duration in minutes (required for FIXED/CUSTOM, max 10080)")
    session_end_policy: str = Field(default="CLOSE_ALL", description="Action upon expiry: CLOSE_ALL or KEEP_OPEN")
    allocated_capital: float = Field(..., description="Allocated virtual capital (min 1,000, max 10,000,000)")
    currency: str = Field(default="USD", description="Currency: USD for US/Crypto/Cmdty/FX, INR for INDIAN_NSE")
    strategy_config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom strategy hyperparameters")
    risk_config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom risk thresholds")

    @field_validator("market")
    @classmethod
    def validate_market_field(cls, v: str) -> str:
        canonical = v.strip().upper()
        if canonical in ("US", "NYSE", "NASDAQ", "US_EQUITIES"):
            return "US_EQUITIES"
        elif canonical in ("NSE", "NSE_CASH", "INDIAN_NSE", "INDIA"):
            return "INDIAN_NSE"
        elif canonical in ("CRYPTO", "CRYPTOCURRENCY"):
            return "CRYPTO"
        elif canonical in ("COMMODITY", "COMMODITIES", "CME"):
            return "COMMODITIES"
        elif canonical in ("FOREX", "FX"):
            return "FOREX"
        raise ValueError(f"Unsupported market '{v}'. Must be one of: US_EQUITIES, INDIAN_NSE, CRYPTO, COMMODITIES, FOREX.")

    @field_validator("instruments")
    @classmethod
    def validate_instruments_list(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("Instruments list must contain at least 1 valid ticker symbol.")
        cleaned = [t.strip().upper() for t in v if t.strip()]
        if not cleaned:
            raise ValueError("Instruments list cannot be empty.")
        if len(cleaned) != len(set(cleaned)):
            duplicates = [t for t in cleaned if cleaned.count(t) > 1]
            raise ValueError(f"Duplicate instruments detected in basket: {list(set(duplicates))}.")
        return cleaned

    @field_validator("horizon")
    @classmethod
    def validate_horizon_field(cls, v: str) -> str:
        h = v.strip().lower()
        if h not in ("1h", "1d", "1wk"):
            raise ValueError(f"Invalid trading horizon '{v}'. Allowed horizons are: '1h', '1d', '1wk'.")
        return h

    @field_validator("duration_type")
    @classmethod
    def validate_duration_type_field(cls, v: str) -> str:
        dt = v.strip().upper()
        if dt not in ("FIXED", "CUSTOM", "MANUAL_STOP"):
            raise ValueError(f"Invalid duration_type '{v}'. Allowed types are: FIXED, CUSTOM, MANUAL_STOP.")
        return dt

    @field_validator("session_end_policy")
    @classmethod
    def validate_policy_field(cls, v: str) -> str:
        pol = v.strip().upper()
        if pol not in ("CLOSE_ALL", "KEEP_OPEN"):
            raise ValueError(f"Invalid session_end_policy '{v}'. Allowed policies are: CLOSE_ALL, KEEP_OPEN.")
        return pol

    @field_validator("currency")
    @classmethod
    def validate_currency_field(cls, v: str) -> str:
        c = v.strip().upper()
        if c not in ("USD", "INR"):
            raise ValueError(f"Unsupported currency '{v}'. Platform supports 'USD' or 'INR'.")
        return c

    @field_validator("allocated_capital")
    @classmethod
    def validate_capital_boundaries(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Allocated virtual capital must be strictly positive.")
        if v < 1_000.0 or v > 10_000_000.0:
            raise ValueError(f"Allocated virtual capital ({v:,.2f}) must be between 1,000 and 10,000,000.")
        return v

    @model_validator(mode="after")
    def validate_cross_field_rules(self) -> "SessionCreateRequest":
        expected_curr = "INR" if self.market == "INDIAN_NSE" else "USD"
        if self.currency != expected_curr:
            raise ValueError(
                f"Currency mismatch: Market '{self.market}' requires currency '{expected_curr}', but got '{self.currency}'."
            )
        if self.duration_type in ("FIXED", "CUSTOM"):
            if self.duration_minutes is None or self.duration_minutes <= 0:
                raise ValueError(f"duration_minutes must be a positive integer for duration_type '{self.duration_type}'.")
            if self.duration_minutes > 10080:
                raise ValueError(f"duration_minutes ({self.duration_minutes}) exceeds maximum permitted duration of 10,080 minutes (1 week).")
        return self


class SessionUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    instruments: Optional[List[str]] = Field(None, min_length=1, max_length=20)
    horizon: Optional[str] = None
    duration_type: Optional[str] = None
    duration_minutes: Optional[int] = None
    session_end_policy: Optional[str] = None
    allocated_capital: Optional[float] = None
    strategy_config: Optional[Dict[str, Any]] = None
    risk_config: Optional[Dict[str, Any]] = None


class SessionStopRequest(BaseModel):
    reason: Optional[str] = Field(default="MANUAL_STOP", description="Reason: MANUAL_STOP, USER_REQUEST, RISK_HALT")


class RecommendationRequest(BaseModel):
    market: str = Field(..., description="Target market: US_EQUITIES, INDIAN_NSE, CRYPTO, COMMODITIES, FOREX")
    target_size: int = Field(default=5, ge=3, le=6, description="Recommended basket size (3 to 6)")
    candidate_tickers: Optional[List[str]] = Field(default=None, description="Optional custom candidate list")
```

### 4.3 Validation Helper Functions

```python
RESERVED_SESSION_SUBPATHS = {"status", "active", "recommendations"}

def _guard_session_id(session_id: str) -> None:
    if session_id.lower() in RESERVED_SESSION_SUBPATHS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{session_id}' is a reserved session route, not a valid session ID.",
        )

CALENDAR_TO_CANONICAL_MARKET = {
    "NSE_CASH": "INDIAN_NSE",
    "US_EQUITIES": "US_EQUITIES",
    "COMMODITY": "COMMODITIES",
    "FOREX": "FOREX",
    "CRYPTO": "CRYPTO",
}

def validate_instruments_jurisdiction(market: str, instruments: List[str]) -> None:
    from src.execution.market_sessions import MarketCalendarManager
    from src.execution.live_bot import ASSET_CATALOG

    calendar = MarketCalendarManager()
    canonical_market = market.strip().upper()
    valid_catalog_tickers = set(ASSET_CATALOG.get(canonical_market, []))

    for ticker in instruments:
        tk = ticker.strip().upper()
        if tk in valid_catalog_tickers:
            continue
        detected_raw = calendar.detect_market_type(tk)
        detected_canonical = CALENDAR_TO_CANONICAL_MARKET.get(detected_raw, detected_raw)
        if detected_canonical != canonical_market:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Instrument mismatch: Ticker '{tk}' belongs to {detected_canonical}, not the selected market '{canonical_market}'.",
            )

def validate_capital_and_currency(market: str, capital: float, currency: str) -> None:
    canonical_market = market.strip().upper()
    expected_currency = "INR" if canonical_market == "INDIAN_NSE" else "USD"
    if currency != expected_currency:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Currency mismatch: Market '{canonical_market}' requires currency '{expected_currency}', but got '{currency}'.",
        )
    if capital <= 0 or capital < 1_000.0 or capital > 10_000_000.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Virtual capital allocation ({capital:,.2f}) must be between 1,000 and 10,000,000 {currency}.",
        )

def validate_duration_and_horizon(duration_type: str, duration_minutes: Optional[int], horizon: str) -> None:
    if horizon not in ("1h", "1d", "1wk"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid trading horizon '{horizon}'. Allowed: '1h', '1d', '1wk'.",
        )
    dt = duration_type.strip().upper()
    if dt not in ("FIXED", "CUSTOM", "MANUAL_STOP"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid duration_type '{dt}'. Allowed: 'FIXED', 'CUSTOM', 'MANUAL_STOP'.",
        )
    if dt in ("FIXED", "CUSTOM"):
        if duration_minutes is None or duration_minutes <= 0 or duration_minutes > 10080:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Duration minutes must be a positive integer <= 10080 (1 week).",
            )
```

### 4.4 SessionManager Access in `server.py`

```python
from src.execution.session_manager import SessionManager

session_manager: Optional[SessionManager] = None

def _get_session_manager() -> SessionManager:
    global session_manager, broker_engine
    if session_manager is None:
        session_manager = SessionManager(ledger=broker_engine.ledger)
    return session_manager
```

### 4.5 11 Endpoint Implementations in `server.py`

```python
# [1] Create Session
@app.post("/api/sessions", tags=["Trading Sessions"], status_code=status.HTTP_201_CREATED)
def create_trading_session(req: SessionCreateRequest):
    validate_capital_and_currency(req.market, req.allocated_capital, req.currency)
    validate_instruments_jurisdiction(req.market, req.instruments)
    validate_duration_and_horizon(req.duration_type, req.duration_minutes, req.horizon)
    mgr = _get_session_manager()
    try:
        session = mgr.create_session(req)
        return {"session": session.to_dict(), "message": "Trading session created successfully."}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

# [2] Get Active Session
@app.get("/api/sessions/active", tags=["Trading Sessions"])
def get_active_trading_session():
    mgr = _get_session_manager()
    session = mgr.get_active_session()
    if session is None:
        return {"session": None}
    return {"session": session.to_dict()}

# [3] Get Basket Recommendations
@app.post("/api/sessions/recommendations", tags=["Trading Sessions"])
def get_session_recommendations(req: RecommendationRequest):
    from src.strategy.universe_selector import UniverseSelector
    bot = _get_live_bot()
    selector = UniverseSelector(
        downloader=engine.downloader if engine else None,
        data_provider=bot.data_provider if bot else None,
    )
    try:
        result = selector.auto_select_basket(
            market=req.market,
            target_size=req.target_size,
            candidate_tickers=req.candidate_tickers,
        )
        return result.to_dict()
    except Exception as exc:
        logger.error(f"Error computing recommendations: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Recommendation failed: {exc}")

# [4] List Sessions
@app.get("/api/sessions", tags=["Trading Sessions"])
def list_trading_sessions(
    status: Optional[str] = Query(None, description="Filter by status"),
    market: Optional[str] = Query(None, description="Filter by market"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    mgr = _get_session_manager()
    sessions = mgr.list_sessions(status=status, market=market, limit=limit, offset=offset)
    return {"total": len(sessions), "sessions": [s.to_dict() for s in sessions]}

# [5] Get Session by ID
@app.get("/api/sessions/{session_id}", tags=["Trading Sessions"])
def get_trading_session_by_id(session_id: str):
    _guard_session_id(session_id)
    mgr = _get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Trading session '{session_id}' not found.")
    return {"session": session.to_dict()}

# [6] Update Session
@app.put("/api/sessions/{session_id}", tags=["Trading Sessions"])
def update_trading_session(session_id: str, req: SessionUpdateRequest):
    _guard_session_id(session_id)
    mgr = _get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")
    if session.status not in ("CREATED", "PAUSED"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot update session '{session_id}' while in '{session.status}' state. Only CREATED or PAUSED sessions can be modified.",
        )
    if req.instruments is not None:
        validate_instruments_jurisdiction(session.market, req.instruments)
    if req.allocated_capital is not None:
        validate_capital_and_currency(session.market, req.allocated_capital, session.currency)
    if req.duration_type is not None or req.duration_minutes is not None:
        dt = req.duration_type or session.duration_type
        dm = req.duration_minutes if req.duration_minutes is not None else session.duration_minutes
        hz = req.horizon or session.horizon
        validate_duration_and_horizon(dt, dm, hz)
    updated = mgr.update_session(session_id, req)
    return {"session": updated.to_dict(), "message": "Session updated successfully."}

# [7] Start Session
@app.post("/api/sessions/{session_id}/start", tags=["Trading Sessions"])
def start_trading_session(session_id: str):
    _guard_session_id(session_id)
    mgr = _get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")
    if session.status == "RUNNING":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Session '{session_id}' is already RUNNING.")
    if session.status in ("COMPLETED", "STOPPED"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot start session '{session_id}' in {session.status} state.")
    active = mgr.get_active_session()
    if active and active.id != session_id and active.status == "RUNNING":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Another session '{active.id}' is currently RUNNING. Stop or pause it first.")
    bot = _get_live_bot()
    started = mgr.start_session(session_id, bot)
    return {"session": started.to_dict(), "message": "Trading session started successfully."}

# [8] Pause Session
@app.post("/api/sessions/{session_id}/pause", tags=["Trading Sessions"])
def pause_trading_session(session_id: str):
    _guard_session_id(session_id)
    mgr = _get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")
    if session.status != "RUNNING":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot pause session in '{session.status}' state. Only RUNNING sessions can be paused.")
    bot = _get_live_bot()
    paused = mgr.pause_session(session_id, bot)
    return {"session": paused.to_dict(), "message": "Trading session paused. New entries halted."}

# [9] Resume Session
@app.post("/api/sessions/{session_id}/resume", tags=["Trading Sessions"])
def resume_trading_session(session_id: str):
    _guard_session_id(session_id)
    mgr = _get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")
    if session.status != "PAUSED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot resume session in '{session.status}' state. Only PAUSED sessions can be resumed.")
    bot = _get_live_bot()
    resumed = mgr.resume_session(session_id, bot)
    return {"session": resumed.to_dict(), "message": "Trading session resumed successfully."}

# [10] Stop Session
@app.post("/api/sessions/{session_id}/stop", tags=["Trading Sessions"])
def stop_trading_session(session_id: str, req: Optional[SessionStopRequest] = None):
    _guard_session_id(session_id)
    mgr = _get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")
    if session.status in ("COMPLETED", "STOPPED"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Session '{session_id}' is already {session.status}.")
    reason = req.reason if req and req.reason else "MANUAL_STOP"
    bot = _get_live_bot()
    stopped = mgr.stop_session(session_id, bot, reason=reason)
    return {"session": stopped.to_dict(), "message": f"Trading session stopped ({reason}). Policy '{stopped.session_end_policy}' executed."}

# [11] Get Session Performance
@app.get("/api/sessions/{session_id}/performance", tags=["Trading Sessions"])
def get_session_performance(session_id: str):
    _guard_session_id(session_id)
    mgr = _get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")
    bot = _get_live_bot()
    metrics = mgr.compute_session_performance(session_id, bot)
    return {"session_id": session_id, "performance": metrics}
```

---

## 5. Verification Method

To independently verify the implementation:

1. **Verify No Route Collision with `/api/sessions/status`**:
   ```powershell
   cd C:\Users\Shivam\Desktop\trade_bot
   py -m pytest tests/test_milestone_m2_sessions.py
   ```
   *Expected*: Passes 5 of 5 tests cleanly without error.

2. **Run New Session Lifecycle Test Suite**:
   Create and execute `tests/test_trading_session_lifecycle.py` verifying:
   - Valid session creation (201 Created).
   - Rejection of capital $< 1,000$, capital $> 10,000,000$, and non-positive capital.
   - Rejection of currency mismatch (`INDIAN_NSE` with `USD`, `US_EQUITIES` with `INR`).
   - Rejection of instrument jurisdiction mismatch (`AAPL` in `INDIAN_NSE`, `RELIANCE.NS` in `US_EQUITIES`).
   - State transition sequencing: `CREATED` -> `RUNNING` -> `PAUSED` -> `RUNNING` -> `STOPPED`.
   - Protection against modifying `RUNNING` session (409 Conflict).
   - Wizard recommendations endpoint returning bounded basket with rationales.
   - Session performance calculation.
   ```powershell
   cd C:\Users\Shivam\Desktop\trade_bot
   py -m pytest tests/test_trading_session_lifecycle.py -v
   ```
   *Expected*: All test cases pass with 0 failures.

3. **Frontend Build & Test Checks**:
   ```powershell
   cd C:\Users\Shivam\Desktop\trade_bot\frontend
   npm test
   npm run build
   ```
   *Expected*: Zero TypeScript compilation errors and all Vitest unit tests pass.
