import React, { useState } from "react";
import {
  TrendingUp,
  TrendingDown,
  XCircle,
  AlertTriangle,
  History,
  Layers,
} from "lucide-react";
import { OpenPosition, ClosedTrade } from "../types";

interface PositionsTableProps {
  positions: OpenPosition[];
  closedTrades: ClosedTrade[];
  onClosePosition: (id: number) => void;
  onFlattenAll: () => void;
}

export const PositionsTable: React.FC<PositionsTableProps> = ({
  positions,
  closedTrades,
  onClosePosition,
  onFlattenAll,
}) => {
  const [activeTab, setActiveTab] = useState<"OPEN" | "CLOSED">("OPEN");

  // Calculate total unrealized PnL across all open positions
  const totalUnrealizedPnL = positions.reduce((acc, p) => acc + p.unrealized_pnl, 0);

  return (
    <div className="glass-panel rounded-xl p-4 flex flex-col space-y-3">
      {/* Table Header & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setActiveTab("OPEN")}
            className={`px-3 py-1.5 rounded-lg text-xs font-mono font-semibold flex items-center transition ${
              activeTab === "OPEN"
                ? "bg-sky-500/20 text-sky-400 border border-sky-500/40"
                : "bg-slate-900/60 text-slate-400 border border-slate-800 hover:text-slate-200"
            }`}
          >
            <Layers className="w-3.5 h-3.5 mr-1.5" />
            Active Positions ({positions.length})
          </button>
          <button
            onClick={() => setActiveTab("CLOSED")}
            className={`px-3 py-1.5 rounded-lg text-xs font-mono font-semibold flex items-center transition ${
              activeTab === "CLOSED"
                ? "bg-sky-500/20 text-sky-400 border border-sky-500/40"
                : "bg-slate-900/60 text-slate-400 border border-slate-800 hover:text-slate-200"
            }`}
          >
            <History className="w-3.5 h-3.5 mr-1.5" />
            Closed Trades ({closedTrades.length})
          </button>
        </div>

        {/* Total Unrealized & Flatten All */}
        {activeTab === "OPEN" && positions.length > 0 && (
          <div className="flex items-center space-x-3">
            <div className="text-xs font-mono">
              <span className="text-slate-400 mr-1.5">Unrealized MTM:</span>
              <span
                className={`font-bold ${
                  totalUnrealizedPnL >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {totalUnrealizedPnL >= 0 ? "+" : ""}${totalUnrealizedPnL.toFixed(2)}
              </span>
            </div>
            <button
              onClick={onFlattenAll}
              className="px-2.5 py-1 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40 text-xs font-mono flex items-center transition"
              title="Liquidate all open positions to cash immediately"
            >
              <AlertTriangle className="w-3.5 h-3.5 mr-1" />
              Flatten All
            </button>
          </div>
        )}
      </div>

      {/* Table Body */}
      {activeTab === "OPEN" ? (
        positions.length === 0 ? (
          <div className="py-8 text-center text-slate-500 text-xs font-mono">
            No active positions open. The autonomous bot will enter trades when neuro-causal confidence exceeds threshold, or place a manual order.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="text-slate-400 border-b border-slate-800/80">
                  <th className="py-2 px-2.5">Asset</th>
                  <th className="py-2 px-2.5">Side</th>
                  <th className="py-2 px-2.5">Entry Price</th>
                  <th className="py-2 px-2.5">Current Price</th>
                  <th className="py-2 px-2.5">Barrier Range (SL ↔ PT)</th>
                  <th className="py-2 px-2.5">Capital / Shares</th>
                  <th className="py-2 px-2.5">Unrealized PnL</th>
                  <th className="py-2 px-2.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {positions.map((pos) => {
                  const isLong = pos.direction === "LONG";
                  const isProfitable = pos.unrealized_pnl >= 0;

                  // Compute visual progress percentage between Stop and Target
                  const range = Math.abs(pos.target_price - pos.stop_price) || 1;
                  let progress = 50;
                  if (isLong) {
                    progress =
                      ((pos.current_price - pos.stop_price) / range) * 100;
                  } else {
                    progress =
                      ((pos.stop_price - pos.current_price) / range) * 100;
                  }
                  progress = Math.min(100, Math.max(0, progress));

                  return (
                    <tr
                      key={pos.id}
                      className="hover:bg-slate-900/40 transition-colors"
                    >
                      <td className="py-2.5 px-2.5 font-bold text-slate-100">
                        {pos.ticker}
                      </td>
                      <td className="py-2.5 px-2.5">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            isLong
                              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                              : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                          }`}
                        >
                          {pos.direction}
                        </span>
                      </td>
                      <td className="py-2.5 px-2.5 text-slate-300">
                        ${pos.entry_price.toFixed(2)}
                      </td>
                      <td className="py-2.5 px-2.5 font-semibold text-slate-100">
                        ${pos.current_price.toFixed(2)}
                      </td>
                      {/* Range slider visual */}
                      <td className="py-2.5 px-2.5 min-w-[140px]">
                        <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1">
                          <span className="text-rose-400">${pos.stop_price.toFixed(1)}</span>
                          <span className="text-emerald-400">${pos.target_price.toFixed(1)}</span>
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
                      <td className="py-2.5 px-2.5 text-slate-400 text-[11px]">
                        <div>${pos.allocated_capital.toFixed(2)}</div>
                        <div className="text-slate-500">{pos.shares.toFixed(4)} shares</div>
                      </td>
                      <td className="py-2.5 px-2.5">
                        <div
                          className={`font-bold flex items-center ${
                            isProfitable ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {isProfitable ? (
                            <TrendingUp className="w-3 h-3 mr-1" />
                          ) : (
                            <TrendingDown className="w-3 h-3 mr-1" />
                          )}
                          {isProfitable ? "+" : ""}${pos.unrealized_pnl.toFixed(2)}
                        </div>
                        <div
                          className={`text-[10px] ${
                            isProfitable ? "text-emerald-500" : "text-rose-500"
                          }`}
                        >
                          ({isProfitable ? "+" : ""}{pos.unrealized_return_pct.toFixed(2)}%)
                        </div>
                      </td>
                      <td className="py-2.5 px-2.5 text-right">
                        <button
                          onClick={() => onClosePosition(pos.id)}
                          className="px-2 py-1 rounded bg-slate-800 hover:bg-rose-500/20 text-slate-300 hover:text-rose-300 border border-slate-700 hover:border-rose-500/30 text-[11px] transition"
                          title="Close position at market"
                        >
                          <XCircle className="w-3.5 h-3.5 inline mr-1" />
                          Close
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      ) : closedTrades.length === 0 ? (
        <div className="py-8 text-center text-slate-500 text-xs font-mono">
          No closed trades recorded yet in this session.
        </div>
      ) : (
        <div className="overflow-x-auto max-h-64 overflow-y-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead>
              <tr className="text-slate-400 border-b border-slate-800/80">
                <th className="py-2 px-2.5">Asset</th>
                <th className="py-2 px-2.5">Side</th>
                <th className="py-2 px-2.5">Entry ➔ Exit</th>
                <th className="py-2 px-2.5">Net PnL</th>
                <th className="py-2 px-2.5">Friction</th>
                <th className="py-2 px-2.5">Exit Reason</th>
                <th className="py-2 px-2.5 text-right">Exit Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {closedTrades.map((t) => {
                const isProfitable = t.net_pnl >= 0;
                return (
                  <tr key={t.id} className="hover:bg-slate-900/40 transition-colors">
                    <td className="py-2 px-2.5 font-bold text-slate-100">{t.ticker}</td>
                    <td className="py-2 px-2.5">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          t.direction === "LONG"
                            ? "bg-emerald-500/20 text-emerald-300"
                            : "bg-rose-500/20 text-rose-300"
                        }`}
                      >
                        {t.direction}
                      </span>
                    </td>
                    <td className="py-2 px-2.5 text-slate-300">
                      ${t.entry_price.toFixed(2)} ➔ ${t.exit_price.toFixed(2)}
                    </td>
                    <td className="py-2 px-2.5">
                      <span
                        className={`font-bold ${
                          isProfitable ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {isProfitable ? "+" : ""}${t.net_pnl.toFixed(2)} ({isProfitable ? "+" : ""}{t.return_pct.toFixed(2)}%)
                      </span>
                    </td>
                    <td className="py-2 px-2.5 text-slate-400">${t.friction_fee.toFixed(2)}</td>
                    <td className="py-2 px-2.5">
                      <span className="px-1.5 py-0.5 rounded bg-slate-800/80 text-[10px] text-slate-300">
                        {t.exit_reason}
                      </span>
                    </td>
                    <td className="py-2 px-2.5 text-right text-slate-500 text-[11px]">
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
  );
};
