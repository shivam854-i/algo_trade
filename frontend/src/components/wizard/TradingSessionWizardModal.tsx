import React from "react";
import { X, Sparkles } from "lucide-react";
import { WizardProgressHeader } from "./WizardProgressHeader";
import { WizardNavigationFooter } from "./WizardNavigationFooter";
import { Step1MarketSelection } from "./Step1MarketSelection";
import { Step2InstrumentSelection } from "./Step2InstrumentSelection";
import { Step3HorizonSelection } from "./Step3HorizonSelection";
import { Step4DurationPolicy } from "./Step4DurationPolicy";
import { Step5CapitalAllocation } from "./Step5CapitalAllocation";
import { Step6Confirmation } from "./Step6Confirmation";
import { useWizardState } from "./useWizardState";
import { TradingSession, SessionStatusInfo } from "../../types";

export interface TradingSessionWizardModalProps {
  isOpen: boolean;
  marketSessions?: Record<string, SessionStatusInfo>;
  onClose: () => void;
  onSessionStarted: (session: TradingSession) => void;
}

export const TradingSessionWizardModal: React.FC<TradingSessionWizardModalProps> = ({
  isOpen,
  marketSessions,
  onClose,
  onSessionStarted,
}) => {
  const {
    state,
    goToStep,
    nextStep,
    prevStep,
    setMarket,
    addInstrument,
    removeInstrument,
    requestRecommendations,
    setHorizon,
    setDurationType,
    setDurationPreset,
    setCustomDuration,
    setSessionEndPolicy,
    setAllocatedCapital,
    setSessionName,
    submitLaunchSession,
  } = useWizardState();

  if (!isOpen) {
    return null;
  }

  const handleLaunch = async () => {
    const session = await submitLaunchSession();
    if (session) {
      onSessionStarted(session);
      onClose();
    }
  };

  const currentError =
    state.validationErrors.market ||
    state.validationErrors.instruments ||
    state.validationErrors.horizon ||
    state.validationErrors.duration ||
    state.validationErrors.sessionEndPolicy ||
    state.validationErrors.capital ||
    state.validationErrors.currency ||
    state.submissionError;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="wizard-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200"
    >
      <div className="relative w-full max-w-3xl max-h-[92vh] flex flex-col bg-[#0b0f19] border border-slate-800 rounded-2xl shadow-2xl overflow-hidden font-sans">
        {/* Modal Top Title Bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800/80 bg-slate-900/40">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-sky-500/20 text-sky-400 border border-sky-500/30 flex items-center justify-center">
              <Sparkles className="w-4 h-4 fill-current" />
            </div>
            <div>
              <h2
                id="wizard-modal-title"
                className="text-sm font-bold font-mono text-slate-100 flex items-center"
              >
                SYNAPSE-TITAN Trading Session Setup Wizard
              </h2>
              <p className="text-[11px] text-slate-500 font-mono">
                {`Step ${state.currentStep} of 6 • Strictly Paper-Trading Virtual Execution`}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
            aria-label="Close setup wizard"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Wizard Progress Header Stepper */}
        <div className="px-6 pt-4">
          <WizardProgressHeader
            currentStep={state.currentStep}
            furthestStepReached={state.furthestStepReached}
            onStepClick={goToStep}
          />
        </div>

        {/* Modal Scrollable Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {state.currentStep === 1 && (
            <Step1MarketSelection
              selectedMarket={state.market}
              marketSessions={marketSessions}
              errorMessage={state.validationErrors.market}
              onSelectMarket={setMarket}
            />
          )}

          {state.currentStep === 2 && (
            <Step2InstrumentSelection
              market={state.market}
              instruments={state.instruments}
              recommendationRationale={state.recommendationRationale}
              recommendationEvaluations={state.recommendationEvaluations}
              isRecommending={state.isRecommending}
              recommendationError={state.recommendationError}
              errorMessage={state.validationErrors.instruments}
              onAddInstrument={addInstrument}
              onRemoveInstrument={removeInstrument}
              onRequestRecommendations={requestRecommendations}
            />
          )}

          {state.currentStep === 3 && (
            <Step3HorizonSelection
              selectedHorizon={state.horizon}
              errorMessage={state.validationErrors.horizon}
              onSelectHorizon={setHorizon}
            />
          )}

          {state.currentStep === 4 && (
            <Step4DurationPolicy
              durationType={state.durationType}
              durationPresetMinutes={state.durationPresetMinutes}
              customDurationMinutes={state.customDurationMinutes}
              sessionEndPolicy={state.sessionEndPolicy}
              errorMessage={state.validationErrors.duration || state.validationErrors.sessionEndPolicy}
              onSetDurationType={setDurationType}
              onSetDurationPreset={setDurationPreset}
              onSetCustomDuration={setCustomDuration}
              onSetSessionEndPolicy={setSessionEndPolicy}
            />
          )}

          {state.currentStep === 5 && (
            <Step5CapitalAllocation
              allocatedCapital={state.allocatedCapital}
              currency={state.currency}
              errorMessage={state.validationErrors.capital || state.validationErrors.currency}
              onSetAllocatedCapital={setAllocatedCapital}
            />
          )}

          {state.currentStep === 6 && (
            <Step6Confirmation
              state={state}
              errorMessage={state.submissionError}
              onJumpToStep={goToStep}
              onSetSessionName={setSessionName}
            />
          )}
        </div>

        {/* Navigation Footer */}
        <div className="px-6 pb-5">
          <WizardNavigationFooter
            currentStep={state.currentStep}
            isSubmitting={state.isSubmitting}
            errorMessage={currentError}
            onPrev={prevStep}
            onNext={nextStep}
            onCancel={onClose}
            onSubmit={handleLaunch}
          />
        </div>
      </div>
    </div>
  );
};
