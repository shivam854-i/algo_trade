import React, { useEffect, useState } from "react";
import {
  Clock,
  Radio,
  Layers,
  TrendingUp,
  TrendingDown,
} from "lucide-react";
import { TradingSession, DataFeedStatus, AccountSummary } from "../../types";
import { SessionControls } from "./SessionControls";

export interface SessionTelemetryBarProps {
  session: TradingSession | null;
  account?: AccountSummary;
  feedHealth?: DataFeedStatus;
  selectedTicker?: string;
  onSelectTicker?: (ticker: string) => void;
  onStartSession: (sessionId: string) => Promise<void>;
  onPauseSession: (sessionId: string) => Promise<void>;
  onResumeSession: (sessionId: string) => Promise<void>;
  onStopSession: (sessionId: string, reason?: string) => Promise<void>;
  onOpenWizard: () => void;
}

export const SessionTelemetryBar: React.FC<SessionTelemetryBarProps> = ({
  session,
  account,
  feedHealth,
  selectedTicker,
  onSelectTicker,
  onStartSession,
  onPauseSession,
  onResumeSession,
  onStopSession,
  onOpenWizard,
}) => {
  const [countdownSec, setCountdownSec] = useState<number | null>(
    session?.remaining_seconds ?? null
  );

  // Sync remaining seconds on session prop changes
  useEffect(() => {
    setCountdownSec(session?.remaining_seconds ?? null);
  }, [session?.remaining_seconds, session?.status]);

  // Local 1-second countdown decrementer (strictly freezes during PAUSED)
  useEffect(() => {
    if (session?.status !== "RUNNING" || countdownSec === null || countdownSec <= 0) {
      return;
    }
    const timer = setInterval(() => {
      setCountdownSec((prev) => (prev !== null && prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [session?.status, countdownSec]);

  if (!session) {
    return null;
  }

  const currencySym = session.currency === "INR" ? "₹" : "$";
  const currencyLocale = session.currency === "INR" ? "en-IN" : "en-US";
  const metrics = session.current_metrics || {};
  const currentCash = Number(metrics.current_cash ?? account?.current_cash ?? account?.cash ?? session.allocated_capital);
  const investedEquity = Number(metrics.invested_equity ?? account?.exposure_notional ?? 0);
  const unrealizedPnL = Number(metrics.unrealized_pnl ?? account?.unrealized_pnl ?? 0);
  const isUnrealizedPos = unrealizedPnL >= 0;

  const formatCountdownStr = (sec: number | null): string => {
    if (sec === null) return "Manual Stop";
    if (sec <= 0) return "00:00:00 (Expired)";
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const getStatusBadge = () => {
    switch (session.status) {
      case "RUNNING":
        return (
          <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[10px] font-bold flex items-center">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse mr-1.5" />
            RUNNING
          </span>
        );
      case "PAUSED":
        return (
          <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[10px] font-bold flex items-center">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 mr-1.5" />
            PAUSED
          </span>
        );
      case "CREATED":
        return (
          <span className="px-2 py-0.5 rounded bg-sky-500/20 text-sky-300 border border-sky-500/40 text-[10px] font-bold">
            CREATED
          </span>
        );
      case "COMPLETED":
        return (
          <span className="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/40 text-[10px] font-bold">
            COMPLETED
          </span>
        );
      case "STOPPED":
      default:
        return (
          <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 text-[10px] font-bold">
            STOPPED
          </span>
        );
    }
  };

  return (
    <div className="glass-panel rounded-xl p-3 border border-slate-800 shadow-lg flex flex-col space-y-2.5">
      {/* Top Row: Session ID, Status, Basket Chips, Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Left: Identity & Badges */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs font-bold text-slate-200">
            Session: <span className="text-sky-400">#{session.id.substring(0, 8)}</span>
          </span>
          {getStatusBadge()}
          <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-300 text-[10px] font-mono">
            {session.market}
          </span>
          <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-400 text-[10px] font-mono">
            Horizon: <strong className="text-slate-200">{session.horizon}</strong>
          </span>

          {/* Basket Chips */}
          <div className="flex items-center space-x-1 ml-1 sm:ml-2">
            <Layers className="w-3.5 h-3.5 text-slate-500" />
            {session.instruments.map((tk) => (
              <button
                key={tk}
                type="button"
                onClick={() => onSelectTicker?.(tk)}
                className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition ${
                  selectedTicker === tk
                    ? "bg-sky-500/20 text-sky-300 border border-sky-500/40 font-bold"
                    : "bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200"
                }`}
              >
                {tk}
              </button>
            ))}
          </div>
        </div>

        {/* Right: Embedded Persistent Lifecycle Controls */}
        <SessionControls
          session={session}
          openPositionsCount={account?.open_positions_count ?? 0}
          onStartSession={onStartSession}
          onPauseSession={onPauseSession}
          onResumeSession={onResumeSession}
          onStopSession={onStopSession}
          onOpenWizard={onOpenWizard}
        />
      </div>

      {/* Bottom Row: Countdown, Financial Metrics (₹/$), Regime & Feed */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 text-xs font-mono pt-2 border-t border-slate-800/60">
        {/* 1. Countdown Clock */}
        <div className="flex flex-col justify-center">
          <span className="text-slate-500 text-[10px] flex items-center">
            <Clock className="w-3 h-3 mr-1 text-sky-400" />
            Remaining Time
          </span>
          <span
            className={`font-bold mt-0.5 ${
              countdownSec !== null && countdownSec < 300
                ? "text-rose-400 animate-pulse"
                : countdownSec !== null && countdownSec < 1800
                ? "text-amber-400"
                : "text-slate-200"
            }`}
          >
            {formatCountdownStr(countdownSec)}
          </span>
        </div>

        {/* 2. Allocated Capital */}
        <div className="flex flex-col justify-center">
          <span className="text-slate-500 text-[10px]">Allocated Capital</span>
          <span className="font-bold text-slate-200 mt-0.5">
            {currencySym}
            {session.allocated_capital.toLocaleString(currencyLocale, { maximumFractionDigits: 0 })}
          </span>
        </div>

        {/* 3. Cash / Invested Equity */}
        <div className="flex flex-col justify-center">
          <span className="text-slate-500 text-[10px]">Cash / Invested</span>
          <span className="font-semibold text-slate-300 mt-0.5">
            {currencySym}
            {(currentCash / 1000).toFixed(1)}k / {currencySym}
            {(investedEquity / 1000).toFixed(1)}k
          </span>
        </div>

        {/* 4. Unrealized P&L */}
        <div className="flex flex-col justify-center">
          <span className="text-slate-500 text-[10px]">Unrealized MTM</span>
          <span
            className={`font-bold mt-0.5 flex items-center ${
              isUnrealizedPos ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {isUnrealizedPos ? (
              <TrendingUp className="w-3 h-3 mr-1" />
            ) : (
              <TrendingDown className="w-3 h-3 mr-1" />
            )}
            {isUnrealizedPos ? "+" : ""}
            {currencySym}
            {unrealizedPnL.toFixed(2)}
          </span>
        </div>

        {/* 5. Policy Tag */}
        <div className="flex flex-col justify-center">
          <span className="text-slate-500 text-[10px]">Expiry Policy</span>
          <span className="font-semibold text-purple-300 mt-0.5">
            {session.session_end_policy === "CLOSE_ALL" ? "Close All Positions" : "Keep Open (Manual)"}
          </span>
        </div>

        {/* 6. Feed & Mode Health */}
        <div className="flex flex-col justify-center">
          <span className="text-slate-500 text-[10px] flex items-center">
            <Radio className="w-3 h-3 mr-1 text-emerald-400" />
            Feed Health
          </span>
          <span className="font-semibold text-emerald-400 mt-0.5 truncate">
            {feedHealth?.data_mode || "LIVE FEED"} ({feedHealth?.average_latency_ms ?? 0}ms)
          </span>
        </div>
      </div>
    </div>
  );
};
