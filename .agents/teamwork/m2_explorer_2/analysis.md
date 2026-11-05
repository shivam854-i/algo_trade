# Milestone 2 (Part B): FastAPI Endpoints & Independent Backend Validation Specification

**Module**: SYNAPSE-TITAN REST API Gateway & Session Lifecycle Management  
**Author**: FastAPI Endpoints & Validation Explorer (`teamwork_explorer`)  
**Target Repository**: `C:\Users\Shivam\Desktop\trade_bot`  
**File Under Specification**: `server.py`  
**Date**: 2026-11-05  

---

## 1. Executive Summary

Milestone 2 establishes institutional-grade user session lifecycle management for the SYNAPSE-TITAN algorithmic paper-trading platform. While Milestone 2 Part A defines the underlying `TradingSession` entity model and SQLite database persistence in `src/execution/session_manager.py` and `src/execution/broker.py`, Part B (this specification) establishes:

1. **11 Dedicated REST API Endpoints in `server.py`**:
   - `POST /api/sessions`: Create new session with strict backend validation.
   - `GET /api/sessions/active`: Retrieve current active session or `{"session": null}`.
   - `GET /api/sessions/{session_id}`: Retrieve session by ID.
   - `GET /api/sessions`: List sessions with query filters (status, market, limit, offset).
   - `PUT /api/sessions/{session_id}`: Update session configuration (permitted only in `CREATED` or `PAUSED` state).
   - `POST /api/sessions/{session_id}/start`: Start trading session, arm autonomous bot, allocate virtual capital.
   - `POST /api/sessions/{session_id}/pause`: Pause session, halt new entries, keep positions monitored.
   - `POST /api/sessions/{session_id}/resume`: Resume session, adjust expiry deadline by pause duration.
   - `POST /api/sessions/{session_id}/stop`: Stop session, execute session-end policy (`CLOSE_ALL` vs `KEEP_OPEN`).
   - `POST /api/sessions/recommendations`: Auto-select recommended stock basket with rationales via `UniverseSelector.auto_select_basket`.
   - `GET /api/sessions/{session_id}/performance`: Retrieve financial KPIs, P&L, drawdown, and trade history.

2. **Guaranteed Route Disambiguation**:
   - Prevention of path collision with the existing physical exchange endpoint `@app.get("/api/sessions/status")` at `server.py:726` using both strict route declaration order (static fixed paths registered before dynamic path parameters) and secondary reserved-keyword path guards.

3. **Five Pillars of Independent Backend Validation**:
   - **Capital Validation**: Strictly positive virtual amount, bounded between 1,000 and 10,000,000.
   - **Currency Validation**: Enforcing `INR` for `INDIAN_NSE` and `USD` for `US_EQUITIES`, `CRYPTO`, `FOREX`, `COMMODITIES`.
   - **Instrument Jurisdiction Validation**: Verifying every ticker belongs to the requested market jurisdiction using `MarketCalendarManager.detect_market_type` and `ASSET_CATALOG`.
   - **Duration & Horizon Validation**: Separating holding horizon (`1h`, `1d`, `1wk`) from session run duration (`FIXED`, `CUSTOM`, `MANUAL_STOP`) with a 1-week (10,080 min) maximum ceiling.
   - **Session-End Policy Validation**: Enforcing policy in `["CLOSE_ALL", "KEEP_OPEN"]`.

---

## 2. Route Architecture & Disambiguation Strategy

### 2.1 The Collision Hazard
In Starlette / FastAPI, routes registered with dynamic path parameters (e.g., `/api/sessions/{session_id}`) will greedily match any subpath unless static routes are registered earlier or regex path constraints are applied.

`server.py:726-730` already exposes:
```python
@app.get("/api/sessions/status", tags=["Sessions"])
def get_sessions_status():
    """Returns complete physical exchange session states, countdowns, and statutory holiday statuses."""
    bot = _get_live_bot()
    return bot.get_all_market_sessions()
```
Existing acceptance test suite `tests/test_milestone_m2_sessions.py` explicitly tests this endpoint:
```python
r_sess = client.get("/api/sessions/status")
assert r_sess.status_code == 200
sessions = r_sess.json()
assert "NSE_INDIA" in sessions
```
If `/api/sessions/{session_id}` were placed before `/api/sessions/status`, FastAPI would capture `"status"` as `session_id`, attempt to find a session with ID `"status"`, fail with a 404 error, and break existing test suites.

### 2.2 Dual-Layer Disambiguation Solution

#### Layer 1: Declaration Order (Precedence by Definition)
All static routes under `/api/sessions` must be registered **before** any dynamic routes containing `{session_id}`:
1. `GET /api/sessions/status` (Existing physical exchange sessions — line 726)
2. `GET /api/sessions/active` (New — returns active session)
3. `POST /api/sessions/recommendations` (New — wizard auto-select recommendations)
4. `GET /api/sessions` (New — session collection list)
5. `POST /api/sessions` (New — create session)
6. Parameterized routes:
   - `GET /api/sessions/{session_id}`
   - `PUT /api/sessions/{session_id}`
   - `POST /api/sessions/{session_id}/start`
   - `POST /api/sessions/{session_id}/pause`
   - `POST /api/sessions/{session_id}/resume`
   - `POST /api/sessions/{session_id}/stop`
   - `GET /api/sessions/{session_id}/performance`

#### Layer 2: Handler-Level Reserved Subpath Guard
In every parameterized endpoint receiving `session_id: str`, an immediate rejection guard protects reserved keywords:
```python
RESERVED_SESSION_SUBPATHS = {"status", "active", "recommendations"}

def _guard_session_id(session_id: str):
    if session_id.lower() in RESERVED_SESSION_SUBPATHS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{session_id}' is a reserved API route name and cannot be used as a session ID."
        )
```

---

## 3. Pydantic Request & Response Schemas

All schemas use Pydantic v2 conventions (`field_validator`, `model_validator`) with comprehensive type hints, descriptions, and OpenAPI documentation metadata.

```python
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

# ----------------- Enums ----------------- #

class SessionStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"

class SessionEndPolicy(str, Enum):
    CLOSE_ALL = "CLOSE_ALL"
    KEEP_OPEN = "KEEP_OPEN"

class DurationType(str, Enum):
    FIXED = "FIXED"
    CUSTOM = "CUSTOM"
    MANUAL_STOP = "MANUAL_STOP"

class TradingHorizon(str, Enum):
    ONE_HOUR = "1h"
    ONE_DAY = "1d"
    ONE_WEEK = "1wk"

class MarketJurisdiction(str, Enum):
    US_EQUITIES = "US_EQUITIES"
    INDIAN_NSE = "INDIAN_NSE"
    CRYPTO = "CRYPTO"
    COMMODITIES = "COMMODITIES"
    FOREX = "FOREX"


# ----------------- Request Schemas ----------------- #

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
        # Normalization of common aliases
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
        raise ValueError(
            f"Unsupported market '{v}'. Must be one of: US_EQUITIES, INDIAN_NSE, CRYPTO, COMMODITIES, FOREX."
        )

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
        # 1. Currency vs Market Matching
        expected_curr = "INR" if self.market == "INDIAN_NSE" else "USD"
        if self.currency != expected_curr:
            raise ValueError(
                f"Currency mismatch: Market '{self.market}' requires currency '{expected_curr}', but got '{self.currency}'."
            )

        # 2. Duration minutes enforcement
        if self.duration_type in ("FIXED", "CUSTOM"):
            if self.duration_minutes is None or self.duration_minutes <= 0:
                raise ValueError(
                    f"duration_minutes must be a positive integer for duration_type '{self.duration_type}'."
                )
            if self.duration_minutes > 10080:  # 1 week in minutes (7 * 24 * 60)
                raise ValueError(
                    f"duration_minutes ({self.duration_minutes}) exceeds maximum permitted duration of 10,080 minutes (1 week)."
                )
        elif self.duration_type == "MANUAL_STOP":
            if self.duration_minutes is not None and self.duration_minutes < 0:
                raise ValueError("duration_minutes cannot be negative.")

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

    @field_validator("instruments")
    @classmethod
    def clean_instruments(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        cleaned = [t.strip().upper() for t in v if t.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("Duplicate instruments detected in basket.")
        return cleaned


class SessionStopRequest(BaseModel):
    reason: Optional[str] = Field(default="MANUAL_STOP", description="Reason: MANUAL_STOP, USER_REQUEST, RISK_HALT")


class RecommendationRequest(BaseModel):
    market: str = Field(..., description="Target market: US_EQUITIES, INDIAN_NSE, CRYPTO, COMMODITIES, FOREX")
    target_size: int = Field(default=5, ge=3, le=6, description="Recommended basket size (3 to 6)")
    candidate_tickers: Optional[List[str]] = Field(default=None, description="Optional custom candidate list")


# ----------------- Response Schemas ----------------- #

class SessionResponse(BaseModel):
    session: Dict[str, Any]
    message: Optional[str] = None


class SessionListResponse(BaseModel):
    total: int
    sessions: List[Dict[str, Any]]


class CandidateEvaluationResponse(BaseModel):
    ticker: str
    market: str
    passed_all_gates: bool
    data_quality_score: float
    missing_bar_ratio: float
    zero_volume_ratio: float
    adv: float
    adv_currency: str
    adv_threshold: float
    spread_bps: float
    annualized_volatility: float
    composite_score: float
    rejection_reasons: List[str]
    pass_details: Dict[str, Any]
    summary_rationale: str


class RecommendationResponse(BaseModel):
    market: str
    target_size: int
    selected_instruments: List[str]
    evaluations: Dict[str, CandidateEvaluationResponse]
    passed_count: int
    rejected_count: int
    summary_rationale: str
    timestamp_utc: str


class SessionPerformanceMetrics(BaseModel):
    session_id: str
    status: str
    market: str
    currency: str
    starting_capital: float
    current_cash: float
    invested_equity: float
    total_equity: float
    realized_pnl: float
    unrealized_pnl: float
    net_pnl: float
    net_return_pct: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    max_drawdown_pct: float
    sharpe_ratio: Optional[float]
    elapsed_seconds: float
    remaining_seconds: Optional[float]
    trades: List[Dict[str, Any]]
    positions: List[Dict[str, Any]]


class PerformanceResponse(BaseModel):
    session_id: str
    performance: SessionPerformanceMetrics
```

---

## 4. Independent Backend Validation Architecture

Backend validation operates independently of frontend validation to guarantee that API calls from curl, mobile apps, or malicious scripts cannot create corrupted sessions.

### 4.1 Jurisdiction Mapping & Instrument Verification

Instruments must match the jurisdiction of the requested market:

```python
from src.execution.market_sessions import MarketCalendarManager
from src.execution.live_bot import ASSET_CATALOG

_calendar = MarketCalendarManager()

# Map detected calendar types to canonical platform market names
CALENDAR_TO_CANONICAL_MARKET = {
    "NSE_CASH": "INDIAN_NSE",
    "US_EQUITIES": "US_EQUITIES",
    "COMMODITY": "COMMODITIES",
    "FOREX": "FOREX",
    "CRYPTO": "CRYPTO",
}

def validate_instruments_jurisdiction(market: str, instruments: List[str]) -> None:
    """Verifies that every instrument belongs to the selected market jurisdiction.
    
    Raises:
        HTTPException(status_code=400) if any instrument does not belong to the market.
    """
    canonical_market = market.strip().upper()
    valid_catalog_tickers = set(ASSET_CATALOG.get(canonical_market, []))

    for ticker in instruments:
        tk = ticker.strip().upper()
        # 1. Fast catalog check
        if tk in valid_catalog_tickers:
            continue

        # 2. Dynamic market calendar detection
        detected_raw = _calendar.detect_market_type(tk)
        detected_canonical = CALENDAR_TO_CANONICAL_MARKET.get(detected_raw, detected_raw)

        if detected_canonical != canonical_market:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Instrument jurisdiction mismatch: Ticker '{tk}' belongs to jurisdiction "
                    f"'{detected_canonical}', not the selected market '{canonical_market}'."
                ),
            )
```

### 4.2 Capital Boundaries and Currency Verification

```python
def validate_capital_and_currency(market: str, capital: float, currency: str) -> None:
    """Validates capital limits and currency alignment with market jurisdiction."""
    canonical_market = market.strip().upper()
    expected_currency = "INR" if canonical_market == "INDIAN_NSE" else "USD"

    if currency != expected_currency:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Currency mismatch: Market '{canonical_market}' requires currency "
                f"'{expected_currency}', but got '{currency}'."
            ),
        )

    if capital <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Allocated virtual capital must be strictly positive.",
        )

    if capital < 1_000.0 or capital > 10_000_000.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Virtual capital allocation ({capital:,.2f}) must be between 1,000 and 10,000,000 {currency}.",
        )
```

### 4.3 Duration and Horizon Verification

```python
def validate_duration_and_horizon(duration_type: str, duration_minutes: Optional[int], horizon: str) -> None:
    """Validates holding horizon separation and run duration boundaries."""
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
        if duration_minutes is None or duration_minutes <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"duration_minutes must be a positive integer for duration_type '{dt}'.",
            )
        if duration_minutes > 10080:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"duration_minutes ({duration_minutes}) exceeds maximum permitted limit of 10,080 minutes (1 week).",
            )
```

---

## 5. Detailed Specifications for All 11 Endpoints

Below are the blueprints and implementations to be inserted into `server.py`.

### Endpoint 1: `POST /api/sessions` — Create Session
```python
@app.post("/api/sessions", tags=["Trading Sessions"], status_code=status.HTTP_201_CREATED)
def create_trading_session(req: SessionCreateRequest):
    """Creates a new user trading session with independent backend parameter validation."""
    # 1. Independent validation
    validate_capital_and_currency(req.market, req.allocated_capital, req.currency)
    validate_instruments_jurisdiction(req.market, req.instruments)
    validate_duration_and_horizon(req.duration_type, req.duration_minutes, req.horizon)

    mgr = _get_session_manager()
    try:
        session = mgr.create_session(req)
        return {"session": session.to_dict(), "message": "Trading session created successfully."}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
```

### Endpoint 2: `GET /api/sessions/active` — Get Active Session
```python
@app.get("/api/sessions/active", tags=["Trading Sessions"])
def get_active_trading_session():
    """Returns currently active (RUNNING or PAUSED) trading session, or {'session': null}."""
    mgr = _get_session_manager()
    session = mgr.get_active_session()
    if session is None:
        return {"session": None}
    return {"session": session.to_dict()}
```

### Endpoint 3: `GET /api/sessions/{session_id}` — Get Session by ID
```python
@app.get("/api/sessions/{session_id}", tags=["Trading Sessions"])
def get_trading_session_by_id(session_id: str):
    """Fetches details for a specific trading session by ID."""
    _guard_session_id(session_id)
    mgr = _get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trading session '{session_id}' not found.",
        )
    return {"session": session.to_dict()}
```

### Endpoint 4: `GET /api/sessions` — List Sessions
```python
@app.get("/api/sessions", tags=["Trading Sessions"])
def list_trading_sessions(
    status: Optional[str] = Query(None, description="Filter by status (CREATED, RUNNING, PAUSED, COMPLETED, STOPPED)"),
    market: Optional[str] = Query(None, description="Filter by market (US_EQUITIES, INDIAN_NSE, etc.)"),
    limit: int = Query(20, ge=1, le=100, description="Max sessions to return"),
    offset: int = Query(0, ge=0, description="Offset index"),
):
    """Lists trading sessions with optional filtering by status and market."""
    mgr = _get_session_manager()
    sessions = mgr.list_sessions(status=status, market=market, limit=limit, offset=offset)
    return {
        "total": len(sessions),
        "sessions": [s.to_dict() for s in sessions],
    }
```

### Endpoint 5: `PUT /api/sessions/{session_id}` — Update Session
```python
@app.put("/api/sessions/{session_id}", tags=["Trading Sessions"])
def update_trading_session(session_id: str, req: SessionUpdateRequest):
    """Updates session parameters. Permitted ONLY when session is in CREATED or PAUSED state."""
    _guard_session_id(session_id)
    mgr = _get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trading session '{session_id}' not found.",
        )

    if session.status not in ("CREATED", "PAUSED"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot update session '{session_id}' while in '{session.status}' state. Only CREATED or PAUSED sessions can be modified.",
        )

    # Validate updated instruments if provided
    if req.instruments is not None:
        validate_instruments_jurisdiction(session.market, req.instruments)

    # Validate updated capital if provided
    if req.allocated_capital is not None:
        validate_capital_and_currency(session.market, req.allocated_capital, session.currency)

    # Validate updated duration if provided
    if req.duration_type is not None or req.duration_minutes is not None:
        dt = req.duration_type or session.duration_type
        dm = req.duration_minutes if req.duration_minutes is not None else session.duration_minutes
        hz = req.horizon or session.horizon
        validate_duration_and_horizon(dt, dm, hz)

    updated = mgr.update_session(session_id, req)
    return {"session": updated.to_dict(), "message": "Session updated successfully."}
```

### Endpoint 6: `POST /api/sessions/{session_id}/start` — Start Session
```python
@app.post("/api/sessions/{session_id}/start", tags=["Trading Sessions"])
def start_trading_session(session_id: str):
    """Starts a trading session, arms the autonomous bot, resets/allocates capital, and activates trading."""
    _guard_session_id(session_id)
    mgr = _get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")

    if session.status == "RUNNING":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Session '{session_id}' is already RUNNING.")
    if session.status in ("COMPLETED", "STOPPED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot start session '{session_id}' because it is already {session.status}.",
        )

    # Check for another active running session
    active = mgr.get_active_session()
    if active and active.id != session_id and active.status == "RUNNING":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Another session '{active.id}' is currently RUNNING. Pause or stop it before starting a new session.",
        )

    bot = _get_live_bot()
    started = mgr.start_session(session_id, bot)
    return {"session": started.to_dict(), "message": "Trading session started successfully."}
```

### Endpoint 7: `POST /api/sessions/{session_id}/pause` — Pause Session
```python
@app.post("/api/sessions/{session_id}/pause", tags=["Trading Sessions"])
def pause_trading_session(session_id: str):
    """Pauses trading session: halts new entries while preserving open positions for monitoring."""
    _guard_session_id(session_id)
    mgr = _get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")

    if session.status != "RUNNING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot pause session '{session_id}' in '{session.status}' state. Only RUNNING sessions can be paused.",
        )

    bot = _get_live_bot()
    paused = mgr.pause_session(session_id, bot)
    return {"session": paused.to_dict(), "message": "Trading session paused. New entries halted."}
```

### Endpoint 8: `POST /api/sessions/{session_id}/resume` — Resume Session
```python
@app.post("/api/sessions/{session_id}/resume", tags=["Trading Sessions"])
def resume_trading_session(session_id: str):
    """Resumes paused session, extends expiration countdown by elapsed pause time, and resumes bot entries."""
    _guard_session_id(session_id)
    mgr = _get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")

    if session.status != "PAUSED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot resume session '{session_id}' in '{session.status}' state. Only PAUSED sessions can be resumed.",
        )

    bot = _get_live_bot()
    resumed = mgr.resume_session(session_id, bot)
    return {"session": resumed.to_dict(), "message": "Trading session resumed successfully."}
```

### Endpoint 9: `POST /api/sessions/{session_id}/stop` — Stop Session
```python
@app.post("/api/sessions/{session_id}/stop", tags=["Trading Sessions"])
def stop_trading_session(session_id: str, req: Optional[SessionStopRequest] = None):
    """Stops trading session and triggers session-end policy (CLOSE_ALL vs KEEP_OPEN)."""
    _guard_session_id(session_id)
    mgr = _get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")

    if session.status in ("COMPLETED", "STOPPED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session '{session_id}' is already {session.status}.",
        )

    reason = req.reason if req and req.reason else "MANUAL_STOP"
    bot = _get_live_bot()
    stopped = mgr.stop_session(session_id, bot, reason=reason)
    return {
        "session": stopped.to_dict(),
        "message": f"Trading session stopped ({reason}). End policy '{stopped.session_end_policy}' executed.",
    }
```

### Endpoint 10: `POST /api/sessions/recommendations` — Basket Recommendations
```python
@app.post("/api/sessions/recommendations", tags=["Trading Sessions"])
def get_session_recommendations(req: RecommendationRequest):
    """Auto-selects bounded recommended stock basket (3-6 instruments) with quantitative rationales."""
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate universe recommendations: {str(exc)}",
        )
```

### Endpoint 11: `GET /api/sessions/{session_id}/performance` — Performance Metrics
```python
@app.get("/api/sessions/{session_id}/performance", tags=["Trading Sessions"])
def get_session_performance(session_id: str):
    """Returns complete financial KPIs, P&L, drawdown, trade history, and duration countdown for a session."""
    _guard_session_id(session_id)
    mgr = _get_session_manager()
    session = mgr.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")

    bot = _get_live_bot()
    metrics = mgr.compute_session_performance(session_id, bot)
    return {
        "session_id": session_id,
        "performance": metrics,
    }
```

---

## 6. Integration Test Specification for `tests/test_trading_session_lifecycle.py`

To independently verify the implementation, `tests/test_trading_session_lifecycle.py` will validate:

1. **Route Precedence & Disambiguation**:
   - `GET /api/sessions/status`: Confirms 200 OK with physical exchange status dictionary, proving zero interference from `{session_id}` route.
   - Calling `/api/sessions/status` does NOT invoke `get_trading_session_by_id`.
   - Accessing `/api/sessions/active` returns `{"session": null}` initially, not a 404 for missing session "active".
2. **Session Creation & Independent Validation**:
   - `POST /api/sessions` with valid US equities payload -> 201 Created.
   - Capital < 1,000 -> 400 Bad Request.
   - Capital > 10,000,000 -> 400 Bad Request.
   - Capital <= 0 -> 400 Bad Request.
   - Currency mismatch (`INDIAN_NSE` with `USD`) -> 400 Bad Request.
   - Currency mismatch (`US_EQUITIES` with `INR`) -> 400 Bad Request.
   - Instrument mismatch (`AAPL` in `INDIAN_NSE` session) -> 400 Bad Request.
   - Instrument mismatch (`RELIANCE.NS` in `US_EQUITIES` session) -> 400 Bad Request.
   - Empty instruments list -> 422 / 400.
   - Duplicate tickers -> 422 / 400.
   - Duration > 10,080 minutes -> 400 Bad Request.
   - Duration <= 0 for FIXED duration -> 400 Bad Request.
3. **Session Querying & Listing**:
   - `GET /api/sessions` lists created sessions.
   - Query filters by `status=CREATED` and `market=US_EQUITIES`.
   - `GET /api/sessions/{session_id}` returns exact session details.
   - Non-existent session returns 404.
4. **Session Update Rules**:
   - `PUT /api/sessions/{session_id}` in `CREATED` state updates name, instruments, capital -> 200 OK.
   - Updating capital or instruments re-runs validation.
   - Updating session while `RUNNING` -> 409 Conflict.
5. **State Machine Lifecycle Transitions**:
   - `POST /api/sessions/{session_id}/start`: Transitions `CREATED` -> `RUNNING`. Arms bot.
   - Starting a second session while one is `RUNNING` -> 409 Conflict.
   - `POST /api/sessions/{session_id}/pause`: Transitions `RUNNING` -> `PAUSED`. Halts bot (`bot.is_running is False`).
   - Pausing when not `RUNNING` -> 400 Bad Request.
   - `POST /api/sessions/{session_id}/resume`: Transitions `PAUSED` -> `RUNNING`. Adjusts `expires_at`.
   - Resuming when not `PAUSED` -> 400 Bad Request.
   - `POST /api/sessions/{session_id}/stop`: Transitions to `STOPPED`. Triggers session-end policy.
   - Stopping an already stopped session -> 400 Bad Request.
6. **Recommendations Endpoint**:
   - `POST /api/sessions/recommendations` with `market="US_EQUITIES"` returns bounded basket (3-6 tickers) with rationale, data quality scores, ADV, and spread.
   - `POST /api/sessions/recommendations` with `market="INDIAN_NSE"` returns Indian tickers with INR thresholds.
7. **Performance Metrics Endpoint**:
   - `GET /api/sessions/{session_id}/performance` returns complete KPIs: cash, total equity, P&L, win rate, and trades.
