import React, { useEffect, useState } from "react";
import {
  Activity,
  Cpu,
  RefreshCw,
  ShieldCheck,
  ShieldAlert,
  Flame,
  LayoutDashboard,
  LineChart,
  Radar,
  Wallet,
  Layers,
  FlaskConical,
  TrendingUp,
  Settings,
  Clock,
  Sparkles,
} from "lucide-react";
import { NavigationTab, BotStatus, AccountSummary } from "../../types";

export interface NavbarProps {
  activeTab: NavigationTab;
  onTabChange: (tab: NavigationTab) => void;
  botStatus?: BotStatus;
  account?: AccountSummary;
  isLoading: boolean;
  onRefresh: () => void;
  onEmergencyKill?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onTabChange,
  botStatus,
  account,
  isLoading,
  onRefresh,
  onEmergencyKill,
}) => {
  const [istTime, setIstTime] = useState<string>("");

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const istString = now.toLocaleTimeString("en-IN", {
        timeZone: "Asia/Kolkata",
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
      setIstTime(`${istString} IST`);
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const totalEquity = account?.total_equity ?? account?.cash ?? 500000;
  const isEmergencyActive = botStatus?.is_running;

  const NAV_ITEMS: { id: NavigationTab; label: string; icon: React.ReactNode }[] = [
    { id: "overview", label: "Overview", icon: <LayoutDashboard className="w-3.5 h-3.5" /> },
    { id: "market-intelligence", label: "Market Intel", icon: <LineChart className="w-3.5 h-3.5" /> },
    { id: "scanner", label: "Quant Scanner", icon: <Radar className="w-3.5 h-3.5" /> },
    { id: "trading-engine", label: "Trading Engine", icon: <Cpu className="w-3.5 h-3.5" /> },
    { id: "portfolio", label: "Portfolio", icon: <Wallet className="w-3.5 h-3.5" /> },
    { id: "positions-orders", label: "Positions & Orders", icon: <Layers className="w-3.5 h-3.5" /> },
    { id: "strategy-lab", label: "Strategy Lab", icon: <FlaskConical className="w-3.5 h-3.5" /> },
    { id: "risk-management", label: "Risk Governance", icon: <ShieldAlert className="w-3.5 h-3.5" /> },
    { id: "analytics", label: "Analytics", icon: <TrendingUp className="w-3.5 h-3.5" /> },
    { id: "monitoring", label: "Monitoring", icon: <Activity className="w-3.5 h-3.5" /> },
    { id: "settings", label: "Settings", icon: <Settings className="w-3.5 h-3.5" /> },
  ];

  return (
    <header className="sticky top-0 z-50 glass-panel border-b border-slate-800 bg-[#060911]/95 backdrop-blur-md">
      {/* Top Cockpit Header Bar */}
      <div className="px-4 py-2.5 flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/60">
        {/* Brand & Market Identity */}
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 font-bold font-mono shadow-[0_0_12px_rgba(6,182,212,0.15)]">
            <Sparkles className="w-4 h-4 text-cyan-400" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-sm font-bold font-mono tracking-wider text-slate-100">
                SYNAPSE<span className="text-cyan-400">-TITAN</span>
              </h1>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 font-semibold">
                INDIA v2.0
              </span>
            </div>
            <p className="text-[10px] text-slate-400 font-mono flex items-center space-x-1.5">
              <span>NSE / BSE Autonomous Neuro-Causal Quant Terminal</span>
            </p>
          </div>
        </div>

        {/* Live IST Clock & Market Status */}
        <div className="hidden lg:flex items-center space-x-3 text-xs font-mono">
          <div className="px-2.5 py-1 rounded-lg bg-slate-900/80 border border-slate-800 text-slate-300 flex items-center space-x-1.5">
            <Clock className="w-3.5 h-3.5 text-cyan-400" />
            <span className="font-semibold text-slate-100">{istTime || "Asia/Kolkata"}</span>
          </div>

          <div className="px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-semibold text-[11px]">NSE MUMBAI ACTIVE</span>
          </div>
        </div>

        {/* Capital, Hardware, & Emergency Controls */}
        <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
          {/* Virtual Paper Balance */}
          <div
            className="px-2.5 py-1 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 flex items-center space-x-1.5"
            title="Institutional Virtual Capital (Paper Trading Only)"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
            <span>
              PAPER EQ: <strong className="text-indigo-200">₹{Math.round(totalEquity).toLocaleString("en-IN")}</strong>
            </span>
          </div>

          {/* GPU Hardware Pill */}
          <div
            className="hidden sm:flex px-2 py-1 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 items-center space-x-1.5 text-[11px]"
            title={`Hardware: ${botStatus?.gpu_device || "NVIDIA RTX 4060 Laptop GPU"} | VRAM: ${botStatus?.vram_mb || 8192}MB`}
          >
            <Cpu className="w-3 h-3 text-cyan-400 shrink-0" />
            <span className="text-slate-400">RTX 4060:</span>
            <span className="text-emerald-400 font-semibold">CUDA OK</span>
          </div>

          {/* Refresh Action */}
          <button
            type="button"
            onClick={onRefresh}
            disabled={isLoading}
            className="p-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-400 hover:text-slate-200 transition disabled:opacity-50"
            title="Sync live telemetry"
            aria-label="Refresh state"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-cyan-400" : ""}`} />
          </button>

          {/* Emergency Kill Switch */}
          <button
            type="button"
            onClick={onEmergencyKill}
            className={`px-2.5 py-1 rounded-lg font-bold text-[11px] flex items-center space-x-1.5 border transition ${
              isEmergencyActive
                ? "bg-rose-500/20 text-rose-300 border-rose-500/50 hover:bg-rose-500/30 shadow-[0_0_10px_rgba(244,63,94,0.3)] animate-pulse"
                : "bg-slate-900 text-rose-400/80 border-rose-900/40 hover:bg-rose-950/40 hover:text-rose-300"
            }`}
            title="Emergency Kill Switch: Immediately halt bot and flatten all open virtual positions."
          >
            <Flame className="w-3.5 h-3.5 text-rose-400" />
            <span>KILL SWITCH</span>
          </button>
        </div>
      </div>

      {/* 11 Navigation Workspace Tabs */}
      <nav className="px-3 py-1 flex items-center space-x-1 overflow-x-auto no-scrollbar text-xs font-mono">
        {NAV_ITEMS.map((item) => {
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`px-3 py-1.5 rounded-lg whitespace-nowrap flex items-center space-x-1.5 font-medium transition-all duration-150 ${
                isActive
                  ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 shadow-[0_0_10px_rgba(6,182,212,0.15)] font-semibold"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/70 border border-transparent"
              }`}
            >
              <span className={isActive ? "text-cyan-400" : "text-slate-400"}>{item.icon}</span>
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
    </header>
  );
};
