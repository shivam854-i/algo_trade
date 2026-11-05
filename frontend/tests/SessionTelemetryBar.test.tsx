import { describe, expect, it } from "vitest";
import React from "react";
import ReactDOMServer from "react-dom/server";
import { SessionTelemetryBar } from "../src/components/session/SessionTelemetryBar";
import { TradingSession, DataFeedStatus } from "../src/types";

describe("Milestone 3: SessionTelemetryBar", () => {
  const mockUsSession: TradingSession = {
    id: "sess_us_12345678",
    market: "US_EQUITIES",
    instruments: ["NVDA", "AAPL", "MSFT"],
    horizon: "1d",
    duration_type: "FIXED",
    duration_minutes: 240,
    session_end_policy: "CLOSE_ALL",
    allocated_capital: 100000,
    currency: "USD",
    status: "RUNNING",
    created_at: "2026-11-05T12:00:00Z",
    accumulated_pause_seconds: 0,
    remaining_seconds: 7200, // 2 hours
    is_active: true,
    is_running: true,
    is_paused: false,
    is_terminal: false,
    is_expired: false,
    current_metrics: {
      initial_capital: 100000,
      current_cash: 85000,
      invested_equity: 15000,
      total_equity: 101250,
      unrealized_pnl: 1250.50,
      realized_pnl: 500.00,
    },
  };

  const mockNseSession: TradingSession = {
    id: "sess_nse_87654321",
    market: "INDIAN_NSE",
    instruments: ["RELIANCE.NS", "TCS.NS"],
    horizon: "1h",
    duration_type: "CUSTOM",
    duration_minutes: 180,
    session_end_policy: "KEEP_OPEN",
    allocated_capital: 500000,
    currency: "INR",
    status: "PAUSED",
    created_at: "2026-11-05T09:15:00Z",
    accumulated_pause_seconds: 300,
    remaining_seconds: 3600, // 1 hour
    is_active: true,
    is_running: false,
    is_paused: true,
    is_terminal: false,
    is_expired: false,
    current_metrics: {
      initial_capital: 500000,
      current_cash: 420000,
      invested_equity: 80000,
      total_equity: 498500,
      unrealized_pnl: -1500.00,
      realized_pnl: 0.00,
    },
  };

  const mockFeed: DataFeedStatus = {
    is_connected: true,
    healthy: true,
    is_realtime: true,
    data_mode: "LIVE_MARKET_DATA",
    paper_trading_only: true,
    stale_tickers: [],
    average_latency_ms: 120,
    last_update_utc: "2026-11-05T12:00:00Z",
  };

  it("renders US session telemetry with dollar metrics, countdown, and RUNNING badge", () => {
    const html = ReactDOMServer.renderToString(
      <SessionTelemetryBar
        session={mockUsSession}
        feedHealth={mockFeed}
        selectedTicker="NVDA"
        onStartSession={async () => {}}
        onPauseSession={async () => {}}
        onResumeSession={async () => {}}
        onStopSession={async () => {}}
        onOpenWizard={() => {}}
      />
    );
    const cleanHtml = html.replace(/<!--[\s\S]*?-->/g, "");

    // Identity & Status
    expect(cleanHtml).toContain("Session: <span class=\"text-sky-400\">#sess_us_</span>");
    expect(cleanHtml).toContain("RUNNING");
    expect(cleanHtml).toContain("US_EQUITIES");
    expect(cleanHtml).toContain("Horizon: <strong class=\"text-slate-200\">1d</strong>");

    // Basket Chips
    expect(cleanHtml).toContain("NVDA");
    expect(cleanHtml).toContain("AAPL");
    expect(cleanHtml).toContain("MSFT");

    // Countdown Clock (7200 seconds -> 02:00:00)
    expect(cleanHtml).toContain("02:00:00");

    // Financial Metrics with $
    expect(cleanHtml).toContain("$100,000"); // Allocated Capital
    expect(cleanHtml).toContain("$85.0k / $15.0k"); // Cash / Invested
    expect(cleanHtml).toContain("+$1250.50"); // Unrealized MTM
    expect(cleanHtml).toContain("Close All Positions"); // Policy
    expect(cleanHtml).toContain("LIVE_MARKET_DATA (120ms)"); // Feed Health
  });

  it("renders Indian NSE session telemetry with Indian Rupee (₹) symbol and PAUSED badge", () => {
    const html = ReactDOMServer.renderToString(
      <SessionTelemetryBar
        session={mockNseSession}
        feedHealth={mockFeed}
        selectedTicker="RELIANCE.NS"
        onStartSession={async () => {}}
        onPauseSession={async () => {}}
        onResumeSession={async () => {}}
        onStopSession={async () => {}}
        onOpenWizard={() => {}}
      />
    );
    const cleanHtml = html.replace(/<!--[\s\S]*?-->/g, "");

    // Identity & Status
    expect(cleanHtml).toContain("Session: <span class=\"text-sky-400\">#sess_nse</span>");
    expect(cleanHtml).toContain("PAUSED");
    expect(cleanHtml).toContain("INDIAN_NSE");
    expect(cleanHtml).toContain("Horizon: <strong class=\"text-slate-200\">1h</strong>");

    // Basket Chips
    expect(cleanHtml).toContain("RELIANCE.NS");
    expect(cleanHtml).toContain("TCS.NS");

    // Countdown Clock (3600 seconds -> 01:00:00)
    expect(cleanHtml).toContain("01:00:00");

    // Financial Metrics with ₹
    expect(cleanHtml).toContain("₹5,00,000"); // Allocated Capital
    expect(cleanHtml).toContain("₹420.0k / ₹80.0k"); // Cash / Invested
    expect(cleanHtml).toContain("₹-1500.00"); // Unrealized MTM
    expect(cleanHtml).toContain("Keep Open (Manual)"); // Policy
  });

  it("renders 'Manual Stop' when session duration_type is MANUAL_STOP", () => {
    const manualSession: TradingSession = {
      ...mockUsSession,
      duration_type: "MANUAL_STOP",
      duration_minutes: null,
      remaining_seconds: null,
    };

    const html = ReactDOMServer.renderToString(
      <SessionTelemetryBar
        session={manualSession}
        onStartSession={async () => {}}
        onPauseSession={async () => {}}
        onResumeSession={async () => {}}
        onStopSession={async () => {}}
        onOpenWizard={() => {}}
      />
    );
    const cleanHtml = html.replace(/<!-- -->/g, "");

    expect(cleanHtml).toContain("Manual Stop");
  });

  it("returns null when session is null", () => {
    const html = ReactDOMServer.renderToString(
      <SessionTelemetryBar
        session={null}
        onStartSession={async () => {}}
        onPauseSession={async () => {}}
        onResumeSession={async () => {}}
        onStopSession={async () => {}}
        onOpenWizard={() => {}}
      />
    );

    expect(html).toBe("");
  });
});
