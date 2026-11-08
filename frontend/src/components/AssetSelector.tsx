import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  CheckCircle2,
  AlertCircle,
  Search,
  Shield,
  ShieldOff,
  Sparkles,
  X,
  LayoutGrid,
  ChevronDown,
  Layers,
  ChevronRight,
} from "lucide-react";
import {
  AssetTelemetry,
  BotTradeResponse,
} from "../types";
import {
  NSE_MASTER_DIRECTORY,
  NSEInstrument,
  formatINR,
} from "../utils/indianMarket";

interface AssetSelectorProps {
  assets: Record<string, AssetTelemetry>;
  selectedTicker: string;
  onSelectTicker: (ticker: string) => void;
  armedTickers: string[];
  onToggleArm: (ticker: string) => void;
  onAddCustomTicker: (ticker: string) => void;
  onPlaceBotTrade?: (
    ticker: string,
    direction?: "AUTO" | "LONG" | "SHORT",
    allocWeight?: number
  ) => Promise<BotTradeResponse>;
}

export type IndexFilter =
  | "ALL"
  | "NIFTY_50"
  | "NIFTY_NEXT_50"
  | "NIFTY_MIDCAP"
  | "BANK_NIFTY"
  | "NIFTY_IT"
  | "NIFTY_AUTO"
  | "NIFTY_PHARMA"
  | "NIFTY_FMCG"
  | "NIFTY_ENERGY"
  | "NIFTY_METALS"
  | "DEFENSE_RAIL"
  | "SENSEX";

export type ViewMode = "GRID" | "GROUPED_SECTOR";

const ALL_SECTORS = [
  "ALL",
  "Banking & Finance",
  "Information Technology",
  "Automobiles",
  "Pharmaceuticals",
  "Energy & Power",
  "Energy & Oil/Gas",
  "Fast Moving Consumer Goods",
  "Metals & Mining",
  "Defense & Aerospace",
  "Railways",
  "Infrastructure",
  "Realty",
  "Chemicals",
  "Consumer Tech",
  "Telecom",
];

export const AssetSelector: React.FC<AssetSelectorProps> = ({
  assets,
  selectedTicker,
  onSelectTicker,
  armedTickers,
  onToggleArm,
  onAddCustomTicker,
  onPlaceBotTrade,
}) => {
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedIndex, setSelectedIndex] = useState<IndexFilter>("ALL");
  const [selectedSector, setSelectedSector] = useState<string>("ALL");
  const [selectedCap, setSelectedCap] = useState<string>("ALL");
  const [viewMode, setViewMode] = useState<ViewMode>("GRID");
  const [collapsedSectors, setCollapsedSectors] = useState<Record<string, boolean>>({});

  const [submittingKey, setSubmittingKey] = useState<string | null>(null);
  const [botAllocPct, setBotAllocPct] = useState<number>(0); // 0 = Kelly Auto
  const [tradeBanner, setTradeBanner] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  const searchInputRef = useRef<HTMLInputElement>(null);

  // Global hotkey: '/' or 'Ctrl+K' focuses search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        (e.key === "/" && (e.target as HTMLElement)?.tagName !== "INPUT") ||
        ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k")
      ) {
        e.preventDefault();
        searchInputRef.current?.focus();
        searchInputRef.current?.select();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Filter and build unified directory combining live telemetry with master catalog
  const filteredInstruments = useMemo(() => {
    return NSE_MASTER_DIRECTORY.filter((item) => {
      // 1. Text Search Query
      if (searchQuery.trim()) {
        const q = searchQuery.trim().toLowerCase();
        const matchesTicker = item.ticker.toLowerCase().includes(q);
        const matchesName = item.name.toLowerCase().includes(q);
        const matchesSector = item.sector.toLowerCase().includes(q);
        if (!matchesTicker && !matchesName && !matchesSector) return false;
      }

      // 2. Index Category Filter
      if (selectedIndex !== "ALL") {
        if (selectedIndex === "NIFTY_50" && item.index !== "NIFTY_50") return false;
        if (selectedIndex === "NIFTY_NEXT_50" && item.index !== "NIFTY_NEXT_50") return false;
        if (selectedIndex === "NIFTY_MIDCAP" && item.index !== "NIFTY_MIDCAP") return false;
        if (selectedIndex === "BANK_NIFTY" && item.sector !== "Banking & Finance") return false;
        if (selectedIndex === "NIFTY_IT" && item.sector !== "Information Technology") return false;
        if (selectedIndex === "NIFTY_AUTO" && item.sector !== "Automobiles") return false;
        if (selectedIndex === "NIFTY_PHARMA" && item.sector !== "Pharmaceuticals") return false;
        if (selectedIndex === "NIFTY_FMCG" && item.sector !== "Fast Moving Consumer Goods") return false;
        if (
          selectedIndex === "NIFTY_ENERGY" &&
          item.sector !== "Energy & Power" &&
          item.sector !== "Energy & Oil/Gas"
        )
          return false;
        if (selectedIndex === "NIFTY_METALS" && item.sector !== "Metals & Mining") return false;
        if (
          selectedIndex === "DEFENSE_RAIL" &&
          item.sector !== "Defense & Aerospace" &&
          item.sector !== "Railways"
        )
          return false;
        if (selectedIndex === "SENSEX" && item.exchange !== "BSE" && !item.ticker.includes(".BO")) {
          // If Sensex selected, show top 30 equivalents
          const sensexSet = new Set([
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "SBIN.NS",
            "BHARTIARTL.NS", "ITC.NS", "KOTAKBANK.NS", "LT.NS", "AXISBANK.NS", "HINDUNILVR.NS",
            "BAJFINANCE.NS", "MARUTI.NS", "ASIANPAINT.NS", "HCLTECH.NS", "SUNPHARMA.NS", "TITAN.NS",
            "ULTRACEMCO.NS", "TATASTEEL.NS", "NTPC.NS", "POWERGRID.NS", "M&M.NS", "JSWSTEEL.NS",
            "BAJAJFINSV.NS", "NESTLEIND.NS", "INDUSINDBK.NS", "TECHM.NS", "TRENT.NS", "BEL.NS"
          ]);
          if (!sensexSet.has(item.ticker)) return false;
        }
      }

      // 3. Sector Filter
      if (selectedSector !== "ALL" && item.sector !== selectedSector) {
        return false;
      }

      // 4. Market Cap Filter
      if (selectedCap !== "ALL" && item.marketCapTier !== selectedCap) {
        return false;
      }

      return true;
    });
  }, [searchQuery, selectedIndex, selectedSector, selectedCap]);

  // Group filtered instruments by Sector
  const groupedBySector = useMemo(() => {
    const groups: Record<string, NSEInstrument[]> = {};
    for (const inst of filteredInstruments) {
      if (!groups[inst.sector]) {
        groups[inst.sector] = [];
      }
      groups[inst.sector].push(inst);
    }
    return groups;
  }, [filteredInstruments]);

  // Toggle Sector Accordion Collapse
  const toggleSectorCollapse = (sector: string) => {
    setCollapsedSectors((prev) => ({
      ...prev,
      [sector]: !prev[sector],
    }));
  };

  // Stock Selection Handler: Selects ticker and arms/streams if not currently active
  const handleStockClick = (ticker: string) => {
    if (!assets[ticker]) {
      onAddCustomTicker(ticker);
    }
    onSelectTicker(ticker);
  };

  // 1-Click Autonomous Bot Trade execution
  const handleBotTradeClick = async (
    e: React.MouseEvent,
    ticker: string,
    direction: "AUTO" | "LONG" | "SHORT"
  ) => {
    e.stopPropagation();
    const cleanTicker = ticker.trim().toUpperCase();
    if (!cleanTicker) return;

    const actionKey = `${cleanTicker}-${direction}`;
    setSubmittingKey(actionKey);
    setTradeBanner(null);

    try {
      if (!assets[cleanTicker]) {
        onAddCustomTicker(cleanTicker);
      }
      onSelectTicker(cleanTicker);

      if (onPlaceBotTrade) {
        const resp = await onPlaceBotTrade(
          cleanTicker,
          direction,
          botAllocPct > 0 ? botAllocPct : undefined
        );
        const statusLabel =
          resp.status === "QUEUED"
            ? "Queued for Market Open"
            : "Executed via Kelly Engine";
        setTradeBanner({
          type: "success",
          text: `[BOT AUTO-TRADE] ${resp.direction} ${resp.ticker} (${statusLabel}) | Target: ₹${resp.target_price.toFixed(2)} | Stop: ₹${resp.stop_price.toFixed(2)} | Size: ${resp.allocation_weight_pct}%`,
        });
      } else {
        setTradeBanner({
          type: "success",
          text: `Added & Armed ${cleanTicker} for Autonomous Bot Trading`,
        });
      }
      window.setTimeout(() => setTradeBanner(null), 6000);
    } catch (err) {
      setTradeBanner({
        type: "error",
        text: err instanceof Error ? err.message : `Bot trade failed for ${cleanTicker}`,
      });
      window.setTimeout(() => setTradeBanner(null), 6000);
    } finally {
      setSubmittingKey(null);
    }
  };

  // Resolve price and live move for any instrument
  const resolvePriceData = (item: NSEInstrument) => {
    const live = assets[item.ticker];
    if (live) {
      return {
        price: live.current_price,
        movePct: live.move_pct,
        regime: live.regime || "REGIME",
        isLive: true,
        isArmed: armedTickers.includes(item.ticker),
        hasPos: live.has_open_position,
      };
    }
    return {
      price: item.basePrice ?? 1000.0,
      movePct: 0.0,
      regime: "LOW_VOL_BULL",
      isLive: false,
      isArmed: armedTickers.includes(item.ticker),
      hasPos: false,
    };
  };

  return (
    <div className="glass-panel rounded-xl p-4 space-y-3.5 border border-slate-800 bg-[#090d18]/90">
      {/* 1. Header: Search Bar, View Toggle, and Sizing Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Search Input Box */}
        <div className="relative flex-1 min-w-[280px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search Indian NSE / BSE equities (e.g. Reliance, TCS, HDFC Bank, Zomato, Trent, BEL, Tata Power)... [Press /]"
            className="w-full pl-9 pr-8 py-2 rounded-lg bg-slate-900/90 border border-slate-800 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500 font-mono transition"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* View Mode & Sizing Controls */}
        <div className="flex items-center space-x-2 text-xs font-mono">
          {/* View Mode Toggles */}
          <div className="flex items-center rounded-lg bg-slate-900 p-0.5 border border-slate-800">
            <button
              type="button"
              onClick={() => setViewMode("GRID")}
              className={`px-2.5 py-1 rounded text-xs flex items-center space-x-1.5 transition ${
                viewMode === "GRID"
                  ? "bg-cyan-500/20 text-cyan-300 font-semibold border border-cyan-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
              title="Card Grid View"
            >
              <LayoutGrid className="w-3.5 h-3.5" />
              <span>Grid</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode("GROUPED_SECTOR")}
              className={`px-2.5 py-1 rounded text-xs flex items-center space-x-1.5 transition ${
                viewMode === "GROUPED_SECTOR"
                  ? "bg-cyan-500/20 text-cyan-300 font-semibold border border-cyan-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
              title="Grouped by Industry Sector View"
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Sectors</span>
            </button>
          </div>

          {/* Bot Sizing Dropdown */}
          <div className="flex items-center space-x-1.5 pl-1">
            <Bot className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
            <select
              value={botAllocPct}
              onChange={(e) => setBotAllocPct(Number(e.target.value))}
              className="bg-slate-900 border border-slate-800 rounded px-2 py-1 text-slate-300 text-xs focus:outline-none focus:border-cyan-500"
              title="Bot position sizing mode"
            >
              <option value={0}>Kelly Auto</option>
              <option value={5}>5% Conservative</option>
              <option value={10}>10% Moderate</option>
              <option value={20}>20% Aggressive</option>
            </select>
          </div>

          {/* Quick Bot Trade for selected stock */}
          <button
            type="button"
            onClick={(e) => handleBotTradeClick(e, selectedTicker, "AUTO")}
            disabled={submittingKey !== null}
            className="px-3 py-1 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/40 text-cyan-300 font-semibold flex items-center space-x-1.5 transition shadow-[0_0_10px_rgba(6,182,212,0.15)] disabled:opacity-50"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Bot Auto-Trade {selectedTicker.replace(/\.(NS|BO)$/i, "")}</span>
          </button>
        </div>
      </div>

      {/* Trade Execution Feedback Banner */}
      {tradeBanner && (
        <div
          className={`px-3 py-2 rounded-lg text-xs font-mono flex items-center justify-between border ${
            tradeBanner.type === "success"
              ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
              : "bg-rose-500/15 text-rose-300 border-rose-500/30"
          }`}
        >
          <div className="flex items-center space-x-2">
            {tradeBanner.type === "success" ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            )}
            <span>{tradeBanner.text}</span>
          </div>
          <button
            type="button"
            onClick={() => setTradeBanner(null)}
            className="text-slate-400 hover:text-slate-200 ml-2"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* 2. Multi-Level Index & Category Navigation Ribbon */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
        <div className="flex flex-wrap items-center gap-1.5 text-xs font-mono">
          {[
            { id: "ALL", label: "All Listed NSE" },
            { id: "NIFTY_50", label: "Nifty 50" },
            { id: "NIFTY_NEXT_50", label: "Nifty Next 50" },
            { id: "NIFTY_MIDCAP", label: "Nifty Midcap" },
            { id: "BANK_NIFTY", label: "Bank Nifty" },
            { id: "NIFTY_IT", label: "Nifty IT" },
            { id: "NIFTY_AUTO", label: "Nifty Auto" },
            { id: "NIFTY_PHARMA", label: "Nifty Pharma" },
            { id: "NIFTY_FMCG", label: "Nifty FMCG" },
            { id: "NIFTY_ENERGY", label: "Nifty Energy" },
            { id: "NIFTY_METALS", label: "Nifty Metals" },
            { id: "DEFENSE_RAIL", label: "Defense & Rail" },
            { id: "SENSEX", label: "BSE Sensex" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setSelectedIndex(tab.id as IndexFilter)}
              className={`px-2.5 py-1 rounded-lg transition text-[11px] whitespace-nowrap ${
                selectedIndex === tab.id
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-semibold shadow-[0_0_8px_rgba(6,182,212,0.2)]"
                  : "bg-slate-900/60 text-slate-400 border border-slate-800/80 hover:text-slate-200 hover:bg-slate-800"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Dropdown Filters for Sector & Market Cap */}
        <div className="flex items-center space-x-2 text-xs font-mono">
          {/* Sector Dropdown */}
          <select
            value={selectedSector}
            onChange={(e) => setSelectedSector(e.target.value)}
            className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1 text-slate-300 text-[11px] focus:outline-none focus:border-cyan-500"
          >
            <option value="ALL">All Sectors ({filteredInstruments.length})</option>
            {ALL_SECTORS.filter((s) => s !== "ALL").map((sec) => (
              <option key={sec} value={sec}>
                {sec}
              </option>
            ))}
          </select>

          {/* Market Cap Tier Dropdown */}
          <select
            value={selectedCap}
            onChange={(e) => setSelectedCap(e.target.value)}
            className="bg-slate-900 border border-slate-800 rounded-lg px-2 py-1 text-slate-300 text-[11px] focus:outline-none focus:border-cyan-500"
          >
            <option value="ALL">All Caps</option>
            <option value="Large Cap">Large Cap</option>
            <option value="Mid Cap">Mid Cap</option>
          </select>

          <span className="text-[11px] font-mono text-slate-400 pl-2">
            Listed: <strong className="text-cyan-300">{filteredInstruments.length}</strong> • Armed:{" "}
            <strong className="text-sky-400">{armedTickers.length}</strong>
          </span>
        </div>
      </div>

      {/* 3. Main Universe Explorer (Grid Mode or Grouped by Sector Mode) */}
      {viewMode === "GRID" ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2.5 max-h-80 overflow-y-auto pr-1">
          {filteredInstruments.map((item) => {
            const isSelected = selectedTicker === item.ticker;
            const data = resolvePriceData(item);
            const isPos = data.movePct >= 0;

            return (
              <div
                key={item.ticker}
                onClick={() => handleStockClick(item.ticker)}
                className={`p-2.5 rounded-lg border cursor-pointer transition-all duration-150 flex flex-col justify-between ${
                  isSelected
                    ? "bg-slate-900 border-cyan-500 shadow-[0_0_10px_rgba(6,182,212,0.25)] ring-1 ring-cyan-500"
                    : "bg-slate-950/60 border-slate-800/80 hover:border-slate-700 hover:bg-slate-900/50"
                }`}
              >
                {/* Top: Ticker, Arm Button */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-1.5">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        data.isLive ? "bg-emerald-400 shadow-[0_0_6px_#34d399]" : "bg-sky-400/80"
                      }`}
                      title={data.isLive ? "Live Streaming Active" : "Click to stream quotes"}
                    />
                    <span className="font-mono font-bold text-xs text-slate-100">
                      {item.ticker}
                    </span>
                  </div>

                  {/* Arm Toggle Button */}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onToggleArm(item.ticker);
                    }}
                    className={`p-1 rounded transition ${
                      data.isArmed
                        ? "text-cyan-400 hover:text-cyan-300 bg-cyan-500/10"
                        : "text-slate-600 hover:text-slate-400 bg-slate-900"
                    }`}
                    title={data.isArmed ? "Armed for Autonomous Trading" : "Disarmed"}
                  >
                    {data.isArmed ? <Shield className="w-3.5 h-3.5" /> : <ShieldOff className="w-3.5 h-3.5" />}
                  </button>
                </div>

                {/* Company Name & Sector Pill */}
                <div className="mt-1">
                  <div className="text-[10px] text-slate-400 truncate" title={item.name}>
                    {item.name}
                  </div>
                  <div className="flex items-center space-x-1 mt-0.5">
                    <span className="text-[9px] px-1 py-0.2 rounded bg-slate-800/80 text-slate-400 font-mono truncate max-w-[90px]">
                      {item.sector}
                    </span>
                    <span className="text-[9px] px-1 py-0.2 rounded bg-slate-900 text-cyan-400/80 font-mono">
                      {item.marketCapTier === "Large Cap" ? "Large" : "Mid"}
                    </span>
                  </div>
                </div>

                {/* Price in INR & 1D Move */}
                <div className="mt-1.5 flex items-baseline justify-between font-mono">
                  <span className="text-sm font-semibold text-slate-200">
                    {formatINR(data.price, { decimals: 2 })}
                  </span>
                  <span
                    className={`text-[11px] font-medium ${
                      isPos ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {isPos ? "+" : ""}
                    {data.movePct.toFixed(2)}%
                  </span>
                </div>

                {/* Bottom: Regime & 1-Click Bot Trade */}
                <div className="mt-1.5 flex items-center justify-between text-[10px] text-slate-500 font-mono pt-1 border-t border-slate-900">
                  <span className="truncate max-w-[70px] text-[9px]">
                    {data.regime.substring(0, 8)}
                  </span>
                  <div className="flex items-center space-x-1">
                    {data.hasPos && (
                      <span className="text-amber-400 font-semibold px-1 rounded bg-amber-500/10 text-[9px]">
                        POS
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={(e) => handleBotTradeClick(e, item.ticker, "AUTO")}
                      className="px-1.5 py-0.5 rounded bg-cyan-500/15 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/30 text-[9px] font-mono font-semibold transition"
                      title={`Let Autonomous Bot trade ${item.ticker}`}
                    >
                      Bot Trade
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* Grouped by Sector Accordion View */
        <div className="space-y-2.5 max-h-80 overflow-y-auto pr-1">
          {Object.entries(groupedBySector).map(([sectorName, instruments]) => {
            const isCollapsed = collapsedSectors[sectorName] ?? false;

            return (
              <div
                key={sectorName}
                className="rounded-lg border border-slate-800/80 bg-slate-950/40 overflow-hidden"
              >
                {/* Sector Header Accordion Button */}
                <button
                  type="button"
                  onClick={() => toggleSectorCollapse(sectorName)}
                  className="w-full px-3 py-2 flex items-center justify-between bg-slate-900/60 hover:bg-slate-900 text-left transition font-mono"
                >
                  <div className="flex items-center space-x-2">
                    {isCollapsed ? (
                      <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5 text-cyan-400" />
                    )}
                    <span className="font-bold text-xs text-slate-200">{sectorName}</span>
                    <span className="px-1.5 py-0.2 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 text-[10px]">
                      {instruments.length} {instruments.length === 1 ? "stock" : "stocks"}
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-500">Click to {isCollapsed ? "expand" : "collapse"}</span>
                </button>

                {/* Sector Stocks Grid */}
                {!isCollapsed && (
                  <div className="p-2.5 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
                    {instruments.map((item) => {
                      const isSelected = selectedTicker === item.ticker;
                      const data = resolvePriceData(item);
                      const isPos = data.movePct >= 0;

                      return (
                        <div
                          key={item.ticker}
                          onClick={() => handleStockClick(item.ticker)}
                          className={`p-2 rounded-lg border cursor-pointer transition flex flex-col justify-between ${
                            isSelected
                              ? "bg-slate-900 border-cyan-500 shadow-[0_0_8px_rgba(6,182,212,0.2)] ring-1 ring-cyan-500"
                              : "bg-slate-950/70 border-slate-800/70 hover:border-slate-700"
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-mono font-bold text-xs text-slate-100">
                              {item.ticker}
                            </span>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                onToggleArm(item.ticker);
                              }}
                              className={`p-0.5 rounded ${
                                data.isArmed ? "text-cyan-400" : "text-slate-600"
                              }`}
                            >
                              {data.isArmed ? (
                                <Shield className="w-3 h-3" />
                              ) : (
                                <ShieldOff className="w-3 h-3" />
                              )}
                            </button>
                          </div>

                          <div className="text-[10px] text-slate-400 truncate mt-0.5" title={item.name}>
                            {item.name}
                          </div>

                          <div className="mt-1 flex items-baseline justify-between font-mono">
                            <span className="text-xs font-semibold text-slate-200">
                              {formatINR(data.price, { decimals: 2 })}
                            </span>
                            <span
                              className={`text-[10px] ${
                                isPos ? "text-emerald-400" : "text-rose-400"
                              }`}
                            >
                              {isPos ? "+" : ""}
                              {data.movePct.toFixed(2)}%
                            </span>
                          </div>

                          <div className="mt-1 pt-1 border-t border-slate-900 flex items-center justify-end">
                            <button
                              type="button"
                              onClick={(e) => handleBotTradeClick(e, item.ticker, "AUTO")}
                              className="px-1.5 py-0.5 rounded bg-cyan-500/15 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/30 text-[9px] font-mono font-semibold"
                            >
                              Bot Trade
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
