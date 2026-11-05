import React, { useState } from "react";
import { Coins, ShieldCheck, AlertCircle } from "lucide-react";
import { SessionCurrency } from "../../types";

interface Step5CapitalAllocationProps {
  allocatedCapital: number;
  currency: SessionCurrency;
  errorMessage?: string;
  onSetAllocatedCapital: (capital: number) => void;
}

const USD_PRESETS = [10000, 25000, 50000, 100000, 500000];
const INR_PRESETS = [50000, 100000, 500000, 1000000, 5000000];

export const Step5CapitalAllocation: React.FC<Step5CapitalAllocationProps> = ({
  allocatedCapital,
  currency,
  errorMessage,
  onSetAllocatedCapital,
}) => {
  const [inputValue, setInputValue] = useState<string>(
    allocatedCapital ? String(allocatedCapital) : "50000"
  );

  const presets = currency === "INR" ? INR_PRESETS : USD_PRESETS;
  const currencySymbol = currency === "INR" ? "₹" : "$";

  const handleInputChange = (val: string) => {
    setInputValue(val);
    const parsed = parseFloat(val);
    if (!isNaN(parsed)) {
      onSetAllocatedCapital(parsed);
    }
  };

  const handlePresetClick = (amount: number) => {
    setInputValue(String(amount));
    onSetAllocatedCapital(amount);
  };

  const isOutOfRange = allocatedCapital < 1000 || allocatedCapital > 10000000;

  return (
    <div className="flex flex-col space-y-5">
      <div>
        <h3 className="text-base font-bold text-slate-100 flex items-center">
          <Coins className="w-4 h-4 mr-2 text-sky-400" />
          Virtual Capital Allocation
        </h3>
        <p className="text-xs text-slate-400 mt-1">
          Allocate simulated paper trading capital for this session. Fractional Kelly and HRP risk sizing will scale as a proportion of this starting balance.
        </p>
      </div>

      {errorMessage && (
        <div className="px-3 py-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Main Capital Input */}
      <div className="glass-panel rounded-xl p-5 border border-slate-800 space-y-4">
        <label className="text-xs font-mono text-slate-400">
          Allocated Paper Capital ({currency})
        </label>

        <div className="relative flex items-center">
          <span className="absolute left-4 font-mono font-bold text-xl text-slate-400 select-none">
            {currencySymbol}
          </span>
          <input
            type="number"
            min="1000"
            max="10000000"
            step="1000"
            value={inputValue}
            onChange={(e) => handleInputChange(e.target.value)}
            className={`w-full bg-slate-900 border rounded-xl pl-10 pr-4 py-3 text-xl font-mono font-bold text-slate-100 focus:outline-none transition ${
              isOutOfRange
                ? "border-rose-500/80 focus:border-rose-400"
                : "border-slate-700 focus:border-sky-500"
            }`}
          />
        </div>

        {/* Quick presets chips */}
        <div className="flex flex-wrap items-center gap-2 pt-1 font-mono text-xs">
          <span className="text-slate-500 text-[11px] mr-1">Quick Presets:</span>
          {presets.map((amt) => {
            const isSelected = allocatedCapital === amt;
            return (
              <button
                key={amt}
                type="button"
                onClick={() => handlePresetClick(amt)}
                className={`px-3 py-1.5 rounded-lg border transition ${
                  isSelected
                    ? "bg-sky-500/20 text-sky-300 border-sky-500/40 font-bold"
                    : "bg-slate-900 text-slate-400 border-slate-800 hover:border-slate-700 hover:text-slate-200"
                }`}
              >
                {`${currencySymbol}${amt.toLocaleString()}`}
              </button>
            );
          })}
        </div>

        {/* Inline boundary guidance */}
        <div className="flex items-center justify-between text-[11px] font-mono text-slate-500 pt-1">
          <span>{`Min: ${currencySymbol}1,000`}</span>
          <span>{`Max: ${currencySymbol}10,000,000`}</span>
        </div>
      </div>

      {/* Virtual Isolation & Invariance Callout */}
      <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2 text-xs font-mono">
        <div className="flex items-center text-emerald-400 font-bold">
          <ShieldCheck className="w-4 h-4 mr-1.5 shrink-0" />
          <span>Strict Paper-Trading Isolation & Invariance Guarantee</span>
        </div>
        <p className="text-slate-400 text-[11px] leading-relaxed">
          • All trading, capital, orders, and positions remain 100% virtual simulated paper funds.
        </p>
        <p className="text-slate-400 text-[11px] leading-relaxed">
          • <strong>Prediction Invariant:</strong> Allocating {currencySymbol}10k vs {currencySymbol}1M changes position size (shares traded) but will never alter the underlying quantitative model predictions or directional signals.
        </p>
      </div>
    </div>
  );
};
