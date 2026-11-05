import React, { useState } from "react";
import {
  Terminal,
  Copy,
  Check,
  Filter,
  Brain,
  ChevronDown,
  ChevronUp,
  ShieldCheck,
} from "lucide-react";
import { LogItem, LogEntry, DecisionMetadata } from "../types";

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
  "DECISION",
] as const;

export type LogCategory = (typeof VALID_CATEGORIES)[number] | "OTHER";

export interface ParsedLog {
  raw: string;
  timestamp: string;
  category: LogCategory;
  message: string;
  metadata?: DecisionMetadata | null;
}

export function isValidCategory(cat: string): cat is (typeof VALID_CATEGORIES)[number] {
  return VALID_CATEGORIES.includes(cat as (typeof VALID_CATEGORIES)[number]);
}

/**
 * Robust log parser handling:
 * 1. Structured backend dicts: { time: "18:58:45", level: "RISK", message: "...", metadata?: {...} }
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
      const catMatch = finalMessage.match(/^\[(BOT|TRADE|PROFIT|STOP|RISK|SESSION|SYSTEM|DECISION)\]\s*/i);
      if (catMatch) {
        const upperCat = catMatch[1].toUpperCase();
        if (isValidCategory(upperCat)) {
          category = upperCat;
        }
        finalMessage = finalMessage.substring(catMatch[0].length);
      }
    }

    let metadata: DecisionMetadata | null = null;
    if (entry.metadata && typeof entry.metadata === "object") {
      metadata = entry.metadata as DecisionMetadata;
    }

    return {
      raw: JSON.stringify(item),
      timestamp: time || new Date().toISOString().substring(11, 19),
      category,
      message: finalMessage,
      metadata,
    };
  }

  // Case 2: String or primitive input
  const line = String(item ?? "");
  let timestamp = "";
  let category: LogCategory = "OTHER";
  let message = line;

  // Check if line begins with a category bracket e.g. [SESSION]
  const leadCatMatch = line.match(/^\[(BOT|TRADE|PROFIT|STOP|RISK|SESSION|SYSTEM|DECISION)\]\s*/i);
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
      const nextCatMatch = message.match(/^\[(BOT|TRADE|PROFIT|STOP|RISK|SESSION|SYSTEM|DECISION)\]\s*/i);
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
    metadata: null,
  };
}

export const ActivityLog: React.FC<ActivityLogProps> = ({ logs = [] }) => {
  const [filter, setFilter] = useState<string>("ALL");
  const [copied, setCopied] = useState<boolean>(false);
  const [expandedIndices, setExpandedIndices] = useState<Record<number, boolean>>({});

  const safeLogs = Array.isArray(logs) ? logs : [];
  const parsedLogs = safeLogs.map(parseLogLine);

  const filteredLogs = parsedLogs.filter((l) => {
    if (filter === "ALL") return true;
    return l.category === filter;
  });

  const toggleExpand = (idx: number) => {
    setExpandedIndices((prev) => ({
      ...prev,
      [idx]: !prev[idx],
    }));
  };

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

    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(formatted);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
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
      case "DECISION":
        return "bg-purple-500/20 text-purple-300 border-purple-500/40";
      case "SYSTEM":
      default:
        return "bg-slate-800 text-slate-400 border-slate-700";
    }
  };

  const getActionBadge = (action?: string) => {
    switch (action) {
      case "ACCEPTED":
        return (
          <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[9px] font-bold">
            ACCEPTED (BUY)
          </span>
        );
      case "REJECTED":
        return (
          <span className="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 text-[9px] font-bold">
            REJECTED (EV &le; 0)
          </span>
        );
      case "HELD_IN_CASH":
        return (
          <span className="px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-300 border border-sky-500/40 text-[9px] font-bold">
            100% CASH PRESERVED
          </span>
        );
      default:
        return null;
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
            {(["ALL", "BOT", "TRADE", "DECISION", "PROFIT", "RISK", "SESSION"] as const).map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setFilter(cat)}
                className={`px-2 py-0.5 rounded transition ${
                  filter === cat
                    ? "bg-sky-500/20 text-sky-400 border border-sky-500/40 font-bold"
                    : "text-slate-500 hover:text-slate-300"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          <button
            type="button"
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
          filteredLogs.map((log, idx) => {
            const isDecision = log.category === "DECISION";
            const isExpanded = Boolean(expandedIndices[idx]);
            const meta = log.metadata;

            return (
              <div
                key={`${log.timestamp}-${idx}`}
                className="py-1.5 px-2 rounded bg-slate-950/60 border border-slate-900 flex flex-col space-y-1.5 hover:bg-slate-900/60 transition-colors"
              >
                {/* Main Log Line */}
                <div className="flex items-baseline space-x-2">
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

                  {isDecision && meta?.action && getActionBadge(meta.action)}

                  <span className="text-slate-300 break-words flex-1 leading-relaxed">
                    {log.message}
                  </span>

                  {isDecision && (
                    <button
                      type="button"
                      onClick={() => toggleExpand(idx)}
                      className="text-sky-400 hover:text-sky-300 text-[10px] font-mono flex items-center space-x-0.5 shrink-0 px-1 py-0.5 rounded bg-slate-900 border border-slate-800"
                    >
                      <span>{isExpanded ? "Hide EV" : "Net EV"}</span>
                      {isExpanded ? (
                        <ChevronUp className="w-3 h-3" />
                      ) : (
                        <ChevronDown className="w-3 h-3" />
                      )}
                    </button>
                  )}
                </div>

                {/* Expandable Net Expectancy Mathematical Drawer */}
                {isDecision && (isExpanded || meta) && (
                  <div
                    className={`${
                      isExpanded ? "block" : "hidden"
                    } mt-1 p-2.5 rounded-lg bg-slate-900/90 border border-purple-500/30 text-[11px] font-mono space-y-2`}
                  >
                    {/* Mathematical Formula Header */}
                    <div className="flex flex-wrap items-center justify-between text-purple-300 border-b border-slate-800 pb-1.5">
                      <span className="font-bold flex items-center">
                        <Brain className="w-3.5 h-3.5 mr-1 text-purple-400" />
                        Net Expectancy Formula:
                      </span>
                      <span className="text-slate-200 font-mono text-[10px] bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                        EV = P(Win) · E[Win] - P(Loss) · E[Loss] - Friction
                      </span>
                    </div>

                    {/* Quantitative Key Metrics Grid */}
                    {meta?.metrics && (
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px] pt-1">
                        <div className="p-1.5 rounded bg-slate-950 border border-slate-800">
                          <span className="text-slate-500 block">Net Expectancy (EV)</span>
                          <span
                            className={`font-bold text-xs ${
                              (meta.metrics.net_expectancy_pct ?? 0) >= 0
                                ? "text-emerald-400"
                                : "text-rose-400"
                            }`}
                          >
                            {(meta.metrics.net_expectancy_pct ?? 0) >= 0 ? "+" : ""}
                            {(meta.metrics.net_expectancy_pct ?? 0).toFixed(2)}%
                          </span>
                        </div>

                        <div className="p-1.5 rounded bg-slate-950 border border-slate-800">
                          <span className="text-slate-500 block">Win Probability (P_win)</span>
                          <span className="font-bold text-xs text-sky-300">
                            {meta.metrics.win_probability
                              ? `${(meta.metrics.win_probability * 100).toFixed(1)}%`
                              : "N/A"}
                          </span>
                        </div>

                        <div className="p-1.5 rounded bg-slate-950 border border-slate-800">
                          <span className="text-slate-500 block">Friction & Slippage</span>
                          <span className="font-bold text-xs text-amber-300">
                            {meta.metrics.round_trip_friction_bps ?? 12.0} bps
                          </span>
                        </div>

                        <div className="p-1.5 rounded bg-slate-950 border border-slate-800">
                          <span className="text-slate-500 block">Payoff Ratio (b)</span>
                          <span className="font-bold text-xs text-slate-200">
                            {meta.metrics.payoff_ratio
                              ? meta.metrics.payoff_ratio.toFixed(2)
                              : "1.75"}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Factor Explanations Bullets */}
                    {meta?.factors && Object.keys(meta.factors).length > 0 && (
                      <div className="space-y-1 pt-1 text-[10px] text-slate-300">
                        <span className="text-slate-500 font-bold block">Factor Rationale:</span>
                        {Object.entries(meta.factors).map(([k, v]) => (
                          <div key={k} className="flex items-start space-x-1.5">
                            <span className="text-purple-400">•</span>
                            <span>
                              <strong className="text-slate-200">{k}:</strong> {v}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* 100% Cash Guarantee Alert */}
                    {meta?.action === "HELD_IN_CASH" && (
                      <div className="p-2 rounded bg-sky-950/40 border border-sky-500/30 text-sky-200 text-[10px] flex items-center space-x-1.5">
                        <ShieldCheck className="w-3.5 h-3.5 text-sky-400 shrink-0" />
                        <span>
                          100% Cash Allocation Guarantee: All candidate trades exhibited EV &le; 0 or crisis regime veto. 100% capital preserved in cash.
                        </span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
