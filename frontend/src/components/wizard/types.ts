import { SessionMarket, TradingHorizon, DurationType, SessionEndPolicy, SessionCurrency, CandidateEvaluation } from "../../types";

export type WizardStepId = 1 | 2 | 3 | 4 | 5 | 6;

export type MarketType = SessionMarket;
export type HorizonType = TradingHorizon;
export type DurationClassification = DurationType;
export type EndPolicy = SessionEndPolicy;

export interface WizardFormState {
  currentStep: WizardStepId;
  furthestStepReached: WizardStepId;

  // Step 1: Market Selection
  market: MarketType;

  // Step 2: Instrument Selection
  instruments: string[];
  recommendationRationale?: string;
  recommendationEvaluations?: Record<string, CandidateEvaluation>;
  isRecommending: boolean;
  recommendationError?: string | null;

  // Step 3: Horizon Selection
  horizon: HorizonType;

  // Step 4: Duration & Policy
  durationType: DurationClassification;
  durationPresetMinutes: number | null; // 60, 240, 1440, 10080
  customDurationMinutes: number | null;
  sessionEndPolicy: EndPolicy;

  // Step 5: Virtual Capital Allocation
  allocatedCapital: number;
  currency: SessionCurrency;

  // Step 6: Metadata & Session Name
  sessionName: string;

  // Submission & Validation States
  validationErrors: Record<string, string>;
  isSubmitting: boolean;
  submissionError: string | null;
}

export interface MarketOption {
  id: MarketType;
  title: string;
  subtitle: string;
  currency: SessionCurrency;
  currencySymbol: "₹" | "$";
  tradingHours: string;
  sessionKey?: string;
  supported: boolean;
  disabledReason?: string;
  defaultTickers: string[];
}
