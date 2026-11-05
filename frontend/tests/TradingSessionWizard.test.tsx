import { describe, expect, it, vi } from "vitest";
import React from "react";
import ReactDOMServer from "react-dom/server";
import { TradingSessionWizardModal } from "../src/components/wizard/TradingSessionWizardModal";
import { Step1MarketSelection } from "../src/components/wizard/Step1MarketSelection";
import { Step2InstrumentSelection } from "../src/components/wizard/Step2InstrumentSelection";
import { Step3HorizonSelection } from "../src/components/wizard/Step3HorizonSelection";
import { Step4DurationPolicy } from "../src/components/wizard/Step4DurationPolicy";
import { Step5CapitalAllocation } from "../src/components/wizard/Step5CapitalAllocation";
import { Step6Confirmation } from "../src/components/wizard/Step6Confirmation";
import {
  useWizardState,
  validateTickerForMarket,
  validateWizardStep,
  isWizardStepValid,
  INITIAL_WIZARD_STATE,
} from "../src/components/wizard/useWizardState";
import { sessionApi } from "../src/services/sessionApi";

describe("Milestone 3: 6-Step Trading Session Setup Wizard", () => {
  describe("Step 1: Market Selection", () => {
    it("renders supported institutional market cards and disables unsupported markets", () => {
      const rawHtml = ReactDOMServer.renderToString(
        <Step1MarketSelection
          selectedMarket="US_EQUITIES"
          marketSessions={{
            US_MARKETS: {
              state: "OPEN",
              is_open: true,
              next_state: "CLOSED",
              seconds_to_next_state: 14400,
              local_time: "10:30 ET",
              exchange_tz: "America/New_York",
              holiday_name: null,
            },
          }}
          onSelectMarket={() => {}}
        />
      );
      const html = rawHtml.replace(/<!-- -->/g, "");

      // Verify supported markets exist
      expect(html).toContain("US Equities");
      expect(html).toContain("Indian Equities");
      expect(html).toContain("Cryptocurrencies");
      expect(html).toContain("Commodities");
      expect(html).toContain("Forex Majors");

      // Verify unsupported European Equities is disabled
      expect(html).toContain("European Equities");
      expect(html).toContain("Unsupported");
      expect(html).toContain("cursor-not-allowed");

      // Verify currency badges
      expect(html).toContain("USD ($)");
      expect(html).toContain("INR (₹)");
    });
  });

  describe("Step 2: Instrument Selection & Auto-Select", () => {
    it("renders basket chips, capacity indicator, and allows manual remove", () => {
      const rawHtml = ReactDOMServer.renderToString(
        <Step2InstrumentSelection
          market="US_EQUITIES"
          instruments={["NVDA", "AAPL", "MSFT"]}
          isRecommending={false}
          onAddInstrument={() => {}}
          onRemoveInstrument={() => {}}
          onRequestRecommendations={() => {}}
        />
      );
      const html = rawHtml.replace(/<!-- -->/g, "");

      expect(html).toContain("NVDA");
      expect(html).toContain("AAPL");
      expect(html).toContain("MSFT");
      expect(html).toContain("Selected Basket: <strong class=\"text-slate-200\">3</strong> / 20 symbols");
      expect(html).toContain("Auto-select for me");
    });

    it("displays quantitative selection rationale and multi-factor badges when recommendations are present", () => {
      const rawHtml = ReactDOMServer.renderToString(
        <Step2InstrumentSelection
          market="US_EQUITIES"
          instruments={["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL"]}
          recommendationRationale="Auto-selected 5 high-liquidity US instruments with ADV > $5M, spread <= 25 bps, and high composite Sharpe edge."
          recommendationEvaluations={{
            NVDA: {
              ticker: "NVDA",
              market: "US_EQUITIES",
              passed_all_gates: true,
              data_quality_score: 0.98,
              missing_bar_ratio: 0.0,
              zero_volume_ratio: 0.0,
              adv: 45000000,
              adv_currency: "$",
              adv_threshold: 5000000,
              spread_bps: 2.1,
              annualized_volatility: 0.42,
              composite_score: 0.88,
              rejection_reasons: [],
              pass_details: {},
              summary_rationale: "High institutional liquidity",
            },
          }}
          isRecommending={false}
          onAddInstrument={() => {}}
          onRemoveInstrument={() => {}}
          onRequestRecommendations={() => {}}
        />
      );
      const html = rawHtml.replace(/<!-- -->/g, "");

      expect(html).toContain("Quantitative Selection Rationale (UniverseSelector)");
      expect(html).toContain("Auto-selected 5 high-liquidity US instruments");
      expect(html).toContain("Data Quality ≥ 90%");
      expect(html).toContain("Liquidity ADV Gate Passed");
      expect(html).toContain("Spread ≤ 25 bps");
      expect(html).toContain("Q: 98%");
    });

    it("validates ticker syntax per market jurisdiction and strictly blocks cross-market contamination", () => {
      // US Equities: AAPL, NVDA, C, GOOGL are valid; foreign tickers are strictly invalid
      expect(validateTickerForMarket("AAPL", "US_EQUITIES")).toBe(true);
      expect(validateTickerForMarket("NVDA", "US_EQUITIES")).toBe(true);
      expect(validateTickerForMarket("C", "US_EQUITIES")).toBe(true);
      expect(validateTickerForMarket("GOOGL", "US_EQUITIES")).toBe(true);
      expect(validateTickerForMarket("RELIANCE.NS", "US_EQUITIES")).toBe(false);
      expect(validateTickerForMarket("TCS.BO", "US_EQUITIES")).toBe(false);
      expect(validateTickerForMarket("BTC-USD", "US_EQUITIES")).toBe(false);
      expect(validateTickerForMarket("GC=F", "US_EQUITIES")).toBe(false);
      expect(validateTickerForMarket("EURUSD=X", "US_EQUITIES")).toBe(false);
      expect(validateTickerForMarket("TOOLONGTICKER", "US_EQUITIES")).toBe(false);

      // Indian NSE: RELIANCE.NS, TCS.BO, 500325.BO are valid; foreign tickers are invalid
      expect(validateTickerForMarket("RELIANCE.NS", "INDIAN_NSE")).toBe(true);
      expect(validateTickerForMarket("TCS.BO", "INDIAN_NSE")).toBe(true);
      expect(validateTickerForMarket("500325.BO", "INDIAN_NSE")).toBe(true);
      expect(validateTickerForMarket("AAPL", "INDIAN_NSE")).toBe(false);
      expect(validateTickerForMarket("NVDA", "INDIAN_NSE")).toBe(false);
      expect(validateTickerForMarket("BTC-USD", "INDIAN_NSE")).toBe(false);
      expect(validateTickerForMarket("GC=F", "INDIAN_NSE")).toBe(false);
      expect(validateTickerForMarket(".NS", "INDIAN_NSE")).toBe(false);

      // Crypto: BTC-USD, ETH-USDT, SOL-USD are valid; foreign tickers are invalid
      expect(validateTickerForMarket("BTC-USD", "CRYPTO")).toBe(true);
      expect(validateTickerForMarket("ETH-USDT", "CRYPTO")).toBe(true);
      expect(validateTickerForMarket("SOL-USD", "CRYPTO")).toBe(true);
      expect(validateTickerForMarket("AAPL", "CRYPTO")).toBe(false);
      expect(validateTickerForMarket("RELIANCE.NS", "CRYPTO")).toBe(false);
      expect(validateTickerForMarket("GC=F", "CRYPTO")).toBe(false);
      expect(validateTickerForMarket("-USD", "CRYPTO")).toBe(false);

      // Commodities: GC=F, SI=F, CL=F, GLD, USO are valid; US equities (AAPL) are invalid
      expect(validateTickerForMarket("GC=F", "COMMODITIES")).toBe(true);
      expect(validateTickerForMarket("SI=F", "COMMODITIES")).toBe(true);
      expect(validateTickerForMarket("CL=F", "COMMODITIES")).toBe(true);
      expect(validateTickerForMarket("GLD", "COMMODITIES")).toBe(true);
      expect(validateTickerForMarket("USO", "COMMODITIES")).toBe(true);
      expect(validateTickerForMarket("AAPL", "COMMODITIES")).toBe(false);
      expect(validateTickerForMarket("MSFT", "COMMODITIES")).toBe(false);
      expect(validateTickerForMarket("RELIANCE.NS", "COMMODITIES")).toBe(false);

      // Forex: EURUSD=X, GBPUSD=X, DX-Y.NYB, UUP are valid; arbitrary 6-letter words (GOOGLE, AMAZON) are invalid
      expect(validateTickerForMarket("EURUSD=X", "FOREX")).toBe(true);
      expect(validateTickerForMarket("GBPUSD=X", "FOREX")).toBe(true);
      expect(validateTickerForMarket("DX-Y.NYB", "FOREX")).toBe(true);
      expect(validateTickerForMarket("UUP", "FOREX")).toBe(true);
      expect(validateTickerForMarket("GOOGLE", "FOREX")).toBe(false);
      expect(validateTickerForMarket("AMAZON", "FOREX")).toBe(false);
      expect(validateTickerForMarket("AAPL", "FOREX")).toBe(false);

      // Edge cases: empty string and whitespace
      expect(validateTickerForMarket("", "US_EQUITIES")).toBe(false);
      expect(validateTickerForMarket("   ", "US_EQUITIES")).toBe(false);
    });
  });

  describe("Step 3: Horizon Selection & Educational Differentiation", () => {
    it("renders 1h, 1d, 1wk horizon cards and the mandatory holding vs duration educational card", () => {
      const html = ReactDOMServer.renderToString(
        <Step3HorizonSelection
          selectedHorizon="1d"
          onSelectHorizon={() => {}}
        />
      );

      expect(html).toContain("1 Hour (Intraday)");
      expect(html).toContain("1 Day (Daily Swing)");
      expect(html).toContain("1 Week (Macro Swing)");
      expect(html).toContain("Recommended Default");

      // Verify mandatory educational distinction banner
      expect(html).toContain("Crucial Distinction: Holding Horizon vs. Session Run Duration");
      expect(html).toContain("Governs the model&#x27;s predictive features, bar interval");
      expect(html).toContain("Governs how long the bot process stays alive");
    });
  });

  describe("Step 4: Session Duration & End Policy", () => {
    it("renders duration presets, custom duration, manual stop, and position end policy options", () => {
      const html = ReactDOMServer.renderToString(
        <Step4DurationPolicy
          durationType="FIXED"
          durationPresetMinutes={240}
          customDurationMinutes={null}
          sessionEndPolicy="CLOSE_ALL"
          onSetDurationType={() => {}}
          onSetDurationPreset={() => {}}
          onSetCustomDuration={() => {}}
          onSetSessionEndPolicy={() => {}}
        />
      );

      expect(html).toContain("1 Hour");
      expect(html).toContain("4 Hours");
      expect(html).toContain("1 Day");
      expect(html).toContain("1 Week");
      expect(html).toContain("Custom Duration");
      expect(html).toContain("Manual Stop (No Expiry)");

      // Policies
      expect(html).toContain("CLOSE_ALL (Liquidate to Cash)");
      expect(html).toContain("KEEP_OPEN (Preserve Positions)");
    });
  });

  describe("Step 5: Virtual Capital Allocation", () => {
    it("renders capital input with market currency symbol and enforce boundaries", () => {
      // USD Market
      const rawUsdHtml = ReactDOMServer.renderToString(
        <Step5CapitalAllocation
          allocatedCapital={50000}
          currency="USD"
          onSetAllocatedCapital={() => {}}
        />
      );
      const usdHtml = rawUsdHtml.replace(/<!-- -->/g, "");
      expect(usdHtml).toContain("$50,000");
      expect(usdHtml).toContain("Min: $1,000");
      expect(usdHtml).toContain("Max: $10,000,000");
      expect(usdHtml).toContain("Strict Paper-Trading Isolation &amp; Invariance Guarantee");

      // INR Market
      const rawInrHtml = ReactDOMServer.renderToString(
        <Step5CapitalAllocation
          allocatedCapital={500000}
          currency="INR"
          onSetAllocatedCapital={() => {}}
        />
      );
      const inrHtml = rawInrHtml.replace(/<!-- -->/g, "");
      expect(inrHtml).toMatch(/₹5,?00,?000/);
      expect(inrHtml).toContain("Min: ₹1,000");
      expect(inrHtml).toContain("Max: ₹10,000,000");
      // Verify ₹25L preset (accommodates Indian 25,00,000 or standard 2,500,000 formatting)
      expect(inrHtml).toMatch(/₹25,?00,?000|₹2,?500,?000/);
    });

    it("validates capital bounds, rejecting empty string, 0, negative, and below-minimum values (999)", () => {
      // Empty string / NaN
      const nanRes = validateWizardStep(5, {
        ...INITIAL_WIZARD_STATE,
        allocatedCapital: NaN,
      });
      expect(nanRes.isValid).toBe(false);
      expect(nanRes.errors.capital).toBe("Allocated virtual capital must be strictly positive.");
      expect(isWizardStepValid(5, { ...INITIAL_WIZARD_STATE, allocatedCapital: NaN })).toBe(false);

      // Zero capital ($0)
      const zeroRes = validateWizardStep(5, {
        ...INITIAL_WIZARD_STATE,
        allocatedCapital: 0,
      });
      expect(zeroRes.isValid).toBe(false);
      expect(zeroRes.errors.capital).toBe("Allocated virtual capital must be strictly positive.");
      expect(isWizardStepValid(5, { ...INITIAL_WIZARD_STATE, allocatedCapital: 0 })).toBe(false);

      // Negative capital (-$500)
      const negRes = validateWizardStep(5, {
        ...INITIAL_WIZARD_STATE,
        allocatedCapital: -500,
      });
      expect(negRes.isValid).toBe(false);
      expect(negRes.errors.capital).toBe("Allocated virtual capital must be strictly positive.");

      // Below lower bound ($999)
      const belowMinRes = validateWizardStep(5, {
        ...INITIAL_WIZARD_STATE,
        allocatedCapital: 999,
      });
      expect(belowMinRes.isValid).toBe(false);
      expect(belowMinRes.errors.capital).toContain("between 1,000 and 10,000,000 USD");

      // Exact lower bound ($1,000) -> valid
      const minRes = validateWizardStep(5, {
        ...INITIAL_WIZARD_STATE,
        allocatedCapital: 1000,
      });
      expect(minRes.isValid).toBe(true);
      expect(minRes.errors.capital).toBeUndefined();
      expect(isWizardStepValid(5, { ...INITIAL_WIZARD_STATE, allocatedCapital: 1000 })).toBe(true);

      // Exact upper bound ($10,000,000) -> valid
      const maxRes = validateWizardStep(5, {
        ...INITIAL_WIZARD_STATE,
        allocatedCapital: 10000000,
      });
      expect(maxRes.isValid).toBe(true);
      expect(maxRes.errors.capital).toBeUndefined();

      // Above upper bound ($10,000,001) -> invalid
      const aboveMaxRes = validateWizardStep(5, {
        ...INITIAL_WIZARD_STATE,
        allocatedCapital: 10000001,
      });
      expect(aboveMaxRes.isValid).toBe(false);
      expect(aboveMaxRes.errors.capital).toContain("between 1,000 and 10,000,000 USD");
    });

    it("renders error alert banner and out-of-range visual styling for invalid capital inputs", () => {
      // Out-of-range value (999) triggers rose border styling
      const outOfRangeHtml = ReactDOMServer.renderToString(
        <Step5CapitalAllocation
          allocatedCapital={999}
          currency="USD"
          errorMessage="Virtual capital must be between 1,000 and 10,000,000 USD."
          onSetAllocatedCapital={() => {}}
        />
      );
      expect(outOfRangeHtml).toContain("border-rose-500/80");
      expect(outOfRangeHtml).toContain("Virtual capital must be between 1,000 and 10,000,000 USD.");

      // Zero capital triggers rose border and strictly positive error message
      const zeroHtml = ReactDOMServer.renderToString(
        <Step5CapitalAllocation
          allocatedCapital={0}
          currency="USD"
          errorMessage="Allocated virtual capital must be strictly positive."
          onSetAllocatedCapital={() => {}}
        />
      );
      expect(zeroHtml).toContain("border-rose-500/80");
      expect(zeroHtml).toContain("Allocated virtual capital must be strictly positive.");
    });
  });

  describe("Step 6: Confirmation Review & Jump Edit Links", () => {
    it("renders comprehensive parameters summary and jump edit links for all 5 steps", () => {
      const rawHtml = ReactDOMServer.renderToString(
        <Step6Confirmation
          state={{
            ...INITIAL_WIZARD_STATE,
            market: "US_EQUITIES",
            instruments: ["NVDA", "AAPL", "MSFT"],
            horizon: "1d",
            durationType: "FIXED",
            durationPresetMinutes: 240,
            sessionEndPolicy: "CLOSE_ALL",
            allocatedCapital: 75000,
            currency: "USD",
          }}
          onJumpToStep={() => {}}
          onSetSessionName={() => {}}
        />
      );
      const html = rawHtml.replace(/<!-- -->/g, "");

      expect(html).toContain("Review Session Parameters &amp; Launch");
      expect(html).toContain("US_EQUITIES");
      expect(html).toContain("NVDA");
      expect(html).toContain("AAPL");
      expect(html).toContain("MSFT");
      expect(html).toContain("1 Day (Daily Swing / 15m &amp; 1h bars)");
      expect(html).toContain("4 Hours (240 min)");
      expect(html).toContain("CLOSE_ALL");
      expect(html).toContain("$75,000.00 USD");

      // Jump edit buttons
      expect(html).toContain("aria-label=\"Edit Market\"");
      expect(html).toContain("aria-label=\"Edit Basket\"");
      expect(html).toContain("aria-label=\"Edit Horizon\"");
      expect(html).toContain("aria-label=\"Edit Duration\"");
      expect(html).toContain("aria-label=\"Edit Capital\"");
    });
  });

  describe("Wizard Modal Orchestrator", () => {
    it("renders modal dialog with Stepper header when isOpen is true", () => {
      const rawHtml = ReactDOMServer.renderToString(
        <TradingSessionWizardModal
          isOpen={true}
          onClose={() => {}}
          onSessionStarted={() => {}}
        />
      );
      const html = rawHtml.replace(/<!-- -->/g, "");

      expect(html).toContain("SYNAPSE-TITAN Trading Session Setup Wizard");
      expect(html).toContain("Step 1 of 6");
      expect(html).toContain("Select Market Jurisdiction");
      expect(html).toContain("Next");
      expect(html).toContain("Cancel");
    });

    it("renders null when isOpen is false", () => {
      const html = ReactDOMServer.renderToString(
        <TradingSessionWizardModal
          isOpen={false}
          onClose={() => {}}
          onSessionStarted={() => {}}
        />
      );

      expect(html).toBe("");
    });
  });
});
