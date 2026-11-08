import React from "react";
import {
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
  currency?: string;
}

export const KpiRibbon: React.FC<KpiRibbonProps> = ({ account, currency = "INR" }) => {
  const currencySym = currency === "USD" ? "$" : "₹";
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
  const exposurePct = account?.exposure_pct ?? 0;
  const exposureNotional = account?.exposure_notional ?? account?.allocated_capital ?? 0;
  const maxDrawdownPct =
    account?.max_drawdown_pct ?? account?.audit?.max_drawdown_pct ?? 0;
  const winRate = account?.audit?.win_rate_pct ?? 0;
  const profitFactor = account?.audit?.profit_factor ?? 0;
  const sharpeRatio = account?.audit?.sharpe_ratio ?? 0;
  const frictionPaid =
    account?.total_transaction_costs ??
    account?.audit?.total_transaction_costs ??
    account?.audit?.total_friction_paid ??
    0;

  const isReturnPos = botReturnPct >= 0;
  const isAlphaPos = alphaPct >= 0;
  const isUnrealizedPos = unrealizedPnL >= 0;

  const formatCurrency = (val: number, decimals: number = 2) => {
    return val.toLocaleString("en-IN", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  };

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      {/* 1. Virtual Account Balance & Cash */}
      <div className="glass-panel rounded-xl p-3 flex flex-col justify-between">
        <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
          <span>Virtual Equity (Paper)</span>
          <span className="font-bold text-sky-400 font-mono">₹</span>
        </div>
        <div className="mt-1 text-lg font-bold font-mono text-slate-100">
          {currencySym}{formatCurrency(equity, 2)}
        </div>
        <div className="text-[11px] font-mono text-slate-500">
          Cash: {currencySym}{formatCurrency(cash, 0)}
        </div>
      </div>

      {/* 2. Total Bot Return & Market Return */}
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
          {marketReturnPct.toFixed(2)}% • Sharpe: {sharpeRatio.toFixed(2)}
        </div>
      </div>

      {/* 3. Exposure & Max Drawdown */}
      <div className="glass-panel rounded-xl p-3 flex flex-col justify-between">
        <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
          <span>Exposure / Max DD</span>
          <Award className="w-3.5 h-3.5 text-amber-400" />
        </div>
        <div
          className={`mt-1 text-lg font-bold font-mono ${
            isAlphaPos ? "text-emerald-400" : "text-slate-100"
          }`}
        >
          {exposurePct.toFixed(1)}% ({currencySym}{(exposureNotional / 1000).toFixed(1)}k)
        </div>
        <div className="text-[11px] font-mono text-slate-500">
          Max DD: -{maxDrawdownPct.toFixed(2)}% • Alpha: {isAlphaPos ? "+" : ""}{alphaPct.toFixed(2)}%
        </div>
      </div>

      {/* 4. Unrealized & Realized MTM PnL */}
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
          {isUnrealizedPos ? "+" : ""}{currencySym}{formatCurrency(unrealizedPnL, 2)}
        </div>
        <div className="text-[11px] font-mono text-slate-500">
          Realized: {realizedPnL >= 0 ? "+" : ""}{currencySym}{formatCurrency(realizedPnL, 2)}
        </div>
      </div>

      {/* 5. Win Rate & Profit Factor */}
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

      {/* 6. Statutory Friction & Slippage Costs */}
      <div className="glass-panel rounded-xl p-3 flex flex-col justify-between">
        <div className="flex items-center justify-between text-slate-400 text-xs font-mono">
          <span>Transaction Costs</span>
          <Percent className="w-3.5 h-3.5 text-slate-500" />
        </div>
        <div className="mt-1 text-lg font-bold font-mono text-slate-300">
          {currencySym}{formatCurrency(frictionPaid, 2)}
        </div>
        <div className="text-[11px] font-mono text-slate-500">
          Commissions + Spread/Slippage
        </div>
      </div>
    </div>
  );
};
