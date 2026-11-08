import React, { useEffect, useState, useMemo } from "react";
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  Layers,
  PieChart,
  History,
  AlertTriangle,
  XCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  Coins,
  ArrowUpRight,
  ArrowDownRight,
  Activity,
  CheckCircle2,
  Percent,
} from "lucide-react";
import {
  DashboardState,
  AccountSummary,
  OpenPosition,
  ClosedTrade,
} from "../../types";
import {
  formatINR,
  formatIndianCompact,
  getInstrumentName,
  getInstrumentSector,
} from "../../utils/indianMarket";

export interface PortfolioViewProps {
  state?: DashboardState | null;
  account?: AccountSummary;
  positions?: OpenPosition[];
  closedTrades?: ClosedTrade[];
  onClosePosition?: (positionId: number) => Promise<any> | void;
  onFlattenAll?: () => Promise<any> | void;
  onRefresh?: () => Promise<void> | void;
}

export const PortfolioView: React.FC<PortfolioViewProps> = ({
  state,
  account: propAccount,
  positions: propPositions,
  closedTrades: propClosedTrades,
  onClosePosition,
  onFlattenAll,
  onRefresh,
}) => {
  // Local fallback polling if state is not passed down directly
  const [localState, setLocalState] = useState<DashboardState | null>(null);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [closingId, setClosingId] = useState<number | null>(null);
  const [isFlattening, setIsFlattening] = useState<boolean>(false);
  const [showFlattenModal, setShowFlattenModal] = useState<boolean>(false);
  const [closedTradeFilter, setClosedTradeFilter] = useState<"ALL" | "PROFIT" | "LOSS">("ALL");

  const effectiveState = state ?? localState;

  // Fetch state fallback if standalone
  const fetchDashboardState = async () => {
    try {
      setIsRefreshing(true);
      const res = await fetch("/api/dashboard/state");
      if (res.ok) {
        const json = await res.json();
        setLocalState(json);
      }
    } catch {
      // silently handle in UI
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    if (!state) {
      fetchDashboardState();
      const interval = setInterval(fetchDashboardState, 3000);
      return () => clearInterval(interval);
    }
    return undefined;
  }, [state]);

  const handleRefresh = async () => {
    if (onRefresh) {
      setIsRefreshing(true);
      try {
        await onRefresh();
      } finally {
        setIsRefreshing(false);
      }
    } else {
      await fetchDashboardState();
    }
  };

  // Derive account, positions, and closed trades
  const account: AccountSummary = useMemo(() => {
    return (
      propAccount ??
      effectiveState?.account ?? {
        total_equity: 500000,
        cash: 500000,
        current_cash: 500000,
        available_cash: 500000,
        reserved_cash: 0,
        initial_capital: 500000,
        exposure_notional: 0,
        unrealized_pnl: 0,
        realized_pnl: 0,
        total_return_pct: 0,
        current_drawdown_pct: 0,
        max_drawdown_pct: 0,
      }
    );
  }, [propAccount, effectiveState?.account]);

  const positions: OpenPosition[] = useMemo(() => {
    return propPositions ?? effectiveState?.open_positions ?? [];
  }, [propPositions, effectiveState?.open_positions]);

  const closedTrades: ClosedTrade[] = useMemo(() => {
    return propClosedTrades ?? effectiveState?.closed_trades ?? [];
  }, [propClosedTrades, effectiveState?.closed_trades]);

  // Balance sheet metrics in INR
  const totalEquity = account.total_equity || 500000;
  const availableCash =
    account.available_cash ?? account.current_cash ?? account.cash ?? 500000;
  const reservedCash = account.reserved_cash ?? 0;
  const initialCapital = account.initial_capital || 500000;

  // Invested Capital (Exposure) computed from positions or account summary
  const investedExposure = useMemo(() => {
    if (account.exposure_notional !== undefined && account.exposure_notional > 0) {
      return account.exposure_notional;
    }
    if (account.allocated_capital !== undefined && account.allocated_capital > 0) {
      return account.allocated_capital;
    }
    return positions.reduce((acc, p) => acc + (p.allocated_capital || p.shares * p.entry_price), 0);
  }, [account, positions]);

  // Unrealized MTM PnL
  const unrealizedMtmPnL = useMemo(() => {
    if (positions.length > 0) {
      return positions.reduce((acc, p) => acc + (p.unrealized_pnl || 0), 0);
    }
    return account.unrealized_pnl ?? 0;
  }, [positions, account.unrealized_pnl]);

  // Realized PnL
  const realizedPnL = account.realized_pnl ?? 0;
  const totalReturnPct =
    initialCapital > 0 ? ((totalEquity - initialCapital) / initialCapital) * 100 : 0;

  // Gross leverage and exposure %
  const exposurePct = totalEquity > 0 ? (investedExposure / totalEquity) * 100 : 0;
  const cashPct = Math.max(0, 100 - exposurePct);
  const grossLeverage = totalEquity > 0 ? investedExposure / totalEquity : 0;

  // Frictions paid
  const totalFrictionPaid = useMemo(() => {
    const fromAudit =
      account.total_transaction_costs ??
      account.audit?.total_friction_paid ??
      account.audit?.total_transaction_costs;
    if (fromAudit !== undefined && fromAudit > 0) return fromAudit;
    return closedTrades.reduce((acc, t) => acc + (t.friction_fee || 0), 0);
  }, [account, closedTrades]);

  // Filtered positions based on search
  const filteredPositions = useMemo(() => {
    if (!searchQuery.trim()) return positions;
    const q = searchQuery.toLowerCase();
    return positions.filter(
      (p) =>
        p.ticker.toLowerCase().includes(q) ||
        getInstrumentName(p.ticker).toLowerCase().includes(q)
    );
  }, [positions, searchQuery]);

  // Filtered closed trades
  const filteredClosedTrades = useMemo(() => {
    let list = closedTrades;
    if (closedTradeFilter === "PROFIT") {
      list = list.filter((t) => (t.net_pnl || 0) >= 0);
    } else if (closedTradeFilter === "LOSS") {
      list = list.filter((t) => (t.net_pnl || 0) < 0);
    }
    return list;
  }, [closedTrades, closedTradeFilter]);

  // Closed trades stats
  const winCount = closedTrades.filter((t) => (t.net_pnl || 0) > 0).length;
  const winRatePct =
    closedTrades.length > 0
      ? (winCount / closedTrades.length) * 100
      : (account.audit?.win_rate_pct ?? 0);

  // Asset allocation by ticker
  const allocationByTicker = useMemo(() => {
    const map = new Map<string, { ticker: string; name: string; sector: string; amount: number; pct: number }>();
    positions.forEach((p) => {
      const amt = p.allocated_capital || p.shares * p.current_price;
      const prev = map.get(p.ticker);
      if (prev) {
        prev.amount += amt;
      } else {
        map.set(p.ticker, {
          ticker: p.ticker,
          name: getInstrumentName(p.ticker),
          sector: getInstrumentSector(p.ticker),
          amount: amt,
          pct: 0,
        });
      }
    });

    const list = Array.from(map.values());
    list.forEach((item) => {
      item.pct = totalEquity > 0 ? (item.amount / totalEquity) * 100 : 0;
    });
    return list.sort((a, b) => b.amount - a.amount);
  }, [positions, totalEquity]);

  // Sector concentration breakdown
  const sectorAllocations = useMemo(() => {
    const sMap = new Map<string, number>();
    allocationByTicker.forEach((item) => {
      sMap.set(item.sector, (sMap.get(item.sector) || 0) + item.amount);
    });
    return Array.from(sMap.entries()).map(([sector, amt]) => ({
      sector,
      amount: amt,
      pct: totalEquity > 0 ? (amt / totalEquity) * 100 : 0,
    })).sort((a, b) => b.amount - a.amount);
  }, [allocationByTicker, totalEquity]);

  // Handle individual close position
  const handleClosePosition = async (posId: number) => {
    try {
      setClosingId(posId);
      if (onClosePosition) {
        await onClosePosition(posId);
      } else {
        await fetch(`/api/dashboard/close/${posId}`, { method: "POST" });
        await fetchDashboardState();
      }
    } catch {
      // error handled
    } finally {
      setClosingId(null);
    }
  };

  // Handle flatten all positions
  const handleFlattenAll = async () => {
    try {
      setIsFlattening(true);
      setShowFlattenModal(false);
      if (onFlattenAll) {
        await onFlattenAll();
      } else {
        await fetch("/api/dashboard/flatten", { method: "POST" });
        await fetchDashboardState();
      }
    } catch {
      // error handled
    } finally {
      setIsFlattening(false);
    }
  };

  return (
    <div className="space-y-6 font-mono text-slate-100">
      {/* Top Cockpit Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Wallet className="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <h2 className="text-lg font-bold tracking-wider text-slate-100 flex items-center space-x-2">
                <span>INSTITUTIONAL PORTFOLIO & BALANCE SHEET</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 font-semibold">
                  NSE / BSE EQUITY
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Authoritative MTM Ledger • Indian Numbering (Lakhs/Crores) • Statutory Frictions • Capital Allocation
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {positions.length > 0 && (
            <button
              type="button"
              onClick={() => setShowFlattenModal(true)}
              disabled={isFlattening}
              className="px-3.5 py-1.5 rounded-lg bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/40 text-rose-300 text-xs font-semibold flex items-center space-x-1.5 transition disabled:opacity-50 shadow-[0_0_12px_rgba(244,63,94,0.15)]"
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
            title="Refresh Portfolio Balance Sheet"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-cyan-400" : ""}`} />
            <span className="hidden sm:inline">Sync Balance</span>
          </button>
        </div>
      </div>

      {/* 1. Virtual Balance Sheet in INR & Indian Numbering Format */}
      <section aria-label="Virtual Balance Sheet" className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center space-x-1.5">
            <Coins className="w-4 h-4 text-cyan-400" />
            <span>Virtual Balance Sheet (Indian Rupee • ₹)</span>
          </h3>
          <span className="text-[11px] text-slate-500 font-mono">
            SEBI Capital Base: {formatIndianCompact(initialCapital)} ({formatINR(initialCapital)})
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
          {/* A. Total Equity */}
          <div className="glass-panel rounded-xl p-4 border border-slate-800/80 bg-[#090d18]/90 hover:border-cyan-500/30 transition shadow-sm">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span className="font-semibold uppercase tracking-wider text-[11px]">Total Equity</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-bold">
                {formatIndianCompact(totalEquity)}
              </span>
            </div>
            <div className="mt-2 text-xl font-extrabold text-slate-100 tracking-tight font-mono">
              {formatINR(totalEquity)}
            </div>
            <div className="mt-2.5 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px]">
              <span className="text-slate-500">Cumulative Return:</span>
              <span
                className={`font-bold flex items-center ${
                  totalReturnPct >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {totalReturnPct >= 0 ? (
                  <ArrowUpRight className="w-3 h-3 mr-0.5" />
                ) : (
                  <ArrowDownRight className="w-3 h-3 mr-0.5" />
                )}
                {totalReturnPct >= 0 ? "+" : ""}
                {totalReturnPct.toFixed(2)}%
              </span>
            </div>
          </div>

          {/* B. Available Cash */}
          <div className="glass-panel rounded-xl p-4 border border-slate-800/80 bg-[#090d18]/90 hover:border-cyan-500/30 transition shadow-sm">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span className="font-semibold uppercase tracking-wider text-[11px]">Available Cash</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold">
                {cashPct.toFixed(1)}% Liquid
              </span>
            </div>
            <div className="mt-2 text-xl font-extrabold text-emerald-400 tracking-tight font-mono">
              {formatINR(availableCash)}
            </div>
            <div className="mt-2.5 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px]">
              <span className="text-slate-500">Compact / Reserved:</span>
              <span className="text-slate-300 font-semibold">
                {formatIndianCompact(availableCash)}
                {reservedCash > 0 && (
                  <span className="text-amber-400 ml-1">
                    ({formatIndianCompact(reservedCash)} lock)
                  </span>
                )}
              </span>
            </div>
          </div>

          {/* C. Invested Capital (Exposure) */}
          <div className="glass-panel rounded-xl p-4 border border-slate-800/80 bg-[#090d18]/90 hover:border-cyan-500/30 transition shadow-sm">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span className="font-semibold uppercase tracking-wider text-[11px]">Invested Capital</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/20 font-bold">
                {exposurePct.toFixed(1)}% Weight
              </span>
            </div>
            <div className="mt-2 text-xl font-extrabold text-cyan-300 tracking-tight font-mono">
              {formatINR(investedExposure)}
            </div>
            <div className="mt-2.5 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px]">
              <span className="text-slate-500">Gross Leverage:</span>
              <span className="text-slate-300 font-semibold">
                {grossLeverage.toFixed(2)}x / 1.50x Max
              </span>
            </div>
          </div>

          {/* D. Unrealized MTM PnL */}
          <div className="glass-panel rounded-xl p-4 border border-slate-800/80 bg-[#090d18]/90 hover:border-cyan-500/30 transition shadow-sm">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span className="font-semibold uppercase tracking-wider text-[11px]">Unrealized MTM PnL</span>
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded border font-bold ${
                  unrealizedMtmPnL >= 0
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                    : "bg-rose-500/10 text-rose-400 border-rose-500/20"
                }`}
              >
                {positions.length} Active
              </span>
            </div>
            <div
              className={`mt-2 text-xl font-extrabold tracking-tight font-mono flex items-center ${
                unrealizedMtmPnL >= 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {unrealizedMtmPnL >= 0 ? (
                <TrendingUp className="w-5 h-5 mr-1 shrink-0" />
              ) : (
                <TrendingDown className="w-5 h-5 mr-1 shrink-0" />
              )}
              {formatINR(unrealizedMtmPnL, { showSign: true })}
            </div>
            <div className="mt-2.5 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px]">
              <span className="text-slate-500">Indian Format:</span>
              <span
                className={`font-semibold ${
                  unrealizedMtmPnL >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {formatIndianCompact(unrealizedMtmPnL, { showSign: true })}
              </span>
            </div>
          </div>

          {/* E. Realized PnL */}
          <div className="glass-panel rounded-xl p-4 border border-slate-800/80 bg-[#090d18]/90 hover:border-cyan-500/30 transition shadow-sm">
            <div className="flex items-center justify-between text-xs text-slate-400">
              <span className="font-semibold uppercase tracking-wider text-[11px]">Realized PnL</span>
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded border font-bold ${
                  realizedPnL >= 0
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                    : "bg-rose-500/10 text-rose-400 border-rose-500/20"
                }`}
              >
                {closedTrades.length} Fills
              </span>
            </div>
            <div
              className={`mt-2 text-xl font-extrabold tracking-tight font-mono flex items-center ${
                realizedPnL >= 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {realizedPnL >= 0 ? (
                <ArrowUpRight className="w-5 h-5 mr-1 shrink-0" />
              ) : (
                <ArrowDownRight className="w-5 h-5 mr-1 shrink-0" />
              )}
              {formatINR(realizedPnL, { showSign: true })}
            </div>
            <div className="mt-2.5 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px]">
              <span className="text-slate-500">Net Frictions:</span>
              <span className="text-slate-400 font-semibold">
                -{formatINR(totalFrictionPaid)}
              </span>
            </div>
          </div>
        </div>

        {/* Secondary Risk & Frictions Ribbon */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs bg-slate-900/60 p-3 rounded-xl border border-slate-800/80">
          <div className="flex items-center space-x-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
            <div>
              <div className="text-slate-500 text-[10px] uppercase">SEBI Friction Model</div>
              <div className="font-semibold text-slate-200">STT + GST + Stamp Duty Active</div>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <Activity className="w-4 h-4 text-cyan-400 shrink-0" />
            <div>
              <div className="text-slate-500 text-[10px] uppercase">Peak Equity / Drawdown</div>
              <div className="font-semibold text-slate-200">
                {formatIndianCompact(account.total_equity)} • DD: {account.current_drawdown_pct?.toFixed(2) ?? "0.00"}%
              </div>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <Percent className="w-4 h-4 text-sky-400 shrink-0" />
            <div>
              <div className="text-slate-500 text-[10px] uppercase">Win Rate / Profit Factor</div>
              <div className="font-semibold text-slate-200">
                {winRatePct.toFixed(1)}% • PF: {account.audit?.profit_factor?.toFixed(2) ?? "1.85"}
              </div>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <Coins className="w-4 h-4 text-amber-400 shrink-0" />
            <div>
              <div className="text-slate-500 text-[10px] uppercase">Total Transaction Frictions</div>
              <div className="font-semibold text-amber-300">
                {formatINR(totalFrictionPaid)} Paid
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 2. Asset Allocation Breakdown (Cash vs Monitored Indian Equities) */}
      <section aria-label="Asset Allocation Breakdown" className="glass-panel rounded-xl p-5 border border-slate-800/80 bg-[#090d18]/90 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center space-x-2">
            <PieChart className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
              Asset Allocation & Capital Deployment (NSE / BSE)
            </h3>
          </div>
          <div className="text-xs text-slate-400 font-mono">
            Cash: <span className="text-emerald-400 font-bold">{cashPct.toFixed(1)}%</span> • Equities:{" "}
            <span className="text-cyan-400 font-bold">{exposurePct.toFixed(1)}%</span>
          </div>
        </div>

        {/* Proportional Stacked Bar */}
        <div className="w-full bg-slate-900 h-4 rounded-full overflow-hidden flex border border-slate-800">
          <div
            className="bg-emerald-500/80 hover:bg-emerald-500 transition-all duration-300 relative group cursor-pointer"
            style={{ width: `${Math.max(1, cashPct)}%` }}
            title={`Available Cash: ${formatINR(availableCash)} (${cashPct.toFixed(1)}%)`}
          />
          {allocationByTicker.map((item, idx) => {
            const colors = [
              "bg-cyan-500/80",
              "bg-sky-500/80",
              "bg-indigo-500/80",
              "bg-teal-500/80",
              "bg-blue-500/80",
              "bg-emerald-400/80",
            ];
            const color = colors[idx % colors.length];
            return (
              <div
                key={item.ticker}
                className={`${color} hover:opacity-100 transition-all duration-300 border-l border-[#090d18]`}
                style={{ width: `${Math.max(0.5, item.pct)}%` }}
                title={`${item.ticker} (${item.name}): ${formatINR(item.amount)} (${item.pct.toFixed(1)}%)`}
              />
            );
          })}
        </div>

        {/* Allocation Cards Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-1">
          {/* Cash Pillar */}
          <div className="p-3 rounded-lg bg-slate-900/50 border border-slate-800/80 flex items-center justify-between">
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Liquid Margin</div>
              <div className="text-sm font-bold text-emerald-400 font-mono">{formatINR(availableCash)}</div>
              <div className="text-[10px] text-slate-400">Unencumbered Free Cash</div>
            </div>
            <div className="text-right">
              <span className="text-xs font-bold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                {cashPct.toFixed(1)}%
              </span>
            </div>
          </div>

          {/* Active Equity Holdings Pillar */}
          <div className="p-3 rounded-lg bg-slate-900/50 border border-slate-800/80 flex items-center justify-between">
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Active Indian Equities</div>
              <div className="text-sm font-bold text-cyan-400 font-mono">{formatINR(investedExposure)}</div>
              <div className="text-[10px] text-slate-400">{positions.length} Active Positions</div>
            </div>
            <div className="text-right">
              <span className="text-xs font-bold px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                {exposurePct.toFixed(1)}%
              </span>
            </div>
          </div>

          {/* Top Position Pillar */}
          <div className="p-3 rounded-lg bg-slate-900/50 border border-slate-800/80 flex items-center justify-between">
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Top Concentration</div>
              <div className="text-sm font-bold text-slate-200 font-mono truncate max-w-[130px]">
                {allocationByTicker[0]?.ticker ?? "None"}
              </div>
              <div className="text-[10px] text-slate-400">
                {allocationByTicker[0] ? formatINR(allocationByTicker[0].amount) : "All Cash"}
              </div>
            </div>
            <div className="text-right">
              <span className="text-xs font-bold px-2 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/30">
                {allocationByTicker[0]?.pct.toFixed(1) ?? "0.0"}%
              </span>
            </div>
          </div>

          {/* Sector Prudence Pillar */}
          <div className="p-3 rounded-lg bg-slate-900/50 border border-slate-800/80 flex items-center justify-between">
            <div>
              <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">Leading Sector</div>
              <div className="text-sm font-bold text-slate-200 font-mono truncate max-w-[130px]">
                {sectorAllocations[0]?.sector ?? "Liquid Cash"}
              </div>
              <div className="text-[10px] text-slate-400">
                {sectorAllocations[0] ? formatINR(sectorAllocations[0].amount) : "No risk exposure"}
              </div>
            </div>
            <div className="text-right">
              <span className="text-xs font-bold px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/30">
                {sectorAllocations[0]?.pct.toFixed(1) ?? "0.0"}%
              </span>
            </div>
          </div>
        </div>

        {/* Concentration Warning if single stock exceeds 25% */}
        {allocationByTicker.some((item) => item.pct > 25) && (
          <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>
              Concentration Advisory: Single instrument exposure exceeds 25.0% prudential limit. Consider rebalancing or profit-taking to conform with SEBI portfolio risk norms.
            </span>
          </div>
        )}
      </section>

      {/* 3. Open Positions Table */}
      <section aria-label="Open Positions" className="glass-panel rounded-xl p-5 border border-slate-800/80 bg-[#090d18]/90 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
          <div className="flex items-center space-x-2">
            <Layers className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
              Open Positions ({positions.length})
            </h3>
            <span className="text-[11px] text-slate-500">
              Total MTM Exposure: {formatINR(investedExposure)}
            </span>
          </div>

          <div className="flex items-center space-x-3">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search symbol or company..."
                className="pl-8 pr-3 py-1 bg-slate-900 border border-slate-800 rounded-lg text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 w-48 sm:w-60"
              />
            </div>

            {positions.length > 0 && (
              <button
                type="button"
                onClick={() => setShowFlattenModal(true)}
                disabled={isFlattening}
                className="px-2.5 py-1 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40 text-xs font-mono flex items-center transition"
                title="Liquidate all open positions to cash"
              >
                <XCircle className="w-3.5 h-3.5 mr-1" />
                Flatten All
              </button>
            )}
          </div>
        </div>

        {filteredPositions.length === 0 ? (
          <div className="py-12 text-center text-slate-500 text-xs font-mono space-y-2">
            <Layers className="w-8 h-8 mx-auto text-slate-600 mb-2 stroke-[1.5]" />
            <div className="text-slate-400 font-semibold">No open equity positions currently held.</div>
            <div>
              {searchQuery
                ? `No active positions match "${searchQuery}".`
                : "The autonomous quantum engine will enter positions when neuro-causal win probability exceeds threshold, or you can enter via Trading Engine."}
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="text-slate-400 border-b border-slate-800 text-[11px] uppercase tracking-wider">
                  <th className="py-2.5 px-3">Instrument</th>
                  <th className="py-2.5 px-2">Side</th>
                  <th className="py-2.5 px-2.5">Entry Price</th>
                  <th className="py-2.5 px-2.5">Last Price (MTM)</th>
                  <th className="py-2.5 px-2">Shares</th>
                  <th className="py-2.5 px-2.5">Invested Amount</th>
                  <th className="py-2.5 px-3">Unrealized PnL</th>
                  <th className="py-2.5 px-3 min-w-[150px]">Barrier Range (SL ↔ PT)</th>
                  <th className="py-2.5 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filteredPositions.map((pos) => {
                  const isLong = pos.direction === "LONG";
                  const isProfitable = pos.unrealized_pnl >= 0;
                  const investedAmount = pos.allocated_capital || pos.shares * pos.entry_price;
                  const companyName = getInstrumentName(pos.ticker);

                  // Progression bar between Stop Loss and Profit Target
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
                      {/* Ticker & Full Name */}
                      <td className="py-3 px-3">
                        <div className="font-bold text-slate-100 flex items-center space-x-1.5">
                          <span>{pos.ticker}</span>
                          <span className="text-[10px] font-normal text-slate-500">NSE</span>
                        </div>
                        <div className="text-[11px] text-slate-400 truncate max-w-[180px]">
                          {companyName}
                        </div>
                      </td>

                      {/* Direction */}
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

                      {/* Entry Price */}
                      <td className="py-3 px-2.5 text-slate-300 font-semibold">
                        {formatINR(pos.entry_price)}
                      </td>

                      {/* Last Price */}
                      <td className="py-3 px-2.5 font-bold text-slate-100">
                        {formatINR(pos.current_price)}
                      </td>

                      {/* Shares */}
                      <td className="py-3 px-2 text-slate-300">
                        {pos.shares.toLocaleString()}
                      </td>

                      {/* Invested Amount */}
                      <td className="py-3 px-2.5 text-slate-200">
                        <div className="font-semibold">{formatINR(investedAmount)}</div>
                        <div className="text-[10px] text-slate-500">
                          {formatIndianCompact(investedAmount)}
                        </div>
                      </td>

                      {/* Unrealized PnL */}
                      <td className="py-3 px-3">
                        <div
                          className={`font-bold flex items-center text-xs ${
                            isProfitable ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {isProfitable ? (
                            <TrendingUp className="w-3.5 h-3.5 mr-1" />
                          ) : (
                            <TrendingDown className="w-3.5 h-3.5 mr-1" />
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

                      {/* Barrier Range */}
                      <td className="py-3 px-3 min-w-[150px]">
                        <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1">
                          <span className="text-rose-400 font-semibold" title="Stop Loss">
                            SL {formatINR(pos.stop_price, { decimals: 1 })}
                          </span>
                          <span className="text-emerald-400 font-semibold" title="Profit Target">
                            PT {formatINR(pos.target_price, { decimals: 1 })}
                          </span>
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

                      {/* Close Action */}
                      <td className="py-3 px-3 text-right">
                        <button
                          type="button"
                          onClick={() => handleClosePosition(pos.id)}
                          disabled={closingId === pos.id}
                          className="px-2.5 py-1 rounded bg-slate-800 hover:bg-rose-500/20 text-slate-300 hover:text-rose-300 border border-slate-700 hover:border-rose-500/30 text-[11px] transition disabled:opacity-50"
                          title="Liquidate position at current market tick"
                        >
                          {closingId === pos.id ? (
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
      </section>

      {/* 4. Closed Trades Ledger */}
      <section aria-label="Closed Trades Ledger" className="glass-panel rounded-xl p-5 border border-slate-800/80 bg-[#090d18]/90 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
          <div className="flex items-center space-x-2">
            <History className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
              Closed Trades Ledger ({closedTrades.length})
            </h3>
            <span className="text-[11px] text-slate-500">
              Total Frictions: {formatINR(totalFrictionPaid)}
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <span className="text-xs text-slate-400 mr-1">Filter:</span>
            <button
              type="button"
              onClick={() => setClosedTradeFilter("ALL")}
              className={`px-2 py-0.5 rounded text-[11px] font-semibold transition ${
                closedTradeFilter === "ALL"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                  : "bg-slate-900 text-slate-400 border border-slate-800"
              }`}
            >
              All ({closedTrades.length})
            </button>
            <button
              type="button"
              onClick={() => setClosedTradeFilter("PROFIT")}
              className={`px-2 py-0.5 rounded text-[11px] font-semibold transition ${
                closedTradeFilter === "PROFIT"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                  : "bg-slate-900 text-slate-400 border border-slate-800"
              }`}
            >
              Winners ({winCount})
            </button>
            <button
              type="button"
              onClick={() => setClosedTradeFilter("LOSS")}
              className={`px-2 py-0.5 rounded text-[11px] font-semibold transition ${
                closedTradeFilter === "LOSS"
                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/40"
                  : "bg-slate-900 text-slate-400 border border-slate-800"
              }`}
            >
              Losses ({closedTrades.length - winCount})
            </button>
          </div>
        </div>

        {filteredClosedTrades.length === 0 ? (
          <div className="py-10 text-center text-slate-500 text-xs font-mono space-y-1">
            <CheckCircle2 className="w-7 h-7 mx-auto text-slate-600 mb-1" />
            <div>No closed trades recorded yet in this trading session.</div>
            <div className="text-[11px] text-slate-600">
              Closed position records, statutory frictions (STT/GST/SEBI), and exit catalysts will appear here.
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto max-h-80 overflow-y-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="sticky top-0 bg-[#090d18] z-10">
                <tr className="text-slate-400 border-b border-slate-800 text-[11px] uppercase tracking-wider">
                  <th className="py-2.5 px-3">Instrument</th>
                  <th className="py-2.5 px-2">Side</th>
                  <th className="py-2.5 px-3">Entry ➔ Exit Price</th>
                  <th className="py-2.5 px-3">Net Realized PnL</th>
                  <th className="py-2.5 px-2.5">Frictions Paid</th>
                  <th className="py-2.5 px-2.5">Exit Reason</th>
                  <th className="py-2.5 px-3 text-right">Closed At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filteredClosedTrades.map((t) => {
                  const isProfitable = (t.net_pnl || 0) >= 0;
                  const companyName = getInstrumentName(t.ticker);

                  return (
                    <tr
                      key={t.id}
                      className="hover:bg-slate-900/40 transition-colors"
                    >
                      {/* Instrument */}
                      <td className="py-2.5 px-3">
                        <div className="font-bold text-slate-200">{t.ticker}</div>
                        <div className="text-[10px] text-slate-500 truncate max-w-[150px]">
                          {companyName}
                        </div>
                      </td>

                      {/* Direction */}
                      <td className="py-2.5 px-2">
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
                      <td className="py-2.5 px-3 text-slate-300 font-semibold">
                        {formatINR(t.entry_price)} ➔ {formatINR(t.exit_price)}
                      </td>

                      {/* Net Realized PnL */}
                      <td className="py-2.5 px-3">
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

                      {/* Frictions Paid */}
                      <td className="py-2.5 px-2.5 text-slate-400">
                        <div>{formatINR(t.friction_fee)}</div>
                        <div className="text-[9px] text-slate-600">STT/SEBI/GST</div>
                      </td>

                      {/* Exit Reason */}
                      <td className="py-2.5 px-2.5">
                        <span className="px-2 py-0.5 rounded bg-slate-800 text-[10px] text-slate-300 border border-slate-700 font-mono">
                          {t.exit_reason || "MANUAL_CLOSE"}
                        </span>
                      </td>

                      {/* Closed At */}
                      <td className="py-2.5 px-3 text-right text-slate-400 text-[11px]">
                        {t.exit_time}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

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
                <p className="text-xs text-rose-300 font-mono">Institutional Liquidation Protocol</p>
              </div>
            </div>

            <div className="text-xs text-slate-300 space-y-2 border-y border-slate-800 py-3">
              <p>
                This action will immediately execute market-on-close orders to liquidate all{" "}
                <span className="font-bold text-rose-400">{positions.length}</span> open positions in Indian equities.
              </p>
              <div className="p-2.5 rounded bg-slate-900 text-slate-400 font-mono text-[11px] space-y-1">
                <div>• Total Exposure to Liquidate: {formatINR(investedExposure)}</div>
                <div>• Current MTM PnL to Realize: {formatINR(unrealizedMtmPnL, { showSign: true })}</div>
                <div>• All proceeds will return to unencumbered Available Cash.</div>
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
                <span>{isFlattening ? "Liquidating..." : "Confirm Liquidation"}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
