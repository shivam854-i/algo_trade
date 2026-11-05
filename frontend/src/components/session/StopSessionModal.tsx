import React, { useState } from "react";
import { AlertTriangle, ShieldAlert, Lock, X, Square } from "lucide-react";
import { TradingSession } from "../../types";

export interface StopSessionModalProps {
  isOpen: boolean;
  session: TradingSession;
  openPositionsCount?: number;
  onClose: () => void;
  onConfirm: (reason: string) => void;
}

export const StopSessionModal: React.FC<StopSessionModalProps> = ({
  isOpen,
  session,
  openPositionsCount = 0,
  onClose,
  onConfirm,
}) => {
  const [reason, setReason] = useState<string>("USER_MANUAL_STOP");

  if (!isOpen) {
    return null;
  }

  const isCloseAll = session.session_end_policy === "CLOSE_ALL";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="stop-session-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-150"
    >
      <div className="relative w-full max-w-lg bg-[#0b0f19] border border-slate-800 rounded-2xl shadow-2xl overflow-hidden font-sans">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800 bg-rose-500/10">
          <div className="flex items-center space-x-2 text-rose-400">
            <AlertTriangle className="w-5 h-5 shrink-0" />
            <h3 id="stop-session-title" className="text-sm font-bold font-mono text-slate-100">
              Stop Trading Session #{session.id.substring(0, 8)}?
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            aria-label="Close dialog"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4 text-xs font-mono">
          <p className="text-slate-300 leading-relaxed">
            Terminating this trading session will immediately halt all autonomous bot execution and signal generation. This action cannot be reversed.
          </p>

          {/* Configured Policy Notice */}
          <div
            className={`p-3.5 rounded-xl border space-y-1.5 ${
              isCloseAll
                ? "bg-purple-950/20 border-purple-500/40 text-purple-200"
                : "bg-sky-950/20 border-sky-500/40 text-sky-200"
            }`}
          >
            <div className="flex items-center font-bold">
              {isCloseAll ? (
                <ShieldAlert className="w-4 h-4 mr-1.5 text-purple-400" />
              ) : (
                <Lock className="w-4 h-4 mr-1.5 text-sky-400" />
              )}
              <span>Configured Session-End Policy: {session.session_end_policy}</span>
            </div>
            <p className="text-[11px] text-slate-300 leading-relaxed">
              {isCloseAll
                ? `All ${openPositionsCount} currently open virtual positions will be immediately liquidated at current market price back to cash balance, and any pending orders will be cancelled.`
                : `Autonomous entries will halt, but open virtual positions will remain active in your ledger for manual execution.`}
            </p>
          </div>

          {/* Reason Selector */}
          <div className="space-y-1.5 pt-1">
            <label className="text-slate-400 text-[11px]">Termination Reason</label>
            <select
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono text-slate-200 focus:outline-none focus:border-rose-500"
            >
              <option value="USER_MANUAL_STOP">Operator Manual Stop</option>
              <option value="RISK_HALT">Risk Governance Halt</option>
              <option value="TARGET_ACHIEVED">Profit Target Reached</option>
            </select>
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-slate-800 bg-slate-900/30 flex items-center justify-end space-x-3">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 text-xs font-mono transition"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(reason)}
            className="px-4 py-2 rounded-lg bg-rose-500 hover:bg-rose-400 text-slate-950 font-mono font-bold text-xs flex items-center space-x-1.5 shadow-md shadow-rose-500/20 transition"
          >
            <Square className="w-3.5 h-3.5 fill-current" />
            <span>Confirm & Stop Session</span>
          </button>
        </div>
      </div>
    </div>
  );
};
