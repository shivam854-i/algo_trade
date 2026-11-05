import React, { useState } from "react";
import { ShieldAlert, Lock, AlertCircle, Timer, PowerOff } from "lucide-react";
import { DurationClassification, EndPolicy } from "./types";

interface Step4DurationPolicyProps {
  durationType: DurationClassification;
  durationPresetMinutes: number | null;
  customDurationMinutes: number | null;
  sessionEndPolicy: EndPolicy;
  errorMessage?: string;
  onSetDurationType: (type: DurationClassification) => void;
  onSetDurationPreset: (minutes: number | null) => void;
  onSetCustomDuration: (minutes: number | null) => void;
  onSetSessionEndPolicy: (policy: EndPolicy) => void;
}

const PRESETS = [
  { label: "1 Hour", minutes: 60, desc: "Quick test or intraday burst" },
  { label: "4 Hours", minutes: 240, desc: "Standard morning/afternoon session" },
  { label: "1 Day", minutes: 1440, desc: "Full 24h market cycle" },
  { label: "1 Week", minutes: 10080, desc: "Continuous swing run (7 days)" },
];

export const Step4DurationPolicy: React.FC<Step4DurationPolicyProps> = ({
  durationType,
  durationPresetMinutes,
  customDurationMinutes,
  sessionEndPolicy,
  errorMessage,
  onSetDurationType,
  onSetDurationPreset,
  onSetCustomDuration,
  onSetSessionEndPolicy,
}) => {
  const [customValue, setCustomValue] = useState<string>(
    customDurationMinutes ? String(customDurationMinutes) : "120"
  );
  const [customUnit, setCustomUnit] = useState<"MINUTES" | "HOURS">("MINUTES");

  const handleCustomChange = (valStr: string, unit: "MINUTES" | "HOURS") => {
    setCustomValue(valStr);
    const num = parseFloat(valStr);
    if (!isNaN(num) && num > 0) {
      const totalMinutes = unit === "HOURS" ? Math.round(num * 60) : Math.round(num);
      onSetCustomDuration(totalMinutes);
    } else {
      onSetCustomDuration(null);
    }
  };

  return (
    <div className="flex flex-col space-y-5">
      <div>
        <h3 className="text-base font-bold text-slate-100 flex items-center">
          <Timer className="w-4 h-4 mr-2 text-sky-400" />
          Session Run Duration & End-of-Session Policy
        </h3>
        <p className="text-xs text-slate-400 mt-1">
          Specify how long the autonomous bot will run and what happens to open positions upon session expiry.
        </p>
      </div>

      {errorMessage && (
        <div className="px-3 py-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Part 1: Duration Classification */}
      <div className="space-y-3">
        <label className="text-xs font-mono text-slate-400">Duration Classification</label>

        {/* 1. Presets */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
          {PRESETS.map((p) => {
            const isSelected =
              durationType === "FIXED" && durationPresetMinutes === p.minutes;
            return (
              <button
                key={p.minutes}
                type="button"
                onClick={() => {
                  onSetDurationType("FIXED");
                  onSetDurationPreset(p.minutes);
                }}
                className={`p-3 rounded-xl border text-left transition font-mono ${
                  isSelected
                    ? "bg-sky-500/15 border-sky-500/80 text-slate-100 shadow-md shadow-sky-500/10"
                    : "bg-slate-900/50 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200"
                }`}
              >
                <div className="font-bold text-xs">{p.label}</div>
                <div className="text-[10px] text-slate-500 mt-1">{p.desc}</div>
              </button>
            );
          })}
        </div>

        {/* 2. Custom Duration & Manual Stop row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
          {/* Custom Duration Toggle & Input */}
          <div
            onClick={() => {
              if (durationType !== "CUSTOM") {
                onSetDurationType("CUSTOM");
                handleCustomChange(customValue, customUnit);
              }
            }}
            className={`p-3 rounded-xl border transition ${
              durationType === "CUSTOM"
                ? "bg-sky-500/15 border-sky-500/80 text-slate-100 shadow-md shadow-sky-500/10"
                : "bg-slate-900/50 border-slate-800 text-slate-400 hover:border-slate-700"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-mono font-bold text-xs">Custom Duration</span>
              <input
                type="radio"
                checked={durationType === "CUSTOM"}
                onChange={() => {
                  onSetDurationType("CUSTOM");
                  handleCustomChange(customValue, customUnit);
                }}
                className="accent-sky-500"
              />
            </div>
            <div className="flex items-center space-x-2 mt-2" onClick={(e) => e.stopPropagation()}>
              <input
                type="number"
                min="1"
                max={customUnit === "HOURS" ? "168" : "10080"}
                value={customValue}
                onChange={(e) => handleCustomChange(e.target.value, customUnit)}
                disabled={durationType !== "CUSTOM"}
                className="w-24 bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs font-mono text-slate-100 focus:outline-none focus:border-sky-500 disabled:opacity-50"
              />
              <select
                value={customUnit}
                onChange={(e) => {
                  const newUnit = e.target.value as "MINUTES" | "HOURS";
                  setCustomUnit(newUnit);
                  handleCustomChange(customValue, newUnit);
                }}
                disabled={durationType !== "CUSTOM"}
                className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-xs font-mono text-slate-100 focus:outline-none focus:border-sky-500 disabled:opacity-50"
              >
                <option value="MINUTES">Minutes</option>
                <option value="HOURS">Hours</option>
              </select>
            </div>
          </div>

          {/* Manual Stop Toggle */}
          <div
            onClick={() => onSetDurationType("MANUAL_STOP")}
            className={`p-3 rounded-xl border cursor-pointer transition ${
              durationType === "MANUAL_STOP"
                ? "bg-sky-500/15 border-sky-500/80 text-slate-100 shadow-md shadow-sky-500/10"
                : "bg-slate-900/50 border-slate-800 text-slate-400 hover:border-slate-700"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-mono font-bold text-xs flex items-center">
                <PowerOff className="w-3.5 h-3.5 mr-1.5 text-amber-400" />
                Manual Stop (No Expiry)
              </span>
              <input
                type="radio"
                checked={durationType === "MANUAL_STOP"}
                onChange={() => onSetDurationType("MANUAL_STOP")}
                className="accent-sky-500"
              />
            </div>
            <p className="text-[10px] text-slate-500 mt-2">
              Session runs continuously until you explicitly click STOP on the dashboard.
            </p>
          </div>
        </div>
      </div>

      {/* Part 2: Session-End Position Policy Selector */}
      <div className="space-y-2.5 pt-2 border-t border-slate-800">
        <label className="text-xs font-mono text-slate-400">
          Session-End Position Policy (Triggered upon expiry or stop)
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Policy 1: CLOSE_ALL */}
          <div
            onClick={() => onSetSessionEndPolicy("CLOSE_ALL")}
            className={`p-3.5 rounded-xl border cursor-pointer transition ${
              sessionEndPolicy === "CLOSE_ALL"
                ? "bg-purple-500/15 border-purple-500/80 text-slate-100 shadow-md shadow-purple-500/10"
                : "bg-slate-900/50 border-slate-800 text-slate-400 hover:border-slate-700"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-mono font-bold text-xs text-purple-300 flex items-center">
                <ShieldAlert className="w-4 h-4 mr-1.5 text-purple-400" />
                CLOSE_ALL (Liquidate to Cash)
              </span>
              <input
                type="radio"
                checked={sessionEndPolicy === "CLOSE_ALL"}
                onChange={() => onSetSessionEndPolicy("CLOSE_ALL")}
                className="accent-purple-500"
              />
            </div>
            <p className="text-[11px] text-slate-400 mt-2 leading-relaxed">
              When session reaches 00:00:00, the bot will automatically close all open positions at market price and cancel pending orders. Recommended for clean session isolation.
            </p>
          </div>

          {/* Policy 2: KEEP_OPEN */}
          <div
            onClick={() => onSetSessionEndPolicy("KEEP_OPEN")}
            className={`p-3.5 rounded-xl border cursor-pointer transition ${
              sessionEndPolicy === "KEEP_OPEN"
                ? "bg-sky-500/15 border-sky-500/80 text-slate-100 shadow-md shadow-sky-500/10"
                : "bg-slate-900/50 border-slate-800 text-slate-400 hover:border-slate-700"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-mono font-bold text-xs text-sky-300 flex items-center">
                <Lock className="w-4 h-4 mr-1.5 text-sky-400" />
                KEEP_OPEN (Preserve Positions)
              </span>
              <input
                type="radio"
                checked={sessionEndPolicy === "KEEP_OPEN"}
                onChange={() => onSetSessionEndPolicy("KEEP_OPEN")}
                className="accent-sky-500"
              />
            </div>
            <p className="text-[11px] text-slate-400 mt-2 leading-relaxed">
              When session reaches 00:00:00, the bot halts new trade entries, but open simulated positions remain active in your virtual ledger for manual management.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
