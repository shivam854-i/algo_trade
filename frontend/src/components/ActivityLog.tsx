import React, { useState } from "react";
import { Terminal, Copy, Check, Filter } from "lucide-react";
import { LogItem, LogEntry } from "../types";

export interface ActivityLogProps {
  logs: LogItem[];
}

export const VALID_CATEGORIES = [
  "BOT",
  "TRADE",
  "PROFIT",
  "STOP",
  "RISK",
  "SESSION",
  "SYSTEM",
] as const;

export type LogCategory = (typeof VALID_CATEGORIES)[number] | "OTHER";

export interface ParsedLog {
  raw: string;
  timestamp: string;
  category: LogCategory;
  message: string;
}

export function isValidCategory(cat: string): cat is (typeof VALID_CATEGORIES)[number] {
  return VALID_CATEGORIES.includes(cat as (typeof VALID_CATEGORIES)[number]);
}

/**
 * Robust log parser handling:
 * 1. Structured backend dicts: { time: "18:58:45", level: "RISK", message: "..." }
 * 2. Bracketed strings: "[14:22:01] [BOT] message..."
 * 3. Categorized strings: "[SESSION] Market closed for NSE"
 * 4. Plain strings, nulls, undefined, and edge cases with zero runtime exceptions.
 */
export function parseLogLine(item: LogItem | unknown): ParsedLog {
  // Case 1: Structured dictionary object from live_bot.py / API
  if (typeof item === "object" && item !== null) {
    const entry = item as Partial<LogEntry>;
    const rawMsg = typeof entry.message === "string" ? entry.message : String(entry.message ?? "");
    let time = entry.time ? String(entry.time) : "";
    let category: LogCategory = "OTHER";

    if (entry.level) {
      const upperLevel = String(entry.level).toUpperCase();
      if (isValidCategory(upperLevel)) {
        category = upperLevel;
      }
    }

    let finalMessage = rawMsg;
    // If timestamp was missing from object, try extracting bracketed time e.g. [14:22:01]
    if (!time) {
      const timeMatch = finalMessage.match(/^\[(.*?)\]\s*/);
      if (timeMatch) {
        time = timeMatch[1];
        finalMessage = finalMessage.substring(timeMatch[0].length);
      }
    }

    // If category was not in level or was OTHER, try extracting bracketed category from message
    if (category === "OTHER") {
      const catMatch = finalMessage.match(/^\[(BOT|TRADE|PROFIT|STOP|RISK|SESSION|SYSTEM)\]\s*/i);
      if (catMatch) {
        const upperCat = catMatch[1].toUpperCase();
        if (isValidCategory(upperCat)) {
          category = upperCat;
        }
        finalMessage = finalMessage.substring(catMatch[0].length);
      }
    }

    return {
      raw: JSON.stringify(item),
      timestamp: time || new Date().toISOString().substring(11, 19),
      category,
      message: finalMessage,
    };
  }

  // Case 2: String or primitive input
  const line = String(item ?? "");
  let timestamp = "";
  let category: LogCategory = "OTHER";
  let message = line;

  // Check if line begins with a category bracket e.g. [SESSION]
  const leadCatMatch = line.match(/^\[(BOT|TRADE|PROFIT|STOP|RISK|SESSION|SYSTEM)\]\s*/i);
  if (leadCatMatch) {
    category = leadCatMatch[1].toUpperCase() as LogCategory;
    message = line.substring(leadCatMatch[0].length);
  } else {
    // Extract timestamp if enclosed in first brackets e.g. [14:22:01]
    const timeMatch = line.match(/^\[(.*?)\]\s*/);
    if (timeMatch) {
      timestamp = timeMatch[1];
      message = line.substring(timeMatch[0].length);

      // Extract category from subsequent bracket e.g. [BOT]
      const nextCatMatch = message.match(/^\[(BOT|TRADE|PROFIT|STOP|RISK|SESSION|SYSTEM)\]\s*/i);
      if (nextCatMatch) {
        category = nextCatMatch[1].toUpperCase() as LogCategory;
        message = message.substring(nextCatMatch[0].length);
      }
    }
  }

  return {
    raw: line,
    timestamp: timestamp || new Date().toISOString().substring(11, 19),
    category,
    message,
  };
}

export const ActivityLog: React.FC<ActivityLogProps> = ({ logs = [] }) => {
  const [filter, setFilter] = useState<string>("ALL");
  const [copied, setCopied] = useState<boolean>(false);

  const safeLogs = Array.isArray(logs) ? logs : [];
  const parsedLogs = safeLogs.map(parseLogLine);

  const filteredLogs = parsedLogs.filter((l) => {
    if (filter === "ALL") return true;
    return l.category === filter;
  });

  const handleCopy = () => {
    const formatted = safeLogs
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const parts: string[] = [];
          if (item.time) parts.push(`[${item.time}]`);
          if (item.level) parts.push(`[${item.level.toUpperCase()}]`);
          if (item.message) parts.push(item.message);
          return parts.join(" ");
        }
        return String(item ?? "");
      })
      .join("\n");

    navigator.clipboard.writeText(formatted);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getTagBadge = (cat: ParsedLog["category"]) => {
    switch (cat) {
      case "BOT":
        return "bg-sky-500/20 text-sky-300 border-sky-500/40";
      case "TRADE":
        return "bg-indigo-500/20 text-indigo-300 border-indigo-500/40";
      case "PROFIT":
        return "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
      case "STOP":
        return "bg-rose-500/20 text-rose-300 border-rose-500/40";
      case "RISK":
        return "bg-amber-500/20 text-amber-300 border-amber-500/40";
      case "SESSION":
        return "bg-purple-500/20 text-purple-300 border-purple-500/40";
      case "SYSTEM":
      default:
        return "bg-slate-800 text-slate-400 border-slate-700";
    }
  };

  return (
    <div className="glass-panel rounded-xl p-4 flex flex-col space-y-3">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div className="flex items-center space-x-2">
          <Terminal className="w-4 h-4 text-sky-400" />
          <span className="font-bold font-mono text-sm text-slate-100">
            Bounded Event Log
          </span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-400">
            RingBuffer: {safeLogs.length} / 100 entries
          </span>
        </div>

        {/* Filters & Copy */}
        <div className="flex items-center space-x-2">
          <div className="flex items-center space-x-1 text-[11px] font-mono">
            <Filter className="w-3 h-3 text-slate-500 mr-0.5" />
            {(["ALL", "BOT", "TRADE", "PROFIT", "RISK", "SESSION"] as const).map((cat) => (
              <button
                key={cat}
                onClick={() => setFilter(cat)}
                className={`px-2 py-0.5 rounded transition ${
                  filter === cat
                    ? "bg-sky-500/20 text-sky-400 border border-sky-500/40"
                    : "text-slate-500 hover:text-slate-300"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          <button
            onClick={handleCopy}
            className="p-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800 transition text-xs font-mono flex items-center"
            title="Copy logs to clipboard"
          >
            {copied ? (
              <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <Copy className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Log Feed */}
      <div className="h-64 overflow-y-auto space-y-1.5 pr-1 font-mono text-xs">
        {filteredLogs.length === 0 ? (
          <div className="py-8 text-center text-slate-600">
            No events match selected filter.
          </div>
        ) : (
          filteredLogs.map((log, idx) => (
            <div
              key={`${log.timestamp}-${idx}`}
              className="py-1 px-2 rounded bg-slate-950/60 border border-slate-900 flex items-baseline space-x-2 hover:bg-slate-900/60 transition-colors"
            >
              <span className="text-slate-500 text-[10px] shrink-0">
                {log.timestamp}
              </span>
              <span
                className={`px-1.5 py-0.2 rounded border text-[9px] font-bold shrink-0 ${getTagBadge(
                  log.category
                )}`}
              >
                {log.category}
              </span>
              <span className="text-slate-300 break-words flex-1 leading-relaxed">
                {log.message}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
