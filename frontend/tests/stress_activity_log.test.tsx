import { describe, expect, it } from "vitest";
import React from "react";
import ReactDOMServer from "react-dom/server";
import { ActivityLog, parseLogLine, VALID_CATEGORIES } from "../src/components/ActivityLog";
import { LogItem } from "../src/types";
import { RingBuffer } from "../src/utils/ringBuffer";

describe("Adversarial Stress Test: ActivityLog Mixed Streaming Payloads", () => {
  const BADGE_STYLES: Record<string, string> = {
    BOT: "bg-sky-500/20 text-sky-300 border-sky-500/40",
    TRADE: "bg-indigo-500/20 text-indigo-300 border-indigo-500/40",
    PROFIT: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
    STOP: "bg-rose-500/20 text-rose-300 border-rose-500/40",
    RISK: "bg-amber-500/20 text-amber-300 border-amber-500/40",
    SESSION: "bg-purple-500/20 text-purple-300 border-purple-500/40",
    SYSTEM: "bg-slate-800 text-slate-400 border-slate-700",
    OTHER: "bg-slate-800 text-slate-400 border-slate-700",
  };

  it("1. Verifies badge styling classes for all valid categories and fallback", () => {
    for (const cat of VALID_CATEGORIES) {
      const item: LogItem = { time: "12:00:00", level: cat, message: `Test for ${cat}` };
      const parsed = parseLogLine(item);
      expect(parsed.category).toBe(cat);

      const html = ReactDOMServer.renderToString(<ActivityLog logs={[item]} />);
      expect(html).toContain(BADGE_STYLES[cat]);
      expect(html).toContain(`>${cat}</span>`);
    }

    // Fallback category OTHER
    const fallbackItem: LogItem = { time: "12:00:00", level: "NON_EXISTENT", message: "Fallback" };
    const parsedFallback = parseLogLine(fallbackItem);
    expect(parsedFallback.category).toBe("OTHER");
    const fallbackHtml = ReactDOMServer.renderToString(<ActivityLog logs={[fallbackItem]} />);
    expect(fallbackHtml).toContain(BADGE_STYLES["OTHER"]);
    expect(fallbackHtml).toContain(">OTHER</span>");
  });

  it("2. Handles mixed adversarial payload batch without exceptions or white screen", () => {
    const mixedPayloads: any[] = [
      // 1. Structured dicts
      { time: "18:58:45", level: "RISK", message: "NVDA: Pre-market order queued" },
      { time: "09:15:00", level: "SESSION", message: "NSE statutory session OPEN" },
      { time: "10:30:12", level: "trade", message: "Long 10 GC=F at 2740.50" }, // lowercase level
      { time: "11:00:00", level: "PROFIT", message: "Target hit +$1,420.00" },
      { time: "11:15:00", level: "STOP", message: "Trailing stop hit -$250.00" },
      { time: "11:30:00", level: "BOT", message: "Neural inference batch executed (RTX 4060)" },
      { time: "11:45:00", level: "SYSTEM", message: "Heartbeat healthy, VRAM 2350MB" },

      // 2. Bracketed raw strings
      "[14:22:01] [BOT] Booting SYNAPSE-TITAN engine...",
      "[SESSION] COMEX Gold maintenance pause 17:00-18:00 ET",
      "[PROFIT] Scalp completed on BTC-USD",
      "[STOP] Hard circuit breaker reached",
      "[RISK] Kelly allocation clamped to max 15%",
      "[TRADE] Market BUY executed",
      "[SYSTEM] Synchronized NTP clock drift < 2ms",

      // 3. Raw strings with timestamp only or plain text
      "[14:22:01] Uncategorized telemetry signal update",
      "Manual operator override triggered via keyboard shortcut",
      "Notice: STT statutory friction applied",

      // 4. Edge cases: empty, whitespace, special chars, huge strings
      "",
      "    ",
      "🚀 High-volatility spike detected: EURUSD +1.2% in 15s 📈💰",
      "<script>alert('xss_injection_attempt')</script>",
      "A".repeat(10000), // very long message

      // 5. Missing / non-standard structured shapes
      { time: "12:00:00" }, // missing level and message
      { level: "BOT" }, // missing time and message
      { message: "Standalone message in dict" }, // missing time and level
      { message: "[13:45:00] [BOT] Extracted from message body" },
      { message: "[SESSION] Session status from message body" },
      {}, // empty object

      // 6. Primitives, nulls, undefineds
      null,
      undefined,
      12345,
      true,
      false,
      NaN,

      // 7. Non-standard dictionaries
      { foo: "bar", amount: 100000, active: true },
      { time: 1730728800, level: 200, message: 99999 }, // numeric types
      { time: null, level: null, message: null },
      { time: undefined, level: undefined, message: undefined },
    ];

    // Assert parseLogLine never throws on ANY payload
    for (let i = 0; i < mixedPayloads.length; i++) {
      const payload = mixedPayloads[i];
      let parsed;
      expect(() => {
        parsed = parseLogLine(payload);
      }).not.toThrow();

      expect(parsed).toBeDefined();
      expect(typeof parsed!.timestamp).toBe("string");
      expect(typeof parsed!.category).toBe("string");
      expect(typeof parsed!.message).toBe("string");
    }

    // Assert React component renders without throwing and without white screen
    let renderedHtml = "";
    expect(() => {
      renderedHtml = ReactDOMServer.renderToString(<ActivityLog logs={mixedPayloads} />);
    }).not.toThrow();

    // Verify UI is not blank / empty
    expect(renderedHtml).toBeTruthy();
    expect(renderedHtml.length).toBeGreaterThan(500);
    expect(renderedHtml).toContain("Bounded Event Log");
    expect(renderedHtml).toContain("RingBuffer:");
    expect(renderedHtml).toContain(">ALL</button>");
    expect(renderedHtml).toContain(">BOT</button>");
    expect(renderedHtml).toContain("NVDA: Pre-market order queued");
    expect(renderedHtml).toContain("NSE statutory session OPEN");
    expect(renderedHtml).toContain("Booting SYNAPSE-TITAN engine...");
  });

  it("3. Streams 5,000 mixed payloads through RingBuffer(100) and renders without memory leak", () => {
    const ring = new RingBuffer<LogItem>(100);

    const categories = ["BOT", "TRADE", "PROFIT", "STOP", "RISK", "SESSION", "SYSTEM"];

    for (let i = 0; i < 5000; i++) {
      if (i % 4 === 0) {
        ring.push({
          time: `12:${String(Math.floor(i / 60) % 60).padStart(2, "0")}:${String(i % 60).padStart(2, "0")}`,
          level: categories[i % categories.length],
          message: `Streaming telemetry event #${i} processed successfully`,
        });
      } else if (i % 4 === 1) {
        ring.push(`[${categories[i % categories.length]}] Raw log line #${i}`);
      } else if (i % 4 === 2) {
        ring.push({
          message: `[12:00:00] [${categories[(i + 1) % categories.length]}] Embedded body event #${i}`,
        });
      } else {
        // Edge cases
        ring.push(i % 2 === 0 ? null as any : { extra: `arbitrary shape #${i}` });
      }

      // Periodically render to verify DOM generation under streaming
      if (i % 1000 === 0) {
        const currentLogs = ring.toArray();
        expect(currentLogs.length).toBeLessThanOrEqual(100);
        const html = ReactDOMServer.renderToString(<ActivityLog logs={currentLogs} />);
        expect(html).toContain("Bounded Event Log");
      }
    }

    expect(ring.size()).toBe(100);
    const finalHtml = ReactDOMServer.renderToString(<ActivityLog logs={ring.toArray()} />);
    expect(finalHtml).toContain("Bounded Event Log");
    expect(finalHtml).toMatch(/RingBuffer:.*100.*\/ 100 entries/);
  });

  it("4. Empty or invalid logs prop renders cleanly without crash", () => {
    expect(() => ReactDOMServer.renderToString(<ActivityLog logs={[]} />)).not.toThrow();
    const emptyHtml = ReactDOMServer.renderToString(<ActivityLog logs={[]} />);
    expect(emptyHtml).toContain("No events match selected filter.");

    expect(() => ReactDOMServer.renderToString(<ActivityLog logs={null as any} />)).not.toThrow();
    expect(() => ReactDOMServer.renderToString(<ActivityLog logs={undefined as any} />)).not.toThrow();
  });
});
