import { describe, expect, it } from "vitest";
import {
  formatCountdown,
  getStatusStyles,
  resolveSessions,
} from "./MarketSessionRibbon";
import { SessionStatusInfo } from "../types";

describe("MarketSessionRibbon Contract & Integration Verification", () => {
  it("formats countdown seconds cleanly into HH:MM:SS and day formats", () => {
    expect(formatCountdown(0)).toBe("00:00:00");
    expect(formatCountdown(-10)).toBe("00:00:00");
    expect(formatCountdown(65)).toBe("00:01:05");
    expect(formatCountdown(3665)).toBe("01:01:05");
    expect(formatCountdown(90000)).toBe("1d 1h 0m");
  });

  it("assigns distinct, valid styling classes for all 6 market states", () => {
    const states = [
      "OPEN",
      "PRE_MARKET",
      "POST_MARKET",
      "HOLIDAY",
      "WEEKEND",
      "CLOSED",
    ] as const;

    states.forEach((st) => {
      const styles = getStatusStyles(st, st === "OPEN");
      expect(styles.badge).toBeDefined();
      expect(styles.card).toBeDefined();
      expect(styles.dot).toBeDefined();
      expect(styles.timerText).toBeDefined();
    });

    // Verify HOLIDAY uses purple theme
    const holidayStyles = getStatusStyles("HOLIDAY", false);
    expect(holidayStyles.badge).toContain("purple");
    expect(holidayStyles.dot).toContain("purple");
  });

  it("ingests authoritative backend market sessions with accurate countdown calculation", () => {
    const mockNow = new Date("2026-11-04T12:00:00Z");
    const targetTime = new Date("2026-11-04T13:30:00Z").toISOString(); // 90 min = 5400 sec

    const backendSessions: Record<string, SessionStatusInfo> = {
      NSE_INDIA: {
        state: "OPEN",
        is_open: true,
        next_state: "CLOSED",
        seconds_to_next_state: 5400,
        next_state_time_utc: targetTime,
        local_time: "17:30:00 IST",
        exchange_tz: "Asia/Kolkata",
        holiday_name: null,
        exchange_name: "NSE Mumbai",
        session_schedule: "09:15–15:30 IST",
      },
      US_MARKETS: {
        state: "PRE_MARKET",
        is_open: false,
        next_state: "OPEN",
        seconds_to_next_state: 5400,
        next_state_time_utc: targetTime,
        local_time: "07:00:00 ET",
        exchange_tz: "America/New_York",
        holiday_name: null,
      },
    };

    const resolved = resolveSessions(backendSessions, mockNow);
    const nse = resolved.find((s) => s.id === "NSE");
    const nyse = resolved.find((s) => s.id === "NYSE");

    expect(nse).toBeDefined();
    expect(nse?.isAuthoritative).toBe(true);
    expect(nse?.isOpen).toBe(true);
    expect(nse?.state).toBe("OPEN");
    expect(nse?.countdownSeconds).toBe(5400);
    expect(nse?.countdownLabel).toBe("Closes in");

    expect(nyse).toBeDefined();
    expect(nyse?.isAuthoritative).toBe(true);
    expect(nyse?.isOpen).toBe(false);
    expect(nyse?.state).toBe("PRE_MARKET");
    expect(nyse?.countdownSeconds).toBe(5400);
    expect(nyse?.countdownLabel).toBe("Opens in");
  });

  it("faithfully reflects statutory exchange HOLIDAY states and presents holiday name", () => {
    const mockNow = new Date("2026-01-26T06:00:00Z"); // Republic Day
    const nextOpen = "2026-01-27T03:45:00Z";

    const backendSessions: Record<string, SessionStatusInfo> = {
      NSE_INDIA: {
        state: "HOLIDAY",
        is_open: false,
        next_state: "OPEN",
        seconds_to_next_state: 78300,
        next_state_time_utc: nextOpen,
        local_time: "11:30:00 IST",
        exchange_tz: "Asia/Kolkata",
        holiday_name: "Republic Day",
        exchange_name: "NSE Mumbai",
      },
      US_MARKETS: {
        state: "HOLIDAY",
        is_open: false,
        next_state: "OPEN",
        seconds_to_next_state: 253800,
        next_state_time_utc: "2026-12-28T14:30:00Z",
        local_time: "11:00:00 ET",
        exchange_tz: "America/New_York",
        holiday_name: "Christmas Day",
        exchange_name: "NYSE / NASDAQ",
      },
    };

    const resolved = resolveSessions(backendSessions, mockNow);
    const nse = resolved.find((s) => s.id === "NSE");
    const nyse = resolved.find((s) => s.id === "NYSE");

    expect(nse?.state).toBe("HOLIDAY");
    expect(nse?.isOpen).toBe(false);
    expect(nse?.holidayName).toBe("Republic Day");
    expect(nse?.countdownLabel).toBe("Republic Day (Opens in)");

    expect(nyse?.state).toBe("HOLIDAY");
    expect(nyse?.isOpen).toBe(false);
    expect(nyse?.holidayName).toBe("Christmas Day");
    expect(nyse?.countdownLabel).toBe("Christmas Day (Opens in)");
  });

  it("gracefully falls back to offline client clock heuristics when backend is disconnected", () => {
    const resolved = resolveSessions(undefined);
    expect(resolved.length).toBe(4);

    resolved.forEach((s) => {
      expect(s.isAuthoritative).toBe(false);
      expect(s.name).toBeDefined();
      expect(s.schedule).toBeDefined();
      expect(s.countdownSeconds).toBeGreaterThanOrEqual(0);
      expect(["OPEN", "CLOSED", "PRE_MARKET", "POST_MARKET", "WEEKEND", "HOLIDAY"]).toContain(
        s.state
      );
    });

    const crypto = resolved.find((s) => s.id === "CRYPTO");
    expect(crypto?.isOpen).toBe(true);
    expect(crypto?.state).toBe("OPEN");
    expect(crypto?.countdownLabel).toBe("Non-Stop");
  });
});
