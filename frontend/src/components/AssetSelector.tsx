import React, { useState } from "react";
import { Plus, Search, Shield, ShieldOff } from "lucide-react";
import { AssetTelemetry } from "../types";

interface AssetSelectorProps {
  assets: Record<string, AssetTelemetry>;
  selectedTicker: string;
  onSelectTicker: (ticker: string) => void;
  armedTickers: string[];
  onToggleArm: (ticker: string) => void;
  onAddCustomTicker: (ticker: string) => void;
}

type CategoryTab = "ALL" | "NSE" | "US" | "COMMODITY" | "CRYPTO" | "FOREX";

export const AssetSelector: React.FC<AssetSelectorProps> = ({
  assets,
  selectedTicker,
  onSelectTicker,
  armedTickers,
  onToggleArm,
  onAddCustomTicker,
}) => {
  const [activeTab, setActiveTab] = useState<CategoryTab>("ALL");
  const [customInput, setCustomInput] = useState<string>("");
  const [searchFilter, setSearchFilter] = useState<string>("");

  const handleAddCustom = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanTicker = customInput.trim().toUpperCase();
    if (!cleanTicker) return;
    onAddCustomTicker(cleanTicker);
    setCustomInput("");
  };

  const assetList = Object.values(assets);

  // Filter based on active tab and search filter
  const filteredAssets = assetList.filter((a) => {
    // Search match
    if (searchFilter && !a.ticker.toLowerCase().includes(searchFilter.toLowerCase())) {
      return false;
    }

    if (activeTab === "ALL") return true;

    const tk = a.ticker.toUpperCase();
    if (activeTab === "NSE") {
      return tk.endsWith(".NS") || tk.endsWith(".BO") || a.jurisdiction === "INDIAN_NSE";
    }
    if (activeTab === "US") {
      return (
        !tk.includes("=") &&
        !tk.includes("-") &&
        !tk.endsWith(".NS") &&
        !tk.endsWith(".BO")
      );
    }
    if (activeTab === "COMMODITY") {
      return tk.endsWith("=F") || a.jurisdiction === "COMMODITY";
    }
    if (activeTab === "CRYPTO") {
      return tk.includes("-USD") || a.jurisdiction === "CRYPTO";
    }
    if (activeTab === "FOREX") {
      return tk.endsWith("=X") || a.jurisdiction === "FOREX";
    }
    return true;
  });

  return (
    <div className="glass-panel rounded-xl p-4 flex flex-col space-y-3">
      {/* Top Header: Tabs & Add Custom Ticker */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-slate-800 pb-3">
        {/* Category Tabs */}
        <div className="flex flex-wrap items-center gap-1.5 text-xs font-mono">
          {(
            [
              { id: "ALL", label: "All Monitored" },
              { id: "NSE", label: "Indian Equities (NSE)" },
              { id: "US", label: "US Equities" },
              { id: "COMMODITY", label: "Commodities" },
              { id: "CRYPTO", label: "Crypto 24/7" },
              { id: "FOREX", label: "Forex" },
            ] as const
          ).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-1.5 rounded-lg transition-all ${
                activeTab === tab.id
                  ? "bg-sky-500/20 text-sky-400 border border-sky-500/40 font-semibold shadow-[0_0_8px_rgba(56,189,248,0.2)]"
                  : "bg-slate-900/60 text-slate-400 border border-slate-800 hover:text-slate-200 hover:bg-slate-800"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Custom Symbol Form */}
        <div className="flex items-center gap-2">
          {/* Quick Filter */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Filter..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              className="bg-slate-950/80 border border-slate-800 rounded-lg pl-8 pr-2.5 py-1 text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500/50 w-28 sm:w-32"
            />
          </div>

          <form onSubmit={handleAddCustom} className="flex items-center gap-1.5">
            <input
              type="text"
              placeholder="Ticker e.g. TSLA, TATAMOTORS.NS"
              value={customInput}
              onChange={(e) => setCustomInput(e.target.value)}
              className="bg-slate-950/80 border border-slate-800 rounded-lg px-2.5 py-1 text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500/50 w-44"
            />
            <button
              type="submit"
              className="px-2.5 py-1 rounded-lg bg-sky-500/20 hover:bg-sky-500/30 text-sky-400 border border-sky-500/40 text-xs font-mono flex items-center transition"
            >
              <Plus className="w-3.5 h-3.5 mr-1" />
              Add
            </button>
          </form>
        </div>
      </div>

      {/* Asset Cards Horizontal Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2.5 max-h-48 overflow-y-auto pr-1">
        {filteredAssets.map((asset) => {
          const isSelected = selectedTicker === asset.ticker;
          const isArmed = armedTickers.includes(asset.ticker);
          const isPos = asset.move_pct >= 0;

          return (
            <div
              key={asset.ticker}
              onClick={() => onSelectTicker(asset.ticker)}
              className={`p-2.5 rounded-lg border cursor-pointer transition-all duration-150 flex flex-col justify-between ${
                isSelected
                  ? "bg-slate-900 border-sky-500 shadow-[0_0_10px_rgba(56,189,248,0.25)] ring-1 ring-sky-500"
                  : "bg-slate-950/60 border-slate-800/80 hover:border-slate-700 hover:bg-slate-900/50"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-1.5">
                  <span
                    className={`w-2 h-2 rounded-full ${
                      asset.exchange_open
                        ? "bg-emerald-400 shadow-[0_0_6px_#34d399]"
                        : "bg-rose-500/80"
                    }`}
                    title={asset.exchange_open ? "Exchange Open" : "Exchange Closed"}
                  />
                  <span className="font-mono font-bold text-xs text-slate-100">
                    {asset.ticker}
                  </span>
                </div>

                {/* Arm / Disarm Button */}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleArm(asset.ticker);
                  }}
                  className={`p-1 rounded transition ${
                    isArmed
                      ? "text-sky-400 hover:text-sky-300 bg-sky-500/10"
                      : "text-slate-600 hover:text-slate-400 bg-slate-900"
                  }`}
                  title={isArmed ? "Armed for Autonomous Trading" : "Disarmed (Observation Only)"}
                >
                  {isArmed ? <Shield className="w-3.5 h-3.5" /> : <ShieldOff className="w-3.5 h-3.5" />}
                </button>
              </div>

              <div className="mt-1 flex items-baseline justify-between font-mono">
                <span className="text-sm font-semibold text-slate-200">
                  {asset.current_price.toFixed(asset.decimals)}
                </span>
                <span
                  className={`text-[11px] font-medium ${
                    isPos ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {isPos ? "+" : ""}
                  {asset.move_pct.toFixed(2)}%
                </span>
              </div>

              <div className="mt-1 flex items-center justify-between text-[10px] text-slate-500 font-mono">
                <span>{asset.regime?.substring(0, 10) || "REGIME"}</span>
                {asset.has_open_position && (
                  <span className="text-amber-400 font-semibold px-1 rounded bg-amber-500/10">
                    POS
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
