import React, { useEffect, useRef, useState } from "react";
import {
  Bot,
  CheckCircle2,
  AlertCircle,
  ArrowUpRight,
  ArrowDownRight,
  Plus,
  Search,
  Shield,
  ShieldOff,
  Sparkles,
  X,
  Loader2,
} from "lucide-react";
import {
  AssetTelemetry,
  BotTradeResponse,
  SearchInstrumentResult,
} from "../types";

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

type CategoryTab = "ALL" | "NIFTY_50" | "BANK_NIFTY" | "NIFTY_IT" | "SENSEX";

// Instant client-side fallback catalog populated exclusively with Indian equities (NSE & BSE)
const FALLBACK_SEARCH_CATALOG: Array<{
  ticker: string;
  name: string;
  category: string;
  exchange: string;
  sector: string;
}> = [
  { ticker: "RELIANCE.NS", name: "Reliance Industries Ltd.", category: "NIFTY_50", exchange: "NSE", sector: "Energy, Telecom & Retail" },
  { ticker: "TCS.NS", name: "Tata Consultancy Services Ltd.", category: "NIFTY_IT", exchange: "NSE", sector: "IT Services & Consulting" },
  { ticker: "HDFCBANK.NS", name: "HDFC Bank Ltd.", category: "BANK_NIFTY", exchange: "NSE", sector: "Banking & Financials" },
  { ticker: "INFY.NS", name: "Infosys Ltd.", category: "NIFTY_IT", exchange: "NSE", sector: "IT & Digital Services" },
  { ticker: "ICICIBANK.NS", name: "ICICI Bank Ltd.", category: "BANK_NIFTY", exchange: "NSE", sector: "Private Banking" },
  { ticker: "SBIN.NS", name: "State Bank of India (SBI)", category: "BANK_NIFTY", exchange: "NSE", sector: "PSU Banking" },
  { ticker: "BHARTIARTL.NS", name: "Bharti Airtel Ltd.", category: "NIFTY_50", exchange: "NSE", sector: "Telecommunications" },
  { ticker: "TATAMOTORS.NS", name: "Tata Motors Ltd.", category: "NIFTY_50", exchange: "NSE", sector: "Automobiles & EV" },
  { ticker: "ITC.NS", name: "ITC Ltd.", category: "NIFTY_50", exchange: "NSE", sector: "FMCG, Cigarettes & Hotels" },
  { ticker: "LT.NS", name: "Larsen & Toubro Ltd.", category: "NIFTY_50", exchange: "NSE", sector: "Infrastructure & EPC" },
  { ticker: "KOTAKBANK.NS", name: "Kotak Mahindra Bank Ltd.", category: "BANK_NIFTY", exchange: "NSE", sector: "Private Banking" },
  { ticker: "AXISBANK.NS", name: "Axis Bank Ltd.", category: "BANK_NIFTY", exchange: "NSE", sector: "Private Banking" },
  { ticker: "HINDUNILVR.NS", name: "Hindustan Unilever Ltd.", category: "NIFTY_50", exchange: "NSE", sector: "FMCG & Consumer Goods" },
  { ticker: "BAJFINANCE.NS", name: "Bajaj Finance Ltd.", category: "NIFTY_50", exchange: "NSE", sector: "NBFC & Consumer Lending" },
  { ticker: "MARUTI.NS", name: "Maruti Suzuki India Ltd.", category: "NIFTY_50", exchange: "NSE", sector: "Automobiles" },
  { ticker: "HCLTECH.NS", name: "HCL Technologies Ltd.", category: "NIFTY_IT", exchange: "NSE", sector: "IT Services & R&D" },
  { ticker: "SUNPHARMA.NS", name: "Sun Pharmaceutical Industries", category: "NIFTY_50", exchange: "NSE", sector: "Pharmaceuticals" },
  { ticker: "TITAN.NS", name: "Titan Company Ltd.", category: "NIFTY_50", exchange: "NSE", sector: "Jewelry & Luxury Goods" },
  { ticker: "ULTRACEMCO.NS", name: "UltraTech Cement Ltd.", category: "NIFTY_50", exchange: "NSE", sector: "Cement & Building Materials" },
  { ticker: "TATASTEEL.NS", name: "Tata Steel Ltd.", category: "NIFTY_50", exchange: "NSE", sector: "Steel & Metallurgy" },
  { ticker: "NTPC.NS", name: "NTPC Ltd.", category: "NIFTY_50", exchange: "NSE", sector: "Power Generation" },
  { ticker: "POWERGRID.NS", name: "Power Grid Corp of India Ltd.", category: "NIFTY_50", exchange: "NSE", sector: "Power Transmission" },
  { ticker: "WIPRO.NS", name: "Wipro Ltd.", category: "NIFTY_IT", exchange: "NSE", sector: "IT Services & AI Solutions" },
  { ticker: "HAL.NS", name: "Hindustan Aeronautics Ltd.", category: "NIFTY_50", exchange: "NSE", sector: "Aerospace & Defense" },
  { ticker: "BEL.NS", name: "Bharat Electronics Ltd.", category: "NIFTY_50", exchange: "NSE", sector: "Defense Electronics" },
  { ticker: "RELIANCE.BO", name: "Reliance Industries (BSE)", category: "SENSEX", exchange: "BSE", sector: "Energy & Conglomerate" },
  { ticker: "TCS.BO", name: "TCS (BSE)", category: "SENSEX", exchange: "BSE", sector: "IT Services" },
  { ticker: "HDFCBANK.BO", name: "HDFC Bank (BSE)", category: "SENSEX", exchange: "BSE", sector: "Banking" },
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
  const [activeTab, setActiveTab] = useState<CategoryTab>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [isSearchOpen, setIsSearchOpen] = useState<boolean>(false);
  const [searchResults, setSearchResults] = useState<SearchInstrumentResult[]>([]);
  const [isSearching, setIsSearching] = useState<boolean>(false);
  const [botAllocPct, setBotAllocPct] = useState<number>(0); // 0 = Kelly Auto-Size
  const [submittingKey, setSubmittingKey] = useState<string | null>(null);
  const [tradeBanner, setTradeBanner] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  const searchContainerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Global keyboard shortcut "/" or "Ctrl+K" to focus the Stock Search Bar
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      const isInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
      if ((e.key === "/" && !isInput) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k")) {
        e.preventDefault();
        searchInputRef.current?.focus();
        setIsSearchOpen(true);
      } else if (e.key === "Escape" && isSearchOpen) {
        setIsSearchOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isSearchOpen]);

  // Close search dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        searchContainerRef.current &&
        !searchContainerRef.current.contains(e.target as Node)
      ) {
        setIsSearchOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Build local instant search results merged with live telemetry
  const buildLocalResults = (q: string, cat: CategoryTab): SearchInstrumentResult[] => {
    const qLower = q.trim().toLowerCase();
    const qUpper = q.trim().toUpperCase();

    const matched = FALLBACK_SEARCH_CATALOG.filter((item) => {
      if (cat === "NIFTY_50" && item.category !== "NIFTY_50") return false;
      if (cat === "BANK_NIFTY" && item.category !== "BANK_NIFTY") return false;
      if (cat === "NIFTY_IT" && item.category !== "NIFTY_IT") return false;
      if (cat === "SENSEX" && item.category !== "SENSEX") return false;

      if (!qLower) return true;
      return (
        item.ticker.toLowerCase().includes(qLower) ||
        item.name.toLowerCase().includes(qLower) ||
        item.sector.toLowerCase().includes(qLower) ||
        item.exchange.toLowerCase().includes(qLower)
      );
    }).slice(0, 12);

    const results: SearchInstrumentResult[] = matched.map((item) => {
      const live = assets[item.ticker];
      return {
        ticker: item.ticker,
        name: item.name,
        category: item.category,
        exchange: item.exchange,
        sector: item.sector,
        in_watchlist: Boolean(live),
        is_armed: armedTickers.includes(item.ticker),
        has_open_position: Boolean(live?.has_open_position),
        current_price: live ? live.current_price : null,
        decimals: live ? live.decimals : 2,
        signal: live ? live.signal : null,
        primary_direction: live ? live.primary_direction : null,
        confidence_pct: live ? live.confidence_pct : null,
        target_price: live ? live.target_price : null,
        stop_price: live ? live.stop_price : null,
        kelly_weight_pct: live ? live.kelly_weight_pct : null,
        regime: live ? live.regime : null,
        exchange_open: live ? live.exchange_open : true,
        tradable_now: live ? live.tradable_now : true,
        is_custom: false,
      };
    });

    if (
      qUpper &&
      qUpper.length <= 18 &&
      !results.some((r) => r.ticker.toUpperCase() === qUpper)
    ) {
      const canonicalTicker = qUpper.includes(".") ? qUpper : `${qUpper}.NS`;
      results.push({
        ticker: canonicalTicker,
        name: `Load & Trade Indian Equity '${canonicalTicker}'`,
        category: canonicalTicker.endsWith(".BO") ? "SENSEX" : "NIFTY_50",
        exchange: canonicalTicker.endsWith(".BO") ? "BSE" : "NSE",
        sector: "Indian Capital Markets",
        in_watchlist: false,
        is_armed: false,
        has_open_position: false,
        current_price: null,
        decimals: 2,
        signal: null,
        primary_direction: null,
        confidence_pct: null,
        target_price: null,
        stop_price: null,
        kelly_weight_pct: null,
        regime: null,
        exchange_open: true,
        tradable_now: true,
        is_custom: true,
      });
    }

    return results;
  };

  // Query backend `/api/dashboard/search` when user opens search bar or types a query
  useEffect(() => {
    const localList = buildLocalResults(searchQuery, activeTab);
    setSearchResults(localList);

    if (!isSearchOpen) return;

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setIsSearching(true);
      try {
        const params = new URLSearchParams({
          q: searchQuery.trim(),
          category: activeTab,
          limit: "14",
        });
        const res = await fetch(`/api/dashboard/search?${params.toString()}`);
        if (res.ok && !cancelled) {
          const data = await res.json();
          if (Array.isArray(data.results) && data.results.length > 0) {
            setSearchResults(data.results);
          }
        }
      } catch {
        // Fallback local catalog already populated
      } finally {
        if (!cancelled) setIsSearching(false);
      }
    }, 120);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [searchQuery, activeTab, isSearchOpen]);

  // Execute a 1-click Bot-Managed Trade from search bar or asset card
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
      if (onPlaceBotTrade) {
        const resp = await onPlaceBotTrade(
          cleanTicker,
          direction,
          botAllocPct > 0 ? botAllocPct : undefined
        );
        const statusLabel =
          resp.status === "QUEUED"
            ? "Queued for Market Open (Bot-Managed)"
            : "Executed & Armed for Bot Management";
        setTradeBanner({
          type: "success",
          text: `[BOT-MANAGED] ${resp.direction} ${resp.ticker} (${statusLabel}) | Target: ${resp.target_price} | Stop: ${resp.stop_price} | Size: ${resp.allocation_weight_pct}%`,
        });
      } else {
        onAddCustomTicker(cleanTicker);
        setTradeBanner({
          type: "success",
          text: `Added & Armed ${cleanTicker} for Autonomous Bot Trading`,
        });
      }
      onSelectTicker(cleanTicker);
      setIsSearchOpen(false);
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

  // Select & Watch a stock from the search dropdown
  const handleSelectFromSearch = (item: SearchInstrumentResult) => {
    const tk = item.ticker.toUpperCase();
    if (!assets[tk]) {
      onAddCustomTicker(tk);
    } else {
      onSelectTicker(tk);
    }
    setIsSearchOpen(false);
  };

  const handleSearchFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchResults.length > 0) {
      handleSelectFromSearch(searchResults[0]);
    } else if (searchQuery.trim()) {
      onAddCustomTicker(searchQuery.trim().toUpperCase());
      setSearchQuery("");
      setIsSearchOpen(false);
    }
  };

  const assetList = Object.values(assets);

  // Filter monitored cards based on active tab and search query
  const filteredAssets = assetList.filter((a) => {
    const q = searchQuery.trim().toLowerCase();
    if (q) {
      const catEntry = FALLBACK_SEARCH_CATALOG.find(
        (c) => c.ticker.toUpperCase() === a.ticker.toUpperCase()
      );
      const matchTicker = a.ticker.toLowerCase().includes(q);
      const matchName = catEntry?.name.toLowerCase().includes(q) ?? false;
      const matchSector = catEntry?.sector.toLowerCase().includes(q) ?? false;
      if (!matchTicker && !matchName && !matchSector) {
        return false;
      }
    }

    if (activeTab === "ALL") return true;

    const tk = a.ticker.toUpperCase();
    if (activeTab === "NIFTY_50") {
      return tk.endsWith(".NS") && !tk.startsWith("^");
    }
    if (activeTab === "BANK_NIFTY") {
      return (
        tk.includes("BANK") ||
        ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS", "INDUSINDBK.NS"].includes(tk)
      );
    }
    if (activeTab === "NIFTY_IT") {
      return (
        ["TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS", "LTIM.NS"].includes(tk)
      );
    }
    if (activeTab === "SENSEX") {
      return tk.endsWith(".BO") || a.jurisdiction === "INDIAN_BSE";
    }
    return true;
  });

  return (
    <div className="glass-panel rounded-xl p-4 flex flex-col space-y-3">
      {/* 1. Prominent Stock Search & 1-Click Bot-Managed Trade Bar */}
      <div ref={searchContainerRef} className="relative z-30">
        <div className="flex flex-col lg:flex-row lg:items-center gap-2.5">
          {/* Search Input Box */}
          <form onSubmit={handleSearchFormSubmit} className="flex-1 relative">
            <Search className="w-4 h-4 text-sky-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              ref={searchInputRef}
              type="text"
              aria-label="Search stocks and place bot trade"
              placeholder="Search Indian NSE / BSE equities (e.g. Reliance, TCS, HDFC Bank, Infosys, SBI)... [Press /]"
              value={searchQuery}
              onFocus={() => setIsSearchOpen(true)}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setIsSearchOpen(true);
              }}
              className="w-full bg-slate-950/90 border border-sky-500/40 focus:border-sky-400 rounded-xl pl-10 pr-24 py-2.5 text-xs sm:text-sm font-mono text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-500/20 shadow-[0_0_15px_rgba(56,189,248,0.1)] transition"
            />
            <div className="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center space-x-1.5">
              {isSearching && (
                <Loader2 className="w-3.5 h-3.5 text-sky-400 animate-spin" />
              )}
              {searchQuery ? (
                <button
                  type="button"
                  onClick={() => {
                    setSearchQuery("");
                    searchInputRef.current?.focus();
                  }}
                  className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition"
                  title="Clear search"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              ) : (
                <span className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-mono bg-slate-900 text-slate-400 border border-slate-700 rounded">
                  / or Ctrl+K
                </span>
              )}
            </div>
          </form>

          {/* Quick Bot Sizing Selector & Instant Bot Auto-Trade on Current Selected Stock */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center space-x-1.5 bg-slate-950/80 border border-slate-800 rounded-xl px-2.5 py-1.5 text-xs font-mono">
              <Bot className="w-3.5 h-3.5 text-sky-400" />
              <span className="text-slate-400 text-[11px]">Bot Size:</span>
              <select
                aria-label="Bot trade allocation size"
                value={botAllocPct}
                onChange={(e) => setBotAllocPct(Number(e.target.value))}
                className="bg-transparent text-sky-300 font-semibold focus:outline-none cursor-pointer text-xs"
              >
                <option value={0} className="bg-slate-900 text-slate-200">
                  Kelly Auto
                </option>
                <option value={5} className="bg-slate-900 text-slate-200">
                  5% Cash
                </option>
                <option value={10} className="bg-slate-900 text-slate-200">
                  10% Cash
                </option>
                <option value={15} className="bg-slate-900 text-slate-200">
                  15% Cash
                </option>
                <option value={20} className="bg-slate-900 text-slate-200">
                  20% Cash
                </option>
              </select>
            </div>

            <button
              type="button"
              disabled={submittingKey !== null}
              onClick={(e) =>
                handleBotTradeClick(
                  e,
                  searchQuery.trim() ? searchQuery.trim().toUpperCase() : selectedTicker,
                  "AUTO"
                )
              }
              className="px-3.5 py-2 rounded-xl bg-gradient-to-r from-sky-500/30 to-emerald-500/30 hover:from-sky-500/40 hover:to-emerald-500/40 text-sky-200 border border-sky-400/50 text-xs font-mono font-bold flex items-center shadow-[0_0_12px_rgba(56,189,248,0.2)] transition cursor-pointer"
              title="Let the Bot analyze, pick direction, set Target & Stop-Loss barriers, and manage the trade automatically"
            >
              <Sparkles className="w-3.5 h-3.5 mr-1.5 text-emerald-300" />
              {submittingKey?.endsWith("-AUTO")
                ? "Bot Analyzing..."
                : `Bot Auto-Trade ${
                    searchQuery.trim()
                      ? searchQuery.trim().toUpperCase()
                      : selectedTicker
                  }`}
            </button>
          </div>
        </div>

        {/* Interactive Search Dropdown with 1-Click Bot Trade Buttons */}
        {isSearchOpen && (
          <div className="absolute left-0 right-0 mt-2 bg-[#0b1120]/98 backdrop-blur-xl border border-sky-500/40 rounded-xl shadow-2xl overflow-hidden max-h-96 flex flex-col">
            <div className="px-3.5 py-2 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between text-[11px] font-mono text-slate-400">
              <span>
                {searchQuery.trim()
                  ? `Matching Stocks & Instruments for "${searchQuery.trim()}"`
                  : "Popular Stocks & Multi-Asset Directory — Click to Analyze or Place a Bot-Handled Trade"}
              </span>
              <span className="text-sky-400">
                Bot Auto-Sets Stop-Loss, Take-Profit & Trailing MTM
              </span>
            </div>

            <div className="overflow-y-auto divide-y divide-slate-800/70">
              {searchResults.map((item) => {
                const isBusyAuto = submittingKey === `${item.ticker}-AUTO`;
                const isBusyLong = submittingKey === `${item.ticker}-LONG`;
                const isBusyShort = submittingKey === `${item.ticker}-SHORT`;

                return (
                  <div
                    key={item.ticker}
                    onClick={() => handleSelectFromSearch(item)}
                    className="px-3.5 py-2.5 hover:bg-slate-900/80 transition flex flex-col sm:flex-row sm:items-center justify-between gap-2 cursor-pointer"
                  >
                    {/* Left: Symbol, Name, Exchange, Sector & Live Price/Signal */}
                    <div className="flex items-start sm:items-center space-x-3">
                      <span
                        className={`w-2 h-2 rounded-full mt-1.5 sm:mt-0 shrink-0 ${
                          item.exchange_open
                            ? "bg-emerald-400 shadow-[0_0_6px_#34d399]"
                            : "bg-rose-500/80"
                        }`}
                        title={item.exchange_open ? "Exchange Open" : "Exchange Closed (Pre-Market Queue Ready)"}
                      />
                      <div>
                        <div className="flex flex-wrap items-center gap-2 font-mono">
                          <span className="font-bold text-sm text-slate-100">
                            {item.ticker}
                          </span>
                          <span className="text-xs text-slate-300 font-sans font-medium">
                            {item.name}
                          </span>
                          <span className="px-1.5 py-0.5 text-[10px] rounded bg-slate-800 text-sky-300 border border-slate-700">
                            {item.exchange}
                          </span>
                          <span className="text-[10px] text-slate-500 hidden md:inline">
                            {item.sector}
                          </span>
                          {item.is_armed && (
                            <span className="px-1.5 py-0.5 text-[10px] rounded bg-sky-500/15 text-sky-300 border border-sky-500/30">
                              ARMED
                            </span>
                          )}
                          {item.has_open_position && (
                            <span className="px-1.5 py-0.5 text-[10px] rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">
                              OPEN POS
                            </span>
                          )}
                        </div>

                        {item.current_price !== null && (
                          <div className="mt-0.5 flex flex-wrap items-center gap-3 text-[11px] font-mono text-slate-400">
                            <span>
                              Price:{" "}
                              <strong className="text-slate-200">
                                {item.current_price.toFixed(item.decimals)}
                              </strong>
                            </span>
                            {item.signal && (
                              <span>
                                AI Signal:{" "}
                                <strong
                                  className={
                                    item.primary_direction && item.primary_direction >= 0
                                      ? "text-emerald-400"
                                      : "text-rose-400"
                                  }
                                >
                                  {item.signal} ({item.confidence_pct}%)
                                </strong>
                              </span>
                            )}
                            {item.target_price && item.stop_price && (
                              <span className="text-slate-500">
                                Bot Barriers: TP {item.target_price.toFixed(item.decimals)} / SL{" "}
                                {item.stop_price.toFixed(item.decimals)}
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Right: 1-Click Bot-Handled Trade Action Buttons */}
                    <div className="flex items-center space-x-1.5 shrink-0">
                      <button
                        type="button"
                        disabled={submittingKey !== null}
                        onClick={(e) => handleBotTradeClick(e, item.ticker, "AUTO")}
                        className="px-2.5 py-1 rounded-lg bg-sky-500/20 hover:bg-sky-500/35 text-sky-300 border border-sky-500/40 text-[11px] font-mono font-semibold flex items-center transition"
                        title="Bot analyzes stock, selects AI direction & Kelly size, and manages TP/SL automatically"
                      >
                        <Bot className="w-3 h-3 mr-1 text-sky-400" />
                        {isBusyAuto ? "Trading..." : "Bot Auto-Trade"}
                      </button>

                      <button
                        type="button"
                        disabled={submittingKey !== null}
                        onClick={(e) => handleBotTradeClick(e, item.ticker, "LONG")}
                        className="px-2 py-1 rounded-lg bg-emerald-500/15 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 text-[11px] font-mono font-semibold flex items-center transition"
                        title="Open LONG position — Bot automatically computes & manages Stop-Loss and Take-Profit"
                      >
                        <ArrowUpRight className="w-3 h-3 mr-0.5" />
                        {isBusyLong ? "..." : "Bot LONG"}
                      </button>

                      <button
                        type="button"
                        disabled={submittingKey !== null}
                        onClick={(e) => handleBotTradeClick(e, item.ticker, "SHORT")}
                        className="px-2 py-1 rounded-lg bg-rose-500/15 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 text-[11px] font-mono font-semibold flex items-center transition"
                        title="Open SHORT position — Bot automatically computes & manages Stop-Loss and Take-Profit"
                      >
                        <ArrowDownRight className="w-3 h-3 mr-0.5" />
                        {isBusyShort ? "..." : "Bot SHORT"}
                      </button>

                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onAddCustomTicker(item.ticker.toUpperCase());
                          setIsSearchOpen(false);
                        }}
                        className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-[11px] font-mono flex items-center transition"
                        title="Add to watchlist & arm Bot without opening immediate trade"
                      >
                        <Plus className="w-3 h-3 mr-0.5" />
                        Watch
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Feedback Banner for Bot-Managed Trade Execution */}
      {tradeBanner && (
        <div
          className={`px-3 py-2 rounded-lg text-xs font-mono flex items-center justify-between ${
            tradeBanner.type === "success"
              ? "bg-emerald-500/15 border border-emerald-500/40 text-emerald-200"
              : "bg-rose-500/15 border border-rose-500/40 text-rose-200"
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

      {/* 2. Category Filter Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2.5">
        <div className="flex flex-wrap items-center gap-1.5 text-xs font-mono">
          {(
            [
              { id: "ALL", label: "All Monitored" },
              { id: "NIFTY_50", label: "Nifty 50" },
              { id: "BANK_NIFTY", label: "Bank Nifty" },
              { id: "NIFTY_IT", label: "Nifty IT" },
              { id: "SENSEX", label: "BSE Sensex" },
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

        <span className="text-[11px] font-mono text-slate-400">
          Monitored: <strong className="text-slate-200">{assetList.length}</strong> • Armed for Auto-Bot:{" "}
          <strong className="text-sky-400">{armedTickers.length}</strong>
        </span>
      </div>

      {/* 3. Monitored Asset Cards Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2.5 max-h-52 overflow-y-auto pr-1">
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

              <div className="mt-1.5 flex items-center justify-between text-[10px] text-slate-500 font-mono">
                <span className="truncate max-w-[75px]">
                  {asset.regime?.substring(0, 10) || "REGIME"}
                </span>
                <div className="flex items-center space-x-1">
                  {asset.has_open_position && (
                    <span className="text-amber-400 font-semibold px-1 rounded bg-amber-500/10">
                      POS
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={(e) => handleBotTradeClick(e, asset.ticker, "AUTO")}
                    className="px-1.5 py-0.5 rounded bg-sky-500/15 hover:bg-sky-500/30 text-sky-300 border border-sky-500/30 text-[9px] font-mono font-semibold transition"
                    title={`Let Bot place & manage trade on ${asset.ticker}`}
                  >
                    Bot Trade
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
