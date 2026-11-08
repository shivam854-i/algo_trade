import React, { useEffect, useState } from "react";
import {
  TrendingUp,
  TrendingDown,
  Clock,
  Calendar,
  Layers,
  Activity,
  RefreshCw,
  Loader2,
} from "lucide-react";
import { MarketIntelligenceData } from "../../types";

export const MarketIntelligenceView: React.FC = () => {
  const [data, setData] = useState<MarketIntelligenceData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchIntelligence = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/market/intelligence");
      if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch market intelligence`);
      const json = await res.json();
      setData(json);
    } catch (err: any) {
      setError(err.message || "Failed to load market intelligence");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchIntelligence();
    const interval = setInterval(fetchIntelligence, 10000);
    return () => clearInterval(interval);
  }, []);

  if (isLoading && !data) {
    return (
      <div className="py-24 flex flex-col items-center justify-center space-y-3 font-mono text-slate-400">
        <Loader2 className="w-8 h-8 animate-spin text-cyan-400" />
        <span className="text-sm">Aggregating Indian Capital Markets Intelligence...</span>
      </div>
    );
  }

  const breadth = data?.market_breadth ?? {
    advances: 34,
    declines: 15,
    unchanged: 1,
    total: 50,
    advance_decline_ratio: 2.27,
  };

  const advancePct = Math.round((breadth.advances / Math.max(breadth.total, 1)) * 100);
  const declinePct = Math.round((breadth.declines / Math.max(breadth.total, 1)) * 100);

  return (
    <div className="space-y-6 font-mono">
      {/* Top Header & Refresh */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div>
          <h2 className="text-lg font-bold text-slate-100 flex items-center space-x-2">
            <Activity className="w-5 h-5 text-cyan-400" />
            <span>INDIAN CAPITAL MARKETS INTELLIGENCE</span>
          </h2>
          <p className="text-xs text-slate-400">
            Authoritative Macro Telemetry • NSE & BSE Benchmarks • Sector Matrix • Advance/Decline
          </p>
        </div>

        <button
          type="button"
          onClick={fetchIntelligence}
          disabled={isLoading}
          className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 text-xs flex items-center space-x-1.5 transition disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-cyan-400" : ""}`} />
          <span>Refresh Data</span>
        </button>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
          Notice: {error}
        </div>
      )}

      {/* 1. Indian Benchmark Indices Cards */}
      <section className="space-y-3">
        <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center space-x-1.5">
          <Layers className="w-4 h-4 text-cyan-400" />
          <span>Key Indian Benchmark Indices</span>
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {(data?.benchmarks ?? []).map((bm) => {
            const isPos = bm.change_pct >= 0;
            return (
              <div
                key={bm.symbol}
                className="p-4 rounded-xl border border-slate-800 bg-slate-900/40 hover:border-slate-700 transition"
              >
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span className="font-bold text-slate-200">{bm.name}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">
                    {bm.exchange}
                  </span>
                </div>

                <div className="mt-2 flex items-baseline justify-between">
                  <span className="text-lg font-bold text-slate-100">
                    ₹{bm.price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </span>
                  <span
                    className={`text-xs font-bold flex items-center ${
                      isPos ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {isPos ? (
                      <TrendingUp className="w-3.5 h-3.5 mr-0.5" />
                    ) : (
                      <TrendingDown className="w-3.5 h-3.5 mr-0.5" />
                    )}
                    {isPos ? "+" : ""}
                    {bm.change_pct.toFixed(2)}%
                  </span>
                </div>

                <div className="mt-2.5 pt-2 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-500">
                  <span>H: ₹{bm.high.toLocaleString("en-IN")}</span>
                  <span>L: ₹{bm.low.toLocaleString("en-IN")}</span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* 2. Market Breadth & Trading Hours Matrix */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Market Breadth (Nifty 50 constituents) */}
        <div className="lg:col-span-5 p-4 rounded-xl border border-slate-800 bg-slate-900/30 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
              Market Breadth (Nifty 50)
            </h3>
            <span className="text-[11px] text-slate-400">
              A/D Ratio: <strong className="text-cyan-400">{breadth.advance_decline_ratio.toFixed(2)}</strong>
            </span>
          </div>

          {/* Breadth Bar */}
          <div className="space-y-1.5">
            <div className="h-3 w-full rounded-full bg-slate-800 overflow-hidden flex">
              <div
                style={{ width: `${advancePct}%` }}
                className="bg-emerald-500 h-full transition-all duration-500"
                title={`Advances: ${breadth.advances}`}
              />
              <div
                style={{ width: `${declinePct}%` }}
                className="bg-rose-500 h-full transition-all duration-500"
                title={`Declines: ${breadth.declines}`}
              />
            </div>
            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <span className="text-emerald-400 font-semibold">{breadth.advances} Advances ({advancePct}%)</span>
              <span className="text-slate-500">{breadth.unchanged} Unchanged</span>
              <span className="text-rose-400 font-semibold">{breadth.declines} Declines ({declinePct}%)</span>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 text-[11px] text-slate-400 space-y-1.5">
            <div className="flex justify-between">
              <span>Overall Sentiment:</span>
              <span className="text-emerald-400 font-bold">
                {breadth.advance_decline_ratio >= 1.5 ? "BULLISH BREADTH" : breadth.advance_decline_ratio >= 0.8 ? "BALANCED" : "BEARISH PRESSURE"}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Constituents Tracked:</span>
              <span className="text-slate-200">{breadth.total} Equities</span>
            </div>
          </div>
        </div>

        {/* NSE & BSE Session Phases */}
        <div className="lg:col-span-7 p-4 rounded-xl border border-slate-800 bg-slate-900/30 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center space-x-1.5">
              <Clock className="w-3.5 h-3.5 text-cyan-400" />
              <span>NSE / BSE Official Daily Trading Schedule</span>
            </h3>
            <span className="text-[11px] px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 font-semibold">
              Timezone: Asia/Kolkata (IST)
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-1">
            <div className="p-3 rounded-lg bg-slate-950/50 border border-slate-800">
              <span className="text-[10px] text-amber-400 font-bold block uppercase">Phase 1: Pre-Open</span>
              <span className="text-sm font-bold text-slate-100 block mt-0.5">09:00 – 09:15 IST</span>
              <span className="text-[10px] text-slate-500 block mt-1">Order collection, cancellation & price discovery matching</span>
            </div>

            <div className="p-3 rounded-lg bg-slate-950/50 border border-emerald-500/30 shadow-[0_0_10px_rgba(16,185,129,0.05)]">
              <span className="text-[10px] text-emerald-400 font-bold block uppercase flex items-center">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse mr-1" />
                Phase 2: Regular (RTH)
              </span>
              <span className="text-sm font-bold text-slate-100 block mt-0.5">09:15 – 15:30 IST</span>
              <span className="text-[10px] text-slate-500 block mt-1">Continuous automated limit and market order execution</span>
            </div>

            <div className="p-3 rounded-lg bg-slate-950/50 border border-slate-800">
              <span className="text-[10px] text-indigo-400 font-bold block uppercase">Phase 3: Post-Market</span>
              <span className="text-sm font-bold text-slate-100 block mt-0.5">15:30 – 16:00 IST</span>
              <span className="text-[10px] text-slate-500 block mt-1">Closing price calculation & fixed closing price trade crossing</span>
            </div>
          </div>
        </div>
      </div>

      {/* 3. Sector Heatmap Matrix */}
      <section className="space-y-3">
        <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center space-x-1.5">
          <Activity className="w-4 h-4 text-cyan-400" />
          <span>Indian Sector Performance Matrix</span>
        </h3>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {(data?.sectors ?? [
            { sector: "IT Services", change_pct: 1.45, lead: "TCS", sentiment: "Bullish" },
            { sector: "Private Banks", change_pct: 0.82, lead: "HDFCBANK", sentiment: "Bullish" },
            { sector: "Automobiles", change_pct: -0.34, lead: "TATAMOTORS", sentiment: "Mild Bearish" },
            { sector: "Pharma", change_pct: 0.65, lead: "SUNPHARMA", sentiment: "Positive" },
            { sector: "Energy & Oil", change_pct: 1.12, lead: "RELIANCE", sentiment: "Bullish" },
            { sector: "FMCG", change_pct: -0.18, lead: "ITC", sentiment: "Neutral" },
          ]).map((sec) => {
            const isPos = sec.change_pct >= 0;
            return (
              <div
                key={sec.sector}
                className="p-3.5 rounded-xl border border-slate-800 bg-slate-900/40 flex flex-col justify-between"
              >
                <div>
                  <span className="text-xs font-bold text-slate-200 block truncate">{sec.sector}</span>
                  <span className="text-[10px] text-slate-500">Lead: {sec.lead}</span>
                </div>

                <div className="mt-3 flex items-center justify-between">
                  <span
                    className={`text-sm font-bold ${isPos ? "text-emerald-400" : "text-rose-400"}`}
                  >
                    {isPos ? "+" : ""}
                    {sec.change_pct.toFixed(2)}%
                  </span>
                  <span
                    className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase ${
                      isPos ? "bg-emerald-500/20 text-emerald-300" : "bg-rose-500/20 text-rose-300"
                    }`}
                  >
                    {sec.sentiment}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* 4. Statutory Exchange Holidays (NSE/BSE 2026/2027) */}
      <section className="space-y-3">
        <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center space-x-1.5">
          <Calendar className="w-4 h-4 text-cyan-400" />
          <span>Statutory Exchange Holidays (NSE & BSE Mumbai)</span>
        </h3>

        <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-900/30">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 text-[11px] uppercase">
                <tr>
                  <th className="py-2.5 px-4 font-semibold">Date</th>
                  <th className="py-2.5 px-4 font-semibold">Holiday Occasion</th>
                  <th className="py-2.5 px-4 font-semibold">Exchange Jurisdictions</th>
                  <th className="py-2.5 px-4 font-semibold">Trading Session Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                {(data?.holidays ?? [
                  { date: "2026-01-26", name: "Republic Day", exchange: "NSE & BSE" },
                  { date: "2026-03-03", name: "Holi", exchange: "NSE & BSE" },
                  { date: "2026-04-03", name: "Good Friday", exchange: "NSE & BSE" },
                  { date: "2026-04-14", name: "Dr. B.R. Ambedkar Jayanti", exchange: "NSE & BSE" },
                  { date: "2026-05-01", name: "Maharashtra Day", exchange: "NSE & BSE" },
                  { date: "2026-10-02", name: "Mahatma Gandhi Jayanti", exchange: "NSE & BSE" },
                  { date: "2026-11-08", name: "Diwali Laxmi Pujan (Muhurat Trading Only)", exchange: "NSE & BSE" },
                  { date: "2026-12-25", name: "Christmas", exchange: "NSE & BSE" },
                ]).map((h) => (
                  <tr key={h.date} className="hover:bg-slate-800/30 transition">
                    <td className="py-2.5 px-4 font-bold text-cyan-400">{h.date}</td>
                    <td className="py-2.5 px-4 text-slate-100 font-medium">{h.name}</td>
                    <td className="py-2.5 px-4 text-slate-400">{h.exchange}</td>
                    <td className="py-2.5 px-4">
                      <span className="px-2 py-0.5 rounded text-[10px] bg-amber-500/15 text-amber-300 border border-amber-500/30 font-semibold">
                        CLOSED (REGULAR HOURS)
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
};
