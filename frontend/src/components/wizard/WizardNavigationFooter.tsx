import React from "react";
import { ChevronLeft, ChevronRight, Rocket, AlertCircle, Loader2 } from "lucide-react";
import { WizardStepId } from "./types";

interface WizardNavigationFooterProps {
  currentStep: WizardStepId;
  isSubmitting?: boolean;
  isNextDisabled?: boolean;
  errorMessage?: string | null;
  onPrev: () => void;
  onNext: () => void;
  onCancel: () => void;
  onSubmit: () => void;
}

export const WizardNavigationFooter: React.FC<WizardNavigationFooterProps> = ({
  currentStep,
  isSubmitting = false,
  isNextDisabled = false,
  errorMessage,
  onPrev,
  onNext,
  onCancel,
  onSubmit,
}) => {
  const isFirstStep = currentStep === 1;
  const isLastStep = currentStep === 6;

  return (
    <div className="w-full pt-4 border-t border-slate-800 flex flex-col space-y-3">
      {errorMessage && (
        <div className="px-3 py-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          <span>{errorMessage}</span>
        </div>
      )}

      <div className="flex items-center justify-between">
        {/* Left: Cancel button */}
        <button
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          className="px-3 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800 text-xs font-mono transition disabled:opacity-50"
        >
          Cancel
        </button>

        {/* Right: Back & Next / Launch */}
        <div className="flex items-center space-x-3">
          {!isFirstStep && (
            <button
              type="button"
              onClick={onPrev}
              disabled={isSubmitting}
              className="px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700 text-xs font-mono flex items-center space-x-1 transition disabled:opacity-50"
            >
              <ChevronLeft className="w-4 h-4" />
              <span>Back</span>
            </button>
          )}

          {!isLastStep ? (
            <button
              type="button"
              onClick={onNext}
              disabled={isSubmitting || isNextDisabled}
              className="px-5 py-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-mono font-bold text-xs flex items-center space-x-1.5 shadow-md shadow-sky-500/20 transition disabled:opacity-50"
            >
              <span>Next</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              type="button"
              onClick={onSubmit}
              disabled={isSubmitting}
              className="px-6 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-mono font-bold text-xs flex items-center space-x-2 shadow-lg shadow-emerald-500/30 transition disabled:opacity-50"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Launching Session...</span>
                </>
              ) : (
                <>
                  <Rocket className="w-4 h-4 fill-current" />
                  <span>Confirm & Launch Session</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
