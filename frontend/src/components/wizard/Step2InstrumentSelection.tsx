import React, { useState } from "react";
import {
  Search,
  Plus,
  X,
  Sparkles,
  Layers,
  AlertCircle,
  Brain,
  CheckCircle2,
  TrendingUp,
  Percent,
} from "lucide-react";
import { MarketType } from "./types";
import { CandidateEvaluation } from "../../types";
import { MARKET_CONFIGS } from "./useWizardState";

interface Step2InstrumentSelectionProps {
  market: MarketType;
  instruments: string[];
  recommendationRationale?: string;
  recommendationEvaluations?: Record<string, CandidateEvaluation>;
  isRecommending: boolean;
  recommendationError?: string | null;
  errorMessage?: string;
  onAddInstrument: (ticker: string) => void;
  onRemoveInstrument: (ticker: string) => void;
  onRequestRecommendations: () => void;
}

export const Step2InstrumentSelection: React.FC<Step2InstrumentSelectionProps> = ({
  market,
  instruments,
  recommendationRationale,
  recommendationEvaluations,
  isRecommending,
  recommendationError,
  errorMessage,
  onAddInstrument,
  onRemoveInstrument,
  onRequestRecommendations,
}) => {
  const [searchInput, setSearchInput] = useState<string>("");
  const presets = MARKET_CONFIGS[market as keyof typeof MARKET_CONFIGS]?.defaultTickers ?? [];

  const handleManualAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchInput.trim()) return;
    onAddInstrument(searchInput.trim());
    setSearchInput("");
  };

  return (
    <div className="flex flex-col space-y-4">
      {/* Step Header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-base font-bold text-slate-100 flex items-center">
            <Layers className="w-4 h-4 mr-2 text-sky-400" />
            Approved Instrument Basket
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            Specify 1 to 20 instruments. The bot is strictly restricted to this universe and cannot open trades outside it.
          </p>
        </div>

        {/* Auto-select button */}
        <button
          type="button"
          onClick={onRequestRecommendations}
          disabled={isRecommending}
          className="px-3.5 py-1.5 rounded-lg bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-300 border border-indigo-500/40 text-xs font-mono font-semibold flex items-center space-x-1.5 shadow-md shadow-indigo-500/10 transition disabled:opacity-50"
        >
          <Sparkles className="w-3.5 h-3.5 fill-current text-indigo-400" />
          <span>{isRecommending ? "Evaluating Quant Gates..." : "Auto-select for me"}</span>
        </button>
      </div>

      {errorMessage && (
        <div className="px-3 py-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{errorMessage}</span>
        </div>
      )}

      {recommendationError && (
        <div className="px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-amber-400" />
          <span>{recommendationError}</span>
        </div>
      )}

      {/* Manual Search & Add Form */}
      <form onSubmit={handleManualAdd} className="flex items-center space-x-2">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder={`Enter symbol (e.g. ${presets[0] || "TICKER"})`}
            className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-9 pr-3 py-2 text-xs font-mono text-slate-100 placeholder-slate-600 focus:outline-none focus:border-sky-500"
          />
        </div>
        <button
          type="submit"
          className="px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-mono font-semibold flex items-center space-x-1 border border-slate-700"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Add</span>
        </button>
      </form>

      {/* Quick Add Presets */}
      {presets.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs font-mono">
          <span className="text-slate-500 text-[11px] mr-1">Quick Presets:</span>
          {presets.map((tk) => {
            const isAdded = instruments.includes(tk);
            return (
              <button
                key={tk}
                type="button"
                onClick={() => (isAdded ? onRemoveInstrument(tk) : onAddInstrument(tk))}
                className={`px-2 py-0.5 rounded text-[11px] border transition ${
                  isAdded
                    ? "bg-sky-500/20 text-sky-300 border-sky-500/40"
                    : "bg-slate-900/60 text-slate-400 border-slate-800 hover:border-slate-700 hover:text-slate-300"
                }`}
              >
                {tk} {isAdded ? "✓" : "+"}
              </button>
            );
          })}
        </div>
      )}

      {/* Selected Basket Chips Container */}
      <div className="glass-panel rounded-xl p-3.5 border border-slate-800">
        <div className="flex items-center justify-between text-xs font-mono pb-2.5 border-b border-slate-800/80 mb-3">
          <span className="text-slate-400">
            Selected Basket: <strong className="text-slate-200">{instruments.length}</strong> / 20 symbols
          </span>
          <span className="text-[11px] text-slate-500">
            {instruments.length === 0 ? "Empty basket" : "Enforced execution universe"}
          </span>
        </div>

        {instruments.length === 0 ? (
          <div className="py-6 text-center text-slate-500 text-xs font-mono">
            No instruments selected. Click "Auto-select for me" or add symbols above.
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {instruments.map((ticker) => {
              const evalInfo = recommendationEvaluations?.[ticker];
              return (
                <div
                  key={ticker}
                  className="px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-slate-200 text-xs font-mono flex items-center space-x-2 shadow-sm"
                >
                  <span className="font-bold text-sky-300">{ticker}</span>
                  {evalInfo && (
                    <span
                      className="text-[10px] text-emerald-400 font-normal"
                      title={`ADV: ${evalInfo.adv_currency}${evalInfo.adv.toLocaleString()} • Spread: ${evalInfo.spread_bps}bps`}
                    >
                      {`(Q: ${Math.round(evalInfo.data_quality_score * 100)}%)`}
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => onRemoveInstrument(ticker)}
                    className="p-0.5 rounded hover:bg-slate-800 text-slate-400 hover:text-rose-400 transition"
                    aria-label={`Remove ${ticker}`}
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Quantitative Auto-Selection Rationale Box */}
      {recommendationRationale && (
        <div className="p-3.5 rounded-xl bg-indigo-950/20 border border-indigo-500/30 text-xs font-mono space-y-2">
          <div className="flex items-center text-indigo-300 font-bold">
            <Brain className="w-4 h-4 mr-1.5 text-indigo-400" />
            <span>Quantitative Selection Rationale (UniverseSelector)</span>
          </div>
          <p className="text-slate-300 leading-relaxed text-[11px]">
            {recommendationRationale}
          </p>
          <div className="flex flex-wrap gap-2 pt-1 text-[10px] text-slate-400">
            <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-emerald-400 flex items-center">
              <CheckCircle2 className="w-3 h-3 mr-1" /> Data Quality ≥ 90%
            </span>
            <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-sky-400 flex items-center">
              <TrendingUp className="w-3 h-3 mr-1" /> Liquidity ADV Gate Passed
            </span>
            <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-purple-400 flex items-center">
              <Percent className="w-3 h-3 mr-1" /> Spread ≤ 25 bps
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
