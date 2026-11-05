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
