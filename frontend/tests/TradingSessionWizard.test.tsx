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
      const html = ReactDOMServer.renderToString(
        <Step2InstrumentSelection
          market="US_EQUITIES"
          instruments={["NVDA", "AAPL", "MSFT"]}
          isRecommending={false}
          onAddInstrument={() => {}}
          onRemoveInstrument={() => {}}
          onRequestRecommendations={() => {}}
        />
      );

      expect(html).toContain("NVDA");
      expect(html).toContain("AAPL");
      expect(html).toContain("MSFT");
      expect(html).toContain("Selected Basket: <strong class=\"text-slate-200\">3</strong> / 20 symbols");
      expect(html).toContain("Auto-select for me");
    });

    it("displays quantitative selection rationale and multi-factor badges when recommendations are present", () => {
      const html = ReactDOMServer.renderToString(
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

      expect(html).toContain("Quantitative Selection Rationale (UniverseSelector)");
      expect(html).toContain("Auto-selected 5 high-liquidity US instruments");
      expect(html).toContain("Data Quality ≥ 90%");
      expect(html).toContain("Liquidity ADV Gate Passed");
      expect(html).toContain("Spread ≤ 25 bps");
      expect(html).toContain("Q: 98%");
    });

    it("validates ticker syntax per market jurisdiction", () => {
      // US Equities: AAPL is valid, RELIANCE.NS is invalid
      expect(validateTickerForMarket("AAPL", "US_EQUITIES")).toBe(true);
      expect(validateTickerForMarket("NVDA", "US_EQUITIES")).toBe(true);

      // Indian NSE: RELIANCE.NS is valid, AAPL is invalid
      expect(validateTickerForMarket("RELIANCE.NS", "INDIAN_NSE")).toBe(true);
      expect(validateTickerForMarket("TCS.BO", "INDIAN_NSE")).toBe(true);
      expect(validateTickerForMarket("AAPL", "INDIAN_NSE")).toBe(false);

      // Crypto: BTC-USD is valid, AAPL is invalid
      expect(validateTickerForMarket("BTC-USD", "CRYPTO")).toBe(true);
      expect(validateTickerForMarket("ETH-USDT", "CRYPTO")).toBe(true);
      expect(validateTickerForMarket("AAPL", "CRYPTO")).toBe(false);

      // Commodities: GC=F is valid
      expect(validateTickerForMarket("GC=F", "COMMODITIES")).toBe(true);
      expect(validateTickerForMarket("SI=F", "COMMODITIES")).toBe(true);

      // Forex: EURUSD=X is valid
      expect(validateTickerForMarket("EURUSD=X", "FOREX")).toBe(true);
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
      const usdHtml = ReactDOMServer.renderToString(
        <Step5CapitalAllocation
          allocatedCapital={50000}
          currency="USD"
          onSetAllocatedCapital={() => {}}
        />
      );
      expect(usdHtml).toContain("$50,000");
      expect(usdHtml).toContain("Min: $1,000");
      expect(usdHtml).toContain("Max: $10,000,000");
      expect(usdHtml).toContain("Strict Paper-Trading Isolation &amp; Invariance Guarantee");

      // INR Market
      const inrHtml = ReactDOMServer.renderToString(
        <Step5CapitalAllocation
          allocatedCapital={500000}
          currency="INR"
          onSetAllocatedCapital={() => {}}
        />
      );
      expect(inrHtml).toMatch(/₹5,?00,?000/);
      expect(inrHtml).toContain("Min: ₹1,000");
      expect(inrHtml).toContain("Max: ₹10,000,000");
    });
  });

  describe("Step 6: Confirmation Review & Jump Edit Links", () => {
    it("renders comprehensive parameters summary and jump edit links for all 5 steps", () => {
      const html = ReactDOMServer.renderToString(
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
      const html = ReactDOMServer.renderToString(
        <TradingSessionWizardModal
          isOpen={true}
          onClose={() => {}}
          onSessionStarted={() => {}}
        />
      );

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
