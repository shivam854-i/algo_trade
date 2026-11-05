# Quantitative Strategy Handoff Report: R4 & R5 Strategy Engine

**Author**: Quantitative Strategy Explorer (`teamwork_explorer`)  
**Recipient**: Lead Orchestrator & Quantitative Implementation Agents  
**Date**: November 5, 2026  
**Type**: Hard Handoff (Investigation Complete)  
**Location**: `C:\Users\Shivam\Desktop\trade_bot\.agents\teamwork\explorer_survey_quant\handoff.md`  

---

## 1. Observation

Direct observations from inspecting `C:\Users\Shivam\Desktop\trade_bot`:

1. **Missing Strategy Package**:
   - `src/` currently contains `backtest/`, `data/`, `execution/`, `features/`, `models/`, `observer/`, and `pipeline.py`.
   - The directory `src/strategy/` does **not exist**. Quantitative decision-making and opportunity selection are currently coupled directly inside `src/execution/live_bot.py`.

2. **Naive Opportunity Ranking in Live Bot**:
   - In `src/execution/live_bot.py` lines 981–984, opportunity selection is naively based on absolute probability distance from 0.50:
     ```python
     candidates.sort(
         key=lambda x: abs(x[1].meta_prediction.success_probability - 0.50),
         reverse=True,
     )
     ```
     This ignores expected win magnitude, expected loss magnitude, statutory friction hurdles, uncertainty bounds, and regime alignment.

3. **Existing Model Capabilities**:
   - `src/models/meta_labeler.py`: Two-stage meta-labeling with purged High/Low triple-barrier labeling, Conservative Conflict Resolution (Stop-Loss priority on dual-wick breach in line 114: `if l_bar <= sl_price: hit_sl = True; ... break`), and empirical payoff asymmetry ratio calibration ($b = \text{AvgWin} / \text{AvgLoss}$).
   - `src/models/regime_hmm.py`: 3-state Causal Forward-Filtering Hidden Markov Model ($\alpha_t(j)$) with Parkinson High-Low jump override and hysteresis quarantine (lines 80–113).
   - `src/models/gpu_acceleration.py`: Supervised Pinball-Loss Causal Quantile TCN predicting monotonic non-crossing quantiles $q_{10} \le q_{50} \le q_{90}$ with ensemble probability fusion (line 209: `fused_prob = round(0.65 * lgbm_prob + 0.35 * neural_prob, 3)`).
   - `src/models/hrp_allocator.py`: Diagonal-preserving Marchenko-Pastur RMT de-noising and Ward's linkage Hierarchical Risk Parity.
   - `src/execution/guardrails.py`: Asymmetric CVaR-Kelly sizing, 20% single-position leverage cap, target volatility scaling, and quadratic drawdown circuit breaker (line 103).
   - `src/execution/frictions.py`: Statutory schedules for US, NSE Cash (intraday vs delivery STT/GST), Crypto, Forex, Commodity, plus Almgren-Chriss square-root market impact and microstructure circuit breakers.

4. **Hardcoded Daily Horizon Assumptions**:
   - `src/features/technical.py` hardcodes daily annualization: `feats["RealizedVol_21d"] = feats["LogReturn"].rolling(window=21).std() * np.sqrt(252)` (line 81).
   - `src/pipeline.py` uses fixed lookback period `"2y"` and interval `"1d"`.
   - `src/execution/live_bot.py` uses fixed `period="1y"` and `interval="1d"`.
   - The system lacks dynamic binding to the user's chosen trading horizon (1 hour, 1 day, 1 week).

5. **Test Suite Status**:
   - Command `py tests/test_phase1_phase2_fixes.py` exited with code 0:
     ```
     [PASS 1] FracDiff analytical lookback L*(0.25, 1e-3) = 21 bars
     [PASS 2] Causal HMM Future-Invariance (state diffs before bar 150): 0 (Expected: 0)
     [PASS 3] Triple-Barrier Dual-Breach Wick Label (Conservative Conflict Resolution): 0 (Expected: 0)
     [PASS 4] HRP RMT Diagonal Variance Preservation Error: 0.00e+00, Ward Weights Sum: 1.0001
     [PASS 5] Frictions -> NSE Delivery: 34.97 bps, NSE Intraday: 16.27 bps, US ($200): 8.15 bps
     [PASS 6] Asymmetric CVaR-Kelly -> Low-Prob (p=0.35) Weight: 0.0%, High-Prob Cap: 20.0%
     [PASS 7] Supervised TCN Pinball Loss: 0.00548, Monotonic Quantiles: q10=-0.0206 <= q50=0.0014 <= q90=0.0224
     [PASS 8] Microstructure Gates -> FX Rollover Allowed: False, Gold Sweep Allowed: False
     === ALL 8 PHASE 1, 2 & 3 MATHEMATICAL & MICROSTRUCTURE INVARIANTS VERIFIED ===
     ```
   - Running `py -m pytest tests/` completed with 130 passed, 1 failed (a 1-cent floating point precision artifact in `test_gate2_adversarial_order_and_session.py`: `95114.66 == 95114.65 ± 0.01`).

---

## 2. Logic Chain

1. **From Observation 1 & 2 to Strategy Package Creation**:
   - Because `src/strategy/` does not exist and `live_bot.py` contains ad-hoc probability ranking, modular quantitative components cannot be isolated, tested, or reused across backtesting, live trading, and API endpoints.
   - Therefore, a dedicated `src/strategy/` package must be created containing `universe_selector.py`, `trade_evaluator.py`, `trade_ranker.py`, `portfolio_selector.py`, `decision_explainer.py`, and `horizon_mapper.py`.

2. **From Observation 2 & 3 to Mathematical Net Expectancy**:
   - Naive probability ranking fails whenever high-probability trades have poor risk-reward ratios or when statutory frictions exceed gross alpha.
   - By combining the meta-model's calibrated probabilities ($P(\text{Win})$), TCN quantile uncertainty bounds, conditional payoff barriers ($\mathbb{E}[\text{Win}]$, $\mathbb{E}[\text{Loss}]$), and `FrictionEvaluator`'s round-trip cost, `TradeEvaluator` computes true Net Expectancy:
     $$\text{EV} = P(\text{Win}) \cdot \mathbb{E}[\text{Win} \mid \text{Win}] - (1 - P(\text{Win})) \cdot \mathbb{E}[\text{Loss} \mid \text{Loss}] - \text{Expected Friction Cost}$$
   - Any opportunity with $\text{EV} \le 0$ has negative mathematical edge and is rejected.

3. **From Observation 3 to Opportunity Ranking & Portfolio Allocation**:
   - `TradeRanker` scales positive EV opportunities by risk-adjusted value ($\text{EV} / \sigma$) and market regime alignment (e.g. boosting trend trades in State 0, vetoing in Crisis State 2).
   - `PortfolioSelector` allocates capital via Fractional Kelly or HRP.
   - When no opportunities meet the positive EV threshold ($\text{EV} > 0$), `PortfolioSelector` triggers the mandatory 100% Cash allocation guarantee.

4. **From Observation 4 to Horizon Mapping (R5)**:
   - A 1-hour horizon requires high-frequency intraday bars (5m), tight ATR barriers ($1.0\times / 0.75\times$), fast HMM detection, and intraday friction schedules.
   - A 1-week horizon requires daily bars (1d), wider ATR barriers ($2.0\times / 1.25\times$), multi-day delivery STT schedules, and longer holding periods.
   - `HorizonMapper` binds these parameters dynamically, ensuring model consistency across horizons.

5. **From Observation 3 to Capital Sizing Invariance (R5)**:
   - Model predictions reflect price physics and must remain decoupled from account balance.
   - Position sizing scales linearly with starting capital:
     $$\text{Allocated Dollars}_i = \text{Virtual Capital} \times w_i, \quad \text{Shares}_i = \frac{\text{Allocated Dollars}_i}{P_{\text{entry}, i}}$$
     leaving win probabilities and price targets untouched.

---

## 3. Caveats

1. **Frontend UI Scope**:
   - Investigation is focused on quantitative backend algorithms and interfaces. Frontend React components (Setup Wizard steps, activity feed UI) are designed to consume these contracts but implemented by the UI agent.
2. **Yahoo Finance Intraday Lookback Constraints**:
   - For 1-hour horizon (5-minute bars), Yahoo Finance caps historical lookbacks to 60 days. The downloader automatically clamps lookback periods to prevent 400 Bad Request errors.
3. **No Overfitting Guarantee**:
   - The net expectancy formula relies on calibrated probabilities and historical barriers. An uncertainty margin is subtracted to enforce conservative estimation.

---

## 4. Conclusion & Concrete Design Blueprint

### 4.1 Interface Contracts and Class Designs

#### A. `UniverseSelector` (`src/strategy/universe_selector.py`)
```python
class UniverseSelector:
    """Filters instruments based on data quality, liquidity, spread, volatility, and tradability."""

    def __init__(self, criteria: Optional[UniverseSelectionCriteria] = None):
        self.criteria = criteria or UniverseSelectionCriteria()

    def evaluate_instrument(
        self,
        ticker: str,
        ohlcv_df: pd.DataFrame,
        live_quote: Optional[LiveQuote] = None,
        market_type: Optional[str] = None,
    ) -> CandidateEvaluation:
        """Evaluates data quality (>=90%), ADV ($5M USD / ₹50M INR), spread (<=25 bps), and volatility (8%-100%)."""

    def auto_select_basket(
        self,
        market: str,
        target_size: int = 5,
        candidate_tickers: Optional[List[str]] = None,
        data_provider: Optional[BaseMarketDataProvider] = None,
        downloader: Optional[MarketDataDownloader] = None,
    ) -> UniverseSelectionResult:
        """Returns bounded recommended basket (3-6 instruments) with per-instrument rationales for the setup wizard."""
```

#### B. `TradeEvaluator` (`src/strategy/trade_evaluator.py`)
```python
@dataclass
class TradeEvaluationResult:
    ticker: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    target_price: float
    stop_price: float
    win_probability: float  # Calibrated fused probability
    conservative_win_prob: float  # Uncertainty-adjusted lower bound
    loss_probability: float
    expected_win_return_pct: float  # E[Win | Win]
    expected_loss_return_pct: float  # E[Loss | Loss] including gap risk
    round_trip_friction_pct: float  # Statutory + Almgren-Chriss slippage
    net_expectancy_pct: float  # EV = P(Win)*E[Win] - P(Loss)*E[Loss] - Friction
    is_positive_ev: bool  # net_expectancy_pct >= min_hurdle (e.g. 0.20%)
    rejection_reason: Optional[str] = None

class TradeEvaluator:
    """Computes mathematical Net Expectancy with uncertainty bounds and friction costs."""

    def evaluate(
        self,
        analysis: SingleAssetAnalysis,
        horizon_params: Optional[HorizonParameters] = None,
        min_ev_hurdle_pct: float = 0.20,
    ) -> TradeEvaluationResult: ...
```

#### C. `TradeRanker` (`src/strategy/trade_ranker.py`)
```python
@dataclass
class RankedOpportunity:
    rank: int
    ticker: str
    direction: str
    evaluation: TradeEvaluationResult
    risk_adjusted_value: float  # EV / Volatility
    regime_multiplier: float  # 1.25 (Trend-aligned), 1.15 (Range-aligned), 0.0 (Crisis)
    composite_score: float
    is_eligible: bool
    rank_justification: str

class TradeRanker:
    """Ranks opportunities by risk-adjusted expected net value and market regime alignment."""

    def rank_opportunities(
        self,
        evaluations: List[TradeEvaluationResult],
        regimes: Dict[str, RegimeState],
        analyses: Dict[str, SingleAssetAnalysis],
    ) -> List[RankedOpportunity]: ...
```

#### D. `PortfolioSelector` (`src/strategy/portfolio_selector.py`)
```python
@dataclass
class PortfolioAllocationResult:
    weights: Dict[str, float]  # ticker -> weight (and "CASH" -> cash_weight)
    cash_weight: float
    allocated_capital: Dict[str, float]  # ticker -> dollar amount
    shares: Dict[str, float]  # ticker -> share quantity
    is_100_percent_cash: bool
    method: str  # "KELLY" or "HRP"
    explanation: str

class PortfolioSelector:
    """Allocates virtual capital via Kelly or HRP with 100% Cash fallback."""

    def allocate(
        self,
        ranked_opportunities: List[RankedOpportunity],
        total_virtual_equity: float,
        method: str = "KELLY",
        returns_df: Optional[pd.DataFrame] = None,
        kelly_fraction: float = 0.30,
        target_vol: float = 0.15,
        current_drawdown: float = 0.0,
        max_position_cap: float = 0.20,
    ) -> PortfolioAllocationResult:
        """If zero opportunities have EV > 0, returns weights={"CASH": 1.0}, cash_weight=1.0."""
```

#### E. `DecisionExplainer` (`src/strategy/decision_explainer.py`)
```python
@dataclass
class PlainLanguageExplanation:
    ticker: str
    action: str  # "ACCEPTED", "REJECTED", "HELD_IN_CASH"
    headline: str
    summary: str
    factors: Dict[str, str]
    metrics: Dict[str, Any]
    timestamp_utc: str

class DecisionExplainer:
    """Generates transparent, plain-language explanations for accepted and rejected trades."""

    def explain_opportunity(
        self,
        opportunity: RankedOpportunity,
        allocation: Optional[PortfolioAllocationResult] = None,
    ) -> PlainLanguageExplanation: ...

    def explain_portfolio_cash_fallback(
        self,
        candidates_count: int,
        reasons_summary: str,
    ) -> PlainLanguageExplanation: ...
```

#### F. `HorizonMapper` (`src/strategy/horizon_mapper.py`)
```python
@dataclass(frozen=True)
class HorizonParameters:
    horizon_name: str  # "1 hour", "1 day", "1 week"
    bar_interval: str  # "5m", "1h", "1d"
    lookback_period: str  # "5d", "60d", "2y"
    feature_fast_ema: int
    feature_slow_ema: int
    atr_window: int
    annualization_factor: float
    hmm_window_bars: int
    tcn_seq_len: int
    tcn_horizon_bars: int
    pt_vol_mult: float
    sl_vol_mult: float
    max_holding_bars: int
    is_intraday_friction: bool
    session_end_policy: str  # "CLOSE_POSITIONS" or "KEEP_OPEN"

class HorizonMapper:
    """Dynamically binds strategy parameters to the selected trading horizon."""

    @staticmethod
    def get_parameters(horizon: str, market_type: str = "US") -> HorizonParameters: ...
```

---

### 4.2 Implementation Plan

1. **Step 1: Create Strategy Package**:
   - Create directory `src/strategy/`.
   - Implement `horizon_mapper.py`, `universe_selector.py`, `trade_evaluator.py`, `trade_ranker.py`, `portfolio_selector.py`, `decision_explainer.py`, and `__init__.py`.
2. **Step 2: Integration with Live Bot & Engine**:
   - Update `MarketPredictionEngine` to accept `horizon` or `HorizonParameters`.
   - Update `LiveBotController` step 6–9: Replace naive probability ranking with `TradeEvaluator` + `TradeRanker` + `PortfolioSelector` + `DecisionExplainer`.
   - Guard against stale feeds and emit plain-language explanations to the activity log.
3. **Step 3: Comprehensive Unit & Integration Tests**:
   - Create `tests/test_strategy_universe_selector.py`
   - Create `tests/test_strategy_trade_evaluator.py`
   - Create `tests/test_strategy_trade_ranker.py`
   - Create `tests/test_strategy_portfolio_selector.py` (including the 100% Cash edge case)
   - Create `tests/test_strategy_horizon_mapper.py`
   - Create `tests/test_strategy_decision_explainer.py`
4. **Step 4: Regression & End-to-End Verification**:
   - Run full pytest suite across `tests/`.

---

## 5. Verification Method

### Test Commands:
```powershell
# 1. Verify Phase 1 & 2 Invariants (Baseline Check)
cd C:\Users\Shivam\Desktop\trade_bot
py tests/test_phase1_phase2_fixes.py

# 2. Run All Existing Tests
py -m pytest tests/test_real_market_paper_trading.py tests/test_market_sessions.py tests/test_adversarial_empirical_challenge.py

# 3. Verify New Strategy Tests (Once implemented)
py -m pytest tests/test_strategy_universe_selector.py tests/test_strategy_trade_evaluator.py tests/test_strategy_trade_ranker.py tests/test_strategy_portfolio_selector.py tests/test_strategy_horizon_mapper.py tests/test_strategy_decision_explainer.py
```

### Invalidation Conditions:
- If `TradeEvaluator` produces positive Net Expectancy for a trade whose expected friction costs exceed gross alpha, the formula implementation is invalid.
- If `PortfolioSelector` allocates $> 0\%$ equity when all opportunities have $\text{EV} \le 0$, the 100% cash fallback guarantee is invalidated.
- If changing `initial_capital` alters model predictions ($P(\text{Win})$, $d^*$, barriers), capital scaling invariance is violated.
- If synthetic prices are generated when live market data is unavailable, virtual guardrails are violated.
