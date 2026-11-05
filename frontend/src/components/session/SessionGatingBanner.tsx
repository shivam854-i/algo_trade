import React from "react";
import { Lock, Sparkles, ArrowRight, History } from "lucide-react";

export interface SessionGatingBannerProps {
  onOpenWizard: () => void;
  onOpenHistory?: () => void;
}

export const SessionGatingBanner: React.FC<SessionGatingBannerProps> = ({
  onOpenWizard,
  onOpenHistory,
}) => {
  return (
    <div className="w-full rounded-xl bg-amber-500/10 border border-amber-500/30 p-3.5 sm:p-4 shadow-lg flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 font-mono">
      <div className="flex items-start sm:items-center space-x-3">
        <div className="w-9 h-9 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30 flex items-center justify-center shrink-0">
          <Lock className="w-5 h-5" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <h3 className="text-xs sm:text-sm font-bold text-amber-200">
              Autonomous Execution Gated: No Active Session
            </h3>
            <span className="px-2 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/40">
              GATED
            </span>
          </div>
          <p className="text-[11px] text-slate-300 mt-0.5">
            Trading execution, quantitative signal evaluation, and paper order placement require an approved trading session configuration.
          </p>
        </div>
      </div>

      <div className="flex items-center space-x-2 shrink-0">
        {onOpenHistory && (
          <button
            type="button"
            onClick={onOpenHistory}
            className="px-3.5 py-2 rounded-xl bg-slate-900/90 hover:bg-slate-800 text-slate-300 border border-slate-700/80 font-bold text-xs flex items-center space-x-1.5 transition"
            title="View past trading session history & audit ledger"
          >
            <History className="w-3.5 h-3.5" />
            <span>History</span>
          </button>
        )}
        <button
          type="button"
          onClick={onOpenWizard}
          className="px-4 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-xs flex items-center justify-center space-x-1.5 shadow-md shadow-amber-500/20 transition"
        >
          <Sparkles className="w-4 h-4 fill-current" />
          <span>Launch Setup Wizard</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
};
