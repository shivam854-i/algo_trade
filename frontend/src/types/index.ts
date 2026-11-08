export interface BotStatus {
  is_running: boolean;
  paper_trading_only?: boolean;
  execution_mode_label?: string;
  data_mode?: "LIVE_MARKET_DATA" | "DELAYED_MARKET_DATA" | "SANDBOX_SIMULATION" | string;
  simulation_mode?: boolean;
  enforce_market_hours: boolean;
  armed_count: number;
  armed_tickers: string[];
  tick_count: number;
  last_tick_time: string;
  gpu_device: string;
  cuda_version: string;
  precision: string;
  vram_mb: number;
}

export interface DataFeedStatus {
  provider?: string;
  router?: string;
  active_us_provider?: string;
  alpaca_configured?: boolean;
  is_connected: boolean;
  healthy: boolean;
  is_realtime: boolean;
  data_mode: "LIVE_MARKET_DATA" | "DELAYED_MARKET_DATA" | "SANDBOX_SIMULATION" | string;
  paper_trading_only: boolean;
  stale_tickers: string[];
  average_latency_ms: number;
  last_update_utc: string;
  last_error?: string | null;
}

export interface PerformanceAudit {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  profit_factor: number;
  sharpe_ratio?: number;
  max_drawdown_pct?: number;
  total_transaction_costs?: number;
  total_friction_paid?: number;
  net_profit?: number;
  avg_trade_return_pct?: number;
}

export interface AccountSummary {
  account_id?: string;
  account_mode?: string;
  paper_trading_only?: boolean;
  cash?: number;
  current_cash?: number;
  available_cash?: number;
  reserved_cash?: number;
  initial_capital?: number;
  allocated_capital?: number;
  exposure_notional?: number;
  exposure_pct?: number;
  max_drawdown_pct?: number;
  current_drawdown_pct?: number;
  total_transaction_costs?: number;
  open_positions_count?: number;
  portfolio_value?: number;
  total_equity: number;
  unrealized_pnl: number;
  realized_pnl: number;
  total_pnl?: number;
  total_return_pct: number;
  market_return_pct?: number;
  alpha_vs_market_pct?: number;
  audit?: PerformanceAudit;
}

export interface ComparisonPoint {
  tick: number;
  time: string;
  bot_return_pct: number;
  market_return_pct: number;
  equity: number;
}

export interface PricePoint {
  tick?: number;
  time?: string;
  price: number;
  high?: number;
  low?: number;
}

export interface AssetTelemetry {
  ticker: string;
  jurisdiction: string;
  decimals: number;
  current_price: number;
  bid_price?: number;
  ask_price?: number;
  spread_bps?: number;
  base_price: number;
  move_pct: number;
  quote_timestamp_utc?: string;
  age_seconds?: number;
  latency_ms?: number;
  is_delayed?: boolean;
  delay_minutes?: number;
  is_stale?: boolean;
  feed_status?: string;
  provider_name?: string;
  signal: string;
  primary_direction: number;
  confidence_pct: number;
  neural_pct: number;
  regime: string;
  is_crisis: boolean;
  is_armed: boolean;
  exchange_open: boolean;
  tradable_now: boolean;
  exchange_name: string;
  exchange_schedule: string;
  exchange_clock: string;
  exchange_reason: string;
  hrp_weight_pct: number;
  kelly_weight_pct: number;
  friction_bps: number;
  target_price: number;
  stop_price: number;
  entry_price: number | null;
  has_open_position: boolean;
  price_series: PricePoint[];
}

export interface OpenPosition {
  id: number;
  ticker: string;
  direction: "LONG" | "SHORT";
  entry_price: number;
  current_price: number;
  bid_price?: number;
  ask_price?: number;
  spread_bps?: number;
  slippage_bps?: number;
  entry_fee?: number;
  target_price: number;
  stop_price: number;
  shares: number;
  allocated_capital: number;
  unrealized_pnl: number;
  unrealized_return_pct: number;
  holding_bars: number;
  market_timestamp?: string;
}

export interface ClosedTrade {
  id: number;
  ticker: string;
  direction: "LONG" | "SHORT";
  entry_price: number;
  exit_price: number;
  shares?: number;
  gross_pnl?: number;
  net_pnl: number;
  return_pct: number;
  friction_fee: number;
  slippage_cost?: number;
  exit_reason: string;
  exit_time: string;
}

export interface PendingOrder {
  order_id: string;
  account_id?: string;
  ticker: string;
  direction: "LONG" | "SHORT";
  shares: number;
  price?: number;
  limit_price?: number;
  filled_shares?: number;
  remaining_shares?: number;
  allocated_capital?: number;
  order_type: "MARKET" | "LIMIT";
  status: "PRE_MARKET_PENDING" | "WORKING" | "PARTIALLY_FILLED" | "QUEUED" | "CANCELLED" | "EXECUTED" | "FILLED" | "REJECTED";
  created_at: string;
  submitted_at?: string;
  executed_at?: string | null;
  rejection_reason?: string | null;
}

export interface LogEntry {
  time?: string;
  level?: string;
  message?: string;
  metadata?: DecisionMetadata | Record<string, any> | null;
}

export type LogItem = string | LogEntry;

export interface DashboardState {
  bot_status: BotStatus;
  data_feed_status?: DataFeedStatus;
  catalog: Record<string, string[]>;
  account: AccountSummary;
  comparison_series: ComparisonPoint[];
  assets: Record<string, AssetTelemetry>;
  open_positions: OpenPosition[];
  closed_trades: ClosedTrade[];
  activity_log: LogItem[];
  pending_orders?: PendingOrder[];
  order_history?: PendingOrder[];
  market_sessions?: Record<string, SessionStatusInfo>;
  active_session?: TradingSession | null;
  currency?: string;
}

export interface SessionStatusInfo {
  state: "OPEN" | "CLOSED" | "PRE_MARKET" | "POST_MARKET" | "WEEKEND" | "HOLIDAY";
  is_open: boolean;
  next_state: string;
  seconds_to_next_state: number;
  local_time: string;
  exchange_tz: string;
  holiday_name: string | null;
  ticker?: string;
  market_type?: string;
  is_tradable?: boolean;
  exchange_name?: string;
  local_timezone?: string;
  local_time_str?: string;
  session_schedule?: string;
  reason?: string;
  next_state_time_utc?: string;
  countdown_display?: string;
  tick_frozen?: boolean;
  seconds_to_next?: number;
  target_time_utc?: string;
}

export interface SearchInstrumentResult {
  ticker: string;
  name: string;
  category: string;
  exchange: string;
  sector: string;
  in_watchlist: boolean;
  is_armed: boolean;
  has_open_position: boolean;
  current_price: number | null;
  decimals: number;
  signal: string | null;
  primary_direction: number | null;
  confidence_pct: number | null;
  target_price: number | null;
  stop_price: number | null;
  kelly_weight_pct: number | null;
  regime: string | null;
  exchange_open: boolean;
  tradable_now: boolean;
  is_custom?: boolean;
}

export interface BotTradeResponse {
  status: string;
  ticker: string;
  direction: "LONG" | "SHORT";
  direction_source?: string;
  order_id?: string;
  state?: string;
  target_price: number;
  stop_price: number;
  allocation_weight_pct: number;
  bot_armed: boolean;
  dashboard_state?: DashboardState;
}

// ============================================================================
// Navigation Tabs & View Routing
// ============================================================================

export type NavigationTab =
  | "overview"
  | "market-intelligence"
  | "scanner"
  | "trading-engine"
  | "portfolio"
  | "positions-orders"
  | "strategy-lab"
  | "risk-management"
  | "analytics"
  | "monitoring"
  | "settings";

export interface IndianBenchmarkInfo {
  symbol: string;
  name: string;
  exchange: string;
  category: string;
  price: number;
  change_pct: number;
  high: number;
  low: number;
  volume: number;
}

export interface SectorPerformanceInfo {
  sector: string;
  change_pct: number;
  lead: string;
  sentiment: string;
}

export interface MarketIntelligenceData {
  benchmarks: IndianBenchmarkInfo[];
  sectors: SectorPerformanceInfo[];
  market_breadth: {
    advances: number;
    declines: number;
    unchanged: number;
    total: number;
    advance_decline_ratio: number;
  };
  trading_schedule: {
    exchange: string;
    timezone: string;
    phases: { name: string; timing: string; description: string }[];
    current_state: string;
    countdown_display: string;
    is_open: boolean;
  };
  holidays: { date: string; name: string; exchange: string }[];
}

export interface ScannerInstrument {
  ticker: string;
  name: string;
  exchange: string;
  sector: string;
  current_price: number;
  change_pct: number;
  volume: number;
  volatility_atr: number;
  regime: string;
  win_probability: number;
  kelly_fraction: number;
  r_r_ratio: number;
  signal: string;
  is_qualified: boolean;
}

export interface RiskMetricsData {
  portfolio_equity_inr: number;
  available_cash_inr: number;
  invested_equity_inr: number;
  var_95_pct: number;
  var_95_inr: number;
  var_99_pct: number;
  var_99_inr: number;
  cvar_95_inr: number;
  current_drawdown_pct: number;
  circuit_breaker_drawdown_limit_pct: number;
  gross_leverage: number;
  max_allowable_leverage: number;
  kelly_multiplier: number;
  sebi_rate_limit_orders_per_sec: number;
  limit_price_protection_pct: number;
  indian_frictions: {
    stt_delivery_both_legs_pct: number;
    stt_intraday_sell_leg_pct: number;
    nse_exchange_turnover_charge_pct: number;
    bse_exchange_turnover_charge_pct: number;
    stamp_duty_buy_leg_delivery_pct: number;
    sebi_turnover_charge_pct: number;
    gst_rate_pct: number;
    brokerage_cap_pct: number;
    almgren_chriss_eta: number;
  };
}

export interface PerformanceAnalyticsData {
  summary: {
    total_trades: number;
    win_rate_pct: number;
    profit_factor: number;
    gross_pnl_inr: number;
    total_friction_inr: number;
    net_pnl_inr: number;
    avg_win_inr: number;
    avg_loss_inr: number;
    sharpe_ratio: number;
    sortino_ratio: number;
    max_drawdown_pct: number;
  };
  returns_distribution: number[];
  equity_series: ComparisonPoint[];
  monthly_matrix: { year: number; month: string; return_pct: number }[];
}

// ============================================================================
// Milestone 3: Trading Session & Lifecycle Management Types
// ============================================================================

export type SessionMarket =
  | "INDIAN_NSE"
  | "INDIAN_BSE"
  | "US_EQUITIES"
  | "CRYPTO"
  | "COMMODITIES"
  | "FOREX";

export type SessionCurrency = "INR" | "USD";

export type TradingHorizon = "1h" | "1d" | "1wk";

export type DurationType = "FIXED" | "CUSTOM" | "MANUAL_STOP";

export type SessionEndPolicy = "CLOSE_ALL" | "KEEP_OPEN";

export type SessionStatus =
  | "CREATED"
  | "RUNNING"
  | "PAUSED"
  | "COMPLETED"
  | "STOPPED";

export interface SessionMetrics {
  initial_capital: number;
  current_cash: number;
  invested_equity: number;
  total_equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_trades?: number;
  winning_trades?: number;
  losing_trades?: number;
  win_rate_pct?: number;
  open_positions_count?: number;
  currency?: string;
}

export interface TradingSession {
  id: string;
  user_id?: string;
  account_id?: string;
  name?: string | null;
  market: SessionMarket | string;
  instruments: string[];
  horizon: TradingHorizon | string;
  duration_type: DurationType | string;
  duration_minutes?: number | null;
  session_end_policy: SessionEndPolicy | string;
  allocated_capital: number;
  currency: SessionCurrency | string;
  strategy_config?: Record<string, any>;
  risk_config?: Record<string, any>;
  status: SessionStatus | string;
  created_at: string;
  started_at?: string | null;
  paused_at?: string | null;
  resumed_at?: string | null;
  ended_at?: string | null;
  expires_at?: string | null;
  accumulated_pause_seconds: number;
  current_metrics?: SessionMetrics | Record<string, any>;
  last_heartbeat_at?: string | null;
  // Computed properties from server
  is_active?: boolean;
  is_running?: boolean;
  is_paused?: boolean;
  is_terminal?: boolean;
  is_expired?: boolean;
  remaining_seconds?: number | null;
}

export interface SessionCreatePayload {
  name?: string;
  market: SessionMarket | string;
  instruments: string[];
  horizon: TradingHorizon | string;
  duration_type: DurationType | string;
  duration_minutes?: number | null;
  session_end_policy: SessionEndPolicy | string;
  allocated_capital: number;
  currency: SessionCurrency | string;
  strategy_config?: Record<string, any>;
  risk_config?: Record<string, any>;
}

export interface SessionUpdatePayload {
  name?: string;
  instruments?: string[];
  horizon?: TradingHorizon | string;
  duration_type?: DurationType | string;
  duration_minutes?: number | null;
  session_end_policy?: SessionEndPolicy | string;
  allocated_capital?: number;
  strategy_config?: Record<string, any>;
  risk_config?: Record<string, any>;
}

export interface SessionStopPayload {
  reason?: "MANUAL_STOP" | "USER_REQUEST" | "USER_MANUAL_STOP" | "RISK_HALT" | string;
}

export interface RecommendationRequest {
  market: SessionMarket | string;
  target_size?: number;
  candidate_tickers?: string[] | null;
}

export interface CandidateEvaluation {
  ticker: string;
  market: string;
  passed_all_gates: boolean;
  data_quality_score: number;
  missing_bar_ratio: number;
  zero_volume_ratio: number;
  adv: number;
  adv_currency: string;
  adv_threshold: number;
  spread_bps: number;
  annualized_volatility: number;
  composite_score: number;
  rejection_reasons: string[];
  pass_details: Record<string, any>;
  summary_rationale: string;
}

export interface SessionRecommendationResponse {
  market: SessionMarket | string;
  target_size: number;
  selected_instruments: string[];
  evaluations: Record<string, CandidateEvaluation>;
  passed_count: number;
  rejected_count: number;
  summary_rationale: string;
  timestamp_utc: string;
}

export interface SessionPerformance {
  session_id: string;
  name?: string;
  status: SessionStatus | string;
  market: SessionMarket | string;
  currency: SessionCurrency | string;
  horizon: TradingHorizon | string;
  duration_type: DurationType | string;
  duration_minutes?: number | null;
  allocated_capital: number;
  starting_capital: number;
  current_cash: number;
  invested_equity: number;
  total_equity: number;
  net_pnl: number;
  realized_pnl: number;
  unrealized_pnl: number;
  return_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  profit_factor: number;
  open_positions_count: number;
  is_active: boolean;
  is_running: boolean;
  is_expired: boolean;
  remaining_seconds?: number | null;
  accumulated_pause_seconds: number;
  session_end_policy: SessionEndPolicy | string;
}

// Explainability Activity Feed Types
export type DecisionAction = "ACCEPTED" | "REJECTED" | "HELD_IN_CASH" | string;

export interface DecisionMetrics {
  net_expectancy_pct?: number;
  win_probability?: number;
  conservative_win_prob?: number;
  round_trip_friction_bps?: number;
  entry_price?: number;
  target_price?: number;
  stop_price?: number;
  payoff_ratio?: number;
  allocation_weight_pct?: number;
  allocated_capital?: number;
  shares?: number;
  currency?: string;
  rejection_reason?: string;
  total_candidates?: number;
  qualifying_count?: number;
  cash_weight_pct?: number;
  portfolio_drawdown_pct?: number;
  [key: string]: any;
}

export interface DecisionMetadata {
  ticker: string;
  action: DecisionAction;
  headline: string;
  summary: string;
  factors: Record<string, string>;
  metrics: DecisionMetrics;
  timestamp_utc: string;
}

