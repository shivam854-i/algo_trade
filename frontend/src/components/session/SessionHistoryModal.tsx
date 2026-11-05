import React, { useEffect, useState } from "react";
import {
  History,
  X,
  RefreshCw,
  ShieldCheck,
  ChevronRight,
  ChevronDown,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { TradingSession, SessionPerformance, SessionStatus, SessionMarket } from "../../types";
import { sessionApi } from "../../services/sessionApi";

export interface SessionHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectSession?: (sessionId: string) => void;
}

export const SessionHistoryModal: React.FC<SessionHistoryModalProps> = ({
  isOpen,
  onClose,
  onSelectSession,
}) => {
  const [sessions, setSessions] = useState<TradingSession[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedMarket, setSelectedMarket] = useState<string>("ALL");
  const [selectedStatus, setSelectedStatus] = useState<string>("ALL");

  // Expanded session for performance details
  const [expandedSessionId, setExpandedSessionId] = useState<string | null>(null);
  const [performanceMap, setPerformanceMap] = useState<Record<string, SessionPerformance>>({});
  const [loadingPerfId, setLoadingPerfId] = useState<string | null>(null);

  const loadSessions = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const params: any = { limit: 50 };
      if (selectedMarket !== "ALL") {
        params.market = selectedMarket as SessionMarket;
      }
      if (selectedStatus !== "ALL") {
        params.status = selectedStatus as SessionStatus;
      }
      const data = await sessionApi.listSessions(params);
      setSessions(data.sessions || []);
      setTotalCount(data.total || 0);
    } catch (err: any) {
      setError(err.message || "Failed to load session history");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadSessions();
    }
  }, [isOpen, selectedMarket, selectedStatus]);

  const toggleExpandSession = async (sessionId: string) => {
    if (expandedSessionId === sessionId) {
      setExpandedSessionId(null);
      return;
    }
    setExpandedSessionId(sessionId);

    // Fetch performance if not cached
    if (!performanceMap[sessionId]) {
      setLoadingPerfId(sessionId);
      try {
        const perf = await sessionApi.fetchSessionPerformance(sessionId);
        setPerformanceMap((prev) => ({ ...prev, [sessionId]: perf }));
      } catch (err) {
        console.error("Failed to load session performance:", err);
      } finally {
        setLoadingPerfId(null);
      }
    }
  };

  if (!isOpen) {
    return null;
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "RUNNING":
        return (
          <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[10px] font-bold flex items-center">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse mr-1" />
            RUNNING
          </span>
        );
      case "PAUSED":
        return (
          <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[10px] font-bold flex items-center">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 mr-1" />
            PAUSED
          </span>
        );
      case "COMPLETED":
        return (
          <span className="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/40 text-[10px] font-bold">
            COMPLETED
          </span>
        );
      case "STOPPED":
        return (
          <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 text-[10px] font-bold">
            STOPPED
          </span>
        );
      case "CREATED":
      default:
        return (
          <span className="px-2 py-0.5 rounded bg-sky-500/20 text-sky-300 border border-sky-500/40 text-[10px] font-bold">
            CREATED
          </span>
        );
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="session-history-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-150"
    >
      <div className="relative w-full max-w-4xl max-h-[90vh] flex flex-col bg-[#0b0f19] border border-slate-800 rounded-2xl shadow-2xl overflow-hidden font-sans">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/40">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-sky-500/20 text-sky-400 border border-sky-500/30 flex items-center justify-center">
              <History className="w-4 h-4" />
            </div>
            <div>
              <h2 id="session-history-title" className="text-sm font-bold font-mono text-slate-100 flex items-center gap-2">
                Trading Session History &amp; Audit Ledger
                <span className="px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-xs text-sky-400 font-mono">
                  {totalCount} Sessions
                </span>
              </h2>
              <p className="text-[11px] text-slate-500 font-mono">
                Isolated performance attribution, historical trades, and compliance logs
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={loadSessions}
              disabled={isLoading}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition disabled:opacity-50"
              title="Refresh session list"
              aria-label="Refresh session list"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
              aria-label="Close session history modal"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Filter Toolbar */}
        <div className="px-6 py-3 border-b border-slate-800/80 bg-slate-950/40 flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-slate-500 text-[11px]">Market:</span>
            {["ALL", "US_EQUITIES", "INDIAN_NSE", "CRYPTO", "COMMODITIES", "FOREX"].map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setSelectedMarket(m)}
                className={`px-2.5 py-1 rounded-md text-[11px] border transition ${
                  selectedMarket === m
                    ? "bg-sky-500/20 text-sky-300 border-sky-500/40 font-bold"
                    : "bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700 hover:text-slate-200"
                }`}
              >
                {m === "ALL" ? "All Markets" : m.replace("_", " ")}
              </button>
            ))}
          </div>

          <div className="flex items-center space-x-2">
            <span className="text-slate-500 text-[11px]">Status:</span>
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="bg-slate-900 border border-slate-800 rounded-md px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
            >
              <option value="ALL">All Statuses</option>
              <option value="RUNNING">RUNNING</option>
              <option value="PAUSED">PAUSED</option>
              <option value="COMPLETED">COMPLETED</option>
              <option value="STOPPED">STOPPED</option>
              <option value="CREATED">CREATED</option>
            </select>
          </div>
        </div>

        {/* Modal Body / Table */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
          {error && (
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
              <span>{error}</span>
            </div>
          )}

          {isLoading && sessions.length === 0 ? (
            <div className="py-12 flex flex-col items-center justify-center text-slate-500 font-mono space-y-2">
              <Loader2 className="w-6 h-6 animate-spin text-sky-400" />
              <span className="text-xs">Loading historical session ledger...</span>
            </div>
          ) : sessions.length === 0 ? (
            <div className="py-12 flex flex-col items-center justify-center text-slate-500 font-mono space-y-2">
              <History className="w-8 h-8 text-slate-600" />
              <span className="text-xs">No trading sessions found matching the selected filters.</span>
            </div>
          ) : (
            <div className="space-y-2.5">
              {sessions.map((sess) => {
                const isExpanded = expandedSessionId === sess.id;
                const perf = performanceMap[sess.id];
                const currencySym = sess.currency === "INR" ? "₹" : "$";
                const metrics = sess.current_metrics || {};
                const realizedPnL = Number(metrics.realized_pnl ?? 0);
                const isPos = realizedPnL >= 0;

                return (
                  <div
                    key={sess.id}
                    className="border border-slate-800/80 rounded-xl bg-slate-900/30 hover:border-slate-700/80 transition overflow-hidden"
                  >
                    {/* Primary Row */}
                    <div
                      className="p-3.5 flex flex-wrap items-center justify-between gap-3 cursor-pointer select-none"
                      onClick={() => {
                        toggleExpandSession(sess.id);
                        onSelectSession?.(sess.id);
                      }}
                    >
                      {/* Identity & Badges */}
                      <div className="flex items-center space-x-3 min-w-[200px]">
                        <button
                          type="button"
                          className="text-slate-500 hover:text-slate-300 transition"
                          aria-label={isExpanded ? "Collapse details" : "Expand details"}
                        >
                          {isExpanded ? (
                            <ChevronDown className="w-4 h-4 text-sky-400" />
                          ) : (
                            <ChevronRight className="w-4 h-4" />
                          )}
                        </button>
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className="font-mono font-bold text-xs text-slate-100">
                              {sess.name || sess.id}
                            </span>
                            {getStatusBadge(sess.status)}
                          </div>
                          <div className="flex items-center space-x-2 mt-1 text-[11px] font-mono text-slate-500">
                            <span>#{sess.id.substring(0, 8)}</span>
                            <span>•</span>
                            <span className="text-slate-400">{sess.market}</span>
                            <span>•</span>
                            <span>Horizon: {sess.horizon}</span>
                            <span>•</span>
                            <span>{new Date(sess.created_at).toLocaleDateString()}</span>
                          </div>
                        </div>
                      </div>

                      {/* Basket Chips */}
                      <div className="hidden md:flex items-center gap-1.5 flex-wrap max-w-xs">
                        {(sess.instruments || []).slice(0, 4).map((ticker) => (
                          <span
                            key={ticker}
                            className="px-2 py-0.5 rounded bg-slate-800/80 border border-slate-700/60 text-[10px] font-mono text-slate-300"
                          >
                            {ticker}
                          </span>
                        ))}
                        {(sess.instruments || []).length > 4 && (
                          <span className="text-[10px] font-mono text-slate-500">
                            +{sess.instruments.length - 4} more
                          </span>
                        )}
                      </div>

                      {/* Financial Metrics */}
                      <div className="flex items-center space-x-4 font-mono text-xs">
                        <div className="text-right">
                          <span className="text-[10px] text-slate-500 block">Allocated</span>
                          <span className="text-slate-200 font-semibold">
                            {currencySym}
                            {Number(sess.allocated_capital).toLocaleString()}
                          </span>
                        </div>

                        <div className="text-right min-w-[70px]">
                          <span className="text-[10px] text-slate-500 block">Realized PnL</span>
                          <span className={`font-bold ${isPos ? "text-emerald-400" : "text-rose-400"}`}>
                            {isPos ? "+" : ""}
                            {currencySym}
                            {realizedPnL.toFixed(2)}
                          </span>
                        </div>

                        <div className="text-right">
                          <span className="text-[10px] text-slate-500 block">Trades</span>
                          <span className="text-slate-300">{metrics.total_trades ?? 0}</span>
                        </div>
                      </div>
                    </div>

                    {/* Expanded Performance & Audit Details */}
                    {isExpanded && (
                      <div className="px-5 py-4 border-t border-slate-800 bg-slate-950/60 space-y-4 font-mono text-xs animate-in fade-in duration-100">
                        {loadingPerfId === sess.id ? (
                          <div className="py-4 flex items-center justify-center space-x-2 text-slate-500 text-xs">
                            <Loader2 className="w-4 h-4 animate-spin text-sky-400" />
                            <span>Computing isolated performance metrics...</span>
                          </div>
                        ) : perf ? (
                          <div className="space-y-3">
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                              <div className="p-3 rounded-lg bg-slate-900 border border-slate-800">
                                <span className="text-[11px] text-slate-500 block">Win Rate</span>
                                <span className="text-sm font-bold text-slate-200">
                                  {perf.win_rate_pct?.toFixed(1) ?? 0}%
                                </span>
                                <span className="text-[10px] text-slate-500 block mt-0.5">
                                  {perf.winning_trades ?? 0}W / {perf.losing_trades ?? 0}L
                                </span>
                              </div>

                              <div className="p-3 rounded-lg bg-slate-900 border border-slate-800">
                                <span className="text-[11px] text-slate-500 block">Profit Factor</span>
                                <span className="text-sm font-bold text-slate-200">
                                  {perf.profit_factor?.toFixed(2) ?? "1.00"}
                                </span>
                                <span className="text-[10px] text-slate-500 block mt-0.5">
                                  Realized: {currencySym}{perf.realized_pnl?.toFixed(2) ?? 0}
                                </span>
                              </div>

                              <div className="p-3 rounded-lg bg-slate-900 border border-slate-800">
                                <span className="text-[11px] text-slate-500 block">Net PnL</span>
                                <span className={`text-sm font-bold ${(perf.net_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                                  {(perf.net_pnl ?? 0) >= 0 ? "+" : ""}{currencySym}{perf.net_pnl?.toFixed(2) ?? 0}
                                </span>
                                <span className="text-[10px] text-slate-500 block mt-0.5">
                                  Cash: {currencySym}{perf.current_cash?.toFixed(0) ?? 0}
                                </span>
                              </div>

                              <div className="p-3 rounded-lg bg-slate-900 border border-slate-800">
                                <span className="text-[11px] text-slate-500 block">Total Return</span>
                                <span className={`text-sm font-bold ${(perf.return_pct ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                                  {(perf.return_pct ?? 0) >= 0 ? "+" : ""}{perf.return_pct?.toFixed(2) ?? 0}%
                                </span>
                                <span className="text-[10px] text-slate-500 block mt-0.5">
                                  Open Pos: {perf.open_positions_count ?? 0}
                                </span>
                              </div>
                            </div>

                            {/* Session Parameters Review */}
                            <div className="p-3 rounded-lg bg-slate-900/40 border border-slate-800/80 flex flex-wrap items-center justify-between gap-3 text-[11px] text-slate-400">
                              <div>
                                <span className="text-slate-500">Duration: </span>
                                <span>{sess.duration_minutes ? `${sess.duration_minutes}m` : sess.duration_type}</span>
                                <span className="mx-2 text-slate-600">•</span>
                                <span className="text-slate-500">End Policy: </span>
                                <span className="text-sky-400">{sess.session_end_policy}</span>
                              </div>
                              <div className="flex items-center space-x-3">
                                <span>Started: {sess.started_at ? new Date(sess.started_at).toLocaleTimeString() : "Never"}</span>
                                <span>Ended: {sess.ended_at ? new Date(sess.ended_at).toLocaleTimeString() : sess.status}</span>
                              </div>
                            </div>
                          </div>
                        ) : (
                          <div className="text-slate-500 text-xs">
                            No trade execution history recorded for this session.
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-900/30 flex items-center justify-between text-xs font-mono">
          <div className="flex items-center space-x-2 text-slate-500 text-[11px]">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span>Strict Isolated Virtual Ledger • Zero Cross-Session Contamination</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
