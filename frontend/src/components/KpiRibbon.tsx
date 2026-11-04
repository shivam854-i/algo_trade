import React from "react";
import {
  DollarSign,
  TrendingUp,
  TrendingDown,
  Award,
  Zap,
  Target,
  Percent,
} from "lucide-react";
import { AccountSummary } from "../types";

interface KpiRibbonProps {
  account?: AccountSummary;
}

export const KpiRibbon: React.FC<KpiRibbonProps> = ({ account }) => {
  const equity = account?.total_equity ?? 100000;
  const cash =
    account?.available_cash ??
    account?.cash ??
    account?.current_cash ??
    100000;
  const botReturnPct = account?.total_return_pct ?? 0;
  const marketReturnPct = account?.market_return_pct ?? 0;
  const alphaPct = account?.alpha_vs_market_pct ?? (botReturnPct - marketReturnPct);
  const unrealizedPnL = account?.unrealized_pnl ?? 0;
  const realizedPnL = account?.realized_pnl ?? 0;
  const winRate = account?.audit?.win_rate_pct ?? 0;
  const profitFactor = account?.audit?.profit_factor ?? 0;
  const frictionPaid = account?.audit?.total_friction_paid ?? 0;

  const isReturnPos = botReturnPct >= 0;
  const isAlphaPos = alphaPct >= 0;
  const isUnrealizedPos = unrealizedPnL >= 0;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      {/* 1. Total Equity */}
      <div className="glass-panel rounded-xl p-3 flex flex-col justify-between">
        <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
          <span>Simulated Equity</span>
          <DollarSign className="w-3.5 h-3.5 text-sky-400" />
        </div>
        <div className="mt-1 text-lg font-bold font-mono text-slate-100">
          ${equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
        <div className="text-[11px] font-mono text-slate-500">
          Cash: ${cash.toLocaleString(undefined, { maximumFractionDigits: 0 })}
        </div>
      </div>

      {/* 2. Total Bot Return */}
      <div className="glass-panel rounded-xl p-3 flex flex-col justify-between">
        <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
          <span>Bot Return</span>
          {isReturnPos ? (
            <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
          ) : (
            <TrendingDown className="w-3.5 h-3.5 text-rose-400" />
          )}
        </div>
        <div
          className={`mt-1 text-lg font-bold font-mono ${
            isReturnPos ? "text-emerald-400" : "text-rose-400"
          }`}
        >
          {isReturnPos ? "+" : ""}
          {botReturnPct.toFixed(2)}%
        </div>
        <div className="text-[11px] font-mono text-slate-500">
          Mkt: {marketReturnPct >= 0 ? "+" : ""}
          {marketReturnPct.toFixed(2)}%
        </div>
      </div>

      {/* 3. Alpha vs Market */}
      <div className="glass-panel rounded-xl p-3 flex flex-col justify-between">
        <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
          <span>Alpha vs Market</span>
          <Award className="w-3.5 h-3.5 text-amber-400" />
        </div>
        <div
          className={`mt-1 text-lg font-bold font-mono ${
            isAlphaPos ? "text-emerald-400" : "text-rose-400"
          }`}
        >
          {isAlphaPos ? "+" : ""}
          {alphaPct.toFixed(2)}%
        </div>
        <div className="text-[11px] font-mono text-slate-500">
          Excess return
        </div>
      </div>

      {/* 4. Unrealized MTM PnL */}
      <div className="glass-panel rounded-xl p-3 flex flex-col justify-between">
        <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
          <span>Unrealized PnL</span>
          <Zap className="w-3.5 h-3.5 text-sky-400" />
        </div>
        <div
          className={`mt-1 text-lg font-bold font-mono ${
            isUnrealizedPos ? "text-emerald-400" : "text-rose-400"
          }`}
        >
          {isUnrealizedPos ? "+" : ""}${unrealizedPnL.toFixed(2)}
        </div>
        <div className="text-[11px] font-mono text-slate-500">
          Realized: ${realizedPnL.toFixed(2)}
        </div>
      </div>

      {/* 5. Win Rate */}
      <div className="glass-panel rounded-xl p-3 flex flex-col justify-between">
        <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
          <span>Win Rate</span>
          <Target className="w-3.5 h-3.5 text-emerald-400" />
        </div>
        <div className="mt-1 text-lg font-bold font-mono text-slate-100">
          {winRate.toFixed(1)}%
        </div>
        <div className="text-[11px] font-mono text-slate-500">
          PF: {profitFactor > 0 ? profitFactor.toFixed(2) : "N/A"}
        </div>
      </div>

      {/* 6. Statutory Friction Paid */}
      <div className="glass-panel rounded-xl p-3 flex flex-col justify-between">
        <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
          <span>Friction Paid</span>
          <Percent className="w-3.5 h-3.5 text-slate-500" />
        </div>
        <div className="mt-1 text-lg font-bold font-mono text-slate-300">
          ${frictionPaid.toFixed(2)}
        </div>
        <div className="text-[11px] font-mono text-slate-500">
          STT / Exchange fees
        </div>
      </div>
    </div>
  );
};
