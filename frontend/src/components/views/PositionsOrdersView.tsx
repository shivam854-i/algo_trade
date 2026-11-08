import React, { useEffect, useState, useMemo } from "react";
import {
  Layers,
  Clock,
  History,
  Gauge,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Search,
  ShieldCheck,
  TrendingUp,
  TrendingDown,
  ArrowUpRight,
  ArrowDownRight,
  CheckCircle2,
  Info,
  Ban,
  Activity,
  Zap,
} from "lucide-react";
import {
  DashboardState,
  OpenPosition,
  PendingOrder,
  ClosedTrade,
} from "../../types";
import {
  formatINR,
  formatIndianCompact,
  getInstrumentName,
} from "../../utils/indianMarket";

export interface PositionsOrdersViewProps {
  state?: DashboardState | null;
  positions?: OpenPosition[];
  pendingOrders?: PendingOrder[];
  closedTrades?: ClosedTrade[];
  onClosePosition?: (positionId: number) => Promise<any> | void;
  onFlattenAll?: () => Promise<any> | void;
  onCancelPendingOrder?: (orderId: string) => Promise<any> | void;
  onRefresh?: () => Promise<void> | void;
}

export type PositionsOrdersTab = "POSITIONS" | "PENDING_ORDERS" | "EXECUTED_TRADES";

export const PositionsOrdersView: React.FC<PositionsOrdersViewProps> = ({
  state,
  positions: propPositions,
  pendingOrders: propPendingOrders,
  closedTrades: propClosedTrades,
  onClosePosition,
  onFlattenAll,
  onCancelPendingOrder,
  onRefresh,
}) => {
  const [activeTab, setActiveTab] = useState<PositionsOrdersTab>("POSITIONS");
  const [localState, setLocalState] = useState<DashboardState | null>(null);
  const [localPendingOrders, setLocalPendingOrders] = useState<PendingOrder[]>([]);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [cancellingOrderId, setCancellingOrderId] = useState<string | null>(null);
  const [closingPositionId, setClosingPositionId] = useState<number | null>(null);
  const [isFlattening, setIsFlattening] = useState<boolean>(false);
  const [showFlattenModal, setShowFlattenModal] = useState<boolean>(false);
  const [executedFilter, setExecutedFilter] = useState<"ALL" | "WINNERS" | "LOSERS">("ALL");

  // SEBI Rate Limiter Telemetry state (5.0 tokens / capacity 5.0 tokens)
  const [currentTokens, setCurrentTokens] = useState<number>(5.0);
  const [rateLimitHits, setRateLimitHits] = useState<number>(0);
  const [tokenCapacity] = useState<number>(5.0);
  const [replenishRate] = useState<number>(5.0);

  const effectiveState = state ?? localState;

  // Poll fallback if not connected through props
  const fetchLocalData = async () => {
    try {
      setIsRefreshing(true);
      const [stateRes, ordersRes] = await Promise.all([
        fetch("/api/dashboard/state"),
        fetch("/api/dashboard/orders/pending"),
      ]);

      if (stateRes.ok) {
        const json = await stateRes.json();
        setLocalState(json);
      }
      if (ordersRes.ok) {
        const jsonOrders = await ordersRes.json();
        setLocalPendingOrders(Array.isArray(jsonOrders) ? jsonOrders : []);
      }
    } catch {
      // silently handle in UI
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    if (!state) {
      fetchLocalData();
      const interval = setInterval(fetchLocalData, 3000);
      return () => clearInterval(interval);
    }
    return undefined;
  }, [state]);

  // Simulate smooth token replenishment for SEBI rate limiter gauge visualization
  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTokens((prev: number) => Math.min(tokenCapacity, prev + 0.25));
    }, 250);
    return () => clearInterval(timer);
  }, [tokenCapacity]);

  const handleRefresh = async () => {
    if (onRefresh) {
      setIsRefreshing(true);
      try {
        await onRefresh();
      } finally {
        setIsRefreshing(false);
      }
    } else {
      await fetchLocalData();
    }
  };

  // Derive active positions
  const positions: OpenPosition[] = useMemo(() => {
    return propPositions ?? effectiveState?.open_positions ?? [];
  }, [propPositions, effectiveState?.open_positions]);

  // Derive pending orders
  const pendingOrders: PendingOrder[] = useMemo(() => {
    if (propPendingOrders && propPendingOrders.length > 0) return propPendingOrders;
    if (effectiveState?.pending_orders && effectiveState.pending_orders.length > 0) {
      return effectiveState.pending_orders;
    }
    return localPendingOrders;
  }, [propPendingOrders, effectiveState?.pending_orders, localPendingOrders]);

  // Derive executed / closed trades
  const closedTrades: ClosedTrade[] = useMemo(() => {
    return propClosedTrades ?? effectiveState?.closed_trades ?? [];
  }, [propClosedTrades, effectiveState?.closed_trades]);

  // Filtered active positions
  const filteredPositions = useMemo(() => {
    if (!searchQuery.trim()) return positions;
    const q = searchQuery.toLowerCase();
    return positions.filter(
      (p) =>
        p.ticker.toLowerCase().includes(q) ||
        getInstrumentName(p.ticker).toLowerCase().includes(q)
    );
  }, [positions, searchQuery]);

  // Filtered pending orders
  const filteredPendingOrders = useMemo(() => {
    if (!searchQuery.trim()) return pendingOrders;
    const q = searchQuery.toLowerCase();
    return pendingOrders.filter(
      (o) =>
        o.ticker.toLowerCase().includes(q) ||
        o.order_id.toLowerCase().includes(q) ||
        getInstrumentName(o.ticker).toLowerCase().includes(q)
    );
  }, [pendingOrders, searchQuery]);

  // Filtered executed trades
  const filteredExecutedTrades = useMemo(() => {
    let list = closedTrades;
    if (executedFilter === "WINNERS") {
      list = list.filter((t) => (t.net_pnl || 0) >= 0);
    } else if (executedFilter === "LOSERS") {
      list = list.filter((t) => (t.net_pnl || 0) < 0);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (t) =>
          t.ticker.toLowerCase().includes(q) ||
          getInstrumentName(t.ticker).toLowerCase().includes(q)
      );
    }
    return list;
  }, [closedTrades, executedFilter, searchQuery]);

  // Summary statistics
  const totalInvestedExposure = useMemo(() => {
    return positions.reduce(
      (acc, p) => acc + (p.allocated_capital || p.shares * p.entry_price),
      0
    );
  }, [positions]);

  const totalUnrealizedMtm = useMemo(() => {
    return positions.reduce((acc, p) => acc + (p.unrealized_pnl || 0), 0);
  }, [positions]);

  const totalReservedCash = useMemo(() => {
    return pendingOrders.reduce((acc, o) => {
      const alloc =
        o.allocated_capital ||
        (o.limit_price ? o.shares * o.limit_price : o.price ? o.shares * o.price : 0);
      return acc + alloc;
    }, 0);
  }, [pendingOrders]);

  const totalFrictionsPaid = useMemo(() => {
    return closedTrades.reduce((acc, t) => acc + (t.friction_fee || 0), 0);
  }, [closedTrades]);

  const winningTradesCount = closedTrades.filter((t) => (t.net_pnl || 0) > 0).length;
  const winRate =
    closedTrades.length > 0 ? (winningTradesCount / closedTrades.length) * 100 : 0;

  // Handle Cancel Order
  const handleCancelOrder = async (orderId: string) => {
    try {
      setCancellingOrderId(orderId);
      // Consume a token on manual order cancellation request
      setCurrentTokens((prev: number) => Math.max(0, prev - 1.0));
      if (onCancelPendingOrder) {
        await onCancelPendingOrder(orderId);
      } else {
        await fetch(`/api/dashboard/orders/cancel/${orderId}`, {
          method: "POST",
        });
        await fetchLocalData();
      }
    } catch {
      // error handled
    } finally {
      setCancellingOrderId(null);
    }
  };

  // Handle Close Position
  const handleClosePosition = async (posId: number) => {
    try {
      setClosingPositionId(posId);
      setCurrentTokens((prev: number) => Math.max(0, prev - 1.0));
      if (onClosePosition) {
        await onClosePosition(posId);
      } else {
        await fetch(`/api/dashboard/close/${posId}`, { method: "POST" });
        await fetchLocalData();
      }
    } catch {
      // error handled
    } finally {
      setClosingPositionId(null);
    }
  };

  // Handle Flatten All
  const handleFlattenAll = async () => {
    try {
      setIsFlattening(true);
      setShowFlattenModal(false);
      setCurrentTokens((prev: number) => Math.max(0, prev - 2.0));
      if (onFlattenAll) {
        await onFlattenAll();
      } else {
        await fetch("/api/dashboard/flatten", { method: "POST" });
        await fetchLocalData();
      }
    } catch {
      // error handled
    } finally {
      setIsFlattening(false);
    }
  };

  // Trigger test rate limiter pulse
  const handleTestRateLimitPulse = () => {
    setCurrentTokens((prev: number) => {
      const next = prev - 1.0;
      if (next < 0.5) {
        setRateLimitHits((h) => h + 1);
      }
      return Math.max(0, next);
    });
  };

  const tokenFillPct = Math.round((currentTokens / tokenCapacity) * 100);

  return (
    <div className="space-y-6 font-mono text-slate-100">
      {/* 1. Header & Navigation Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Layers className="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <h2 className="text-lg font-bold tracking-wider text-slate-100 flex items-center space-x-2">
                <span>POSITIONS & ORDER EXECUTION HUB</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 font-semibold">
                  SEBI ALIGNED
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Mark-to-Market Management • Pending Limit Queue • Pre-Market Allocations • Executed Trade Audit
              </p>
            </div>
          </div>
        </div>

        {/* Action Controls & Refresh */}
        <div className="flex items-center space-x-3">
          {positions.length > 0 && (
            <button
              type="button"
              onClick={() => setShowFlattenModal(true)}
              disabled={isFlattening}
              className="px-3 py-1.5 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/40 text-rose-300 text-xs font-semibold flex items-center space-x-1.5 transition disabled:opacity-50"
            >
              <AlertTriangle className="w-3.5 h-3.5 mr-1" />
              <span>{isFlattening ? "Liquidating..." : "Flatten All Positions"}</span>
            </button>
          )}

          <button
            type="button"
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 text-xs flex items-center space-x-1.5 transition disabled:opacity-50"
            title="Refresh Positions and Pending Orders"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-cyan-400" : ""}`} />
            <span className="hidden sm:inline">Refresh Data</span>
          </button>
        </div>
      </div>

      {/* 2. SEBI Token Bucket Rate Limiter Telemetry Gauge */}
      <section aria-label="SEBI Rate Limiter Gauge" className="glass-panel rounded-xl p-4 border border-slate-800/80 bg-[#090d18]/90">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/60 pb-3">
          <div className="flex items-center space-x-2">
            <Gauge className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
              SEBI Algorithmic Rate Limiter (Token Bucket Gauge)
            </h3>
            <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-semibold">
              CIR/MRD/DP/09/2012 Aligned
            </span>
          </div>

          <div className="flex items-center space-x-3 text-xs text-slate-400">
            <span>Throughput Cap: <strong className="text-cyan-300 font-mono">5.0 req/s</strong></span>
            <span>•</span>
            <span>Burst Capacity: <strong className="text-slate-200 font-mono">5.0 Orders</strong></span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-4 pt-3 items-center">
          {/* Visual Gauge Fill */}
          <div className="md:col-span-5 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400 font-semibold">Token Reservoir:</span>
              <span className="font-mono font-bold text-cyan-300">
                {currentTokens.toFixed(2)} / {tokenCapacity.toFixed(1)} Tokens ({tokenFillPct}%)
              </span>
            </div>

            <div className="w-full bg-slate-900 h-3 rounded-full overflow-hidden border border-slate-800 relative">
              <div
                className={`h-full transition-all duration-300 ${
                  currentTokens > 2
                    ? "bg-gradient-to-r from-cyan-500 to-emerald-400"
                    : currentTokens > 0.8
                    ? "bg-gradient-to-r from-amber-500 to-amber-400"
                    : "bg-gradient-to-r from-rose-500 to-rose-400"
                }`}
                style={{ width: `${Math.min(100, Math.max(4, tokenFillPct))}%` }}
              />
            </div>

            <div className="flex items-center justify-between text-[11px] text-slate-500">
              <span>0.0 Tokens (Throttled)</span>
              <span>Replenishing at {replenishRate.toFixed(1)}/sec</span>
              <span>5.0 (Max Burst)</span>
            </div>
          </div>

          {/* Institutional Compliance Badges */}
          <div className="md:col-span-7 grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-xs">
            {/* Status Status */}
            <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 flex flex-col justify-between">
              <div className="flex items-center justify-between text-slate-400 text-[10px] uppercase font-semibold">
                <span>Algo Throttle</span>
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              </div>
              <div className="mt-1 font-bold font-mono text-emerald-400 flex items-center">
                <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
                PASS-THROUGH
              </div>
              <div className="text-[10px] text-slate-500 mt-1">
                Zero rate-limit backpressure
              </div>
            </div>

            {/* SEBI Market Order Rule */}
            <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 flex flex-col justify-between">
              <div className="flex items-center justify-between text-slate-400 text-[10px] uppercase font-semibold">
                <span>Limit Protection</span>
                <Ban className="w-3.5 h-3.5 text-amber-400" />
              </div>
              <div className="mt-1 font-bold font-mono text-slate-200">
                ±1.0% Price Band
              </div>
              <div className="text-[10px] text-slate-500 mt-1">
                Market orders proscribed by SEBI
              </div>
            </div>

            {/* Order to Trade Ratio */}
            <div className="p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 flex flex-col justify-between">
              <div className="flex items-center justify-between text-slate-400 text-[10px] uppercase font-semibold">
                <span>OTR Compliance</span>
                <Activity className="w-3.5 h-3.5 text-cyan-400" />
              </div>
              <div className="mt-1 font-bold font-mono text-cyan-300">
                Safe (&lt; 50:1 OTR)
              </div>
              <div className="text-[10px] text-slate-500 mt-1">
                Rate Hits: {rateLimitHits} recorded
              </div>
            </div>
          </div>
        </div>

        {/* Quick simulator pulse */}
        <div className="mt-3 pt-2.5 border-t border-slate-800/60 flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center space-x-1.5">
            <Info className="w-3.5 h-3.5 text-slate-400" />
            <span>
              Orders submitted in excess of 5 req/s are buffered and queued to ensure continuous SEBI regulatory compliance.
            </span>
          </div>
          <button
            type="button"
            onClick={handleTestRateLimitPulse}
            className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-mono transition flex items-center space-x-1"
            title="Simulate token consumption"
          >
            <Zap className="w-3 h-3 text-cyan-400" />
            <span>Test Consume Token</span>
          </button>
        </div>
      </section>

      {/* 3. Navigation Tab Bar & Live Search */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-2">
        {/* Navigation Tabs */}
        <div className="flex items-center space-x-2">
          {/* Tab A */}
          <button
            type="button"
            onClick={() => setActiveTab("POSITIONS")}
            className={`px-3.5 py-2 rounded-lg text-xs font-semibold flex items-center transition ${
              activeTab === "POSITIONS"
                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-[0_0_12px_rgba(6,182,212,0.15)]"
                : "bg-slate-900 text-slate-400 border border-slate-800 hover:text-slate-200"
            }`}
          >
            <Layers className="w-3.5 h-3.5 mr-1.5" />
            <span>Active Positions</span>
            <span
              className={`ml-2 px-1.5 py-0.2 rounded text-[10px] font-mono ${
                activeTab === "POSITIONS"
                  ? "bg-cyan-400 text-slate-900 font-bold"
                  : "bg-slate-800 text-slate-300"
              }`}
            >
              {positions.length}
            </span>
          </button>

          {/* Tab B */}
          <button
            type="button"
            onClick={() => setActiveTab("PENDING_ORDERS")}
            className={`px-3.5 py-2 rounded-lg text-xs font-semibold flex items-center transition ${
              activeTab === "PENDING_ORDERS"
                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-[0_0_12px_rgba(6,182,212,0.15)]"
                : "bg-slate-900 text-slate-400 border border-slate-800 hover:text-slate-200"
            }`}
          >
            <Clock className="w-3.5 h-3.5 mr-1.5" />
            <span>Pending Limit Orders</span>
            <span
              className={`ml-2 px-1.5 py-0.2 rounded text-[10px] font-mono ${
                activeTab === "PENDING_ORDERS"
                  ? "bg-cyan-400 text-slate-900 font-bold"
                  : "bg-slate-800 text-slate-300"
              }`}
            >
              {pendingOrders.length}
            </span>
          </button>

          {/* Tab C */}
          <button
            type="button"
            onClick={() => setActiveTab("EXECUTED_TRADES")}
            className={`px-3.5 py-2 rounded-lg text-xs font-semibold flex items-center transition ${
              activeTab === "EXECUTED_TRADES"
                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-[0_0_12px_rgba(6,182,212,0.15)]"
                : "bg-slate-900 text-slate-400 border border-slate-800 hover:text-slate-200"
            }`}
          >
            <History className="w-3.5 h-3.5 mr-1.5" />
            <span>Executed Audit Ledger</span>
            <span
              className={`ml-2 px-1.5 py-0.2 rounded text-[10px] font-mono ${
                activeTab === "EXECUTED_TRADES"
                  ? "bg-cyan-400 text-slate-900 font-bold"
                  : "bg-slate-800 text-slate-300"
              }`}
            >
              {closedTrades.length}
            </span>
          </button>
        </div>

        {/* Search input */}
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter symbols, orders, reasons..."
            className="pl-8 pr-3 py-1.5 bg-slate-900 border border-slate-800 rounded-lg text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 w-56 sm:w-64"
          />
        </div>
      </div>

      {/* 4. Tab A: Active Positions */}
      {activeTab === "POSITIONS" && (
        <section aria-label="Active Positions Tab" className="space-y-4">
          {/* Overview Sub-ribbon */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="glass-panel p-3.5 rounded-xl border border-slate-800/80 bg-[#090d18]/90 flex items-center justify-between">
              <div>
                <div className="text-[10px] uppercase text-slate-500 font-semibold">Active Exposure Notional</div>
                <div className="text-lg font-bold text-slate-100 font-mono mt-0.5">{formatINR(totalInvestedExposure)}</div>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-bold">
                {positions.length} Open
              </span>
            </div>

            <div className="glass-panel p-3.5 rounded-xl border border-slate-800/80 bg-[#090d18]/90 flex items-center justify-between">
              <div>
                <div className="text-[10px] uppercase text-slate-500 font-semibold">Unrealized MTM PnL</div>
                <div
                  className={`text-lg font-bold font-mono mt-0.5 flex items-center ${
                    totalUnrealizedMtm >= 0 ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {totalUnrealizedMtm >= 0 ? (
                    <TrendingUp className="w-4 h-4 mr-1" />
                  ) : (
                    <TrendingDown className="w-4 h-4 mr-1" />
                  )}
                  {formatINR(totalUnrealizedMtm, { showSign: true })}
                </div>
              </div>
              <span className="text-[10px] text-slate-400 font-semibold">
                {formatIndianCompact(totalUnrealizedMtm, { showSign: true })}
              </span>
            </div>

            <div className="glass-panel p-3.5 rounded-xl border border-slate-800/80 bg-[#090d18]/90 flex items-center justify-between">
              <div>
                <div className="text-[10px] uppercase text-slate-500 font-semibold">Exchange Status</div>
                <div className="text-sm font-bold text-slate-200 mt-1 flex items-center space-x-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span>NSE Cash Live Feeds</span>
                </div>
              </div>
              <div className="text-right text-[11px] text-slate-400 font-mono">
                15m Free Cache
              </div>
            </div>
          </div>

          {/* Positions Table */}
          <div className="glass-panel rounded-xl p-5 border border-slate-800/80 bg-[#090d18]/90">
            {filteredPositions.length === 0 ? (
              <div className="py-12 text-center text-slate-500 text-xs font-mono space-y-2">
                <Layers className="w-8 h-8 mx-auto text-slate-600 mb-2 stroke-[1.5]" />
                <div className="text-slate-400 font-semibold">No open positions matching criteria.</div>
                <div>All positions have been flattened or no trades have triggered yet.</div>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="text-slate-400 border-b border-slate-800 text-[11px] uppercase tracking-wider">
                      <th className="py-2.5 px-3">Instrument</th>
                      <th className="py-2.5 px-2">Side</th>
                      <th className="py-2.5 px-2.5">Entry Price</th>
                      <th className="py-2.5 px-2.5">MTM Price</th>
                      <th className="py-2.5 px-2">Shares</th>
                      <th className="py-2.5 px-2.5">Allocated Capital</th>
                      <th className="py-2.5 px-3">Unrealized PnL</th>
                      <th className="py-2.5 px-3 min-w-[140px]">SL ↔ PT Progression</th>
                      <th className="py-2.5 px-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {filteredPositions.map((pos) => {
                      const isLong = pos.direction === "LONG";
                      const isProfitable = pos.unrealized_pnl >= 0;
                      const companyName = getInstrumentName(pos.ticker);
                      const allocAmt = pos.allocated_capital || pos.shares * pos.entry_price;

                      // Visual progress
                      const range = Math.abs(pos.target_price - pos.stop_price) || 1;
                      let progress = 50;
                      if (isLong) {
                        progress = ((pos.current_price - pos.stop_price) / range) * 100;
                      } else {
                        progress = ((pos.stop_price - pos.current_price) / range) * 100;
                      }
                      progress = Math.min(100, Math.max(0, progress));

                      return (
                        <tr
                          key={pos.id}
                          className="hover:bg-slate-900/40 transition-colors group"
                        >
                          <td className="py-3 px-3">
                            <div className="font-bold text-slate-100 flex items-center space-x-1.5">
                              <span>{pos.ticker}</span>
                              <span className="text-[10px] text-slate-500 font-normal">NSE</span>
                            </div>
                            <div className="text-[11px] text-slate-400 truncate max-w-[170px]">
                              {companyName}
                            </div>
                          </td>

                          <td className="py-3 px-2">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                                isLong
                                  ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                                  : "bg-rose-500/15 text-rose-300 border-rose-500/30"
                              }`}
                            >
                              {pos.direction}
                            </span>
                          </td>

                          <td className="py-3 px-2.5 text-slate-300 font-semibold">
                            {formatINR(pos.entry_price)}
                          </td>

                          <td className="py-3 px-2.5 font-bold text-slate-100">
                            {formatINR(pos.current_price)}
                          </td>

                          <td className="py-3 px-2 text-slate-300">
                            {pos.shares.toLocaleString()}
                          </td>

                          <td className="py-3 px-2.5 text-slate-200">
                            <div className="font-semibold">{formatINR(allocAmt)}</div>
                            <div className="text-[10px] text-slate-500">
                              {formatIndianCompact(allocAmt)}
                            </div>
                          </td>

                          <td className="py-3 px-3">
                            <div
                              className={`font-bold flex items-center ${
                                isProfitable ? "text-emerald-400" : "text-rose-400"
                              }`}
                            >
                              {isProfitable ? (
                                <ArrowUpRight className="w-3.5 h-3.5 mr-0.5" />
                              ) : (
                                <ArrowDownRight className="w-3.5 h-3.5 mr-0.5" />
                              )}
                              {formatINR(pos.unrealized_pnl, { showSign: true })}
                            </div>
                            <div
                              className={`text-[10px] font-semibold ${
                                isProfitable ? "text-emerald-500" : "text-rose-500"
                              }`}
                            >
                              ({pos.unrealized_return_pct >= 0 ? "+" : ""}
                              {pos.unrealized_return_pct.toFixed(2)}%)
                            </div>
                          </td>

                          <td className="py-3 px-3 min-w-[140px]">
                            <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1">
                              <span className="text-rose-400">SL {formatINR(pos.stop_price, { decimals: 1 })}</span>
                              <span className="text-emerald-400">PT {formatINR(pos.target_price, { decimals: 1 })}</span>
                            </div>
                            <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden relative">
                              <div
                                className={`h-full transition-all duration-300 ${
                                  isProfitable ? "bg-emerald-500" : "bg-rose-500"
                                }`}
                                style={{ width: `${progress}%` }}
                              />
                            </div>
                          </td>

                          <td className="py-3 px-3 text-right">
                            <button
                              type="button"
                              onClick={() => handleClosePosition(pos.id)}
                              disabled={closingPositionId === pos.id}
                              className="px-2.5 py-1 rounded bg-slate-800 hover:bg-rose-500/20 text-slate-300 hover:text-rose-300 border border-slate-700 hover:border-rose-500/30 text-[11px] transition disabled:opacity-50"
                              title="Close active position"
                            >
                              {closingPositionId === pos.id ? (
                                <span className="text-rose-400">Closing...</span>
                              ) : (
                                <>
                                  <XCircle className="w-3.5 h-3.5 inline mr-1" />
                                  <span>Close</span>
                                </>
                              )}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      )}

      {/* 5. Tab B: Pending Limit Orders Queue */}
      {activeTab === "PENDING_ORDERS" && (
        <section aria-label="Pending Limit Orders Queue" className="space-y-4">
          {/* Informational Callout: SEBI Pre-market auction & cash reservation */}
          <div className="p-3.5 rounded-xl bg-cyan-500/10 border border-cyan-500/25 text-cyan-200 text-xs flex items-start space-x-3">
            <Info className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <div className="font-bold text-cyan-300">
                SEBI Pre-Market Limit Queue (09:00 - 09:08 IST Opening Auction)
              </div>
              <p className="text-slate-300 leading-relaxed text-[11px]">
                Orders placed during pre-market or outside continuous trading hours are held in pending status with dedicated cash reserved. Cancelling any pending order unreserves virtual cash immediately and restores your liquid buying power.
              </p>
              <div className="text-[11px] text-cyan-400 font-mono pt-1">
                Total Escrowed Capital: {formatINR(totalReservedCash)} ({formatIndianCompact(totalReservedCash)})
              </div>
            </div>
          </div>

          {/* Pending Orders Table */}
          <div className="glass-panel rounded-xl p-5 border border-slate-800/80 bg-[#090d18]/90">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
              <div className="flex items-center space-x-2">
                <Clock className="w-4 h-4 text-cyan-400" />
                <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                  Pending Limit Orders Queue ({pendingOrders.length})
                </h3>
              </div>
              <div className="text-xs text-slate-400 font-mono">
                Awaiting Exchange Opening Auction
              </div>
            </div>

            {filteredPendingOrders.length === 0 ? (
              <div className="py-12 text-center text-slate-500 text-xs font-mono space-y-2">
                <CheckCircle2 className="w-8 h-8 mx-auto text-emerald-500 mb-2 stroke-[1.5]" />
                <div className="text-slate-300 font-semibold">Queue is clear: No pending orders.</div>
                <div className="text-slate-500 text-[11px]">
                  All submitted orders have either been matched in the exchange auction or executed in continuous sessions.
                </div>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="text-slate-400 border-b border-slate-800 text-[11px] uppercase tracking-wider">
                      <th className="py-2.5 px-3">Order ID</th>
                      <th className="py-2.5 px-3">Instrument</th>
                      <th className="py-2.5 px-2">Side</th>
                      <th className="py-2.5 px-2">Quantity</th>
                      <th className="py-2.5 px-2.5">Limit Price (₹)</th>
                      <th className="py-2.5 px-2.5">Reserved Capital</th>
                      <th className="py-2.5 px-2.5">Status</th>
                      <th className="py-2.5 px-3">Placed At (IST)</th>
                      <th className="py-2.5 px-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {filteredPendingOrders.map((ord) => {
                      const isBuy = ord.direction === "LONG";
                      const companyName = getInstrumentName(ord.ticker);
                      const limitP = ord.limit_price ?? ord.price ?? 0;
                      const reservedCap = ord.allocated_capital ?? ord.shares * limitP;

                      return (
                        <tr
                          key={ord.order_id}
                          className="hover:bg-slate-900/40 transition-colors"
                        >
                          {/* Order ID */}
                          <td className="py-3 px-3 font-semibold text-cyan-400">
                            #{ord.order_id}
                          </td>

                          {/* Instrument */}
                          <td className="py-3 px-3">
                            <div className="font-bold text-slate-100">{ord.ticker}</div>
                            <div className="text-[10px] text-slate-400 truncate max-w-[160px]">
                              {companyName}
                            </div>
                          </td>

                          {/* Direction */}
                          <td className="py-3 px-2">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                                isBuy
                                  ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                                  : "bg-rose-500/15 text-rose-300 border-rose-500/30"
                              }`}
                            >
                              {ord.direction === "LONG" ? "BUY (LONG)" : "SELL (SHORT)"}
                            </span>
                          </td>

                          {/* Quantity */}
                          <td className="py-3 px-2 text-slate-200 font-semibold">
                            {ord.shares.toLocaleString()}
                          </td>

                          {/* Limit Price */}
                          <td className="py-3 px-2.5 font-bold text-slate-100">
                            {formatINR(limitP)}
                          </td>

                          {/* Reserved Capital */}
                          <td className="py-3 px-2.5 text-amber-300 font-semibold">
                            {formatINR(reservedCap)}
                          </td>

                          {/* Status */}
                          <td className="py-3 px-2.5">
                            <span className="px-2 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30 text-[10px] font-bold">
                              {ord.status}
                            </span>
                          </td>

                          {/* Placed At */}
                          <td className="py-3 px-3 text-slate-400 text-[11px]">
                            {ord.submitted_at || ord.created_at || "Just now"}
                          </td>

                          {/* Cancel Order Action */}
                          <td className="py-3 px-3 text-right">
                            <button
                              type="button"
                              onClick={() => handleCancelOrder(ord.order_id)}
                              disabled={cancellingOrderId === ord.order_id}
                              className="px-2.5 py-1 rounded bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40 text-[11px] font-semibold transition disabled:opacity-50"
                              title="Cancel pending order and immediately unreserve virtual cash"
                            >
                              {cancellingOrderId === ord.order_id ? (
                                <span className="text-rose-400">Cancelling...</span>
                              ) : (
                                <>
                                  <XCircle className="w-3.5 h-3.5 inline mr-1" />
                                  <span>Cancel Order</span>
                                </>
                              )}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      )}

      {/* 6. Tab C: Executed Trade Audit Ledger */}
      {activeTab === "EXECUTED_TRADES" && (
        <section aria-label="Executed Trade Audit Ledger" className="space-y-4">
          {/* Summary KPI Strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="glass-panel p-3 rounded-xl border border-slate-800/80 bg-[#090d18]/90">
              <div className="text-[10px] uppercase text-slate-500 font-semibold">Total Executed Trades</div>
              <div className="text-base font-bold text-slate-100 font-mono mt-0.5">{closedTrades.length} Fills</div>
            </div>
            <div className="glass-panel p-3 rounded-xl border border-slate-800/80 bg-[#090d18]/90">
              <div className="text-[10px] uppercase text-slate-500 font-semibold">Win Rate</div>
              <div className="text-base font-bold text-emerald-400 font-mono mt-0.5">{winRate.toFixed(1)}%</div>
            </div>
            <div className="glass-panel p-3 rounded-xl border border-slate-800/80 bg-[#090d18]/90">
              <div className="text-[10px] uppercase text-slate-500 font-semibold">Total Frictions Paid</div>
              <div className="text-base font-bold text-amber-300 font-mono mt-0.5">{formatINR(totalFrictionsPaid)}</div>
            </div>
            <div className="glass-panel p-3 rounded-xl border border-slate-800/80 bg-[#090d18]/90">
              <div className="text-[10px] uppercase text-slate-500 font-semibold">Execution Venue</div>
              <div className="text-base font-bold text-cyan-300 font-mono mt-0.5">NSE Cash Equities</div>
            </div>
          </div>

          {/* Ledger Table */}
          <div className="glass-panel rounded-xl p-5 border border-slate-800/80 bg-[#090d18]/90">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3 mb-4">
              <div className="flex items-center space-x-2">
                <History className="w-4 h-4 text-cyan-400" />
                <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                  Executed Trade Audit Ledger ({closedTrades.length})
                </h3>
              </div>

              <div className="flex items-center space-x-2">
                <span className="text-xs text-slate-400 mr-1">Filter:</span>
                <button
                  type="button"
                  onClick={() => setExecutedFilter("ALL")}
                  className={`px-2 py-0.5 rounded text-[11px] font-semibold transition ${
                    executedFilter === "ALL"
                      ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                      : "bg-slate-900 text-slate-400 border border-slate-800"
                  }`}
                >
                  All ({closedTrades.length})
                </button>
                <button
                  type="button"
                  onClick={() => setExecutedFilter("WINNERS")}
                  className={`px-2 py-0.5 rounded text-[11px] font-semibold transition ${
                    executedFilter === "WINNERS"
                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                      : "bg-slate-900 text-slate-400 border border-slate-800"
                  }`}
                >
                  Winners ({winningTradesCount})
                </button>
                <button
                  type="button"
                  onClick={() => setExecutedFilter("LOSERS")}
                  className={`px-2 py-0.5 rounded text-[11px] font-semibold transition ${
                    executedFilter === "LOSERS"
                      ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                      : "bg-slate-900 text-slate-400 border border-slate-800"
                  }`}
                >
                  Losses ({closedTrades.length - winningTradesCount})
                </button>
              </div>
            </div>

            {filteredExecutedTrades.length === 0 ? (
              <div className="py-12 text-center text-slate-500 text-xs font-mono space-y-2">
                <History className="w-8 h-8 mx-auto text-slate-600 mb-2 stroke-[1.5]" />
                <div className="text-slate-400 font-semibold">No executed trades match current filters.</div>
                <div className="text-[11px] text-slate-500">
                  Completed market orders and exit fills with regulatory tax itemization will be logged here.
                </div>
              </div>
            ) : (
              <div className="overflow-x-auto max-h-96 overflow-y-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="sticky top-0 bg-[#090d18] z-10">
                    <tr className="text-slate-400 border-b border-slate-800 text-[11px] uppercase tracking-wider">
                      <th className="py-2.5 px-3">Trade ID</th>
                      <th className="py-2.5 px-3">Instrument</th>
                      <th className="py-2.5 px-2">Side</th>
                      <th className="py-2.5 px-3">Entry ➔ Exit Price</th>
                      <th className="py-2.5 px-3">Net Realized PnL</th>
                      <th className="py-2.5 px-2.5">Statutory Frictions</th>
                      <th className="py-2.5 px-2.5">Exit Reason</th>
                      <th className="py-2.5 px-3 text-right">Execution Time (IST)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {filteredExecutedTrades.map((t) => {
                      const isProfitable = (t.net_pnl || 0) >= 0;
                      const companyName = getInstrumentName(t.ticker);

                      return (
                        <tr
                          key={t.id}
                          className="hover:bg-slate-900/40 transition-colors"
                        >
                          {/* Trade ID */}
                          <td className="py-3 px-3 font-semibold text-slate-400">
                            #TRD-{t.id}
                          </td>

                          {/* Instrument */}
                          <td className="py-3 px-3">
                            <div className="font-bold text-slate-200">{t.ticker}</div>
                            <div className="text-[10px] text-slate-500 truncate max-w-[150px]">
                              {companyName}
                            </div>
                          </td>

                          {/* Direction */}
                          <td className="py-3 px-2">
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                t.direction === "LONG"
                                  ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                                  : "bg-rose-500/15 text-rose-300 border border-rose-500/30"
                              }`}
                            >
                              {t.direction}
                            </span>
                          </td>

                          {/* Entry ➔ Exit */}
                          <td className="py-3 px-3 text-slate-300 font-semibold">
                            {formatINR(t.entry_price)} ➔ {formatINR(t.exit_price)}
                          </td>

                          {/* Net Realized PnL */}
                          <td className="py-3 px-3">
                            <span
                              className={`font-bold flex items-center ${
                                isProfitable ? "text-emerald-400" : "text-rose-400"
                              }`}
                            >
                              {isProfitable ? (
                                <ArrowUpRight className="w-3.5 h-3.5 mr-0.5" />
                              ) : (
                                <ArrowDownRight className="w-3.5 h-3.5 mr-0.5" />
                              )}
                              {formatINR(t.net_pnl, { showSign: true })}
                            </span>
                            <span
                              className={`text-[10px] ${
                                isProfitable ? "text-emerald-500" : "text-rose-500"
                              }`}
                            >
                              ({t.return_pct >= 0 ? "+" : ""}{t.return_pct.toFixed(2)}%)
                            </span>
                          </td>

                          {/* Frictions */}
                          <td className="py-3 px-2.5 text-slate-400">
                            <div>{formatINR(t.friction_fee)}</div>
                            <div className="text-[9px] text-slate-600">STT/SEBI/GST</div>
                          </td>

                          {/* Exit Reason */}
                          <td className="py-3 px-2.5">
                            <span className="px-2 py-0.5 rounded bg-slate-800 text-[10px] text-slate-300 border border-slate-700">
                              {t.exit_reason || "MANUAL_CLOSE"}
                            </span>
                          </td>

                          {/* Time */}
                          <td className="py-3 px-3 text-right text-slate-400 text-[11px]">
                            {t.exit_time}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Flatten All Confirmation Modal */}
      {showFlattenModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="glass-panel rounded-2xl p-6 border border-rose-500/40 bg-[#090d18] max-w-md w-full space-y-4 shadow-2xl">
            <div className="flex items-center space-x-3 text-rose-400">
              <div className="p-2.5 rounded-xl bg-rose-500/15 border border-rose-500/30">
                <AlertTriangle className="w-6 h-6 text-rose-400" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-100">Flatten All Active Positions?</h3>
                <p className="text-xs text-rose-300 font-mono">Immediate Market-on-Close Order</p>
              </div>
            </div>

            <div className="text-xs text-slate-300 space-y-2 border-y border-slate-800 py-3">
              <p>
                Confirming will immediately liquidate all{" "}
                <span className="font-bold text-rose-400">{positions.length}</span> open positions in Indian equities at the current live market tick.
              </p>
              <div className="p-2.5 rounded bg-slate-900 text-slate-400 font-mono text-[11px] space-y-1">
                <div>• Total Exposure to Liquidate: {formatINR(totalInvestedExposure)}</div>
                <div>• Current MTM PnL to Realize: {formatINR(totalUnrealizedMtm, { showSign: true })}</div>
                <div>• All capital returns to Available Cash.</div>
              </div>
            </div>

            <div className="flex items-center justify-end space-x-3 pt-2">
              <button
                type="button"
                onClick={() => setShowFlattenModal(false)}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleFlattenAll}
                disabled={isFlattening}
                className="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition flex items-center space-x-1.5 shadow-[0_0_15px_rgba(244,63,94,0.3)] disabled:opacity-50"
              >
                <AlertTriangle className="w-4 h-4" />
                <span>{isFlattening ? "Liquidating..." : "Confirm Flatten All"}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
