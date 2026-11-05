import React from "react";
import {
  CheckCircle2,
  Edit3,
  Globe,
  Layers,
  Clock,
  Timer,
  Coins,
  ShieldAlert,
  Lock,
  Tag,
} from "lucide-react";
import { WizardFormState, WizardStepId } from "./types";

interface Step6ConfirmationProps {
  state: WizardFormState;
  errorMessage?: string | null;
  onJumpToStep: (step: WizardStepId) => void;
  onSetSessionName: (name: string) => void;
}

export const Step6Confirmation: React.FC<Step6ConfirmationProps> = ({
  state,
  errorMessage,
  onJumpToStep,
  onSetSessionName,
}) => {
  const currencySym = state.currency === "INR" ? "₹" : "$";

  const formatDurationDisplay = () => {
    if (state.durationType === "MANUAL_STOP") {
      return "Manual Stop (No automated expiry)";
    }
    if (state.durationType === "FIXED") {
      const mins = state.durationPresetMinutes ?? 240;
      const hrs = (mins / 60).toFixed(mins % 60 === 0 ? 0 : 1);
      return `${hrs} Hours (${mins} min)`;
    }
    const mins = state.customDurationMinutes ?? 60;
    return `${mins} Minutes`;
  };

  const formatHorizonDisplay = () => {
    switch (state.horizon) {
      case "1h":
        return "1 Hour (Intraday Momentum / 5m bars)";
      case "1d":
        return "1 Day (Daily Swing / 15m & 1h bars)";
      case "1wk":
        return "1 Week (Macro Position / Daily bars)";
      default:
        return state.horizon;
    }
  };

  return (
    <div className="flex flex-col space-y-4">
      <div>
        <h3 className="text-base font-bold text-slate-100 flex items-center">
          <CheckCircle2 className="w-4 h-4 mr-2 text-emerald-400" />
          Review Session Parameters & Launch
        </h3>
        <p className="text-xs text-slate-400 mt-1">
          Verify all configuration parameters before confirming. You can jump directly to any step to make modifications.
        </p>
      </div>

      {errorMessage && (
        <div className="px-3 py-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono">
          {errorMessage}
        </div>
      )}

      {/* Session Name Customizer */}
      <div className="glass-panel rounded-xl p-3.5 border border-slate-800 space-y-2">
        <label className="text-xs font-mono text-slate-400 flex items-center">
          <Tag className="w-3.5 h-3.5 mr-1.5 text-sky-400" />
          Session Name (Optional)
        </label>
        <input
          type="text"
          value={state.sessionName}
          onChange={(e) => onSetSessionName(e.target.value)}
          placeholder={`${state.market} - ${state.horizon.toUpperCase()} Trading Session`}
          maxLength={120}
          className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-500"
        />
      </div>

      {/* Summary Parameter Grid */}
      <div className="glass-panel rounded-xl p-4 border border-slate-800 space-y-3 font-mono text-xs">
        {/* 1. Market Jurisdiction */}
        <div className="flex items-center justify-between pb-2.5 border-b border-slate-800/80">
          <div className="flex items-center space-x-2 text-slate-400">
            <Globe className="w-4 h-4 text-sky-400" />
            <span>Market Jurisdiction:</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="font-bold text-slate-200">{state.market}</span>
            <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-900 border border-slate-800 text-slate-400">
              {state.currency}
            </span>
            <button
              type="button"
              onClick={() => onJumpToStep(1)}
              className="text-sky-400 hover:text-sky-300 p-1 flex items-center text-[11px]"
              aria-label="Edit Market"
            >
              <Edit3 className="w-3 h-3 mr-0.5" />
              Edit
            </button>
          </div>
        </div>

        {/* 2. Approved Basket */}
        <div className="flex items-start justify-between pb-2.5 border-b border-slate-800/80">
          <div className="flex items-center space-x-2 text-slate-400 pt-1">
            <Layers className="w-4 h-4 text-sky-400" />
            <span>Approved Basket:</span>
          </div>
          <div className="flex flex-col items-end space-y-1">
            <div className="flex flex-wrap gap-1 justify-end max-w-xs">
              {state.instruments.map((tk) => (
                <span
                  key={tk}
                  className="px-1.5 py-0.5 rounded text-[10px] bg-sky-500/15 border border-sky-500/30 text-sky-300 font-bold"
                >
                  {tk}
                </span>
              ))}
            </div>
            <div className="flex items-center space-x-2">
              <span className="text-[10px] text-slate-500">
                ({state.instruments.length} symbols locked)
              </span>
              <button
                type="button"
                onClick={() => onJumpToStep(2)}
                className="text-sky-400 hover:text-sky-300 p-1 flex items-center text-[11px]"
                aria-label="Edit Basket"
              >
                <Edit3 className="w-3 h-3 mr-0.5" />
                Edit
              </button>
            </div>
          </div>
        </div>

        {/* 3. Trading Horizon */}
        <div className="flex items-center justify-between pb-2.5 border-b border-slate-800/80">
          <div className="flex items-center space-x-2 text-slate-400">
            <Clock className="w-4 h-4 text-sky-400" />
            <span>Trading Horizon:</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="font-bold text-slate-200">{formatHorizonDisplay()}</span>
            <button
              type="button"
              onClick={() => onJumpToStep(3)}
              className="text-sky-400 hover:text-sky-300 p-1 flex items-center text-[11px]"
              aria-label="Edit Horizon"
            >
              <Edit3 className="w-3 h-3 mr-0.5" />
              Edit
            </button>
          </div>
        </div>

        {/* 4. Duration & End Policy */}
        <div className="flex items-center justify-between pb-2.5 border-b border-slate-800/80">
          <div className="flex items-center space-x-2 text-slate-400">
            <Timer className="w-4 h-4 text-sky-400" />
            <span>Duration & Policy:</span>
          </div>
          <div className="flex items-center space-x-2">
            <div className="flex items-center space-x-1.5">
              <span className="font-bold text-slate-200">{formatDurationDisplay()}</span>
              <span className="text-slate-600">•</span>
              <span
                className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                  state.sessionEndPolicy === "CLOSE_ALL"
                    ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                    : "bg-sky-500/20 text-sky-300 border border-sky-500/40"
                }`}
              >
                {state.sessionEndPolicy}
              </span>
            </div>
            <button
              type="button"
              onClick={() => onJumpToStep(4)}
              className="text-sky-400 hover:text-sky-300 p-1 flex items-center text-[11px]"
              aria-label="Edit Duration"
            >
              <Edit3 className="w-3 h-3 mr-0.5" />
              Edit
            </button>
          </div>
        </div>

        {/* 5. Virtual Capital Allocation */}
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2 text-slate-400">
            <Coins className="w-4 h-4 text-sky-400" />
            <span>Allocated Capital:</span>
          </div>
          <div className="flex items-center space-x-2">
            <span className="font-bold text-emerald-400 text-sm">
              {`${currencySym}${Number(state.allocatedCapital).toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })} ${state.currency}`}
            </span>
            <button
              type="button"
              onClick={() => onJumpToStep(5)}
              className="text-sky-400 hover:text-sky-300 p-1 flex items-center text-[11px]"
              aria-label="Edit Capital"
            >
              <Edit3 className="w-3 h-3 mr-0.5" />
              Edit
            </button>
          </div>
        </div>
      </div>

      {/* Confirmation Policy Notice */}
      <div className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 text-xs font-mono space-y-1.5 text-slate-400">
        <div className="flex items-center text-slate-200 font-bold">
          {state.sessionEndPolicy === "CLOSE_ALL" ? (
            <ShieldAlert className="w-4 h-4 mr-1.5 text-purple-400" />
          ) : (
            <Lock className="w-4 h-4 mr-1.5 text-sky-400" />
          )}
          <span>Policy Impact Notice: {state.sessionEndPolicy}</span>
        </div>
        <p className="text-[11px] leading-relaxed">
          {state.sessionEndPolicy === "CLOSE_ALL"
            ? "When duration elapses or upon manual STOP, all open positions will be flattened at current market price and liquidated back to your virtual cash balance."
            : "When duration elapses, automated new entries will halt, but open positions remain active in your ledger for manual execution."}
        </p>
      </div>
    </div>
  );
};
