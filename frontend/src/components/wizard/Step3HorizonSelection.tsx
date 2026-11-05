import React from "react";
import { Check, Clock, Lightbulb } from "lucide-react";
import { HorizonType } from "./types";

interface Step3HorizonSelectionProps {
  selectedHorizon: HorizonType;
  errorMessage?: string;
  onSelectHorizon: (horizon: HorizonType) => void;
}

interface HorizonOption {
  id: HorizonType;
  title: string;
  badge: string;
  interval: string;
  holdingTime: string;
  description: string;
  frictionProfile: string;
  isRecommended?: boolean;
}

const HORIZONS: HorizonOption[] = [
  {
    id: "1h",
    title: "1 Hour (Intraday)",
    badge: "5-Minute Bars",
    interval: "5m",
    holdingTime: "1 to 4 hours",
    description: "Fast execution, sensitive to intraday momentum and microstructural order flow.",
    frictionProfile: "Higher friction drag; tight triple-barrier stops and targets.",
  },
  {
    id: "1d",
    title: "1 Day (Daily Swing)",
    badge: "15m / 1h Bars",
    interval: "15m / 1h",
    holdingTime: "1 to 5 trading days",
    description: "Balanced multi-day trends capturing macro momentum with optimal Kelly capital compounding.",
    frictionProfile: "Low-to-moderate friction; optimal risk-adjusted Net Expectancy.",
    isRecommended: true,
  },
  {
    id: "1wk",
    title: "1 Week (Macro Swing)",
    badge: "Daily (1d) Bars",
    interval: "1d",
    holdingTime: "1 to 4 weeks",
    description: "Patient multi-week regime following, macro volatility cones, and fundamental persistence.",
    frictionProfile: "Minimal transaction fee friction; wider volatility stops.",
  },
];

export const Step3HorizonSelection: React.FC<Step3HorizonSelectionProps> = ({
  selectedHorizon,
  errorMessage,
  onSelectHorizon,
}) => {
  return (
    <div className="flex flex-col space-y-4">
      <div>
        <h3 className="text-base font-bold text-slate-100 flex items-center">
          <Clock className="w-4 h-4 mr-2 text-sky-400" />
          Select Trading Horizon
        </h3>
        <p className="text-xs text-slate-400 mt-1">
          Binds the quantitative strategy parameters: feature windows, bar intervals, HMM regime lookback, and triple-barrier exit rules.
        </p>
      </div>

      {errorMessage && (
        <div className="px-3 py-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono">
          {errorMessage}
        </div>
      )}

      {/* Horizon Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {HORIZONS.map((h) => {
          const isSelected = selectedHorizon === h.id;
          return (
            <div
              key={h.id}
              onClick={() => onSelectHorizon(h.id)}
              className={`glass-panel rounded-xl p-4 border cursor-pointer transition flex flex-col justify-between ${
                isSelected
                  ? "border-sky-500/80 bg-sky-500/10 shadow-md shadow-sky-500/10"
                  : "border-slate-800/80 hover:border-slate-700 bg-slate-900/30"
              }`}
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-100 text-sm">{h.title}</span>
                  {isSelected ? (
                    <div className="w-5 h-5 rounded-full bg-sky-500 text-slate-950 flex items-center justify-center">
                      <Check className="w-3.5 h-3.5 stroke-[3]" />
                    </div>
                  ) : (
                    <div className="w-5 h-5 rounded-full border border-slate-700" />
                  )}
                </div>

                {h.isRecommended && (
                  <span className="inline-block mt-1 px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                    Recommended Default
                  </span>
                )}

                <p className="text-[11px] text-slate-400 mt-2 leading-relaxed">
                  {h.description}
                </p>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-800/60 space-y-1.5 text-[11px] font-mono">
                <div className="flex items-center justify-between text-slate-400">
                  <span>Bar Interval:</span>
                  <strong className="text-slate-200">{h.interval}</strong>
                </div>
                <div className="flex items-center justify-between text-slate-400">
                  <span>Avg Holding:</span>
                  <strong className="text-slate-200">{h.holdingTime}</strong>
                </div>
                <div className="text-[10px] text-slate-500 pt-1">
                  {h.frictionProfile}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Mandatory Educational Callout Card */}
      <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs font-mono space-y-2">
        <div className="flex items-center font-bold text-amber-300">
          <Lightbulb className="w-4 h-4 mr-2 text-amber-400 shrink-0" />
          <span>Crucial Distinction: Holding Horizon vs. Session Run Duration</span>
        </div>
        <p className="text-slate-300 text-[11px] leading-relaxed">
          • <strong>Holding Horizon (This Step)</strong>: Governs the model's predictive features, bar interval (5m vs 1h vs 1d), and expected duration trade positions are held before profit-taking or stop-loss evaluation.
        </p>
        <p className="text-slate-300 text-[11px] leading-relaxed">
          • <strong>Session Run Duration (Configured in Step 4)</strong>: Governs how long the bot process stays alive actively scanning the market.
        </p>
        <div className="p-2 rounded bg-slate-900/80 border border-slate-800 text-[10px] text-slate-400">
          💡 <em>Example: You can run a 4-hour morning session while using 1-day holding swing positions that remain open across trading sessions!</em>
        </div>
      </div>
    </div>
  );
};
