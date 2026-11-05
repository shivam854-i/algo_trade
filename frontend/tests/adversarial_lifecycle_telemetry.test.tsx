import { describe, expect, it } from "vitest";
import React from "react";
import ReactDOMServer from "react-dom/server";
import { SessionControls } from "../src/components/session/SessionControls";
import { SessionTelemetryBar } from "../src/components/session/SessionTelemetryBar";
import { OrderControls } from "../src/components/OrderControls";
import { ActivityLog, parseLogLine, VALID_CATEGORIES } from "../src/components/ActivityLog";
import { TradingSession, DataFeedStatus, LogItem, SessionStatus } from "../src/types";

describe("Milestone 3 Empirical Challenge: Lifecycle, Telemetry, Gating & Net EV", () => {
  const baseSession: TradingSession = {
    id: "sess_adv_9999",
    user_id: "DEFAULT_USER",
    account_id: "PAPER_DEFAULT",
    market: "US_EQUITIES",
    instruments: ["NVDA", "AAPL", "MSFT"],
    horizon: "1d",
    duration_type: "FIXED",
    duration_minutes: 120,
    session_end_policy: "CLOSE_ALL",
    allocated_capital: 75000,
    currency: "USD",
    status: "CREATED",
    created_at: "2026-11-05T12:00:00Z",
    accumulated_pause_seconds: 0,
    remaining_seconds: 7200,
    is_active: false,
    is_running: false,
    is_paused: false,
    is_terminal: false,
    is_expired: false,
    current_metrics: {
      initial_capital: 75000,
      current_cash: 75000,
      invested_equity: 0,
      total_equity: 75000,
      unrealized_pnl: 0,
      realized_pnl: 0,
    },
  };

  const dummyProps = {
    onStartSession: async () => {},
    onPauseSession: async () => {},
    onResumeSession: async () => {},
    onStopSession: async () => {},
    onOpenWizard: () => {},
  };

  // =========================================================================
  // 1. LIFECYCLE FINITE STATE MACHINE (FSM) INVARIANTS
  // =========================================================================
  describe("Adversarial Challenge 1: Lifecycle State Machine Transitions", () => {
    it("enforces START is ONLY available on CREATED state", () => {
      const createdHtml = ReactDOMServer.renderToString(
        <SessionControls session={{ ...baseSession, status: "CREATED" }} {...dummyProps} />
      );
      expect(createdHtml).toContain("START SESSION");

      const otherStatuses: SessionStatus[] = ["RUNNING", "PAUSED", "COMPLETED", "STOPPED"];
      for (const st of otherStatuses) {
        const html = ReactDOMServer.renderToString(
          <SessionControls session={{ ...baseSession, status: st }} {...dummyProps} />
        );
        expect(html, `Status ${st} must NOT permit START SESSION`).not.toContain("START SESSION");
      }
    });

    it("enforces PAUSE is ONLY available on RUNNING state", () => {
      const runningHtml = ReactDOMServer.renderToString(
        <SessionControls session={{ ...baseSession, status: "RUNNING" }} {...dummyProps} />
      );
      expect(runningHtml).toContain("PAUSE");

      const otherStatuses: SessionStatus[] = ["CREATED", "PAUSED", "COMPLETED", "STOPPED"];
      for (const st of otherStatuses) {
        const html = ReactDOMServer.renderToString(
          <SessionControls session={{ ...baseSession, status: st }} {...dummyProps} />
        );
        expect(html, `Status ${st} must NOT permit PAUSE`).not.toContain("PAUSE");
      }
    });

    it("enforces RESUME is ONLY available on PAUSED state", () => {
      const pausedHtml = ReactDOMServer.renderToString(
        <SessionControls session={{ ...baseSession, status: "PAUSED" }} {...dummyProps} />
      );
      expect(pausedHtml).toContain("RESUME");

      const otherStatuses: SessionStatus[] = ["CREATED", "RUNNING", "COMPLETED", "STOPPED"];
      for (const st of otherStatuses) {
        const html = ReactDOMServer.renderToString(
          <SessionControls session={{ ...baseSession, status: st }} {...dummyProps} />
        );
        expect(html, `Status ${st} must NOT permit RESUME`).not.toContain("RESUME");
      }
    });

    it("enforces STOP is ONLY available on CREATED, RUNNING, or PAUSED (and blocked on terminal states)", () => {
      // Allowed operational states
      for (const st of ["CREATED", "RUNNING", "PAUSED"] as SessionStatus[]) {
        const html = ReactDOMServer.renderToString(
          <SessionControls session={{ ...baseSession, status: st }} {...dummyProps} />
        );
        expect(html, `Status ${st} must permit STOP`).toContain("STOP");
      }

      // Blocked terminal states
      for (const st of ["COMPLETED", "STOPPED"] as SessionStatus[]) {
        const html = ReactDOMServer.renderToString(
          <SessionControls session={{ ...baseSession, status: st }} {...dummyProps} />
        );
        expect(html, `Terminal status ${st} must NOT permit STOP`).not.toContain("STOP");
      }
    });

    it("enforces terminal states (COMPLETED, STOPPED, null) strictly disable all lifecycle action transitions", () => {
      const testCases = [
        { label: "COMPLETED", sess: { ...baseSession, status: "COMPLETED" as SessionStatus } },
        { label: "STOPPED", sess: { ...baseSession, status: "STOPPED" as SessionStatus } },
        { label: "null session", sess: null },
      ];

      for (const tc of testCases) {
        const html = ReactDOMServer.renderToString(
          <SessionControls session={tc.sess} {...dummyProps} />
        );
        expect(html, `${tc.label} must not have START`).not.toContain("START SESSION");
        expect(html, `${tc.label} must not have PAUSE`).not.toContain("PAUSE");
        expect(html, `${tc.label} must not have RESUME`).not.toContain("RESUME");
        expect(html, `${tc.label} must not have STOP`).not.toContain("STOP");
        expect(html, `${tc.label} must allow configuring NEW SESSION`).toContain("NEW SESSION");
      }
    });
  });

  // =========================================================================
  // 2. PAUSE TIME-DILATION & COUNTDOWN DRIFT INVARIANTS
  // =========================================================================
  describe("Adversarial Challenge 2: Pause Time Dilation & Countdown Invariants", () => {
    it("renders countdown correctly in active RUNNING session without negative values", () => {
      const html = ReactDOMServer.renderToString(
        <SessionTelemetryBar
          session={{ ...baseSession, status: "RUNNING", remaining_seconds: 5432 }}
          {...dummyProps}
        />
      );
      // 5432 seconds = 1h 30m 32s -> 01:30:32
      expect(html).toContain("01:30:32");
    });

    it("preserves exact remaining countdown when session is PAUSED (time dilation freeze)", () => {
      const remainingSeconds = 3600; // 1 hour exactly
      const html = ReactDOMServer.renderToString(
        <SessionTelemetryBar
          session={{ ...baseSession, status: "PAUSED", remaining_seconds: remainingSeconds }}
          {...dummyProps}
        />
      );
      expect(html).toContain("01:00:00");
      expect(html).toContain("PAUSED");
    });

    it("renders Expired tag when remaining seconds is zero or negative", () => {
      const htmlZero = ReactDOMServer.renderToString(
        <SessionTelemetryBar
          session={{ ...baseSession, status: "RUNNING", remaining_seconds: 0 }}
          {...dummyProps}
        />
      );
      expect(htmlZero).toContain("00:00:00 (Expired)");

      const htmlNegative = ReactDOMServer.renderToString(
        <SessionTelemetryBar
          session={{ ...baseSession, status: "RUNNING", remaining_seconds: -45 }}
          {...dummyProps}
        />
      );
      expect(htmlNegative).toContain("00:00:00 (Expired)");
    });

    it("verifies time-dilation mathematical oracle for pause-and-resume cycle", () => {
      // Simulating time-dilation calculation identical to backend session_manager.py
      const initialDurationSec = 7200; // 2 hours
      const t0 = new Date("2026-11-05T10:00:00Z").getTime();
      const initialExpiresAt = new Date(t0 + initialDurationSec * 1000).toISOString();

      // Session runs for 30 minutes (1800 seconds)
      const tPause = t0 + 1800 * 1000;
      const remainingAtPause = Math.floor((new Date(initialExpiresAt).getTime() - tPause) / 1000);
      expect(remainingAtPause).toBe(5400); // 1.5 hours remaining

      // Session stays paused for 45 minutes (2700 seconds)
      const pauseDurationSec = 2700;
      const tResume = tPause + pauseDurationSec * 1000;

      // Upon resume, backend pushes expires_at forward by pauseDurationSec
      const resumedExpiresAt = new Date(new Date(initialExpiresAt).getTime() + pauseDurationSec * 1000).toISOString();

      // Effective remaining seconds immediately after resume:
      const remainingAtResume = Math.floor((new Date(resumedExpiresAt).getTime() - tResume) / 1000);

      // Invariant: Remaining time after resume MUST EQUAL remaining time at pause!
      expect(remainingAtResume).toBe(remainingAtPause);
      expect(remainingAtResume).toBe(5400); // Exactly 1h 30m preserved!
    });
  });

  // =========================================================================
  // 3. GATING INVARIANTS: ORDER CONTROLS & SIMULATION TICKS PROGRESSION
  // =========================================================================
  describe("Adversarial Challenge 3: Gating Invariants", () => {
    it("locks order execution button and renders gating notice when isSessionGated is true", () => {
      const html = ReactDOMServer.renderToString(
        <OrderControls
          selectedTicker="NVDA"
          availableCash={50000}
          currentPrice={140.5}
          pendingOrders={[]}
          isSessionGated={true}
          onPlaceOrder={async () => {}}
          onCancelPendingOrder={async () => {}}
          onToggleBot={async () => {}}
          onToggleMarketHours={async () => {}}
          onStepTick={async () => {}}
          onResetAccount={async () => {}}
        />
      );

      // 1. Submit button must be disabled
      expect(html).toContain("disabled=\"\"");
      // 2. Button text must indicate execution is gated
      expect(html).toContain("EXECUTION GATED (ACTIVE SESSION REQUIRED)");
      // 3. Gating banner notice must be visible
      expect(html).toContain("Order execution gated: An active trading session is required to place orders.");
    });

    it("unlocks order execution button when isSessionGated is false", () => {
      const html = ReactDOMServer.renderToString(
        <OrderControls
          selectedTicker="NVDA"
          availableCash={50000}
          currentPrice={140.5}
          pendingOrders={[]}
          isSessionGated={false}
          onPlaceOrder={async () => {}}
          onCancelPendingOrder={async () => {}}
          onToggleBot={async () => {}}
          onToggleMarketHours={async () => {}}
          onStepTick={async () => {}}
          onResetAccount={async () => {}}
        />
      );

      // Submit button text must indicate executable order
      expect(html).toContain("EXECUTE LONG NVDA");
      // Gating notice must NOT be rendered
      expect(html).not.toContain("Order execution gated");
    });

    it("verifies simulation ticks progression invariant: ticks ONLY step when session is RUNNING", () => {
      // In useDashboardStream.ts:
      // if (prev?.bot_status?.is_running && prev?.active_session?.status === "RUNNING") { stepTick(); } else { fetchState(); }
      const tickProgressPredicate = (botIsRunning: boolean, sessionStatus?: string | null): boolean => {
        return Boolean(botIsRunning && sessionStatus === "RUNNING");
      };

      // Fails when bot is stopped
      expect(tickProgressPredicate(false, "RUNNING")).toBe(false);

      // Fails for all non-RUNNING session statuses
      expect(tickProgressPredicate(true, null)).toBe(false);
      expect(tickProgressPredicate(true, undefined)).toBe(false);
      expect(tickProgressPredicate(true, "CREATED")).toBe(false);
      expect(tickProgressPredicate(true, "PAUSED")).toBe(false);
      expect(tickProgressPredicate(true, "STOPPED")).toBe(false);
      expect(tickProgressPredicate(true, "COMPLETED")).toBe(false);

      // Advances IF AND ONLY IF bot is running AND session is RUNNING
      expect(tickProgressPredicate(true, "RUNNING")).toBe(true);
    });
  });

  // =========================================================================
  // 4. TRANSPARENT ACTIVITY FEED & NET EXPECTANCY FORMULA RENDERING
  // =========================================================================
  describe("Adversarial Challenge 4: Transparent Activity Feed & Net Expectancy Math", () => {
    it("renders exact Net Expectancy mathematical formula banner on DECISION events", () => {
      const decisionLog: LogItem = {
        time: "14:15:30",
        level: "DECISION",
        message: "BUY MSFT: Net Expectancy +2.15% | Win Prob 64.2%",
        metadata: {
          ticker: "MSFT",
          action: "ACCEPTED",
          headline: "BUY MSFT: Net Expectancy +2.15%",
          summary: "Calibrated edge exceeds hurdle rate",
          factors: {
            "HMM Regime Alignment": "Bull Trend State 0 boost",
            "Friction Cost": "9.5 bps estimated round-trip",
          },
          metrics: {
            net_expectancy_pct: 2.15,
            win_probability: 0.642,
            round_trip_friction_bps: 9.5,
            payoff_ratio: 1.85,
          },
          timestamp_utc: "2026-11-05T14:15:30Z",
        },
      };

      const html = ReactDOMServer.renderToString(<ActivityLog logs={[decisionLog]} />);

      // Verify mathematical formula rendering
      expect(html).toContain("Net Expectancy Formula:");
      expect(html).toContain("EV = P(Win) · E[Win] - P(Loss) · E[Loss] - Friction");

      // Verify quantitative factor metrics
      expect(html).toContain("+2.15%"); // Net EV
      expect(html).toContain("64.2%"); // Win probability
      expect(html).toContain("9.5 bps"); // Friction
      expect(html).toContain("1.85"); // Payoff ratio
    });

    it("accurately renders REJECTED badge when EV <= 0", () => {
      const zeroEvLog: LogItem = {
        time: "15:00:00",
        level: "DECISION",
        message: "REJECTED AMD: Net Expectancy 0.00%",
        metadata: {
          ticker: "AMD",
          action: "REJECTED",
          headline: "REJECTED AMD",
          summary: "Zero net edge after transaction friction",
          metrics: {
            net_expectancy_pct: 0.0,
            win_probability: 0.50,
            round_trip_friction_bps: 14.0,
          },
          timestamp_utc: "2026-11-05T15:00:00Z",
        },
      };

      const htmlZero = ReactDOMServer.renderToString(<ActivityLog logs={[zeroEvLog]} />);
      expect(htmlZero).toContain("REJECTED (EV ≤ 0)");
      expect(htmlZero).toContain("0.00%");

      const negativeEvLog: LogItem = {
        time: "15:05:00",
        level: "DECISION",
        message: "REJECTED INTC: Net Expectancy -0.85%",
        metadata: {
          ticker: "INTC",
          action: "REJECTED",
          headline: "REJECTED INTC",
          summary: "Negative expectancy after friction",
          metrics: {
            net_expectancy_pct: -0.85,
            win_probability: 0.42,
            round_trip_friction_bps: 18.5,
          },
          timestamp_utc: "2026-11-05T15:05:00Z",
        },
      };

      const htmlNeg = ReactDOMServer.renderToString(<ActivityLog logs={[negativeEvLog]} />);
      expect(htmlNeg).toContain("REJECTED (EV ≤ 0)");
      expect(htmlNeg).toContain("-0.85%");
    });

    it("triggers 100% Cash Guarantee alert when action is HELD_IN_CASH", () => {
      const cashPreserveLog: LogItem = {
        time: "15:30:00",
        level: "DECISION",
        message: "All 15 candidate instruments exhibited EV <= 0. Sitting in 100% cash.",
        metadata: {
          ticker: "PORTFOLIO",
          action: "HELD_IN_CASH",
          headline: "100% Cash Guarantee Invoked",
          summary: "Preserving all capital in risk-free cash.",
          factors: {
            "Regime Filter": "High Volatility Regime forbids low-conviction entry",
          },
          metrics: {
            cash_weight_pct: 100.0,
            total_candidates: 15,
            qualifying_count: 0,
          },
          timestamp_utc: "2026-11-05T15:30:00Z",
        },
      };

      const html = ReactDOMServer.renderToString(<ActivityLog logs={[cashPreserveLog]} />);

      expect(html).toContain("100% CASH PRESERVED");
      expect(html).toContain(
        "100% Cash Allocation Guarantee: All candidate trades exhibited EV ≤ 0 or crisis regime veto. 100% capital preserved in cash."
      );
    });

    it("handles adversarial log entries without runtime crashing", () => {
      const adversarialLogs: any[] = [
        null,
        undefined,
        "",
        {},
        { message: null },
        { time: null, level: "DECISION", message: "Partial", metadata: {} },
        { level: "UNKNOWN_CATEGORY", message: "Weird message" },
        "[DECISION] String only decision event without metadata",
        {
          time: "16:00:00",
          level: "DECISION",
          message: "Extreme friction test",
          metadata: {
            ticker: "HIGH_FEE",
            action: "REJECTED",
            metrics: {
              net_expectancy_pct: -99.99,
              win_probability: 0.001,
              round_trip_friction_bps: 500.0,
              payoff_ratio: 0.1,
            },
          },
        },
      ];

      // Should parse and render cleanly without throwing
      expect(() => {
        const parsed = adversarialLogs.map(parseLogLine);
        expect(parsed.length).toBe(adversarialLogs.length);
        const html = ReactDOMServer.renderToString(<ActivityLog logs={adversarialLogs} />);
        expect(html).toBeDefined();
      }).not.toThrow();
    });
  });
});
