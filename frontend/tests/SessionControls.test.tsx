import { describe, expect, it } from "vitest";
import React from "react";
import ReactDOMServer from "react-dom/server";
import { SessionControls } from "../src/components/session/SessionControls";
import { StopSessionModal } from "../src/components/session/StopSessionModal";
import { TradingSession } from "../src/types";

describe("Milestone 3: SessionControls & StopSessionModal", () => {
  const mockBaseSession: TradingSession = {
    id: "sess_test123",
    user_id: "DEFAULT_USER",
    account_id: "PAPER_DEFAULT",
    market: "US_EQUITIES",
    instruments: ["NVDA", "AAPL"],
    horizon: "1d",
    duration_type: "FIXED",
    duration_minutes: 240,
    session_end_policy: "CLOSE_ALL",
    allocated_capital: 50000,
    currency: "USD",
    status: "CREATED",
    created_at: "2026-11-05T12:00:00Z",
    accumulated_pause_seconds: 0,
    is_active: false,
    is_running: false,
    is_paused: false,
    is_terminal: false,
    is_expired: false,
  };

  describe("State Transition & Control Button Enablement", () => {
    it("renders START SESSION button when session is in CREATED state", () => {
      const html = ReactDOMServer.renderToString(
        <SessionControls
          session={{ ...mockBaseSession, status: "CREATED" }}
          onStartSession={async () => {}}
          onPauseSession={async () => {}}
          onResumeSession={async () => {}}
          onStopSession={async () => {}}
          onOpenWizard={() => {}}
        />
      );

      expect(html).toContain("START SESSION");
      expect(html).toContain("STOP");
      expect(html).not.toContain("RESUME");
    });

    it("renders PAUSE and STOP buttons when session is in RUNNING state", () => {
      const html = ReactDOMServer.renderToString(
        <SessionControls
          session={{ ...mockBaseSession, status: "RUNNING" }}
          onStartSession={async () => {}}
          onPauseSession={async () => {}}
          onResumeSession={async () => {}}
          onStopSession={async () => {}}
          onOpenWizard={() => {}}
        />
      );

      expect(html).toContain("PAUSE");
      expect(html).toContain("STOP");
      expect(html).not.toContain("START SESSION");
      expect(html).not.toContain("RESUME");
    });

    it("renders RESUME and STOP buttons when session is in PAUSED state", () => {
      const html = ReactDOMServer.renderToString(
        <SessionControls
          session={{ ...mockBaseSession, status: "PAUSED" }}
          onStartSession={async () => {}}
          onPauseSession={async () => {}}
          onResumeSession={async () => {}}
          onStopSession={async () => {}}
          onOpenWizard={() => {}}
        />
      );

      expect(html).toContain("RESUME");
      expect(html).toContain("STOP");
      expect(html).not.toContain("PAUSE");
    });

    it("renders NEW SESSION button when session is in COMPLETED state", () => {
      const html = ReactDOMServer.renderToString(
        <SessionControls
          session={{ ...mockBaseSession, status: "COMPLETED" }}
          onStartSession={async () => {}}
          onPauseSession={async () => {}}
          onResumeSession={async () => {}}
          onStopSession={async () => {}}
          onOpenWizard={() => {}}
        />
      );

      expect(html).toContain("NEW SESSION");
      expect(html).not.toContain("START SESSION");
      expect(html).not.toContain("PAUSE");
      expect(html).not.toContain("STOP");
    });

    it("renders NEW SESSION button when session is null (no active session)", () => {
      const html = ReactDOMServer.renderToString(
        <SessionControls
          session={null}
          onStartSession={async () => {}}
          onPauseSession={async () => {}}
          onResumeSession={async () => {}}
          onStopSession={async () => {}}
          onOpenWizard={() => {}}
        />
      );

      expect(html).toContain("NEW SESSION");
    });
  });

  describe("StopSessionModal Confirmation Safeguards", () => {
    it("renders safety warning and CLOSE_ALL liquidation explanation when open", () => {
      const html = ReactDOMServer.renderToString(
        <StopSessionModal
          isOpen={true}
          session={{ ...mockBaseSession, session_end_policy: "CLOSE_ALL" }}
          openPositionsCount={3}
          onClose={() => {}}
          onConfirm={() => {}}
        />
      );

      const cleanHtml = html.replace(/<!-- -->/g, "");
      expect(cleanHtml).toContain("Stop Trading Session #sess_tes?");
      expect(cleanHtml).toContain("Configured Session-End Policy: CLOSE_ALL");
      expect(cleanHtml).toContain("All 3 currently open virtual positions will be immediately liquidated");
      expect(cleanHtml).toContain("Operator Manual Stop");
      expect(cleanHtml).toContain("Risk Governance Halt");
      expect(cleanHtml).toContain("Confirm &amp; Stop Session");
    });

    it("renders KEEP_OPEN preservation explanation when policy is KEEP_OPEN", () => {
      const html = ReactDOMServer.renderToString(
        <StopSessionModal
          isOpen={true}
          session={{ ...mockBaseSession, session_end_policy: "KEEP_OPEN" }}
          openPositionsCount={2}
          onClose={() => {}}
          onConfirm={() => {}}
        />
      );

      const cleanHtml = html.replace(/<!-- -->/g, "");
      expect(cleanHtml).toContain("Configured Session-End Policy: KEEP_OPEN");
      expect(cleanHtml).toContain("open virtual positions will remain active in your ledger for manual execution");
    });

    it("renders null when isOpen is false", () => {
      const html = ReactDOMServer.renderToString(
        <StopSessionModal
          isOpen={false}
          session={mockBaseSession}
          onClose={() => {}}
          onConfirm={() => {}}
        />
      );

      expect(html).toBe("");
    });
  });
});
