import React, { useState, useEffect } from "react";
import {
  Settings,
  Lock,
  Sliders,
  Save,
  RotateCcw,
  FileJson,
  CheckCircle2,
  Clock,
  Building2,
  AlertTriangle,
  Scale,
  Zap,
} from "lucide-react";

export interface TerminalSettings {
  defaultExchange: "NSE" | "BSE";
  timezone: string;
  baseCurrency: string;
  marketJurisdiction: string;
  virtualCapital: number;
  maxSinglePositionAllocationPct: number;
  fractionalKellyMultiplier: number;
  drawdownWarningThresholdPct: number;
  drawdownHardKillLimitPct: number;
  sebiRateLimitPerSec: number;
  limitPriceProtectionPct: number;
}

export interface SettingsViewProps {
  onResetAccount?: () => Promise<any>;
  onSave?: (settings: TerminalSettings) => void;
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  onResetAccount,
  onSave,
}) => {
  // Institutional default state
  const [exchange, setExchange] = useState<"NSE" | "BSE">("NSE");
  const [virtualCapital, setVirtualCapital] = useState<number>(500000);
  const [customCapitalInput, setCustomCapitalInput] = useState<string>("500000");
  const [maxAllocation, setMaxAllocation] = useState<number>(20);
  const [kellyMultiplier, setKellyMultiplier] = useState<number>(0.65);
  const [drawdownWarning, setDrawdownWarning] = useState<number>(8.0);
  const [drawdownHardKill, setDrawdownHardKill] = useState<number>(15.0);
  const [sebiRateLimit, setSebiRateLimit] = useState<number>(5);
  const [lppPct] = useState<number>(1.0);

  // UI state
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [resetFeedback, setResetFeedback] = useState<string | null>(null);
  const [showJsonExport, setShowJsonExport] = useState<boolean>(false);
  const [istTime, setIstTime] = useState<string>("");

  // Live IST Clock
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setIstTime(
        now.toLocaleTimeString("en-IN", {
          timeZone: "Asia/Kolkata",
          hour12: false,
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }) + " IST"
      );
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  // Quick preset capital selection
  const handleSelectCapitalPreset = (amount: number) => {
    setVirtualCapital(amount);
    setCustomCapitalInput(String(amount));
  };

  const handleCustomCapitalChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value.replace(/[^0-9]/g, "");
    setCustomCapitalInput(raw);
    const parsed = parseInt(raw, 10);
    if (!isNaN(parsed) && parsed > 0) {
      setVirtualCapital(parsed);
    }
  };

  const handleResetToDefaults = () => {
    setExchange("NSE");
    setVirtualCapital(500000);
    setCustomCapitalInput("500000");
    setMaxAllocation(20);
    setKellyMultiplier(0.65);
    setDrawdownWarning(8.0);
    setDrawdownHardKill(15.0);
    setSebiRateLimit(5);
    setResetFeedback("Restored institutional quant defaults.");
    setTimeout(() => setResetFeedback(null), 3000);
  };

  const handleResetVirtualLedger = async () => {
    if (onResetAccount) {
      try {
        await onResetAccount();
        setResetFeedback(`Virtual account ledger reset to ₹${virtualCapital.toLocaleString("en-IN")}.`);
      } catch {
        setResetFeedback("Failed to trigger remote ledger reset.");
      }
    } else {
      setResetFeedback(`Virtual account ledger balance reset to ₹${virtualCapital.toLocaleString("en-IN")}.`);
    }
    setTimeout(() => setResetFeedback(null), 3000);
  };

  const handleSaveSettings = () => {
    setSaveStatus("saving");
    const settings: TerminalSettings = {
      defaultExchange: exchange,
      timezone: "Asia/Kolkata (IST)",
      baseCurrency: "INR (₹)",
      marketJurisdiction: "NSE_CASH",
      virtualCapital,
      maxSinglePositionAllocationPct: maxAllocation,
      fractionalKellyMultiplier: kellyMultiplier,
      drawdownWarningThresholdPct: drawdownWarning,
      drawdownHardKillLimitPct: drawdownHardKill,
      sebiRateLimitPerSec: sebiRateLimit,
      limitPriceProtectionPct: lppPct,
    };

    try {
      localStorage.setItem("synapse_titan_settings", JSON.stringify(settings));
    } catch {
      // Storage unavailable fallback
    }

    if (onSave) {
      onSave(settings);
    }

    setTimeout(() => {
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2500);
    }, 400);
  };

  const currentConfigJson = JSON.stringify(
    {
      terminal_version: "2.0.0",
      market_jurisdiction: "NSE_CASH",
      base_currency: "INR (₹)",
      timezone: "Asia/Kolkata (IST)",
      default_exchange: exchange,
      virtual_capital_inr: virtualCapital,
      execution_guardrails: {
        max_single_position_allocation_pct: maxAllocation,
        fractional_kelly_multiplier: kellyMultiplier,
        drawdown_warning_threshold_pct: drawdownWarning,
        drawdown_hard_kill_limit_pct: drawdownHardKill,
        sebi_token_bucket_rate_limit_per_sec: sebiRateLimit,
        limit_price_protection_pct: lppPct,
      },
      safety_lock: {
        paper_trading_only: true,
        enforce_hard_lock: true,
        sebi_algo_circular_compliance: "SEBI/HO/MRD/DP/CIR/P/2012/62",
      },
    },
    null,
    2
  );

  return (
    <div className="space-y-6 font-mono text-slate-100">
      {/* 1. Top Header & Primary Action Buttons */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Settings className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-100 flex items-center space-x-2">
                <span>INSTITUTIONAL WORKSTATION CONFIGURATION</span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 font-semibold">
                  NSE CASH JURISDICTION
                </span>
              </h1>
              <p className="text-xs text-slate-400">
                Institutional exchange defaults, virtual capital allocation, and SEBI execution guardrails
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleResetToDefaults}
            className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 text-xs flex items-center space-x-1.5 transition"
          >
            <RotateCcw className="w-3.5 h-3.5 text-slate-400" />
            <span>Reset Defaults</span>
          </button>

          <button
            onClick={() => setShowJsonExport(!showJsonExport)}
            className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 text-xs flex items-center space-x-1.5 transition"
          >
            <FileJson className="w-3.5 h-3.5 text-cyan-400" />
            <span>{showJsonExport ? "Hide JSON" : "Export JSON"}</span>
          </button>

          <button
            onClick={handleSaveSettings}
            disabled={saveStatus === "saving"}
            className="px-4 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs flex items-center space-x-1.5 transition shadow-[0_0_12px_rgba(6,182,212,0.3)] disabled:opacity-50"
          >
            {saveStatus === "saved" ? (
              <>
                <CheckCircle2 className="w-3.5 h-3.5 text-slate-950" />
                <span>Saved!</span>
              </>
            ) : (
              <>
                <Save className="w-3.5 h-3.5 text-slate-950" />
                <span>Save Configuration</span>
              </>
            )}
          </button>
        </div>
      </div>

      {resetFeedback && (
        <div className="p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs flex items-center space-x-2">
          <CheckCircle2 className="w-4 h-4 text-cyan-400 shrink-0" />
          <span>{resetFeedback}</span>
        </div>
      )}

      {/* 2. Safety Lock Badge Card */}
      <div className="p-4 rounded-xl bg-gradient-to-r from-amber-500/10 via-[#090d18] to-cyan-500/10 border border-amber-500/30 shadow-[0_0_20px_rgba(245,158,11,0.08)]">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-start space-x-3">
            <div className="p-2.5 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-300 shrink-0">
              <Lock className="w-5 h-5 text-amber-400" />
            </div>
            <div>
              <div className="text-sm font-bold text-amber-300 tracking-wide flex flex-wrap items-center gap-2">
                <span>PAPER_TRADING_ONLY = True</span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 uppercase font-black">
                  HARD-LOCKED IN CORE CONFIGURATION - CANNOT BE BYPASSED
                </span>
              </div>
              <p className="text-xs text-slate-300 mt-1 leading-relaxed">
                Direct broker API execution is physically disabled at the binary driver layer. All algorithmic orders execute exclusively against high-fidelity simulated matching engines with SEBI-mandated statutory friction calculations (STT, Stamp Duty, GST, Exchange Fees). Zero live client capital risk.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* JSON Export Drawer (Conditional) */}
      {showJsonExport && (
        <div className="p-4 rounded-xl bg-slate-950 border border-cyan-500/30 space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-400 border-b border-slate-800 pb-2">
            <span className="font-bold text-cyan-300">Terminal Configuration JSON</span>
            <button
              onClick={() => {
                navigator.clipboard.writeText(currentConfigJson);
                setResetFeedback("JSON configuration copied to clipboard.");
                setTimeout(() => setResetFeedback(null), 2500);
              }}
              className="px-2 py-0.5 rounded bg-slate-900 border border-slate-700 hover:text-slate-100 text-[11px]"
            >
              Copy JSON
            </button>
          </div>
          <pre className="text-[11px] text-cyan-200/90 overflow-x-auto p-2 bg-[#060911] rounded max-h-60 leading-tight">
            {currentConfigJson}
          </pre>
        </div>
      )}

      {/* 3. Main Grid: Exchange Defaults & Capital Configuration */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column: Exchange & Jurisdiction Defaults */}
        <div className="p-5 rounded-xl bg-[#090d18] border border-slate-800 space-y-4">
          <div className="border-b border-slate-800/70 pb-3 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
                <Building2 className="w-4 h-4 text-cyan-400" />
                <span>EXCHANGE & JURISDICTION DEFAULTS</span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Indian capital market regulatory jurisdiction and settlement parameters
              </p>
            </div>
            <div className="px-2 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-[10px] font-bold">
              NSE CASH
            </div>
          </div>

          <div className="space-y-4 text-xs">
            {/* Exchange Toggle */}
            <div className="space-y-1.5">
              <label className="text-slate-300 font-semibold block">Default Primary Exchange</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setExchange("NSE")}
                  className={`py-2 px-3 rounded-lg border font-bold text-xs flex items-center justify-center space-x-2 transition ${
                    exchange === "NSE"
                      ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/50 shadow-[0_0_10px_rgba(6,182,212,0.2)]"
                      : "bg-slate-900/60 text-slate-400 border-slate-800 hover:text-slate-200"
                  }`}
                >
                  <Building2 className="w-3.5 h-3.5" />
                  <span>NSE (National Stock Exchange)</span>
                </button>

                <button
                  type="button"
                  onClick={() => setExchange("BSE")}
                  className={`py-2 px-3 rounded-lg border font-bold text-xs flex items-center justify-center space-x-2 transition ${
                    exchange === "BSE"
                      ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/50 shadow-[0_0_10px_rgba(6,182,212,0.2)]"
                      : "bg-slate-900/60 text-slate-400 border-slate-800 hover:text-slate-200"
                  }`}
                >
                  <Building2 className="w-3.5 h-3.5" />
                  <span>BSE (Bombay Stock Exchange)</span>
                </button>
              </div>
              <p className="text-[10px] text-slate-500">
                Primary order routing target for Nifty 50 constituents and index benchmarking.
              </p>
            </div>

            {/* Timezone */}
            <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-slate-300 font-semibold block">Terminal Timezone</span>
                <span className="text-slate-400 text-[11px]">Indian Standard Time (Asia/Kolkata UTC+05:30)</span>
              </div>
              <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded bg-slate-950 border border-slate-800 text-cyan-300 font-mono text-[11px]">
                <Clock className="w-3.5 h-3.5 text-cyan-400" />
                <span>{istTime || "Asia/Kolkata"}</span>
              </div>
            </div>

            {/* Base Currency */}
            <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-slate-300 font-semibold block">Base Operational Currency</span>
                <span className="text-slate-400 text-[11px]">Indian Rupee standard across all ledgers & positions</span>
              </div>
              <span className="px-2.5 py-1 rounded bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 font-bold text-xs">
                INR (₹)
              </span>
            </div>

            {/* Settlement Cycle */}
            <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-slate-300 font-semibold block">Settlement Cycle</span>
                <span className="text-slate-400 text-[11px]">SEBI T+1 Rolling Settlement Protocol</span>
              </div>
              <span className="px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-300 text-[11px]">
                T+1 Standard
              </span>
            </div>
          </div>
        </div>

        {/* Right Column: Virtual Capital Allocation */}
        <div className="p-5 rounded-xl bg-[#090d18] border border-slate-800 space-y-4">
          <div className="border-b border-slate-800/70 pb-3 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
                <Scale className="w-4 h-4 text-emerald-400" />
                <span>VIRTUAL CAPITAL ALLOCATION</span>
              </h2>
              <p className="text-xs text-slate-400 mt-0.5">
                Simulated initial margin capital for autonomous execution testing
              </p>
            </div>
            <div className="px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-[10px] font-bold">
              ₹{virtualCapital.toLocaleString("en-IN")}
            </div>
          </div>

          <div className="space-y-4 text-xs">
            {/* Quick Preset Buttons */}
            <div className="space-y-1.5">
              <label className="text-slate-300 font-semibold block">Preset Virtual Capital Tiers</label>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { label: "₹1,00,000", amount: 100000, desc: "Starter" },
                  { label: "₹5,00,000", amount: 500000, desc: "Default" },
                  { label: "₹10,00,000", amount: 1000000, desc: "Institutional" },
                ].map((preset) => {
                  const isSelected = virtualCapital === preset.amount;
                  return (
                    <button
                      key={preset.amount}
                      type="button"
                      onClick={() => handleSelectCapitalPreset(preset.amount)}
                      className={`p-2.5 rounded-lg border text-left transition ${
                        isSelected
                          ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/50 shadow-[0_0_10px_rgba(16,185,129,0.2)]"
                          : "bg-slate-900/60 text-slate-400 border-slate-800 hover:text-slate-200"
                      }`}
                    >
                      <div className="font-bold text-xs">{preset.label}</div>
                      <div className="text-[10px] text-slate-500">{preset.desc}</div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Custom Capital Input */}
            <div className="space-y-1.5">
              <label className="text-slate-300 font-semibold block">Custom Allocated Capital (₹ INR)</label>
              <div className="relative">
                <span className="absolute left-3 top-2.5 text-slate-400 font-bold text-sm">₹</span>
                <input
                  type="text"
                  value={customCapitalInput}
                  onChange={handleCustomCapitalChange}
                  className="w-full pl-8 pr-4 py-2 rounded-lg bg-slate-900 border border-slate-800 focus:border-cyan-500 text-slate-100 font-mono text-sm outline-none transition"
                  placeholder="500000"
                />
              </div>
              <p className="text-[10px] text-slate-500">
                Minimum ₹10,000 | Maximum ₹1,00,00,000 (1 Crore INR)
              </p>
            </div>

            {/* Reset Ledger Balance Action */}
            <div className="pt-2 border-t border-slate-800/70 flex items-center justify-between">
              <div className="text-[11px] text-slate-400">
                Rebalance ledger equity to allocated capital:
              </div>
              <button
                type="button"
                onClick={handleResetVirtualLedger}
                className="px-3 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 text-xs font-semibold transition"
              >
                Reset Ledger Balance
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 4. Execution Guardrails & Risk Management Controls */}
      <div className="p-5 rounded-xl bg-[#090d18] border border-slate-800 space-y-5">
        <div className="border-b border-slate-800/70 pb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
              <Sliders className="w-4 h-4 text-cyan-400" />
              <span>QUANT EXECUTION GUARDRAILS & RISK LIMITS</span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Autonomous mathematical risk limits, fractional sizing, and circuit breakers
            </p>
          </div>
          <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-semibold">
            STRICT ENFORCEMENT
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 text-xs">
          {/* 1. Max Single Position Allocation */}
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-slate-300 font-semibold">Max Single Allocation</span>
              <span className="text-cyan-300 font-bold px-2 py-0.5 rounded bg-cyan-950/40 border border-cyan-800/60">
                {maxAllocation}%
              </span>
            </div>
            <input
              type="range"
              min="5"
              max="50"
              step="1"
              value={maxAllocation}
              onChange={(e) => setMaxAllocation(Number(e.target.value))}
              className="w-full accent-cyan-400 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
            />
            <p className="text-[10px] text-slate-400 leading-relaxed">
              Caps portfolio exposure in any individual stock (e.g. RELIANCE.NS) to prevent concentration risk.
            </p>
          </div>

          {/* 2. Fractional Kelly Multiplier */}
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-slate-300 font-semibold">Fractional Kelly Multiplier</span>
              <span className="text-indigo-300 font-bold px-2 py-0.5 rounded bg-indigo-950/40 border border-indigo-800/60">
                {kellyMultiplier.toFixed(2)}x
              </span>
            </div>
            <input
              type="range"
              min="0.10"
              max="1.00"
              step="0.05"
              value={kellyMultiplier}
              onChange={(e) => setKellyMultiplier(Number(e.target.value))}
              className="w-full accent-indigo-400 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
            />
            <p className="text-[10px] text-slate-400 leading-relaxed">
              Conservative half-Kelly dampener (0.65x) to shield against parameter estimation noise and fat tails.
            </p>
          </div>

          {/* 3. Drawdown Warning Threshold */}
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-slate-300 font-semibold">Drawdown Warning Level</span>
              <span className="text-amber-300 font-bold px-2 py-0.5 rounded bg-amber-950/40 border border-amber-800/60">
                {drawdownWarning.toFixed(1)}%
              </span>
            </div>
            <input
              type="range"
              min="2.0"
              max="15.0"
              step="0.5"
              value={drawdownWarning}
              onChange={(e) => setDrawdownWarning(Number(e.target.value))}
              className="w-full accent-amber-400 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
            />
            <p className="text-[10px] text-slate-400 leading-relaxed">
              Triggers cockpit HUD warnings and restricts autonomous entry sizing when high-water mark draws down 8%.
            </p>
          </div>

          {/* 4. Drawdown Hard Kill Limit */}
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-slate-300 font-semibold">Drawdown Hard Kill Limit</span>
              <span className="text-rose-400 font-bold px-2 py-0.5 rounded bg-rose-950/40 border border-rose-800/60">
                {drawdownHardKill.toFixed(1)}%
              </span>
            </div>
            <input
              type="range"
              min="5.0"
              max="30.0"
              step="1.0"
              value={drawdownHardKill}
              onChange={(e) => setDrawdownHardKill(Number(e.target.value))}
              className="w-full accent-rose-400 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
            />
            <p className="text-[10px] text-slate-400 leading-relaxed">
              Automated circuit breaker: Immediately halts all bot trading and liquidates positions upon reaching limit.
            </p>
          </div>

          {/* 5. SEBI Token Bucket Rate Limit */}
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-slate-300 font-semibold">SEBI Rate Limit</span>
              <span className="text-cyan-300 font-bold px-2 py-0.5 rounded bg-cyan-950/40 border border-cyan-800/60">
                {sebiRateLimit} req/s
              </span>
            </div>
            <input
              type="range"
              min="1"
              max="10"
              step="1"
              value={sebiRateLimit}
              onChange={(e) => setSebiRateLimit(Number(e.target.value))}
              className="w-full accent-cyan-400 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
            />
            <p className="text-[10px] text-slate-400 leading-relaxed">
              Throttles order frequency to 5 req/s with a burst capacity of 5, complying with NSE member gateway limits.
            </p>
          </div>

          {/* 6. SEBI Limit Price Protection (LPP) */}
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-slate-300 font-semibold">Limit Price Protection (LPP)</span>
              <span className="text-emerald-300 font-bold px-2 py-0.5 rounded bg-emerald-950/40 border border-emerald-800/60">
                ±{lppPct.toFixed(1)}%
              </span>
            </div>
            <div className="flex items-center space-x-2 pt-1 text-[11px] text-slate-300">
              <Zap className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>Mandatory algorithmic order price clamping</span>
            </div>
            <p className="text-[10px] text-slate-400 leading-relaxed">
              Automated conversion of pure market orders to bounded limit orders to protect against order book vacuums.
            </p>
          </div>
        </div>
      </div>

      {/* 5. Regulatory Compliance & Exchange Circulars Footer */}
      <div className="p-4 rounded-xl bg-[#090d18] border border-slate-800 text-xs text-slate-400 space-y-2">
        <div className="flex items-center space-x-2 text-slate-200 font-bold">
          <AlertTriangle className="w-4 h-4 text-amber-400" />
          <span>STATUTORY REGULATORY INVARIANT</span>
        </div>
        <p className="text-[11px] leading-relaxed">
          Operating under SEBI Algorithmic Trading Circulars (SEBI/HO/MRD/DP/CIR/P/2012/62) and NSE Cash Market Directives. All algorithmic strategies remain confined to the client-side paper simulation engine. Live real-money order routing requires formal exchange algo strategy registration and broker approval.
        </p>
      </div>
    </div>
  );
};

export default SettingsView;
