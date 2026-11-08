import React, { useState } from "react";
import { Play, Pause, Square, AlertOctagon, Sparkles, Loader2, History } from "lucide-react";
import { TradingSession } from "../../types";
import { StopSessionModal } from "./StopSessionModal";

export interface SessionControlsProps {
  session: TradingSession | null;
  openPositionsCount?: number;
  disabled?: boolean;
  onStartSession: (sessionId: string) => Promise<void>;
  onPauseSession: (sessionId: string) => Promise<void>;
  onResumeSession: (sessionId: string) => Promise<void>;
  onStopSession: (sessionId: string, reason?: string) => Promise<void>;
  onOpenWizard: () => void;
  onOpenHistory?: () => void;
}

export const SessionControls: React.FC<SessionControlsProps> = ({
  session,
  openPositionsCount = 0,
  disabled = false,
  onStartSession,
  onPauseSession,
  onResumeSession,
  onStopSession,
  onOpenWizard,
  onOpenHistory,
}) => {
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isStopModalOpen, setIsStopModalOpen] = useState<boolean>(false);
  const [errorNotice, setErrorNotice] = useState<string | null>(null);

  const status = session?.status ?? "NONE";
  const isCreated = status === "CREATED";
  const isRunning = status === "RUNNING";
  const isPaused = status === "PAUSED";
  const isTerminal = status === "COMPLETED" || status === "STOPPED" || status === "NONE" || !session;

  const handleAction = async (actionFn: () => Promise<void>) => {
    setIsSubmitting(true);
    setErrorNotice(null);
    try {
      await actionFn();
    } catch (err: any) {
      setErrorNotice(err.message || "Session transition failed");
      setTimeout(() => setErrorNotice(null), 5000);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex items-center space-x-2 font-mono text-xs">
      {errorNotice && (
        <span className="text-rose-400 text-[11px] animate-pulse mr-2 flex items-center">
          <AlertOctagon className="w-3.5 h-3.5 mr-1 shrink-0" />
          {errorNotice}
        </span>
      )}

      {/* 1. START SESSION (When CREATED) */}
      {isCreated && session && (
        <button
          type="button"
          onClick={() => handleAction(() => onStartSession(session.id))}
          disabled={disabled || isSubmitting}
          className="px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold flex items-center shadow-md shadow-emerald-500/20 transition disabled:opacity-50"
          title="Launch session and begin autonomous trading"
        >
          {isSubmitting ? (
            <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
          ) : (
            <Play className="w-3.5 h-3.5 mr-1.5 fill-current" />
          )}
          START SESSION
        </button>
      )}

      {/* 2. RESUME (When PAUSED) */}
      {isPaused && session && (
        <button
          type="button"
          onClick={() => handleAction(() => onResumeSession(session.id))}
          disabled={disabled || isSubmitting}
          className="px-3 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 font-semibold flex items-center transition disabled:opacity-50"
          title="Resume autonomous trading and extend expiry countdown"
        >
          {isSubmitting ? (
            <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
          ) : (
            <Play className="w-3.5 h-3.5 mr-1.5 fill-current" />
          )}
          RESUME
        </button>
      )}

      {/* 3. PAUSE (When RUNNING) */}
      {isRunning && session && (
        <button
          type="button"
          onClick={() => handleAction(() => onPauseSession(session.id))}
          disabled={disabled || isSubmitting}
          className="px-3 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 font-semibold flex items-center transition disabled:opacity-50"
          title="Suspend new trade entries while preserving open position monitoring"
        >
          {isSubmitting ? (
            <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
          ) : (
            <Pause className="w-3.5 h-3.5 mr-1.5" />
          )}
          PAUSE
        </button>
      )}

      {/* 4. STOP (When CREATED, RUNNING, or PAUSED) */}
      {(isRunning || isPaused || isCreated) && session && (
        <button
          type="button"
          onClick={() => setIsStopModalOpen(true)}
          disabled={disabled || isSubmitting}
          className="px-2.5 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40 font-semibold flex items-center transition disabled:opacity-50"
          title="Terminate trading session and trigger session-end policy"
        >
          <Square className="w-3.5 h-3.5 mr-1 fill-current" />
          STOP
        </button>
      )}

      {/* 5. NEW SESSION WIZARD (Available when no active session or session is in terminal state) */}
      {isTerminal && (
        <button
          type="button"
          onClick={onOpenWizard}
          disabled={disabled || isSubmitting}
          className="px-3 py-1.5 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold flex items-center shadow-md shadow-sky-500/20 transition disabled:opacity-50"
          title="Configure and launch a new paper-trading session"
        >
          <Sparkles className="w-3.5 h-3.5 mr-1.5" />
          NEW SESSION
        </button>
      )}

      {/* 6. SESSION HISTORY AUDIT LEDGER */}
      {onOpenHistory && (
        <button
          type="button"
          onClick={onOpenHistory}
          disabled={disabled || isSubmitting}
          className="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700/80 text-xs font-mono flex items-center transition disabled:opacity-50"
          title="View past trading session history & audit ledger"
          aria-label="View session history"
        >
          <History className="w-3.5 h-3.5 mr-1 text-slate-400" />
          HISTORY
        </button>
      )}

      {/* Safety Stop Confirmation Modal */}
      {session && (
        <StopSessionModal
          isOpen={isStopModalOpen}
          session={session}
          openPositionsCount={openPositionsCount}
          onClose={() => setIsStopModalOpen(false)}
          onConfirm={(reason) => {
            setIsStopModalOpen(false);
            handleAction(() => onStopSession(session.id, reason));
          }}
        />
      )}
    </div>
  );
};
