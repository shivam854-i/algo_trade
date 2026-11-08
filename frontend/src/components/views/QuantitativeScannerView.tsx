import React, { useEffect, useState, useMemo } from "react";
import {
  Radar,
  Search,
  ArrowUpDown,
  CheckCircle2,
  XCircle,
  RefreshCw,
} from "lucide-react";
import { ScannerInstrument, PricePoint, AssetTelemetry } from "../../types";
import { ChartContainer } from "../ChartContainer";

export interface QuantitativeScannerViewProps {
  onSelectTicker: (ticker: string) => void;
  chartData: PricePoint[];
  assets: Record<string, AssetTelemetry>;
  onPlaceBotTrade: (ticker: string, direction?: "AUTO" | "LONG" | "SHORT", allocWeight?: number) => Promise<any>;
}

export const QuantitativeScannerView: React.FC<QuantitativeScannerViewProps> = ({
  onSelectTicker,
  chartData,
  assets,
  onPlaceBotTrade,
}) => {
  const [instruments, setInstruments] = useState<ScannerInstrument[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedSector, setSelectedSector] = useState<string>("ALL");
  const [onlyQualified, setOnlyQualified] = useState<boolean>(false);
  const [sortField, setSortField] = useState<keyof ScannerInstrument>("win_probability");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [inspectingTicker, setInspectingTicker] = useState<string | null>(null);

  const fetchScanner = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/market/scanner");
      if (!res.ok) throw new Error(`HTTP ${res.status}: Failed to fetch scanner data`);
      const json = await res.json();
      setInstruments(json.instruments || []);
    } catch (err: any) {
      setError(err.message || "Failed to load scanner instruments");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchScanner();
  }, []);

  const sectors = useMemo(() => {
    const s = new Set<string>();
    instruments.forEach((inst) => {
      if (inst.sector) s.add(inst.sector);
    });
    return Array.from(s).sort();
  }, [instruments]);

  const handleSort = (field: keyof ScannerInstrument) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  };

  const filteredInstruments = useMemo(() => {
    return instruments
      .filter((inst) => {
        if (onlyQualified && !inst.is_qualified) return false;
        if (selectedSector !== "ALL" && inst.sector !== selectedSector) return false;
        if (!searchQuery) return true;
        const q = searchQuery.toLowerCase();
        return (
          inst.ticker.toLowerCase().includes(q) ||
          inst.name.toLowerCase().includes(q) ||
          inst.sector.toLowerCase().includes(q)
        );
      })
      .sort((a, b) => {
        let valA = a[sortField];
        let valB = b[sortField];
        if (typeof valA === "string") {
          return sortDirection === "asc"
            ? (valA as string).localeCompare(valB as string)
            : (valB as string).localeCompare(valA as string);
        }
        return sortDirection === "asc"
          ? (Number(valA) - Number(valB))
          : (Number(valB) - Number(valA));
      });
  }, [instruments, onlyQualified, selectedSector, searchQuery, sortField, sortDirection]);

  const activeInspectAsset = inspectingTicker ? assets[inspectingTicker] : null;

  return (
    <div className="space-y-4 font-mono">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div>
          <h2 className="text-base font-bold text-slate-100 flex items-center space-x-2">
            <Radar className="w-5 h-5 text-cyan-400" />
            <span>INSTITUTIONAL QUANTITATIVE SCANNER</span>
          </h2>
          <p className="text-xs text-slate-400">
            Real-time ATR Volatility • 3-State HMM Regime • Meta-Probability • Kelly Allocation Fraction
          </p>
        </div>

        <button
          type="button"
          onClick={fetchScanner}
          disabled={isLoading}
          className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 text-xs flex items-center space-x-1.5 transition disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-cyan-400" : ""}`} />
          <span>Rescan Universe</span>
        </button>
      </div>

      {error && (
        <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs">
          Notice: {error}
        </div>
      )}

      {/* Filter Toolbar */}
      <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/40 flex flex-wrap items-center justify-between gap-3 text-xs">
        {/* Search */}
        <div className="relative flex-1 min-w-[220px]">
          <Search className="w-3.5 h-3.5 text-cyan-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            placeholder="Search by symbol or name (e.g. RELIANCE, TCS, HDFC)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-950/80 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
          />
        </div>

        {/* Sector Select */}
        <div className="flex items-center space-x-2">
          <span className="text-slate-500">Sector:</span>
          <select
            value={selectedSector}
            onChange={(e) => setSelectedSector(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-cyan-500"
          >
            <option value="ALL">All Sectors ({instruments.length})</option>
            {sectors.map((sec) => (
              <option key={sec} value={sec}>
                {sec}
              </option>
            ))}
          </select>
        </div>

        {/* Edge Qualified Toggle */}
        <label className="flex items-center space-x-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={onlyQualified}
            onChange={(e) => setOnlyQualified(e.target.checked)}
            className="rounded border-slate-700 bg-slate-900 text-cyan-500 focus:ring-cyan-500"
          />
          <span className="text-slate-300">Show Only Positive Net EV</span>
        </label>

        <span className="text-[11px] text-slate-500">
          Showing: <strong className="text-cyan-400">{filteredInstruments.length}</strong> / {instruments.length}
        </span>
      </div>

      {/* Scanner High-Density Table */}
      <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-900/30">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 text-[11px] uppercase">
              <tr>
                <th className="py-2.5 px-3 font-semibold cursor-pointer" onClick={() => handleSort("ticker")}>
                  <div className="flex items-center space-x-1">
                    <span>Instrument</span>
                    <ArrowUpDown className="w-3 h-3 text-slate-600" />
                  </div>
                </th>
                <th className="py-2.5 px-3 font-semibold cursor-pointer" onClick={() => handleSort("current_price")}>
                  <div className="flex items-center space-x-1">
                    <span>Price (₹)</span>
                    <ArrowUpDown className="w-3 h-3 text-slate-600" />
                  </div>
                </th>
                <th className="py-2.5 px-3 font-semibold cursor-pointer" onClick={() => handleSort("change_pct")}>
                  <div className="flex items-center space-x-1">
                    <span>24h %</span>
                    <ArrowUpDown className="w-3 h-3 text-slate-600" />
                  </div>
                </th>
                <th className="py-2.5 px-3 font-semibold cursor-pointer" onClick={() => handleSort("volatility_atr")}>
                  <div className="flex items-center space-x-1">
                    <span>ATR (14)</span>
                    <ArrowUpDown className="w-3 h-3 text-slate-600" />
                  </div>
                </th>
                <th className="py-2.5 px-3 font-semibold">Regime</th>
                <th className="py-2.5 px-3 font-semibold cursor-pointer" onClick={() => handleSort("win_probability")}>
                  <div className="flex items-center space-x-1">
                    <span>Win Prob</span>
                    <ArrowUpDown className="w-3 h-3 text-slate-600" />
                  </div>
                </th>
                <th className="py-2.5 px-3 font-semibold cursor-pointer" onClick={() => handleSort("kelly_fraction")}>
                  <div className="flex items-center space-x-1">
                    <span>Kelly Sizing</span>
                    <ArrowUpDown className="w-3 h-3 text-slate-600" />
                  </div>
                </th>
                <th className="py-2.5 px-3 font-semibold cursor-pointer" onClick={() => handleSort("r_r_ratio")}>
                  <div className="flex items-center space-x-1">
                    <span>R:R</span>
                    <ArrowUpDown className="w-3 h-3 text-slate-600" />
                  </div>
                </th>
                <th className="py-2.5 px-3 font-semibold">Signal</th>
                <th className="py-2.5 px-3 font-semibold text-center">Status</th>
                <th className="py-2.5 px-3 font-semibold text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {filteredInstruments.map((item) => {
                const isPos = item.change_pct >= 0;
                const winPct = (item.win_probability * 100).toFixed(1);
                const kellyPct = (item.kelly_fraction * 100).toFixed(1);

                return (
                  <tr
                    key={item.ticker}
                    className="hover:bg-slate-800/40 transition cursor-pointer"
                    onClick={() => {
                      onSelectTicker(item.ticker);
                      setInspectingTicker(item.ticker);
                    }}
                  >
                    <td className="py-2.5 px-3">
                      <div className="font-bold text-slate-100">{item.ticker}</div>
                      <div className="text-[10px] text-slate-500 truncate max-w-[140px]">{item.name}</div>
                    </td>
                    <td className="py-2.5 px-3 font-bold text-slate-200">
                      ₹{item.current_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </td>
                    <td className={`py-2.5 px-3 font-semibold ${isPos ? "text-emerald-400" : "text-rose-400"}`}>
                      {isPos ? "+" : ""}
                      {item.change_pct.toFixed(2)}%
                    </td>
                    <td className="py-2.5 px-3 text-slate-400">₹{item.volatility_atr.toFixed(2)}</td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                          item.regime.includes("Trending") || item.regime.includes("State 0")
                            ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                            : item.regime.includes("Crisis") || item.regime.includes("State 2")
                            ? "bg-rose-500/15 text-rose-300 border border-rose-500/30"
                            : "bg-amber-500/15 text-amber-300 border border-amber-500/30"
                        }`}
                      >
                        {item.regime}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 font-bold text-cyan-400">{winPct}%</td>
                    <td className="py-2.5 px-3 text-indigo-300">{kellyPct}%</td>
                    <td className="py-2.5 px-3 text-slate-300">{item.r_r_ratio.toFixed(2)}x</td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          item.signal === "BUY"
                            ? "bg-emerald-500/20 text-emerald-300"
                            : item.signal === "SELL"
                            ? "bg-rose-500/20 text-rose-300"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {item.signal}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      {item.is_qualified ? (
                        <span className="inline-flex items-center text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold">
                          <CheckCircle2 className="w-3 h-3 mr-1 text-emerald-400" />
                          EDGE QUALIFIED
                        </span>
                      ) : (
                        <span className="inline-flex items-center text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 font-medium">
                          <XCircle className="w-3 h-3 mr-1 text-slate-500" />
                          PRESERVE CASH
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectTicker(item.ticker);
                          setInspectingTicker(item.ticker);
                        }}
                        className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] border border-slate-700 transition"
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Slide-over Inspection Drawer */}
      {inspectingTicker && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex justify-end">
          <div className="w-full max-w-2xl bg-[#090d18] border-l border-slate-800 h-full p-6 flex flex-col space-y-4 overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-base font-bold text-slate-100 flex items-center space-x-2">
                  <span>{inspectingTicker}</span>
                  <span className="text-xs text-slate-400 font-normal">
                    {instruments.find((i) => i.ticker === inspectingTicker)?.name}
                  </span>
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setInspectingTicker(null)}
                className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs"
              >
                Close Drawer
              </button>
            </div>

            <div className="space-y-3">
              <ChartContainer
                asset={activeInspectAsset || undefined}
                selectedTicker={inspectingTicker}
                chartData={chartData}
              />
            </div>

            <div className="pt-2 flex justify-end space-x-3">
              <button
                type="button"
                onClick={() => {
                  onPlaceBotTrade(inspectingTicker, "AUTO");
                  setInspectingTicker(null);
                }}
                className="px-4 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs shadow-[0_0_12px_rgba(6,182,212,0.3)] transition"
              >
                Execute Bot Trade via Kelly Engine
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
