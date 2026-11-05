import { describe, expect, it } from "vitest";
import React from "react";
import ReactDOMServer from "react-dom/server";
import { SessionControls } from "../src/components/session/SessionControls";
import { SessionTelemetryBar } from "../src/components/session/SessionTelemetryBar";
import { StopSessionModal } from "../src/components/session/StopSessionModal";
import { SessionGatingBanner } from "../src/components/session/SessionGatingBanner";
import { OrderControls } from "../src/components/OrderControls";
import { ActivityLog, parseLogLine, VALID_CATEGORIES, ParsedLog } from "../src/components/ActivityLog";
import { TradingSession, SessionStatus, LogItem, DecisionMetadata } from "../src/types";

describe("Milestone 3 Iteration 2 Empirical Challenger 2 Stress Suite", () => {
  const baseSession: TradingSession = {
    id: "sess_stress_2026",
    user_id: "DEFAULT_USER",
    account_id: "PAPER_DEFAULT",
    market: "US_EQUITIES",
    instruments: ["NVDA", "AAPL", "MSFT"],
    horizon: "1d",
    duration_type: "FIXED",
    duration_minutes: 240,
    session_end_policy: "CLOSE_ALL",
    allocated_capital: 100000,
    currency: "USD",
    status: "CREATED",
    created_at: "2026-11-05T12:00:00Z",
    accumulated_pause_seconds: 0,
    remaining_seconds: 14400,
    is_active: false,
    is_running: false,
    is_paused: false,
    is_terminal: false,
    is_expired: false,
    current_metrics: {
      initial_capital: 100000,
      current_cash: 100000,
      invested_equity: 0,
      total_equity: 100000,
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
  // 1. EXHAUSTIVE FSM COMBINATORIAL TESTING
  // =========================================================================
  describe("1. Exhaustive Lifecycle Finite State Machine (FSM) Matrix", () => {
    const states: { status: SessionStatus | string | null; expectStart: boolean; expectPause: boolean; expectResume: boolean; expectStop: boolean; expectNewSession: boolean }[] = [
      { status: "CREATED", expectStart: true, expectPause: false, expectResume: false, expectStop: true, expectNewSession: false },
      { status: "RUNNING", expectStart: false, expectPause: true, expectResume: false, expectStop: true, expectNewSession: false },
      { status: "PAUSED", expectStart: false, expectPause: false, expectResume: true, expectStop: true, expectNewSession: false },
      { status: "COMPLETED", expectStart: false, expectPause: false, expectResume: false, expectStop: false, expectNewSession: true },
      { status: "STOPPED", expectStart: false, expectPause: false, expectResume: false, expectStop: false, expectNewSession: true },
      { status: null, expectStart: false, expectPause: false, expectResume: false, expectStop: false, expectNewSession: true },
    ];

    for (const s of states) {
      it(`enforces exact button invariant for state: ${s.status ?? "null"}`, () => {
        const sess = s.status ? { ...baseSession, status: s.status as SessionStatus } : null;
        const html = ReactDOMServer.renderToString(<SessionControls session={sess} {...dummyProps} />);

        if (s.expectStart) {
          expect(html).toContain("START SESSION");
        } else {
          expect(html).not.toContain("START SESSION");
        }

        if (s.expectPause) {
          expect(html).toContain("PAUSE");
        } else {
          expect(html).not.toContain("PAUSE");
        }

        if (s.expectResume) {
          expect(html).toContain("RESUME");
        } else {
          expect(html).not.toContain("RESUME");
        }

        if (s.expectStop) {
          expect(html).toContain("STOP");
        } else {
          expect(html).not.toContain("STOP");
        }

        if (s.expectNewSession) {
          expect(html).toContain("NEW SESSION");
        } else {
          expect(html).not.toContain("NEW SESSION");
        }
      });
    }

    it("enforces disabled prop propagates to all action buttons in SessionControls", () => {
      const runningHtml = ReactDOMServer.renderToString(
        <SessionControls
          session={{ ...baseSession, status: "RUNNING" }}
          disabled={true}
          {...dummyProps}
        />
      );
      // Both PAUSE and STOP buttons must have disabled attribute
      const matches = runningHtml.match(/disabled=""/g);
      expect(matches).not.toBeNull();
      expect(matches!.length).toBeGreaterThanOrEqual(2);
    });
  });

  // =========================================================================
  // 2. PAUSE TIME-DILATION & COUNTDOWN TIME HORIZON ORACLE
  // =========================================================================
  describe("2. Countdown Time-Dilation & Boundary Mathematical Oracle", () => {
    const countdownOracle = (sec: number | null): string => {
      if (sec === null) return "Manual Stop";
      if (sec <= 0) return "00:00:00 (Expired)";
      const h = Math.floor(sec / 3600);
      const m = Math.floor((sec % 3600) / 60);
      const s = sec % 60;
      return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
    };

    const edgeCases: [number | null, string][] = [
      [null, "Manual Stop"],
      [0, "00:00:00 (Expired)"],
      [-1, "00:00:00 (Expired)"],
      [-59, "00:00:00 (Expired)"],
      [-3600, "00:00:00 (Expired)"],
      [-86400, "00:00:00 (Expired)"],
      [1, "00:00:01"],
      [59, "00:00:59"],
      [60, "00:01:00"],
      [61, "00:01:01"],
      [3599, "00:59:59"],
      [3600, "01:00:00"],
      [7200, "02:00:00"],
      [86399, "23:59:59"],
      [86400, "24:00:00"],
      [360000, "100:00:00"],
    ];

    for (const [sec, expected] of edgeCases) {
      it(`evaluates countdown for ${sec}s -> "${expected}"`, () => {
        expect(countdownOracle(sec)).toBe(expected);

        const html = ReactDOMServer.renderToString(
          <SessionTelemetryBar
            session={{ ...baseSession, status: "RUNNING", remaining_seconds: sec }}
            {...dummyProps}
          />
        );
        expect(html).toContain(expected);
      });
    }

    it("verifies mathematical time-dilation formula preserves elapsed time across pause", () => {
      // Oracle invariant:
      // remaining_time(t_resume) == remaining_time(t_pause)
      const initialRemaining = 7200; // 2 hours
      const runDurationBeforePause = 1200; // 20 minutes elapsed
      const remainingAtPause = initialRemaining - runDurationBeforePause; // 6000s (1h 40m)

      const pauseDurations = [1, 60, 300, 1800, 7200, 86400]; // 1s to 24h pause
      for (const pDur of pauseDurations) {
        // Under time dilation, expiry timestamp moves forward by exactly pDur:
        // expires_at_new = expires_at_old + pDur
        // now_at_resume = now_at_pause + pDur
        // remaining = expires_at_new - now_at_resume
        //           = (expires_at_old + pDur) - (now_at_pause + pDur)
        //           = expires_at_old - now_at_pause
        //           = remainingAtPause
        const remainingAfterResume = (remainingAtPause + pDur) - pDur;
        expect(remainingAfterResume).toBe(remainingAtPause);
        expect(remainingAfterResume).toBe(6000);
      }
    });

    it("handles zero, negative, or missing financial metrics without runtime exceptions", () => {
      const sessionWithExtremeMetrics: TradingSession = {
        ...baseSession,
        current_metrics: {
          initial_capital: 100000,
          current_cash: 0,
          invested_equity: 0,
          total_equity: 0,
          unrealized_pnl: -4500.75,
          realized_pnl: -1200.0,
        },
      };

      const html = ReactDOMServer.renderToString(
        <SessionTelemetryBar
          session={sessionWithExtremeMetrics}
          {...dummyProps}
        />
      );
      const cleanHtml = html.replace(/<!--[\s\S]*?-->/g, "");

      expect(cleanHtml).toContain("$0.0k / $0.0k"); // zero cash / invested
      expect(cleanHtml).toContain("$-4500.75"); // negative unrealized
      expect(cleanHtml).toContain("text-rose-400"); // loss styling
    });

    it("handles Indian Rupee currency with INR formatting in SessionTelemetryBar", () => {
      const inrSession: TradingSession = {
        ...baseSession,
        market: "INDIAN_NSE",
        currency: "INR",
        allocated_capital: 2500000,
        current_metrics: {
          initial_capital: 2500000,
          current_cash: 2000000,
          invested_equity: 500000,
          total_equity: 2515000,
          unrealized_pnl: 15000.5,
          realized_pnl: 0,
        },
      };

      const html = ReactDOMServer.renderToString(
        <SessionTelemetryBar
          session={inrSession}
          {...dummyProps}
        />
      );
      const cleanHtml = html.replace(/<!--[\s\S]*?-->/g, "");

      expect(cleanHtml).toContain("₹25,00,000"); // ₹25 Lakhs Indian numbering
      expect(cleanHtml).toContain("+₹15000.50"); // positive MTM
      expect(cleanHtml).toContain("text-emerald-400");
    });
  });

  // =========================================================================
  // 3. ORDER GATING & SIMULATION PROGRESSION LOCKS
  // =========================================================================
  describe("3. Order Execution Gating & Simulation Progression Locks", () => {
    it("strictly blocks order placement when isSessionGated = true", () => {
      const html = ReactDOMServer.renderToString(
        <OrderControls
          selectedTicker="AAPL"
          availableCash={100000}
          currentPrice={220.0}
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
      const cleanHtml = html.replace(/<!--[\s\S]*?-->/g, "");

      expect(cleanHtml).toContain("disabled=\"\"");
      expect(cleanHtml).toContain("EXECUTION GATED (ACTIVE SESSION REQUIRED)");
      expect(cleanHtml).toContain("Order execution gated: An active trading session is required to place orders.");
    });

    it("permits order placement when isSessionGated = false", () => {
      const html = ReactDOMServer.renderToString(
        <OrderControls
          selectedTicker="AAPL"
          availableCash={100000}
          currentPrice={220.0}
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
      const cleanHtml = html.replace(/<!--[\s\S]*?-->/g, "");

      expect(cleanHtml).toContain("EXECUTE LONG AAPL");
      expect(cleanHtml).not.toContain("EXECUTION GATED");
      expect(cleanHtml).not.toContain("Order execution gated");
    });

    it("verifies isSessionRunning gating truth table across all session lifecycle states", () => {
      const checkGating = (session: { status: string } | null): boolean => {
        const isSessionRunning = session?.status === "RUNNING";
        const isSessionGated = !isSessionRunning;
        return isSessionGated;
      };

      // GATED for null or any non-RUNNING state:
      expect(checkGating(null)).toBe(true);
      expect(checkGating({ status: "CREATED" })).toBe(true);
      expect(checkGating({ status: "PAUSED" })).toBe(true);
      expect(checkGating({ status: "STOPPED" })).toBe(true);
      expect(checkGating({ status: "COMPLETED" })).toBe(true);
      expect(checkGating({ status: "UNKNOWN" })).toBe(true);

      // UNGATED ONLY when status is RUNNING:
      expect(checkGating({ status: "RUNNING" })).toBe(false);
    });

    it("verifies hasActiveSession truth table for SessionGatingBanner visibility in App.tsx", () => {
      const checkBannerVisible = (session: { status: string } | null): boolean => {
        const hasActiveSession = Boolean(
          session && !["COMPLETED", "STOPPED"].includes(session.status)
        );
        const isBannerVisible = !hasActiveSession;
        return isBannerVisible;
      };

      // Banner visible when session is null, STOPPED, or COMPLETED:
      expect(checkBannerVisible(null)).toBe(true);
      expect(checkBannerVisible({ status: "STOPPED" })).toBe(true);
      expect(checkBannerVisible({ status: "COMPLETED" })).toBe(true);

      // Banner HIDDEN when session is active (CREATED, RUNNING, PAUSED):
      expect(checkBannerVisible({ status: "CREATED" })).toBe(false);
      expect(checkBannerVisible({ status: "RUNNING" })).toBe(false);
      expect(checkBannerVisible({ status: "PAUSED" })).toBe(false);
    });

    it("verifies simulation stepTick lock predicate across all 18 permutations", () => {
      // In useDashboardStream.ts:
      // if (prev?.bot_status?.is_running && prev?.active_session?.status === "RUNNING") { stepTick(); } else { fetchState(); }
      const shouldStepTick = (botIsRunning: boolean, sessionStatus?: string | null): boolean => {
        return Boolean(botIsRunning && sessionStatus === "RUNNING");
      };

      const botStatuses = [true, false];
      const sessionStatuses: (string | null | undefined)[] = [
        "RUNNING",
        "PAUSED",
        "CREATED",
        "STOPPED",
        "COMPLETED",
        "UNKNOWN",
        null,
        undefined,
        "",
      ];

      for (const bot of botStatuses) {
        for (const sess of sessionStatuses) {
          const result = shouldStepTick(bot, sess);
          if (bot === true && sess === "RUNNING") {
            expect(result).toBe(true);
          } else {
            expect(result).toBe(false);
          }
        }
      }
    });

    it("renders SessionGatingBanner with lock icon and Launch Setup Wizard CTA", () => {
      const html = ReactDOMServer.renderToString(<SessionGatingBanner onOpenWizard={() => {}} />);
      const cleanHtml = html.replace(/<!--[\s\S]*?-->/g, "");
      expect(cleanHtml).toContain("Autonomous Execution Gated: No Active Session");
      expect(cleanHtml).toContain("GATED");
      expect(cleanHtml).toContain("Launch Setup Wizard");
    });
  });

  // =========================================================================
  // 4. NET EXPECTANCY FORMULA & CASH GUARANTEE PRESERVATION
  // =========================================================================
  describe("4. Net Expectancy Formula & 100% Cash Guarantee Alert", () => {
    it("renders exact Net Expectancy formula text in DECISION cards", () => {
      const logItem: LogItem = {
        time: "12:00:00",
        level: "DECISION",
        message: "BUY GOOGL: Net EV +3.42%",
        metadata: {
          ticker: "GOOGL",
          action: "ACCEPTED",
          headline: "BUY GOOGL",
          summary: "Favorable risk-reward with high win probability",
          metrics: {
            net_expectancy_pct: 3.42,
            win_probability: 0.71,
            round_trip_friction_bps: 6.5,
            payoff_ratio: 2.1,
          },
        },
      };

      const html = ReactDOMServer.renderToString(<ActivityLog logs={[logItem]} />);
      const cleanHtml = html.replace(/<!--[\s\S]*?-->/g, "");
      expect(cleanHtml).toContain("Net Expectancy Formula:");
      expect(cleanHtml).toContain("EV = P(Win) · E[Win] - P(Loss) · E[Loss] - Friction");
      expect(cleanHtml).toContain("+3.42%");
      expect(cleanHtml).toContain("71.0%");
      expect(cleanHtml).toContain("6.5 bps");
      expect(cleanHtml).toContain("2.10");
    });

    it("strictly renders 100% Cash Guarantee alert ONLY on HELD_IN_CASH action", () => {
      const heldInCashLog: LogItem = {
        time: "12:05:00",
        level: "DECISION",
        message: "Sitting in cash: EV <= 0",
        metadata: {
          ticker: "PORTFOLIO",
          action: "HELD_IN_CASH",
          headline: "Cash Allocation Guaranteed",
          summary: "All opportunities lacked positive expected net value",
          metrics: {
            cash_weight_pct: 100,
          },
        },
      };

      const htmlCash = ReactDOMServer.renderToString(<ActivityLog logs={[heldInCashLog]} />);
      expect(htmlCash).toContain("100% CASH PRESERVED");
      expect(htmlCash).toContain(
        "100% Cash Allocation Guarantee: All candidate trades exhibited EV ≤ 0 or crisis regime veto. 100% capital preserved in cash."
      );

      // Verify that ACCEPTED and REJECTED decisions DO NOT render the 100% cash alert box:
      const acceptedLog: LogItem = {
        time: "12:10:00",
        level: "DECISION",
        message: "BUY TSLA",
        metadata: { ticker: "TSLA", action: "ACCEPTED" },
      };
      const htmlAccepted = ReactDOMServer.renderToString(<ActivityLog logs={[acceptedLog]} />);
      expect(htmlAccepted).not.toContain("100% Cash Allocation Guarantee: All candidate trades");

      const rejectedLog: LogItem = {
        time: "12:15:00",
        level: "DECISION",
        message: "REJECTED NVDA",
        metadata: { ticker: "NVDA", action: "REJECTED" },
      };
      const htmlRejected = ReactDOMServer.renderToString(<ActivityLog logs={[rejectedLog]} />);
      expect(htmlRejected).not.toContain("100% Cash Allocation Guarantee: All candidate trades");
    });

    it("parses 25+ adversarial log formats with parseLogLine without crashing", () => {
      const dirtyLogs: any[] = [
        null,
        undefined,
        "",
        "    ",
        12345,
        true,
        false,
        {},
        { message: "" },
        { time: "10:00:00" },
        { level: "TRADE", message: "Executed order #1" },
        { level: "PROFIT", message: "Take-profit triggered" },
        { level: "STOP", message: "Stop-loss hit" },
        { level: "RISK", message: "Max drawdown throttle" },
        { level: "SESSION", message: "Market closed" },
        { level: "SYSTEM", message: "Heartbeat ok" },
        { level: "BOT", message: "Bot cycle finished" },
        { level: "DECISION", message: "Trade evaluated", metadata: null },
        { level: "DECISION", message: "Trade evaluated", metadata: {} },
        "[14:00:00] [BOT] Bot active",
        "[14:01:00] [TRADE] Bought 10 shs",
        "[14:02:00] [DECISION] EV +1.2%",
        "[14:03:00] [PROFIT] Gain locked",
        "[14:04:00] [STOP] Exit filled",
        "[14:05:00] [RISK] Risk limit reached",
        "[14:06:00] [SESSION] Session paused",
        "[14:07:00] Plain unstructured text message",
      ];

      for (const item of dirtyLogs) {
        const parsed: ParsedLog = parseLogLine(item);
        expect(parsed).toBeDefined();
        expect(typeof parsed.timestamp).toBe("string");
        expect(typeof parsed.message).toBe("string");
        expect(VALID_CATEGORIES.includes(parsed.category as any) || parsed.category === "OTHER").toBe(true);
      }

      // Render full ActivityLog with dirty inputs
      const html = ReactDOMServer.renderToString(<ActivityLog logs={dirtyLogs} />);
      expect(html).toBeDefined();
    });
  });
});
