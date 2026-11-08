import React, { useState } from "react";
import {
  Cpu,
  Play,
  Pause,
  Square,
  History,
  Flame,
  AlertTriangle,
  Send,
  Zap,
} from "lucide-react";
import {
  DashboardState,
  TradingSession,
} from "../../types";

export interface TradingEngineViewProps {
  state: DashboardState | null;
  activeSession: TradingSession | null;
  onOpenWizard: () => void;
  onOpenHistory: () => void;
  onPauseSession: (sessionId: string) => Promise<any>;
  onResumeSession: (sessionId: string) => Promise<any>;
  onStopSession: (sessionId: string, reason?: string) => Promise<any>;
  onFlattenAll: () => Promise<any>;
  onPlaceOrder: (
    ticker: string,
    direction: "LONG" | "SHORT" | "AUTO",
    allocWeight?: number,
    orderType?: "MARKET" | "LIMIT",
    limitPrice?: number
  ) => Promise<void>;
  selectedTicker: string;
}

export const TradingEngineView: React.FC<TradingEngineViewProps> = ({
  state,
  activeSession,
  onOpenWizard,
  onOpenHistory,
  onPauseSession,
  onResumeSession,
  onStopSession,
  onFlattenAll,
  onPlaceOrder,
  selectedTicker,
}) => {
  const [orderSide, setOrderSide] = useState<"BUY" | "SELL">("BUY");
  const [orderQuantity, setOrderQuantity] = useState<number>(10);
  const [orderPrice, setOrderPrice] = useState<number>(0);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [orderFeedback, setOrderFeedback] = useState<{ type: "success" | "error"; msg: string } | null>(null);

  const selectedAsset = state?.assets?.[selectedTicker];
  const currPrice = selectedAsset?.current_price ?? 2500;
  const currentLimitPrice = orderPrice > 0 ? orderPrice : currPrice;

  // SEBI 1% Limit Price Protection (LPP) rule validation
  const maxBuyLimit = currPrice * 1.01;
  const minSellLimit = currPrice * 0.99;
  const isLppViolated =
    orderSide === "BUY"
      ? currentLimitPrice > maxBuyLimit
      : currentLimitPrice < minSellLimit;

  // Approximate Indian Frictions (STT 0.1%, Broker 20, Exch 0.00345%, GST 18%, Stamp Duty 0.015%)
  const orderNotional = orderQuantity * currentLimitPrice;
  const approxFriction = orderNotional * 0.0012 + 20;

  const handleOrderSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isLppViolated) {
      setOrderFeedback({
        type: "error",
        msg: `SEBI LPP Violation: For ${orderSide}, price must be within ±1.0% of market reference price (₹${currPrice.toFixed(2)})`,
      });
      return;
    }

    setIsSubmitting(true);
    setOrderFeedback(null);
    try {
      await onPlaceOrder(
        selectedTicker,
        orderSide === "BUY" ? "LONG" : "SHORT",
        10,
        "LIMIT",
        currentLimitPrice
      );
      setOrderFeedback({
        type: "success",
        msg: `Paper Limit Order submitted: ${orderSide} ${orderQuantity} ${selectedTicker} @ ₹${currentLimitPrice.toFixed(2)}`,
      });
    } catch (err: any) {
      setOrderFeedback({
        type: "error",
        msg: err.message || "Failed to submit limit order",
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const metrics = activeSession?.current_metrics || {};
  const currencySym = activeSession?.currency === "INR" ? "₹" : "₹";
  const allocatedCap = activeSession?.allocated_capital ?? 500000;
  const currentCash = Number(metrics.current_cash ?? allocatedCap);
  const investedEquity = Number(metrics.invested_equity ?? 0);
  const realizedPnL = Number(metrics.realized_pnl ?? 0);
  const unrealizedPnL = Number(metrics.unrealized_pnl ?? 0);
  const isRunning = activeSession?.status === "RUNNING";
  const isPaused = activeSession?.status === "PAUSED";

  return (
    <div className="space-y-6 font-mono">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <h2 className="text-base font-bold text-slate-100 flex items-center space-x-2">
            <Cpu className="w-5 h-5 text-cyan-400" />
            <span>AUTONOMOUS TRADING ENGINE CONTROL</span>
          </h2>
          <p className="text-xs text-slate-400">
            Lifecycle Governance • Isolated Capital Sessions • SEBI 1% Limit Price Protection
          </p>
        </div>

        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={onOpenHistory}
            className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 text-xs flex items-center space-x-1.5 transition"
          >
            <History className="w-3.5 h-3.5 text-slate-400" />
            <span>Session History Ledger</span>
          </button>
        </div>
      </div>

      {/* 1. Active Session Cockpit Card */}
      <section className="p-5 rounded-xl border border-slate-800 bg-slate-900/40 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
              <Zap className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="text-sm font-bold text-slate-100">
                  {activeSession ? activeSession.name || activeSession.id : "NO ACTIVE TRADING SESSION"}
                </h3>
                {activeSession && (
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      isRunning
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                        : isPaused
                        ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    {activeSession.status}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-400">
                {activeSession
                  ? `Jurisdiction: ${activeSession.market} • Horizon: ${activeSession.horizon} • Expiry Policy: ${activeSession.session_end_policy}`
                  : "All live order generation is currently gated. Launch a verified Indian equity trading session to deploy algorithms."}
              </p>
            </div>
          </div>

          {/* Session Action Buttons */}
          <div className="flex items-center space-x-2">
            {!activeSession ? (
              <button
                type="button"
                onClick={onOpenWizard}
                className="px-4 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs shadow-[0_0_12px_rgba(6,182,212,0.3)] transition"
              >
                Launch New Indian Session Wizard
              </button>
            ) : (
              <>
                {isRunning ? (
                  <button
                    type="button"
                    onClick={() => onPauseSession(activeSession.id)}
                    className="px-3 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 text-xs font-semibold flex items-center space-x-1.5 transition"
                  >
                    <Pause className="w-3.5 h-3.5" />
                    <span>Pause Session</span>
                  </button>
                ) : isPaused ? (
                  <button
                    type="button"
                    onClick={() => onResumeSession(activeSession.id)}
                    className="px-3 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 text-xs font-semibold flex items-center space-x-1.5 transition"
                  >
                    <Play className="w-3.5 h-3.5" />
                    <span>Resume Session</span>
                  </button>
                ) : null}

                <button
                  type="button"
                  onClick={() => onStopSession(activeSession.id, "USER_MANUAL_STOP")}
                  className="px-3 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40 text-xs font-semibold flex items-center space-x-1.5 transition"
                >
                  <Square className="w-3.5 h-3.5" />
                  <span>Stop Session</span>
                </button>
              </>
            )}
          </div>
        </div>

        {/* Telemetry Metrics Grid */}
        {activeSession && (
          <div className="grid grid-cols-2 sm:grid-cols-6 gap-3 pt-2">
            <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
              <span className="text-[10px] text-slate-500 block uppercase">Allocated Capital</span>
              <span className="text-sm font-bold text-slate-100">
                {currencySym}{Math.round(allocatedCap).toLocaleString("en-IN")}
              </span>
            </div>

            <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
              <span className="text-[10px] text-slate-500 block uppercase">Available Virtual Cash</span>
              <span className="text-sm font-bold text-cyan-400">
                {currencySym}{Math.round(currentCash).toLocaleString("en-IN")}
              </span>
            </div>

            <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
              <span className="text-[10px] text-slate-500 block uppercase">Invested Capital</span>
              <span className="text-sm font-bold text-indigo-300">
                {currencySym}{Math.round(investedEquity).toLocaleString("en-IN")}
              </span>
            </div>

            <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
              <span className="text-[10px] text-slate-500 block uppercase">Unrealized MTM</span>
              <span className={`text-sm font-bold ${unrealizedPnL >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                {unrealizedPnL >= 0 ? "+" : ""}{currencySym}{unrealizedPnL.toFixed(2)}
              </span>
            </div>

            <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
              <span className="text-[10px] text-slate-500 block uppercase">Realized PnL</span>
              <span className={`text-sm font-bold ${realizedPnL >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                {realizedPnL >= 0 ? "+" : ""}{currencySym}{realizedPnL.toFixed(2)}
              </span>
            </div>

            <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
              <span className="text-[10px] text-slate-500 block uppercase">Active Trades</span>
              <span className="text-sm font-bold text-slate-200">
                {metrics.total_trades ?? 0} ({metrics.winning_trades ?? 0} Won)
              </span>
            </div>
          </div>
        )}
      </section>

      {/* 2. Manual Limit Order Placement with SEBI 1% LPP */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-7 p-5 rounded-xl border border-slate-800 bg-slate-900/30 space-y-4">
          <div className="border-b border-slate-800/80 pb-2">
            <h3 className="text-sm font-bold text-slate-200 flex items-center space-x-2">
              <Send className="w-4 h-4 text-cyan-400" />
              <span>Manual Paper Limit Order Placement</span>
            </h3>
            <p className="text-[11px] text-slate-400">
              Strictly enforced with SEBI ±1.0% Limit Price Protection (LPP) against current reference price.
            </p>
          </div>

          <form onSubmit={handleOrderSubmit} className="space-y-4 text-xs">
            {/* Side Selection */}
            <div className="flex space-x-2">
              <button
                type="button"
                onClick={() => setOrderSide("BUY")}
                className={`flex-1 py-2 rounded-lg font-bold border transition ${
                  orderSide === "BUY"
                    ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/50 shadow-[0_0_10px_rgba(16,185,129,0.2)]"
                    : "bg-slate-950 text-slate-400 border-slate-800"
                }`}
              >
                BUY (LONG)
              </button>
              <button
                type="button"
                onClick={() => setOrderSide("SELL")}
                className={`flex-1 py-2 rounded-lg font-bold border transition ${
                  orderSide === "SELL"
                    ? "bg-rose-500/20 text-rose-300 border-rose-500/50 shadow-[0_0_10px_rgba(244,63,94,0.2)]"
                    : "bg-slate-950 text-slate-400 border-slate-800"
                }`}
              >
                SELL (SHORT)
              </button>
            </div>

            {/* Inputs: Quantity & Limit Price */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-slate-400 block mb-1">Selected Instrument</label>
                <div className="p-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-200 font-bold">
                  {selectedTicker} (Mkt: ₹{currPrice.toFixed(2)})
                </div>
              </div>

              <div>
                <label className="text-slate-400 block mb-1">Quantity (Shares)</label>
                <input
                  type="number"
                  min={1}
                  max={5000}
                  value={orderQuantity}
                  onChange={(e) => setOrderQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                  className="w-full p-2 rounded-lg bg-slate-950 border border-slate-800 text-slate-100 font-bold focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="text-slate-400 block mb-1">
                  Limit Price (₹) [Max Buy: ₹{maxBuyLimit.toFixed(2)} • Min Sell: ₹{minSellLimit.toFixed(2)}]
                </label>
                <input
                  type="number"
                  step="0.05"
                  value={currentLimitPrice}
                  onChange={(e) => setOrderPrice(parseFloat(e.target.value) || 0)}
                  className={`w-full p-2 rounded-lg bg-slate-950 border font-bold focus:outline-none ${
                    isLppViolated ? "border-rose-500 text-rose-300" : "border-slate-800 text-slate-100"
                  }`}
                />
              </div>

              <div>
                <label className="text-slate-400 block mb-1">Order Turnover (₹)</label>
                <div className="p-2 rounded-lg bg-slate-950 border border-slate-800 text-cyan-400 font-bold">
                  ₹{orderNotional.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </div>
              </div>
            </div>

            {isLppViolated && (
              <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-[11px] flex items-center space-x-1.5">
                <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
                <span>
                  LPP Violation: {orderSide} limit price cannot exceed ±1% band (₹{minSellLimit.toFixed(2)} – ₹{maxBuyLimit.toFixed(2)}).
                </span>
              </div>
            )}

            {orderFeedback && (
              <div
                className={`p-2.5 rounded-lg border text-[11px] ${
                  orderFeedback.type === "success"
                    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                    : "bg-rose-500/10 border-rose-500/30 text-rose-300"
                }`}
              >
                {orderFeedback.msg}
              </div>
            )}

            <div className="flex items-center justify-between pt-2">
              <span className="text-[11px] text-slate-500">
                Est. Indian Frictions (STT/GST): ~₹{approxFriction.toFixed(2)}
              </span>

              <button
                type="submit"
                disabled={isSubmitting || isLppViolated}
                className="px-5 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 disabled:opacity-40 text-slate-950 font-bold text-xs transition"
              >
                {isSubmitting ? "Placing Limit Order..." : `Submit ${orderSide} Limit Order`}
              </button>
            </div>
          </form>
        </div>

        {/* Emergency Kill & Safeguards */}
        <div className="lg:col-span-5 p-5 rounded-xl border border-rose-900/30 bg-rose-950/10 space-y-4">
          <div className="border-b border-rose-900/40 pb-2">
            <h3 className="text-sm font-bold text-rose-300 flex items-center space-x-2">
              <Flame className="w-4 h-4 text-rose-400" />
              <span>Autonomous Engine Circuit Breakers</span>
            </h3>
            <p className="text-[11px] text-slate-400">
              Immediate institutional capital preservation overrides.
            </p>
          </div>

          <div className="space-y-3 text-xs text-slate-300">
            <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 space-y-1">
              <span className="font-bold text-slate-200 block">SEBI Token Bucket Limiter</span>
              <p className="text-[11px] text-slate-400">
                Firm hard-ceiling capped at 5 orders/second. Prevents infinite order churn or runaway loops.
              </p>
            </div>

            <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800 space-y-1">
              <span className="font-bold text-slate-200 block">15.0% Kill Drawdown Circuit Breaker</span>
              <p className="text-[11px] text-slate-400">
                If active portfolio drawdown breaches 15%, all open positions are liquidated and engine halts.
              </p>
            </div>

            <button
              type="button"
              onClick={onFlattenAll}
              className="w-full py-2.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs uppercase tracking-wider shadow-[0_0_15px_rgba(225,29,72,0.4)] transition"
            >
              Flatten All Open Positions (Emergency)
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
