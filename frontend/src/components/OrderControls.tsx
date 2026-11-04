import React, { useState } from "react";
import {
  Play,
  Pause,
  Clock,
  RotateCcw,
  Zap,
  ArrowUpRight,
  ArrowDownRight,
  Trash2,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";
import { BotStatus, PendingOrder } from "../types";

interface OrderControlsProps {
  selectedTicker: string;
  botStatus?: BotStatus;
  availableCash: number;
  currentPrice: number;
  pendingOrders: PendingOrder[];
  onPlaceOrder: (
    ticker: string,
    direction: "LONG" | "SHORT",
    allocWeight?: number,
    orderType?: "MARKET" | "LIMIT",
    limitPrice?: number,
    targetPrice?: number,
    stopPrice?: number
  ) => Promise<void>;
  onCancelPendingOrder: (orderId: string) => Promise<void>;
  onToggleBot: () => Promise<void>;
  onToggleMarketHours: () => Promise<void>;
  onStepTick: (shockPct?: number) => Promise<void>;
  onResetAccount: () => Promise<void>;
}

export const OrderControls: React.FC<OrderControlsProps> = ({
  selectedTicker,
  botStatus,
  availableCash,
  currentPrice,
  pendingOrders,
  onPlaceOrder,
  onCancelPendingOrder,
  onToggleBot,
  onToggleMarketHours,
  onStepTick,
  onResetAccount,
}) => {
  const [direction, setDirection] = useState<"LONG" | "SHORT">("LONG");
  const [allocWeight, setAllocWeight] = useState<number>(10);
  const [orderType, setOrderType] = useState<"MARKET" | "LIMIT">("MARKET");
  const [limitPrice, setLimitPrice] = useState<string>(
    currentPrice > 0 ? currentPrice.toString() : ""
  );
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [orderFeedback, setOrderFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const approxCapital = (availableCash * allocWeight) / 100;
  const approxShares =
    currentPrice > 0 ? (approxCapital / currentPrice).toFixed(4) : "0";

  const handleSubmitOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setOrderFeedback(null);

    try {
      const parsedLimit =
        orderType === "LIMIT" && limitPrice && !isNaN(parseFloat(limitPrice))
          ? parseFloat(limitPrice)
          : undefined;
      if (orderType === "LIMIT" && (parsedLimit === undefined || parsedLimit <= 0)) {
        throw new Error("Please enter a valid limit price greater than 0");
      }
      await onPlaceOrder(
        selectedTicker,
        direction,
        allocWeight,
        orderType,
        parsedLimit,
        undefined,
        undefined
      );
      setOrderFeedback({
        type: "success",
        message: `${direction} order submitted for ${selectedTicker} ($${approxCapital.toLocaleString(
          undefined,
          { maximumFractionDigits: 0 }
        )})`,
      });
      setTimeout(() => setOrderFeedback(null), 4000);
    } catch (err) {
      setOrderFeedback({
        type: "error",
        message: err instanceof Error ? err.message : "Order placement failed",
      });
      setTimeout(() => setOrderFeedback(null), 6000);
    } finally {
      setIsSubmitting(false);
    }
  };

  const isRunning = botStatus?.is_running ?? true;
  const enforceMarketHours = botStatus?.enforce_market_hours ?? true;

  return (
    <div className="glass-panel rounded-xl p-4 flex flex-col space-y-4">
      {/* Bot Controls & Simulation Mode Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div className="flex items-center space-x-2">
          {/* Autonomous Bot Running Toggle */}
          <button
            onClick={onToggleBot}
            className={`px-3 py-1.5 rounded-lg text-xs font-mono font-semibold flex items-center transition ${
              isRunning
                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/30"
                : "bg-amber-500/20 text-amber-300 border border-amber-500/40 hover:bg-amber-500/30"
            }`}
          >
            {isRunning ? (
              <>
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse mr-2" />
                <Play className="w-3.5 h-3.5 mr-1" />
                Auto-Bot: RUNNING
              </>
            ) : (
              <>
                <Pause className="w-3.5 h-3.5 mr-1 text-amber-400" />
                Auto-Bot: PAUSED
              </>
            )}
          </button>

          {/* Market Hours Strict vs 24/7 Sandbox Toggle */}
          <button
            onClick={onToggleMarketHours}
            className={`px-3 py-1.5 rounded-lg text-xs font-mono font-semibold flex items-center transition ${
              enforceMarketHours
                ? "bg-slate-900 text-sky-400 border border-sky-500/30 hover:border-sky-500/60"
                : "bg-purple-500/20 text-purple-300 border border-purple-500/40 hover:bg-purple-500/30"
            }`}
            title="Toggle between strict exchange session schedule and 24/7 sandbox simulation"
          >
            <Clock className="w-3.5 h-3.5 mr-1.5" />
            {enforceMarketHours ? "Strict Exchange Hours" : "24/7 Sandbox Mode"}
          </button>
        </div>

        {/* Step Simulation Tick */}
        <div className="flex items-center space-x-1.5">
          <button
            onClick={() => onStepTick()}
            className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-mono flex items-center transition"
            title="Advance market simulation by 1 tick"
          >
            <Zap className="w-3.5 h-3.5 mr-1 text-sky-400" />
            Step Tick
          </button>
          <button
            onClick={onResetAccount}
            className="p-1.5 rounded-lg bg-slate-900 hover:bg-rose-500/20 text-slate-400 hover:text-rose-400 border border-slate-800 transition"
            title="Reset simulation account to $100,000.00"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Manual Order Placement Ticket */}
      <form onSubmit={handleSubmitOrder} className="space-y-3">
        <div className="flex items-center justify-between text-xs font-mono">
          <span className="text-slate-300 font-bold flex items-center">
            Order Ticket:{" "}
            <span className="text-sky-400 ml-1.5 text-sm">{selectedTicker}</span>
          </span>
          <span className="text-slate-400">
            Available Cash:{" "}
            <span className="text-slate-200 font-semibold">
              ${availableCash.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </span>
          </span>
        </div>

        {/* Direction Tabs (BUY vs SELL) */}
        <div className="grid grid-cols-2 gap-2 font-mono">
          <button
            type="button"
            onClick={() => setDirection("LONG")}
            className={`py-2 rounded-lg font-bold text-xs flex items-center justify-center transition ${
              direction === "LONG"
                ? "bg-emerald-500 text-slate-950 shadow-[0_0_12px_rgba(16,185,129,0.3)]"
                : "bg-slate-900 text-slate-400 border border-slate-800 hover:text-slate-200"
            }`}
          >
            <ArrowUpRight className="w-4 h-4 mr-1" />
            BUY / LONG
          </button>
          <button
            type="button"
            onClick={() => setDirection("SHORT")}
            className={`py-2 rounded-lg font-bold text-xs flex items-center justify-center transition ${
              direction === "SHORT"
                ? "bg-rose-500 text-slate-950 shadow-[0_0_12px_rgba(244,63,94,0.3)]"
                : "bg-slate-900 text-slate-400 border border-slate-800 hover:text-slate-200"
            }`}
          >
            <ArrowDownRight className="w-4 h-4 mr-1" />
            SELL / SHORT
          </button>
        </div>

        {/* Capital Allocation Slider */}
        <div className="space-y-1 font-mono text-xs">
          <div className="flex items-center justify-between text-slate-400">
            <span>Capital Allocation</span>
            <span className="text-sky-400 font-bold">
              {allocWeight}% (~${approxCapital.toLocaleString(undefined, { maximumFractionDigits: 0 })},{" "}
              {approxShares} shares)
            </span>
          </div>
          <input
            type="range"
            min="2"
            max="50"
            step="1"
            value={allocWeight}
            onChange={(e) => setAllocWeight(Number(e.target.value))}
            className="w-full accent-sky-400 bg-slate-800 h-1.5 rounded-lg cursor-pointer"
          />
        </div>

        {/* Order Type Toggle */}
        <div className="flex items-center space-x-3 text-xs font-mono">
          <label className="flex items-center space-x-1.5 cursor-pointer text-slate-300">
            <input
              type="radio"
              name="orderType"
              value="MARKET"
              checked={orderType === "MARKET"}
              onChange={() => setOrderType("MARKET")}
              className="accent-sky-400"
            />
            <span>Market Order</span>
          </label>
          <label className="flex items-center space-x-1.5 cursor-pointer text-slate-300">
            <input
              type="radio"
              name="orderType"
              value="LIMIT"
              checked={orderType === "LIMIT"}
              onChange={() => setOrderType("LIMIT")}
              className="accent-sky-400"
            />
            <span>Limit Order</span>
          </label>
          {orderType === "LIMIT" && (
            <input
              type="number"
              step="any"
              value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)}
              placeholder="Limit Price"
              className="bg-slate-950 border border-slate-800 rounded px-2 py-0.5 text-xs font-mono w-28 text-slate-100"
            />
          )}
        </div>

        {/* Submit Button */}
        <button
          type="submit"
          disabled={isSubmitting}
          className={`w-full py-2 rounded-lg font-mono font-bold text-xs tracking-wider transition ${
            direction === "LONG"
              ? "bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40"
              : "bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40"
          } ${isSubmitting ? "opacity-50 cursor-wait" : ""}`}
        >
          {isSubmitting ? "SUBMITTING..." : `EXECUTE ${direction} ${selectedTicker}`}
        </button>

        {/* Order Feedback Alert */}
        {orderFeedback && (
          <div
            className={`p-2 rounded-lg text-xs font-mono flex items-start space-x-2 ${
              orderFeedback.type === "success"
                ? "bg-emerald-500/10 border border-emerald-500/30 text-emerald-300"
                : "bg-rose-500/10 border border-rose-500/30 text-rose-300"
            }`}
          >
            {orderFeedback.type === "success" ? (
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400 mt-0.5" />
            ) : (
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-400 mt-0.5" />
            )}
            <span>{orderFeedback.message}</span>
          </div>
        )}
      </form>

      {/* Pending Orders Queue Manager */}
      <div className="border-t border-slate-800 pt-3 space-y-2">
        <div className="flex items-center justify-between text-xs font-mono">
          <span className="font-bold text-slate-300 flex items-center">
            <Clock className="w-3.5 h-3.5 mr-1.5 text-amber-400" />
            Pre-Market Pending Orders ({pendingOrders.length})
          </span>
          <span className="text-[10px] text-slate-500">
            Auto-executes on market open
          </span>
        </div>

        {pendingOrders.length === 0 ? (
          <div className="py-3 text-center text-slate-600 text-[11px] font-mono">
            No pending orders waiting for market open.
          </div>
        ) : (
          <div className="space-y-1.5 max-h-36 overflow-y-auto">
            {pendingOrders.map((ord) => (
              <div
                key={ord.order_id}
                className="bg-slate-950/70 border border-slate-800 rounded p-2 flex items-center justify-between text-xs font-mono"
              >
                <div className="flex items-center space-x-2">
                  <span
                    className={`px-1 py-0.5 rounded text-[10px] font-bold ${
                      ord.direction === "LONG"
                        ? "bg-emerald-500/20 text-emerald-300"
                        : "bg-rose-500/20 text-rose-300"
                    }`}
                  >
                    {ord.direction}
                  </span>
                  <span className="font-bold text-slate-200">{ord.ticker}</span>
                  <span className="text-slate-400 text-[11px]">
                    {ord.shares} shs
                  </span>
                  <span className="px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 text-[10px]">
                    {ord.status}
                  </span>
                </div>

                <button
                  onClick={() => onCancelPendingOrder(ord.order_id)}
                  className="p-1 rounded bg-slate-900 hover:bg-rose-500/20 text-slate-400 hover:text-rose-400 transition"
                  title="Cancel pre-market order"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
