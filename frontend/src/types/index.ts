export interface BotStatus {
  is_running: boolean;
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

export interface PerformanceAudit {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  profit_factor: number;
  total_friction_paid: number;
}

export interface AccountSummary {
  cash?: number;
  current_cash?: number;
  available_cash?: number;
  reserved_cash?: number;
  initial_capital?: number;
  allocated_capital?: number;
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
}

export interface AssetTelemetry {
  ticker: string;
  jurisdiction: string;
  decimals: number;
  current_price: number;
  base_price: number;
  move_pct: number;
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
  target_price: number;
  stop_price: number;
  shares: number;
  allocated_capital: number;
  unrealized_pnl: number;
  unrealized_return_pct: number;
  holding_bars: number;
}

export interface ClosedTrade {
  id: number;
  ticker: string;
  direction: "LONG" | "SHORT";
  entry_price: number;
  exit_price: number;
  net_pnl: number;
  return_pct: number;
  friction_fee: number;
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
  order_type: "MARKET" | "LIMIT";
  status: "PRE_MARKET_PENDING" | "QUEUED" | "CANCELLED" | "EXECUTED";
  created_at: string;
  executed_at?: string | null;
}

export interface LogEntry {
  time?: string;
  level?: string;
  message?: string;
}

export type LogItem = string | LogEntry;

export interface DashboardState {
  bot_status: BotStatus;
  catalog: Record<string, string[]>;
  account: AccountSummary;
  comparison_series: ComparisonPoint[];
  assets: Record<string, AssetTelemetry>;
  open_positions: OpenPosition[];
  closed_trades: ClosedTrade[];
  activity_log: LogItem[];
  pending_orders?: PendingOrder[];
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
