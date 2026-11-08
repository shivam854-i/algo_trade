import React, { useEffect, useState } from "react";
import { Clock, ShieldCheck, CalendarOff } from "lucide-react";
import { usePageVisibility } from "../hooks/usePageVisibility";
import { SessionStatusInfo } from "../types";

export interface MarketSessionRibbonProps {
  marketSessions?: Record<string, SessionStatusInfo>;
  sessions?: Record<string, SessionStatusInfo>; // Backward-compatible alias
}

export interface DisplaySession {
  id: string;
  name: string;
  region: string;
  schedule: string;
  isOpen: boolean;
  state: "OPEN" | "CLOSED" | "PRE_MARKET" | "POST_MARKET" | "WEEKEND" | "HOLIDAY";
  localClock: string;
  countdownLabel: string;
  countdownSeconds: number;
  holidayName?: string | null;
  isAuthoritative: boolean;
}

export const BENCHMARK_CONFIG = [
  {
    id: "NSE",
    primaryKey: "NSE_INDIA",
    aliases: ["NSE", "RELIANCE.NS", "NIFTY", "NIFTY_50"],
    defaultName: "NSE India (Nifty 50)",
    defaultRegion: "National Stock Exchange",
    defaultSchedule: "09:15–15:30 IST",
    timeZone: "Asia/Kolkata",
    tzName: "IST",
  },
  {
    id: "NYSE",
    primaryKey: "US_MARKETS",
    aliases: ["NYSE", "NASDAQ", "NVDA", "AAPL"],
    defaultName: "NYSE / NASDAQ",
    defaultRegion: "US Equities",
    defaultSchedule: "09:30–16:00 ET",
    timeZone: "America/New_York",
    tzName: "ET",
  },
  {
    id: "COMEX",
    primaryKey: "CME_GLOBEX",
    aliases: ["COMEX", "GC=F"],
    defaultName: "CME COMEX",
    defaultRegion: "Commodities (Gold GC=F)",
    defaultSchedule: "23h/day Mon–Fri",
    timeZone: "America/New_York",
    tzName: "ET",
  },
  {
    id: "CRYPTO",
    primaryKey: "CRYPTO_247",
    aliases: ["CRYPTO", "BTC-USD"],
    defaultName: "Crypto 24/7",
    defaultRegion: "Global (BTC / ETH)",
    defaultSchedule: "24/7 Non-Stop",
    timeZone: "UTC",
    tzName: "UTC",
  },
];

export function formatCountdown(totalSec: number): string {
  if (totalSec <= 0) return "00:00:00";
  const hours = Math.floor(totalSec / 3600);
  const minutes = Math.floor((totalSec % 3600) / 60);
  const seconds = totalSec % 60;

  if (hours > 24) {
    const days = Math.floor(hours / 24);
    const remHours = hours % 24;
    return `${days}d ${remHours}h ${minutes}m`;
  }

  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}

export function getStatusStyles(state: DisplaySession["state"], isLive: boolean) {
  if (isLive || state === "OPEN") {
    return {
      dot: "bg-emerald-400 animate-pulse shadow-[0_0_8px_#34d399]",
      badge: "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40",
      card: "bg-slate-900/80 border-emerald-500/30 shadow-[0_0_12px_rgba(16,185,129,0.08)]",
      timerText: "text-emerald-400",
    };
  }
  if (state === "PRE_MARKET") {
    return {
      dot: "bg-amber-400 animate-pulse",
      badge: "bg-amber-500/20 text-amber-300 border border-amber-500/40",
      card: "bg-slate-950/70 border-amber-500/30",
      timerText: "text-amber-400",
    };
  }
  if (state === "POST_MARKET") {
    return {
      dot: "bg-blue-400",
      badge: "bg-blue-500/20 text-blue-300 border border-blue-500/40",
      card: "bg-slate-950/70 border-blue-500/30",
      timerText: "text-blue-400",
    };
  }
  if (state === "HOLIDAY") {
    return {
      dot: "bg-purple-400",
      badge: "bg-purple-500/20 text-purple-300 border border-purple-500/40",
      card: "bg-slate-950/70 border-purple-500/30 shadow-[0_0_12px_rgba(168,85,247,0.08)]",
      timerText: "text-purple-300",
    };
  }
  if (state === "WEEKEND") {
    return {
      dot: "bg-slate-500",
      badge: "bg-slate-500/20 text-slate-300 border border-slate-500/40",
      card: "bg-slate-950/70 border-slate-800",
      timerText: "text-slate-400",
    };
  }
  // CLOSED default
  return {
    dot: "bg-rose-500",
    badge: "bg-rose-500/20 text-rose-300 border border-rose-500/40",
    card: "bg-slate-950/70 border-slate-800",
    timerText: "text-amber-400",
  };
}

export function computeOfflineSession(cfg: (typeof BENCHMARK_CONFIG)[0], now: Date): DisplaySession {
  const utcTime = now.getTime();

  if (cfg.id === "NSE") {
    const istOffset = 5.5 * 3600 * 1000;
    const istDate = new Date(utcTime + istOffset);
    const day = istDate.getUTCDay();
    const h = istDate.getUTCHours();
    const m = istDate.getUTCMinutes();
    const s = istDate.getUTCSeconds();
    const minsToday = h * 60 + m;
    const secsToday = minsToday * 60 + s;

    let state: DisplaySession["state"] = "CLOSED";
    let isOpen = false;
    let label = "Opens in";
    let secRemaining = 0;

    if (day >= 1 && day <= 5) {
      if (minsToday >= 555 && minsToday < 930) {
        // 09:15 - 15:30
        state = "OPEN";
        isOpen = true;
        label = "Closes in";
        secRemaining = 930 * 60 - secsToday;
      } else if (minsToday >= 540 && minsToday < 555) {
        // 09:00 - 09:15
        state = "PRE_MARKET";
        label = "Opens in";
        secRemaining = 555 * 60 - secsToday;
      } else if (minsToday >= 930 && minsToday < 960) {
        // 15:30 - 16:00
        state = "POST_MARKET";
        label = "Closes in";
        secRemaining = 960 * 60 - secsToday;
      } else if (minsToday < 540) {
        state = "CLOSED";
        secRemaining = 555 * 60 - secsToday;
      } else {
        state = "CLOSED";
        const daysToNext = day === 5 ? 3 : 1;
        secRemaining = daysToNext * 86400 + 555 * 60 - secsToday;
      }
    } else {
      state = "WEEKEND";
      label = "Opens Mon in";
      const daysToMon = day === 0 ? 1 : 2;
      secRemaining = daysToMon * 86400 + 555 * 60 - secsToday;
    }

    const clock = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")} IST`;
    return {
      id: "NSE",
      name: cfg.defaultName,
      region: cfg.defaultRegion,
      schedule: cfg.defaultSchedule,
      isOpen,
      state,
      localClock: clock,
      countdownLabel: label,
      countdownSeconds: Math.max(0, secRemaining),
      isAuthoritative: false,
    };
  }

  if (cfg.id === "NYSE") {
    const isEDT = now.getMonth() >= 2 && now.getMonth() <= 10;
    const nyOffset = (isEDT ? -4 : -5) * 3600 * 1000;
    const nyDate = new Date(utcTime + nyOffset);
    const day = nyDate.getUTCDay();
    const h = nyDate.getUTCHours();
    const m = nyDate.getUTCMinutes();
    const s = nyDate.getUTCSeconds();
    const minsToday = h * 60 + m;
    const secsToday = minsToday * 60 + s;

    let state: DisplaySession["state"] = "CLOSED";
    let isOpen = false;
    let label = "Opens in";
    let secRemaining = 0;

    if (day >= 1 && day <= 5) {
      if (minsToday >= 570 && minsToday < 960) {
        // 09:30 - 16:00
        state = "OPEN";
        isOpen = true;
        label = "Closes in";
        secRemaining = 960 * 60 - secsToday;
      } else if (minsToday >= 240 && minsToday < 570) {
        // 04:00 - 09:30
        state = "PRE_MARKET";
        label = "Opens in";
        secRemaining = 570 * 60 - secsToday;
      } else if (minsToday >= 960 && minsToday < 1200) {
        // 16:00 - 20:00
        state = "POST_MARKET";
        label = "Closes in";
        secRemaining = 1200 * 60 - secsToday;
      } else if (minsToday < 240) {
        state = "CLOSED";
        secRemaining = 570 * 60 - secsToday;
      } else {
        state = "CLOSED";
        const daysToNext = day === 5 ? 3 : 1;
        secRemaining = daysToNext * 86400 + 570 * 60 - secsToday;
      }
    } else {
      state = "WEEKEND";
      label = "Opens Mon in";
      const daysToMon = day === 0 ? 1 : 2;
      secRemaining = daysToMon * 86400 + 570 * 60 - secsToday;
    }

    const clock = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")} ${isEDT ? "EDT" : "EST"}`;
    return {
      id: "NYSE",
      name: cfg.defaultName,
      region: cfg.defaultRegion,
      schedule: `09:30–16:00 ${isEDT ? "EDT" : "EST"}`,
      isOpen,
      state,
      localClock: clock,
      countdownLabel: label,
      countdownSeconds: Math.max(0, secRemaining),
      isAuthoritative: false,
    };
  }

  if (cfg.id === "COMEX") {
    const isEDT = now.getMonth() >= 2 && now.getMonth() <= 10;
    const nyOffset = (isEDT ? -4 : -5) * 3600 * 1000;
    const nyDate = new Date(utcTime + nyOffset);
    const day = nyDate.getUTCDay();
    const h = nyDate.getUTCHours();
    const m = nyDate.getUTCMinutes();
    const s = nyDate.getUTCSeconds();
    const secsToday = (h * 60 + m) * 60 + s;

    let state: DisplaySession["state"] = "CLOSED";
    let isOpen = false;
    let label = "Opens in";
    let secRemaining = 0;

    const isWeekend = day === 6 || (day === 0 && h < 18) || (day === 5 && h >= 17);
    const isBreak = !isWeekend && h === 17;

    if (!isWeekend && !isBreak) {
      state = "OPEN";
      isOpen = true;
      label = "Break/Close in";
      let targetH = 17;
      let diff = targetH - h;
      if (diff <= 0) diff += 24;
      secRemaining = diff * 3600 - (m * 60 + s);
    } else if (isBreak) {
      state = "CLOSED";
      label = "Reopens in";
      secRemaining = 3600 - (m * 60 + s);
    } else {
      state = "WEEKEND";
      label = "Opens Sun in";
      const daysToSun = (7 - day) % 7;
      secRemaining = daysToSun * 86400 + 18 * 3600 - secsToday;
    }

    const clock = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")} ${isEDT ? "EDT" : "EST"}`;
    return {
      id: "COMEX",
      name: cfg.defaultName,
      region: cfg.defaultRegion,
      schedule: cfg.defaultSchedule,
      isOpen,
      state,
      localClock: clock,
      countdownLabel: label,
      countdownSeconds: Math.max(0, secRemaining),
      isAuthoritative: false,
    };
  }

  // CRYPTO 24/7
  return {
    id: "CRYPTO",
    name: cfg.defaultName,
    region: cfg.defaultRegion,
    schedule: cfg.defaultSchedule,
    isOpen: true,
    state: "OPEN",
    localClock: now.toISOString().substring(11, 19) + " UTC",
    countdownLabel: "Non-Stop",
    countdownSeconds: 0,
    isAuthoritative: false,
  };
}

export function resolveSessions(
  sessionData?: Record<string, SessionStatusInfo>,
  now: Date = new Date()
): DisplaySession[] {
  const utcTime = now.getTime();

  return BENCHMARK_CONFIG.map((cfg) => {
    // 1. Try to find backend session object
    let backendSess: SessionStatusInfo | undefined;
    if (sessionData) {
      backendSess = sessionData[cfg.primaryKey];
      if (!backendSess) {
        for (const alias of cfg.aliases) {
          if (sessionData[alias]) {
            backendSess = sessionData[alias];
            break;
          }
        }
      }
    }

    // If backend session exists, use authoritative data
    if (backendSess) {
      const isOpen = backendSess.is_open ?? (backendSess.state === "OPEN");
      const state = backendSess.state;
      const holidayName = backendSess.holiday_name;

      // Dynamic countdown: compute remaining seconds from UTC target timestamp
      let countdownSec = backendSess.seconds_to_next_state ?? 0;
      const targetUtc = backendSess.next_state_time_utc || backendSess.target_time_utc;
      if (targetUtc) {
        const targetMs = new Date(targetUtc).getTime();
        if (!isNaN(targetMs)) {
          countdownSec = Math.max(0, Math.floor((targetMs - utcTime) / 1000));
        }
      }

      // Determine label
      let countdownLabel = "Opens in";
      if (state === "OPEN") {
        countdownLabel = cfg.id === "COMEX" ? "Break/Close in" : "Closes in";
      } else if (state === "HOLIDAY") {
        countdownLabel = holidayName ? `${holidayName} (Opens in)` : "Holiday (Opens in)";
      } else if (state === "WEEKEND") {
        countdownLabel = cfg.id === "COMEX" ? "Opens Sun in" : "Opens Mon in";
      } else if (state === "POST_MARKET") {
        countdownLabel = "Closes in";
      } else if (cfg.id === "CRYPTO") {
        countdownLabel = "Non-Stop";
      }

      // Format local clock in exchange timezone
      let localClock = backendSess.local_time_str || backendSess.local_time || "";
      if (!localClock) {
        try {
          const timeStr = new Intl.DateTimeFormat("en-GB", {
            timeZone: backendSess.exchange_tz || backendSess.local_timezone || cfg.timeZone,
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
          }).format(now);
          localClock = `${timeStr} ${cfg.tzName}`;
        } catch {
          localClock = now.toISOString().substring(11, 19) + " UTC";
        }
      }

      return {
        id: cfg.id,
        name: backendSess.exchange_name || cfg.defaultName,
        region: cfg.defaultRegion,
        schedule: backendSess.session_schedule || cfg.defaultSchedule,
        isOpen,
        state,
        localClock,
        countdownLabel,
        countdownSeconds: countdownSec,
        holidayName,
        isAuthoritative: true,
      };
    }

    // 2. Offline Fallback Heuristics (when backend disconnected)
    return computeOfflineSession(cfg, now);
  });
}

export const MarketSessionRibbon: React.FC<MarketSessionRibbonProps> = ({
  marketSessions,
  sessions,
}) => {
  const isVisible = usePageVisibility();
  const sessionData = marketSessions ?? sessions;

  const [displaySessions, setDisplaySessions] = useState<DisplaySession[]>(() =>
    resolveSessions(sessionData)
  );

  useEffect(() => {
    // Immediate sync on prop change
    setDisplaySessions(resolveSessions(sessionData));

    if (!isVisible) return;

    // 1-second countdown tick
    const timer = setInterval(() => {
      setDisplaySessions(resolveSessions(sessionData));
    }, 1000);

    return () => clearInterval(timer);
  }, [sessionData, isVisible]);

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
      {displaySessions.map((s) => {
        const isLive = s.isOpen;
        const styles = getStatusStyles(s.state, isLive);

        return (
          <div
            key={s.id}
            className={`rounded-lg p-3 border transition-all duration-200 ${styles.card}`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <span className={`w-2 h-2 rounded-full ${styles.dot}`} />
                <span className="font-bold text-sm text-slate-100">{s.name}</span>
              </div>
              <span
                className={`text-[10px] font-mono px-1.5 py-0.5 rounded font-semibold tracking-wide ${styles.badge}`}
              >
                {s.state}
              </span>
            </div>

            <div className="mt-2 flex items-center justify-between text-xs font-mono">
              <span className="text-slate-400 flex items-center">
                <Clock className="w-3 h-3 mr-1 text-slate-500" />
                {s.localClock}
              </span>
              <span className={`font-semibold ${styles.timerText}`}>
                {s.countdownLabel === "Non-Stop" ? (
                  <span className="flex items-center text-sky-400">
                    <ShieldCheck className="w-3 h-3 mr-1" />
                    24/7/365
                  </span>
                ) : (
                  `${s.countdownLabel} ${formatCountdown(s.countdownSeconds)}`
                )}
              </span>
            </div>

            <div className="mt-1 text-[11px] text-slate-500 flex items-center justify-between">
              <span>{s.schedule}</span>
              <span
                className="text-[10px] text-slate-400 truncate max-w-[130px]"
                title={s.holidayName || s.region}
              >
                {s.state === "HOLIDAY" && s.holidayName ? (
                  <span className="text-purple-300 font-medium flex items-center">
                    <CalendarOff className="w-2.5 h-2.5 mr-0.5 inline" />
                    {s.holidayName}
                  </span>
                ) : (
                  s.region
                )}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
};
