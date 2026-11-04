import React from "react";
import {
  Activity,
  Cpu,
  Eye,
  EyeOff,
  RefreshCw,
  Server,
} from "lucide-react";
import { BotStatus } from "../types";

interface HeaderProps {
  botStatus?: BotStatus;
  isTabVisible: boolean;
  isLoading: boolean;
  onRefresh: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  botStatus,
  isTabVisible,
  isLoading,
  onRefresh,
}) => {
  return (
    <header className="glass-panel border-b border-slate-800 px-4 py-3 flex flex-wrap items-center justify-between gap-4">
      {/* Brand & Title */}
      <div className="flex items-center space-x-3">
        <div className="w-9 h-9 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400 font-bold font-mono">
          <Activity className="w-5 h-5 text-sky-400" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-base font-bold font-mono tracking-wider text-slate-100">
              SYNAPSE<span className="text-sky-400">-TITAN</span>
            </h1>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/30 font-semibold">
              v2.0 PRO
            </span>
          </div>
          <p className="text-[11px] text-slate-400 font-mono">
            Autonomous Neuro-Causal Quant Execution Engine
          </p>
        </div>
      </div>

      {/* Telemetry & System Badges */}
      <div className="flex flex-wrap items-center gap-2.5 text-xs font-mono">
        {/* Tab Visibility / Memory Protection Badge */}
        <div
          className={`px-2.5 py-1 rounded-lg border flex items-center space-x-1.5 ${
            isTabVisible
              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
              : "bg-amber-500/10 border-amber-500/30 text-amber-400"
          }`}
          title={
            isTabVisible
              ? "Tab visible: live updates running with bounded ring buffers"
              : "Tab hidden: polling and canvas renders suspended (0 bytes/sec leak protection)"
          }
        >
          {isTabVisible ? (
            <>
              <Eye className="w-3.5 h-3.5 text-emerald-400" />
              <span>ACTIVE</span>
            </>
          ) : (
            <>
              <EyeOff className="w-3.5 h-3.5 text-amber-400" />
              <span>PROTECTED (TAB HIDDEN)</span>
            </>
          )}
        </div>

        {/* GPU / Hardware Telemetry */}
        {botStatus?.gpu_device && (
          <div className="px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 flex items-center space-x-1.5">
            <Cpu className="w-3.5 h-3.5 text-sky-400" />
            <span className="text-slate-200 font-semibold">
              {botStatus.gpu_device.replace("NVIDIA GeForce ", "")}
            </span>
            <span className="text-slate-500 text-[10px]">
              ({botStatus.precision} • {botStatus.vram_mb > 0 ? `${(botStatus.vram_mb / 1024).toFixed(1)}GB` : "CPU"})
            </span>
          </div>
        )}

        {/* Tick Count & Server Time */}
        <div className="hidden md:flex items-center space-x-2 px-2.5 py-1 rounded-lg bg-slate-900/60 border border-slate-800 text-slate-400">
          <Server className="w-3 h-3 text-slate-500" />
          <span>
            Tick <span className="text-sky-400 font-bold">#{botStatus?.tick_count ?? 0}</span>
          </span>
          <span className="text-slate-600">•</span>
          <span>{botStatus?.last_tick_time || "Syncing"}</span>
        </div>

        {/* Refresh Snapshot Button */}
        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800 transition"
          title="Force fresh snapshot sync"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-sky-400" : ""}`} />
        </button>
      </div>
    </header>
  );
};
