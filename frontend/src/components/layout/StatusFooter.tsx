import React from "react";
import { ShieldCheck, HardDrive, Zap, Lock, Database } from "lucide-react";

export interface StatusFooterProps {
  latencyMs?: number;
  dataMode?: string;
  isTabVisible?: boolean;
}

export const StatusFooter: React.FC<StatusFooterProps> = ({
  latencyMs = 0,
  dataMode = "LIVE_MARKET_DATA",
  isTabVisible = true,
}) => {
  return (
    <footer className="glass-panel border-t border-slate-800/80 px-4 py-2.5 text-[11px] font-mono text-slate-500 flex flex-wrap items-center justify-between gap-3 bg-[#060911]/90">
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex items-center text-emerald-400 font-medium">
          <ShieldCheck className="w-3.5 h-3.5 mr-1 text-emerald-400" />
          Paper-Trading Safety Lock Active
        </span>
        <span className="hidden sm:inline text-slate-700">•</span>
        <span className="flex items-center text-slate-400">
          <Lock className="w-3 h-3 mr-1 text-cyan-400" />
          SEBI Token Bucket Limiter (5 req/s)
        </span>
        <span className="hidden sm:inline text-slate-700">•</span>
        <span className="flex items-center text-slate-400">
          <Database className="w-3 h-3 mr-1 text-indigo-400" />
          SQLite WAL Persistence
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-slate-400">
        <span className="flex items-center text-slate-400">
          <HardDrive className="w-3 h-3 mr-1 text-sky-400" />
          Heap Target &lt; 150 MB (Zero-GC)
        </span>
        <span className="hidden sm:inline text-slate-700">•</span>
        <span className="flex items-center text-slate-400">
          <Zap className="w-3 h-3 mr-1 text-amber-400" />
          {dataMode} ({latencyMs.toFixed(0)} ms)
        </span>
        <span className="hidden sm:inline text-slate-700">•</span>
        <span className="flex items-center">
          <span
            className={`w-2 h-2 rounded-full mr-1.5 ${
              isTabVisible ? "bg-emerald-400 animate-pulse" : "bg-amber-400"
            }`}
          />
          {isTabVisible ? "Telemetry Active" : "Auto-Suspended (Tab Inactive)"}
        </span>
      </div>
    </footer>
  );
};
