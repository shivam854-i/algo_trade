import { describe, expect, it } from "vitest";
import { parseLogLine } from "./ActivityLog";
import { LogItem } from "../types";

describe("ActivityLog parseLogLine Contract Verification", () => {
  it("safely parses structured dictionary objects from live_bot.py without crashing", () => {
    const liveBotEvent: LogItem = {
      time: "18:58:45",
      level: "RISK",
      message: "NVDA: US Pre-Market session - order queued",
    };

    const parsed = parseLogLine(liveBotEvent);
    expect(parsed.timestamp).toBe("18:58:45");
    expect(parsed.category).toBe("RISK");
    expect(parsed.message).toBe("NVDA: US Pre-Market session - order queued");
  });

  it("safely parses backend SESSION events", () => {
    const sessionEvent: LogItem = {
      time: "09:15:00",
      level: "SESSION",
      message: "NSE: Statutory exchange open",
    };

    const parsed = parseLogLine(sessionEvent);
    expect(parsed.timestamp).toBe("09:15:00");
    expect(parsed.category).toBe("SESSION");
    expect(parsed.message).toBe("NSE: Statutory exchange open");
  });

  it("safely parses bracketed string formats", () => {
    const stringLog: LogItem = "[14:22:01] [BOT] Booting SYNAPSE-TITAN on RTX 4060...";
    const parsed = parseLogLine(stringLog);
    expect(parsed.timestamp).toBe("14:22:01");
    expect(parsed.category).toBe("BOT");
    expect(parsed.message).toBe("Booting SYNAPSE-TITAN on RTX 4060...");
  });

  it("safely parses strings with leading category and no timestamp", () => {
    const stringLog: LogItem = "[SESSION] Market closed for COMEX Gold";
    const parsed = parseLogLine(stringLog);
    expect(parsed.category).toBe("SESSION");
    expect(parsed.message).toBe("Market closed for COMEX Gold");
    expect(parsed.timestamp).toBeDefined();
  });

  it("safely handles unformatted strings", () => {
    const stringLog: LogItem = "Manual override initiated";
    const parsed = parseLogLine(stringLog);
    expect(parsed.category).toBe("OTHER");
    expect(parsed.message).toBe("Manual override initiated");
  });

  it("safely handles null, undefined, and empty objects without throwing TypeError", () => {
    expect(() => parseLogLine(null as any)).not.toThrow();
    expect(() => parseLogLine(undefined as any)).not.toThrow();
    expect(() => parseLogLine({} as any)).not.toThrow();

    const fromNull = parseLogLine(null as any);
    expect(fromNull.category).toBe("OTHER");
    expect(fromNull.message).toBe("");

    const fromEmpty = parseLogLine({} as any);
    expect(fromEmpty.category).toBe("OTHER");
    expect(fromEmpty.message).toBe("");
  });

  it("extracts timestamp and category from message if object fields are omitted", () => {
    const partialObj: LogItem = {
      message: "[10:30:00] [STOP] Trailing stop triggered at 2740.0",
    };
    const parsed = parseLogLine(partialObj);
    expect(parsed.timestamp).toBe("10:30:00");
    expect(parsed.category).toBe("STOP");
    expect(parsed.message).toBe("Trailing stop triggered at 2740.0");
  });
});
