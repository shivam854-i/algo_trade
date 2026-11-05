import React from "react";
import { Check } from "lucide-react";
import { WizardStepId } from "./types";

interface WizardProgressHeaderProps {
  currentStep: WizardStepId;
  furthestStepReached: WizardStepId;
  onStepClick: (step: WizardStepId) => void;
}

const STEPS = [
  { id: 1 as WizardStepId, label: "Market" },
  { id: 2 as WizardStepId, label: "Instruments" },
  { id: 3 as WizardStepId, label: "Horizon" },
  { id: 4 as WizardStepId, label: "Duration" },
  { id: 5 as WizardStepId, label: "Capital" },
  { id: 6 as WizardStepId, label: "Review" },
];

export const WizardProgressHeader: React.FC<WizardProgressHeaderProps> = ({
  currentStep,
  furthestStepReached,
  onStepClick,
}) => {
  return (
    <div className="w-full pb-4 border-b border-slate-800">
      <div className="flex items-center justify-between max-w-2xl mx-auto px-2">
        {STEPS.map((s, idx) => {
          const isCompleted = s.id < currentStep;
          const isCurrent = s.id === currentStep;
          const isReachable = s.id <= furthestStepReached;

          return (
            <React.Fragment key={s.id}>
              {/* Step Node */}
              <div className="flex flex-col items-center">
                <button
                  type="button"
                  onClick={() => isReachable && onStepClick(s.id)}
                  disabled={!isReachable}
                  className={`w-8 h-8 rounded-full flex items-center justify-center font-mono text-xs font-bold transition ${
                    isCompleted
                      ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 hover:bg-emerald-500/30"
                      : isCurrent
                      ? "bg-sky-500 text-slate-950 font-black shadow-lg shadow-sky-500/30 ring-2 ring-sky-400/50"
                      : isReachable
                      ? "bg-slate-900 text-slate-300 border border-slate-700 hover:border-slate-500"
                      : "bg-slate-950 text-slate-600 border border-slate-900 cursor-not-allowed"
                  }`}
                  aria-label={`Step ${s.id}: ${s.label}`}
                >
                  {isCompleted ? <Check className="w-4 h-4 stroke-[3]" /> : s.id}
                </button>
                <span
                  className={`mt-1.5 text-[11px] font-mono tracking-wider transition ${
                    isCurrent
                      ? "text-sky-400 font-bold"
                      : isCompleted
                      ? "text-slate-300"
                      : "text-slate-500"
                  }`}
                >
                  {s.label}
                </span>
              </div>

              {/* Connecting Bar */}
              {idx < STEPS.length - 1 && (
                <div
                  className={`flex-1 h-0.5 mx-2 -mt-4 transition ${
                    s.id < currentStep ? "bg-emerald-500/50" : "bg-slate-800"
                  }`}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};
