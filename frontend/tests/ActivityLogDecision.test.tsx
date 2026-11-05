import { describe, expect, it } from "vitest";
import React from "react";
import ReactDOMServer from "react-dom/server";
import { ActivityLog, parseLogLine, VALID_CATEGORIES } from "../src/components/ActivityLog";
import { LogItem } from "../src/types";

describe("Milestone 3: ActivityLog DECISION Category & Net Expectancy Formula", () => {
  it("includes DECISION in VALID_CATEGORIES list", () => {
    expect(VALID_CATEGORIES).toContain("DECISION");
  });

  it("safely parses structured DECISION events with quantitative metadata", () => {
    const decisionLog: LogItem = {
      time: "14:30:15",
      level: "DECISION",
      message: "BUY NVDA: Net Expectancy +1.84% | Win Prob 62.5%",
      metadata: {
        ticker: "NVDA",
        action: "ACCEPTED",
        headline: "BUY NVDA: Net Expectancy +1.84%",
        summary: "Opportunity meets risk-adjusted edge hurdles with calibrated win probability of 62.5%.",
        factors: {
          "Regime Multiplier": "1.20x (Trending State 0)",
          "Transaction Friction": "8.5 bps estimated round-trip",
        },
        metrics: {
          net_expectancy_pct: 1.84,
          win_probability: 0.625,
          conservative_win_prob: 0.581,
          round_trip_friction_bps: 8.5,
          payoff_ratio: 1.78,
          allocation_weight_pct: 15.0,
        },
        timestamp_utc: "2026-11-05T14:30:15Z",
      },
    };

    const parsed = parseLogLine(decisionLog);
    expect(parsed.category).toBe("DECISION");
    expect(parsed.timestamp).toBe("14:30:15");
    expect(parsed.message).toBe("BUY NVDA: Net Expectancy +1.84% | Win Prob 62.5%");
    expect(parsed.metadata).toBeDefined();
    expect(parsed.metadata?.action).toBe("ACCEPTED");
    expect(parsed.metadata?.metrics.net_expectancy_pct).toBe(1.84);
  });

  it("safely parses bracketed string with [DECISION]", () => {
    const line: LogItem = "[11:15:20] [DECISION] REJECTED AAPL: Net edge <= 0";
    const parsed = parseLogLine(line);
    expect(parsed.category).toBe("DECISION");
    expect(parsed.timestamp).toBe("11:15:20");
    expect(parsed.message).toBe("REJECTED AAPL: Net edge <= 0");
  });

  it("renders DECISION tag badge, ACCEPTED sub-badge, and Mathematical Net Expectancy formula", () => {
    const decisionLog: LogItem = {
      time: "14:30:15",
      level: "DECISION",
      message: "BUY NVDA: Net Expectancy +1.84%",
      metadata: {
        ticker: "NVDA",
        action: "ACCEPTED",
        headline: "BUY NVDA",
        summary: "High positive expectancy trade",
        factors: {
          "HMM Regime Alignment": "State 0 Trending gives 1.20x edge boost",
          "Friction Load": "8.2 bps statutory + spread fee",
        },
        metrics: {
          net_expectancy_pct: 1.84,
          win_probability: 0.624,
          round_trip_friction_bps: 8.2,
          payoff_ratio: 1.78,
        },
        timestamp_utc: "2026-11-05T14:30:15Z",
      },
    };

    const html = ReactDOMServer.renderToString(<ActivityLog logs={[decisionLog]} />);

    // Tag badge
    expect(html).toContain("bg-purple-500/20 text-purple-300 border-purple-500/40");
    expect(html).toContain(">DECISION</span>");

    // Action sub-badge
    expect(html).toContain("ACCEPTED (BUY)");

    // Mathematical Net Expectancy formula
    expect(html).toContain("Net Expectancy Formula:");
    expect(html).toContain("EV = P(Win) · E[Win] - P(Loss) · E[Loss] - Friction");

    // Quantitative metrics
    expect(html).toContain("+1.84%");
    expect(html).toContain("62.4%");
    expect(html).toContain("8.2 bps");
    expect(html).toContain("1.78");

    // Factor bullets
    expect(html).toContain("HMM Regime Alignment");
    expect(html).toContain("State 0 Trending gives 1.20x edge boost");
  });

  it("renders REJECTED (EV <= 0) badge when action is REJECTED", () => {
    const rejectedLog: LogItem = {
      time: "15:00:00",
      level: "DECISION",
      message: "REJECTED TSLA: Net edge is -0.42%",
      metadata: {
        ticker: "TSLA",
        action: "REJECTED",
        headline: "REJECTED TSLA",
        summary: "Negative Net Expectancy after friction",
        factors: {
          "Spread Drag": "High spread 28 bps exceeds hurdle",
        },
        metrics: {
          net_expectancy_pct: -0.42,
          win_probability: 0.45,
          round_trip_friction_bps: 28.0,
        },
        timestamp_utc: "2026-11-05T15:00:00Z",
      },
    };

    const html = ReactDOMServer.renderToString(<ActivityLog logs={[rejectedLog]} />);
    expect(html).toContain("REJECTED (EV ≤ 0)");
    expect(html).toContain("-0.42%");
  });

  it("renders 100% Cash Guarantee alert when action is HELD_IN_CASH", () => {
    const cashLog: LogItem = {
      time: "15:30:00",
      level: "DECISION",
      message: "100% Cash Allocation Guarantee: Zero qualifying opportunities with positive EV",
      metadata: {
        ticker: "PORTFOLIO",
        action: "HELD_IN_CASH",
        headline: "100% Cash Preserved",
        summary: "All candidates failed expected net value hurdle",
        factors: {
          "Risk Governance": "Zero trades met minimum Sharpe threshold",
        },
        metrics: {
          cash_weight_pct: 100.0,
          total_candidates: 12,
          qualifying_count: 0,
        },
        timestamp_utc: "2026-11-05T15:30:00Z",
      },
    };

    const html = ReactDOMServer.renderToString(<ActivityLog logs={[cashLog]} />);
    expect(html).toContain("100% CASH PRESERVED");
    expect(html).toContain("100% Cash Allocation Guarantee: All candidate trades exhibited EV ≤ 0");
  });
});
