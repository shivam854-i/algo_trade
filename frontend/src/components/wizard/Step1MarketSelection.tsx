import React from "react";
import { Check, Shield, Globe } from "lucide-react";
import { MarketType } from "./types";
import { SessionStatusInfo } from "../../types";

interface Step1MarketSelectionProps {
  selectedMarket: MarketType;
  marketSessions?: Record<string, SessionStatusInfo>;
  errorMessage?: string;
  onSelectMarket: (market: MarketType) => void;
}

interface MarketDefinition {
  id: MarketType | "EU_EQUITIES";
  title: string;
  subtitle: string;
  currency: string;
  currencySymbol: string;
  tradingHours: string;
  sessionKey?: string;
  isSupported: boolean;
  disabledReason?: string;
}

const MARKETS: MarketDefinition[] = [
  {
    id: "INDIAN_NSE",
    title: "Indian Equities",
    subtitle: "NSE Nifty 50 Cash & Index Market",
    currency: "INR",
    currencySymbol: "₹",
    tradingHours: "09:15–15:30 IST",
    sessionKey: "NSE_INDIA",
    isSupported: true,
  },
  {
    id: "US_EQUITIES",
    title: "US Equities",
    subtitle: "NYSE & NASDAQ Tech & Liquid Equities",
    currency: "USD",
    currencySymbol: "$",
    tradingHours: "09:30–16:00 ET",
    sessionKey: "US_MARKETS",
    isSupported: false,
    disabledReason: "Disabled (NSE-Only Focus Active)",
  },
  {
    id: "CRYPTO",
    title: "Cryptocurrencies",
    subtitle: "BTC, ETH, SOL Institutional Feeds",
    currency: "USD",
    currencySymbol: "$",
    tradingHours: "24/7/365 Continuous",
    sessionKey: "CRYPTO_247",
    isSupported: false,
    disabledReason: "Disabled (NSE-Only Focus Active)",
  },
  {
    id: "COMMODITIES",
    title: "Commodities",
    subtitle: "Gold (GC=F), Silver (SI=F), Crude (CL=F)",
    currency: "USD",
    currencySymbol: "$",
    tradingHours: "23h/day Mon–Fri",
    sessionKey: "CME_GLOBEX",
    isSupported: false,
    disabledReason: "Disabled (NSE-Only Focus Active)",
  },
  {
    id: "FOREX",
    title: "Forex Majors",
    subtitle: "EUR/USD, GBP/USD, USD/JPY ECN",
    currency: "USD",
    currencySymbol: "$",
    tradingHours: "24/5 (Sun 17:00–Fri 17:00 ET)",
    isSupported: false,
    disabledReason: "Disabled (NSE-Only Focus Active)",
  },
  {
    id: "EU_EQUITIES",
    title: "European Equities",
    subtitle: "LSE / Euronext Blue-Chips",
    currency: "EUR",
    currencySymbol: "€",
    tradingHours: "08:00–16:30 GMT",
    isSupported: false,
    disabledReason: "Disabled (Provider Integration Coming Soon)",
  },
];

export const Step1MarketSelection: React.FC<Step1MarketSelectionProps> = ({
  selectedMarket,
  marketSessions = {},
  errorMessage,
  onSelectMarket,
}) => {
  return (
    <div className="flex flex-col space-y-4">
      <div>
        <h3 className="text-base font-bold text-slate-100 flex items-center">
          <Globe className="w-4 h-4 mr-2 text-sky-400" />
          Select Market Jurisdiction
        </h3>
        <p className="text-xs text-slate-400 mt-1">
          Choose the market jurisdiction for your simulated trading session. Currency and market hours will adapt automatically.
        </p>
      </div>

      {errorMessage && (
        <div className="px-3 py-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono">
          {errorMessage}
        </div>
      )}

      {/* Market Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {MARKETS.map((m) => {
          const isSelected = selectedMarket === m.id;
          const sessionInfo = m.sessionKey ? marketSessions[m.sessionKey] : undefined;
          const isOpen = sessionInfo?.is_open ?? (m.id === "CRYPTO");

          if (!m.isSupported) {
            return (
              <div
                key={m.id}
                className="glass-panel rounded-xl p-3.5 border border-slate-800/40 opacity-40 cursor-not-allowed select-none flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-300 text-sm">{m.title}</span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-900 text-slate-500 border border-slate-800">
                      Unsupported
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 mt-1">{m.subtitle}</p>
                </div>
                <div className="mt-3 pt-2 border-t border-slate-800/40 flex items-center justify-between text-[10px] font-mono text-slate-600">
                  <span>{m.disabledReason}</span>
                  <span>{`${m.currency} (${m.currencySymbol})`}</span>
                </div>
              </div>
            );
          }

          return (
            <div
              key={m.id}
              onClick={() => onSelectMarket(m.id as MarketType)}
              className={`glass-panel rounded-xl p-3.5 border cursor-pointer transition flex flex-col justify-between ${
                isSelected
                  ? "border-sky-500/80 bg-sky-500/10 shadow-md shadow-sky-500/10"
                  : "border-slate-800/80 hover:border-slate-700 bg-slate-900/30"
              }`}
            >
              <div>
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-100 text-sm">{m.title}</span>
                  {isSelected ? (
                    <div className="w-5 h-5 rounded-full bg-sky-500 text-slate-950 flex items-center justify-center">
                      <Check className="w-3.5 h-3.5 stroke-[3]" />
                    </div>
                  ) : (
                    <div className="w-5 h-5 rounded-full border border-slate-700" />
                  )}
                </div>
                <p className="text-[11px] text-slate-400 mt-1">{m.subtitle}</p>
              </div>

              <div className="mt-4 pt-2.5 border-t border-slate-800/60 flex items-center justify-between text-[11px] font-mono">
                <span className="text-slate-400">
                  Currency: <strong className="text-slate-200">{`${m.currency} (${m.currencySymbol})`}</strong>
                </span>
                <span
                  className={`flex items-center ${
                    isOpen ? "text-emerald-400" : "text-slate-500"
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
                      isOpen ? "bg-emerald-400 animate-pulse" : "bg-slate-600"
                    }`}
                  />
                  {isOpen ? "FEED OPEN" : "CLOSED"}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="p-3 rounded-lg bg-slate-900/60 border border-slate-800 text-[11px] font-mono text-slate-400 flex items-center space-x-2">
        <Shield className="w-4 h-4 text-emerald-400 shrink-0" />
        <span>
          Selected market: <strong className="text-slate-200">{selectedMarket}</strong>. All executions are strictly virtual paper-trading isolated. Real market data is used.
        </span>
      </div>
    </div>
  );
};
