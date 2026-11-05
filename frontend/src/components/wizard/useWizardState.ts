import { useState, useCallback } from "react";
import {
  WizardFormState,
  WizardStepId,
  MarketType,
  HorizonType,
  DurationClassification,
  EndPolicy,
} from "./types";
import { sessionApi } from "../../services/sessionApi";
import { TradingSession, SessionCreatePayload } from "../../types";

export const MARKET_CONFIGS = {
  US_EQUITIES: {
    currency: "USD" as const,
    defaultTickers: ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL"],
  },
  INDIAN_NSE: {
    currency: "INR" as const,
    defaultTickers: ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "TATAMOTORS.NS"],
  },
  CRYPTO: {
    currency: "USD" as const,
    defaultTickers: ["BTC-USD", "ETH-USD", "SOL-USD"],
  },
  COMMODITIES: {
    currency: "USD" as const,
    defaultTickers: ["GC=F", "SI=F", "CL=F"],
  },
  FOREX: {
    currency: "USD" as const,
    defaultTickers: ["EURUSD=X", "GBPUSD=X", "USDJPY=X"],
  },
};

export const INITIAL_WIZARD_STATE: WizardFormState = {
  currentStep: 1,
  furthestStepReached: 1,
  market: "US_EQUITIES",
  instruments: ["NVDA", "AAPL", "MSFT"],
  horizon: "1d",
  durationType: "FIXED",
  durationPresetMinutes: 240, // 4 hours
  customDurationMinutes: null,
  sessionEndPolicy: "CLOSE_ALL",
  allocatedCapital: 50000,
  currency: "USD",
  sessionName: "",
  validationErrors: {},
  isRecommending: false,
  recommendationRationale: undefined,
  recommendationEvaluations: undefined,
  recommendationError: null,
  isSubmitting: false,
  submissionError: null,
};

// Standard approved commodity and forex standalone symbols matching backend session_manager.py:312-316
export const COMMODITY_STANDALONE_SYMBOLS = ["GLD", "SLV", "USO", "UNG"] as const;
export const FOREX_STANDALONE_SYMBOLS = ["DX-Y.NYB", "UUP"] as const;

/**
 * Validates ticker symbol syntax strictly according to market jurisdiction rules.
 * Directly mirrors backend validation contracts in `src/execution/session_manager.py:304-320`.
 *
 * Rules:
 * - US_EQUITIES: Alphanumeric only, 1-5 chars, NO dots (.), NO hyphens (-), NO equal signs (=).
 * - INDIAN_NSE: 1-20 chars symbol strictly ending with .NS or .BO suffix.
 * - CRYPTO: Standard crypto pair with 2-10 chars base symbol ending with -USD or -USDT.
 * - COMMODITIES: Standard futures symbol ending with =F (e.g. GC=F) or approved commodity ETF (GLD, SLV, USO, UNG).
 * - FOREX: 6 uppercase letters ending with =X (e.g. EURUSD=X) or approved FX index symbols (DX-Y.NYB, UUP).
 */
export function validateTickerForMarket(ticker: string, market: MarketType): boolean {
  if (!ticker || typeof ticker !== "string") return false;
  const clean = ticker.trim().toUpperCase();
  if (!clean) return false;

  switch (market) {
    case "US_EQUITIES":
      // Alphanumeric only, 1-5 chars, NO dots (.), NO hyphens (-), NO equal signs (=)
      return /^[A-Z0-9]{1,5}$/.test(clean);

    case "INDIAN_NSE":
      // Must end with .NS or .BO (e.g. RELIANCE.NS, TCS.BO, 500325.BO)
      return /^[A-Z0-9_&-]{1,20}\.(NS|BO)$/.test(clean);

    case "CRYPTO":
      // Must match standard crypto ticker patterns (-USD or -USDT suffix)
      return /^[A-Z0-9]{2,10}-(USD|USDT)$/.test(clean);

    case "COMMODITIES":
      // Must end with =F (e.g. GC=F, SI=F) or match standard commodity symbol
      return (
        /^[A-Z0-9]{1,5}=F$/.test(clean) ||
        (COMMODITY_STANDALONE_SYMBOLS as readonly string[]).includes(clean)
      );

    case "FOREX":
      // 6 uppercase letters ending with =X (e.g. EURUSD=X) or recognized FX index
      return (
        /^[A-Z]{6}=X$/.test(clean) ||
        (FOREX_STANDALONE_SYMBOLS as readonly string[]).includes(clean)
      );

    default:
      return false;
  }
}

/**
 * Pure standalone step validator for wizard forms.
 */
export function validateWizardStep(
  step: WizardStepId | number,
  currentState: WizardFormState
): { isValid: boolean; errors: Record<string, string> } {
  const errors: Record<string, string> = {};

  if (step === 1) {
    if (!currentState.market || !MARKET_CONFIGS[currentState.market as keyof typeof MARKET_CONFIGS]) {
      errors.market = "Please select a supported market jurisdiction.";
    }
  } else if (step === 2) {
    if (!currentState.instruments || currentState.instruments.length === 0) {
      errors.instruments = "Please select at least 1 instrument to trade.";
    } else if (currentState.instruments.length > 20) {
      errors.instruments = "Maximum 20 instruments allowed per session.";
    } else {
      // Check ticker format validity
      const invalidTickers = currentState.instruments.filter(
        (t) => !validateTickerForMarket(t, currentState.market)
      );
      if (invalidTickers.length > 0) {
        errors.instruments = `Invalid ticker format for ${currentState.market}: ${invalidTickers.join(", ")}`;
      }
    }
  } else if (step === 3) {
    if (!["1h", "1d", "1wk"].includes(currentState.horizon)) {
      errors.horizon = "Please select a valid trading holding horizon (1h, 1d, 1wk).";
    }
  } else if (step === 4) {
    if (!["FIXED", "CUSTOM", "MANUAL_STOP"].includes(currentState.durationType)) {
      errors.duration = "Please select a valid duration type.";
    } else if (currentState.durationType === "FIXED") {
      if (!currentState.durationPresetMinutes || currentState.durationPresetMinutes <= 0) {
        errors.duration = "Please select a duration preset.";
      }
    } else if (currentState.durationType === "CUSTOM") {
      const mins = currentState.customDurationMinutes;
      if (!mins || mins < 1 || mins > 10080) {
        errors.duration = "Custom duration must be between 1 minute and 10,080 minutes (1 week).";
      }
    }
    if (!["CLOSE_ALL", "KEEP_OPEN"].includes(currentState.sessionEndPolicy)) {
      errors.sessionEndPolicy = "Please select a session-end position policy.";
    }
  } else if (step === 5) {
    const capital = currentState.allocatedCapital;
    if (typeof capital !== "number" || isNaN(capital) || capital <= 0) {
      errors.capital = "Allocated virtual capital must be strictly positive.";
    } else if (capital < 1000 || capital > 10000000) {
      errors.capital = `Virtual capital must be between 1,000 and 10,000,000 ${currentState.currency}.`;
    }
    const expectedCurrency = currentState.market === "INDIAN_NSE" ? "INR" : "USD";
    if (currentState.currency !== expectedCurrency) {
      errors.currency = `Currency mismatch: Market ${currentState.market} requires ${expectedCurrency}.`;
    }
  }

  return {
    isValid: Object.keys(errors).length === 0,
    errors,
  };
}

/**
 * Boolean-returning convenience helper for standalone step validation.
 */
export function isWizardStepValid(
  step: WizardStepId | number,
  currentState: WizardFormState
): boolean {
  return validateWizardStep(step, currentState).isValid;
}

export function useWizardState(initialState: Partial<WizardFormState> = {}) {
  const [state, setState] = useState<WizardFormState>({
    ...INITIAL_WIZARD_STATE,
    ...initialState,
  });

  const validateStep = useCallback(
    (step: WizardStepId | number, currentState = state) => {
      return validateWizardStep(step, currentState);
    },
    [state]
  );

  const resetWizard = useCallback((overrideState: Partial<WizardFormState> = {}) => {
    setState({
      ...INITIAL_WIZARD_STATE,
      ...overrideState,
    });
  }, []);

  const goToStep = useCallback(
    (targetStep: WizardStepId) => {
      setState((prev) => {
        // Can only jump to steps already reached or step 1
        if (targetStep <= prev.furthestStepReached || targetStep === 1) {
          return {
            ...prev,
            currentStep: targetStep,
            validationErrors: {},
          };
        }
        return prev;
      });
    },
    []
  );

  const nextStep = useCallback(() => {
    setState((prev) => {
      const { isValid, errors } = validateStep(prev.currentStep, prev);
      if (!isValid) {
        return {
          ...prev,
          validationErrors: errors,
        };
      }
      if (prev.currentStep < 6) {
        const next = (prev.currentStep + 1) as WizardStepId;
        return {
          ...prev,
          currentStep: next,
          furthestStepReached: Math.max(prev.furthestStepReached, next) as WizardStepId,
          validationErrors: {},
        };
      }
      return prev;
    });
  }, [validateStep]);

  const prevStep = useCallback(() => {
    setState((prev) => {
      if (prev.currentStep > 1) {
        return {
          ...prev,
          currentStep: (prev.currentStep - 1) as WizardStepId,
          validationErrors: {},
        };
      }
      return prev;
    });
  }, []);

  const setMarket = useCallback((market: MarketType) => {
    setState((prev) => {
      const config = MARKET_CONFIGS[market as keyof typeof MARKET_CONFIGS];
      const newCurrency = config ? config.currency : "USD";
      // Clear instruments if market changes and existing instruments are incompatible
      const compatibleTickers = prev.instruments.filter((t) => validateTickerForMarket(t, market));
      const nextTickers =
        compatibleTickers.length > 0 ? compatibleTickers : (config ? config.defaultTickers.slice(0, 3) : []);

      return {
        ...prev,
        market,
        currency: newCurrency,
        instruments: nextTickers,
        recommendationRationale: undefined,
        recommendationEvaluations: undefined,
        recommendationError: null,
        validationErrors: {},
      };
    });
  }, []);

  const setInstruments = useCallback((instruments: string[]) => {
    setState((prev) => ({
      ...prev,
      instruments: Array.from(new Set(instruments.map((t) => t.trim().toUpperCase()))),
      validationErrors: { ...prev.validationErrors, instruments: "" },
    }));
  }, []);

  const addInstrument = useCallback((ticker: string) => {
    const clean = ticker.trim().toUpperCase();
    if (!clean) return;
    setState((prev) => {
      if (prev.instruments.includes(clean)) {
        return {
          ...prev,
          validationErrors: { ...prev.validationErrors, instruments: `Ticker ${clean} already in basket.` },
        };
      }
      if (prev.instruments.length >= 20) {
        return {
          ...prev,
          validationErrors: { ...prev.validationErrors, instruments: "Maximum basket size of 20 reached." },
        };
      }
      if (!validateTickerForMarket(clean, prev.market)) {
        return {
          ...prev,
          validationErrors: {
            ...prev.validationErrors,
            instruments: `Invalid ticker format for ${prev.market}: "${clean}".`,
          },
        };
      }
      return {
        ...prev,
        instruments: [...prev.instruments, clean],
        validationErrors: { ...prev.validationErrors, instruments: "" },
      };
    });
  }, []);

  const removeInstrument = useCallback((ticker: string) => {
    setState((prev) => ({
      ...prev,
      instruments: prev.instruments.filter((t) => t !== ticker),
      validationErrors: { ...prev.validationErrors, instruments: "" },
    }));
  }, []);

  const requestRecommendations = useCallback(async () => {
    setState((prev) => ({
      ...prev,
      isRecommending: true,
      recommendationError: null,
    }));
    try {
      const resp = await sessionApi.fetchRecommendations({
        market: state.market,
        target_size: 5,
      });
      setState((prev) => ({
        ...prev,
        isRecommending: false,
        instruments: resp.selected_instruments,
        recommendationRationale: resp.summary_rationale,
        recommendationEvaluations: resp.evaluations,
        validationErrors: { ...prev.validationErrors, instruments: "" },
      }));
    } catch (err: any) {
      setState((prev) => ({
        ...prev,
        isRecommending: false,
        recommendationError: err.message || "Failed to fetch auto-selection recommendations",
      }));
    }
  }, [state.market]);

  const setHorizon = useCallback((horizon: HorizonType) => {
    setState((prev) => ({ ...prev, horizon, validationErrors: { ...prev.validationErrors, horizon: "" } }));
  }, []);

  const setDurationType = useCallback((durationType: DurationClassification) => {
    setState((prev) => ({
      ...prev,
      durationType,
      durationPresetMinutes: durationType === "FIXED" ? (prev.durationPresetMinutes || 240) : null,
      customDurationMinutes: durationType === "CUSTOM" ? (prev.customDurationMinutes || 60) : null,
      validationErrors: { ...prev.validationErrors, duration: "" },
    }));
  }, []);

  const setDurationPreset = useCallback((minutes: number | null) => {
    setState((prev) => ({
      ...prev,
      durationType: "FIXED",
      durationPresetMinutes: minutes,
      validationErrors: { ...prev.validationErrors, duration: "" },
    }));
  }, []);

  const setCustomDuration = useCallback((minutes: number | null) => {
    setState((prev) => ({
      ...prev,
      durationType: "CUSTOM",
      customDurationMinutes: minutes,
      validationErrors: { ...prev.validationErrors, duration: "" },
    }));
  }, []);

  const setSessionEndPolicy = useCallback((sessionEndPolicy: EndPolicy) => {
    setState((prev) => ({ ...prev, sessionEndPolicy, validationErrors: { ...prev.validationErrors, sessionEndPolicy: "" } }));
  }, []);

  const setAllocatedCapital = useCallback((allocatedCapital: number) => {
    setState((prev) => {
      let capitalError = "";
      if (typeof allocatedCapital !== "number" || isNaN(allocatedCapital) || allocatedCapital <= 0) {
        capitalError = "Allocated virtual capital must be strictly positive.";
      } else if (allocatedCapital < 1000 || allocatedCapital > 10000000) {
        capitalError = `Virtual capital must be between 1,000 and 10,000,000 ${prev.currency}.`;
      }
      return {
        ...prev,
        allocatedCapital,
        validationErrors: { ...prev.validationErrors, capital: capitalError },
      };
    });
  }, []);

  const setSessionName = useCallback((sessionName: string) => {
    setState((prev) => ({ ...prev, sessionName }));
  }, []);

  const submitLaunchSession = useCallback(async (): Promise<TradingSession | null> => {
    // Validate all steps 1 through 5
    for (let s = 1; s <= 5; s++) {
      const { isValid, errors } = validateStep(s as WizardStepId, state);
      if (!isValid) {
        setState((prev) => ({
          ...prev,
          currentStep: s as WizardStepId,
          validationErrors: errors,
          submissionError: `Validation error in Step ${s}. Please fix before launching.`,
        }));
        return null;
      }
    }

    setState((prev) => ({
      ...prev,
      isSubmitting: true,
      submissionError: null,
    }));

    try {
      // Calculate effective duration minutes
      let durationMinutes: number | null = null;
      if (state.durationType === "FIXED") {
        durationMinutes = state.durationPresetMinutes ?? 240;
      } else if (state.durationType === "CUSTOM") {
        durationMinutes = state.customDurationMinutes ?? 60;
      } else {
        durationMinutes = null;
      }

      const payload: SessionCreatePayload = {
        name: state.sessionName.trim() || `${state.market} - ${state.horizon.toUpperCase()} Session`,
        market: state.market,
        instruments: state.instruments,
        horizon: state.horizon,
        duration_type: state.durationType,
        duration_minutes: durationMinutes,
        session_end_policy: state.sessionEndPolicy,
        allocated_capital: Number(state.allocatedCapital),
        currency: state.currency,
        strategy_config: {},
        risk_config: {},
      };

      // 1. Create session
      const createdSession = await sessionApi.createSession(payload);

      // 2. Start session immediately
      const runningSession = await sessionApi.startSession(createdSession.id);

      setState((prev) => ({
        ...prev,
        isSubmitting: false,
      }));

      return runningSession;
    } catch (err: any) {
      setState((prev) => ({
        ...prev,
        isSubmitting: false,
        submissionError: err.message || "Failed to create and start session",
      }));
      return null;
    }
  }, [state, validateStep]);

  return {
    state,
    goToStep,
    nextStep,
    prevStep,
    setMarket,
    setInstruments,
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
    validateStep,
    submitLaunchSession,
    resetWizard,
  };
}
