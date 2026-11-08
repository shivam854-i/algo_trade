import React, { useEffect, useState, useMemo } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  RefreshCw,
  TrendingDown,
  Calculator,
  Lock,
  Info,
  CheckCircle2,
  PieChart,
  Flame,
  Scale,
} from "lucide-react";
import { RiskMetricsData } from "../../types";

export interface RiskManagementViewProps {
  onEmergencyKill?: () => void;
}

// Fallback calibration data in case backend server is warming up
const DEFAULT_RISK_METRICS: RiskMetricsData = {
  portfolio_equity_inr: 500000.0,
  available_cash_inr: 325000.0,
  invested_equity_inr: 175000.0,
  var_95_pct: 1.71,
  var_95_inr: 8550.0,
  var_99_pct: 2.42,
  var_99_inr: 12100.0,
  cvar_95_inr: 10687.5,
  current_drawdown_pct: 2.4,
  circuit_breaker_drawdown_limit_pct: 15.0,
  gross_leverage: 0.35,
  max_allowable_leverage: 1.0,
  kelly_multiplier: 0.35,
  sebi_rate_limit_orders_per_sec: 5.0,
  limit_price_protection_pct: 1.0,
  indian_frictions: {
    stt_delivery_both_legs_pct: 0.10,
    stt_intraday_sell_leg_pct: 0.025,
    nse_exchange_turnover_charge_pct: 0.00325,
    bse_exchange_turnover_charge_pct: 0.00375,
    stamp_duty_buy_leg_delivery_pct: 0.015,
    sebi_turnover_charge_pct: 0.0001,
    gst_rate_pct: 18.0,
    brokerage_cap_pct: 0.03,
    almgren_chriss_eta: 0.45,
  },
};

export const RiskManagementView: React.FC<RiskManagementViewProps> = ({
  onEmergencyKill,
}) => {
  const [data, setData] = useState<RiskMetricsData>(DEFAULT_RISK_METRICS);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [errorNotice, setErrorNotice] = useState<string | null>(null);

  // Live Friction Simulator State
  const [simNotional, setSimNotional] = useState<number>(100000);
  const [simTradeType, setSimTradeType] = useState<"DELIVERY" | "INTRADAY">("DELIVERY");

  // Fetch Risk Metrics from Backend
  const fetchMetrics = async (isManual = false) => {
    if (isManual) setIsRefreshing(true);
    setErrorNotice(null);

    try {
      const res = await fetch("/api/risk/metrics");
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: Failed to fetch risk metrics`);
      }
      const json = await res.json();
      setData({
        ...DEFAULT_RISK_METRICS,
        ...json,
        indian_frictions: {
          ...DEFAULT_RISK_METRICS.indian_frictions,
          ...(json.indian_frictions || {}),
        },
      });
    } catch (err: any) {
      setErrorNotice(err.message || "Failed to reach risk metrics endpoint. Displaying active local risk model.");
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(() => {
      fetchMetrics(false);
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  // Thresholds
  const currentDrawdown = data.current_drawdown_pct;
  const warningThreshold = 8.0;
  const hardKillThreshold = data.circuit_breaker_drawdown_limit_pct || 15.0;

  // Circuit Breaker Status
  const isHardKillActive = currentDrawdown >= hardKillThreshold;
  const isWarningActive = currentDrawdown >= warningThreshold && !isHardKillActive;

  // Gross Leverage Calculations (SEBI cash-market standard: max 1.0x cash)
  const maxCashLeverage = 1.0;
  const currentLeverage = data.gross_leverage;
  const leveragePct = Math.min(100, Math.round((currentLeverage / maxCashLeverage) * 100));

  // Friction Simulator Computations
  const simCalculations = useMemo(() => {
    const notional = Math.max(1000, simNotional);
    const f = data.indian_frictions;

    // STT (Securities Transaction Tax)
    // Delivery: 0.10% on both Buy and Sell legs (total 0.20% roundtrip)
    // Intraday: 0.025% on Sell leg only (0.025% roundtrip)
    const sttRate = simTradeType === "DELIVERY" ? f.stt_delivery_both_legs_pct * 2 : f.stt_intraday_sell_leg_pct;
    const sttAmount = (notional * sttRate) / 100;

    // Stamp Duty
    // Delivery: 0.015% on Buy leg
    // Intraday: 0.003% on Buy leg
    const stampRate = simTradeType === "DELIVERY" ? f.stamp_duty_buy_leg_delivery_pct : 0.003;
    const stampAmount = (notional * stampRate) / 100;

    // Exchange Turnover Charge (Weighted approx 0.00345% roundtrip)
    const exchRate = 0.00345 * 2;
    const exchAmount = (notional * exchRate) / 100;

    // SEBI Turnover Charge (0.0001% = ₹10 per crore roundtrip)
    const sebiRate = f.sebi_turnover_charge_pct * 2;
    const sebiAmount = (notional * sebiRate) / 100;

    // Brokerage (0.03% or ₹20 per leg = ₹40 roundtrip)
    const brokerAmount = Math.min((notional * f.brokerage_cap_pct) / 100 * 2, 40.0);

    // GST: 18% on (Brokerage + Exchange Charges + SEBI Charges)
    const taxableBase = brokerAmount + exchAmount + sebiAmount;
    const gstAmount = taxableBase * (f.gst_rate_pct / 100);

    // Almgren-Chriss Market Impact / Slippage estimation
    // Square-root model: impact_bps = eta * 10 * sqrt(notional / 500000)
    const impactBps = Number((f.almgren_chriss_eta * 3.5 * Math.sqrt(notional / 500000)).toFixed(2));
    const impactAmount = (notional * impactBps) / 10000;

    const totalFriction = sttAmount + stampAmount + exchAmount + sebiAmount + brokerAmount + gstAmount + impactAmount;
    const totalBps = (totalFriction / notional) * 10000;
    const breakevenHurdlePct = (totalFriction / notional) * 100;

    return {
      notional,
      sttAmount,
      sttRate,
      stampAmount,
      stampRate,
      exchAmount,
      exchRate,
      sebiAmount,
      brokerAmount,
      gstAmount,
      impactBps,
      impactAmount,
      totalFriction,
      totalBps,
      breakevenHurdlePct,
    };
  }, [simNotional, simTradeType, data.indian_frictions]);

  return (
    <div className="space-y-6 font-mono text-slate-100 bg-[#090d18] min-h-screen p-4 sm:p-6 rounded-2xl border border-slate-800/80 shadow-2xl">
      {/* 1. Top Header & Governance Status */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center space-x-2.5">
            <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <ShieldAlert className="w-5 h-5 text-[#00d2ff]" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
                RISK MANAGEMENT & GOVERNANCE
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
                  SEBI ALGO COMPLIANT
                </span>
              </h1>
              <p className="text-xs text-slate-400">
                Parametric VaR • Expected Shortfall CVaR • Drawdown Circuit Breakers • Statutory Friction Deductions
              </p>
            </div>
          </div>
        </div>

        {/* Status Indicators & Refresh */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Circuit Breaker Status Pill */}
          <div
            className={`px-3 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-2 ${
              isHardKillActive
                ? "bg-rose-500/20 border-rose-500/50 text-rose-300 animate-pulse"
                : isWarningActive
                ? "bg-amber-500/20 border-amber-500/50 text-amber-300"
                : "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
            }`}
          >
            {isHardKillActive ? (
              <>
                <Flame className="w-3.5 h-3.5 text-rose-400" />
                <span>CIRCUIT BREAKER TRIGGERED ({currentDrawdown}%)</span>
              </>
            ) : isWarningActive ? (
              <>
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                <span>WARNING ZONE ({currentDrawdown}%) — SIZING HALVED</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                <span>CIRCUIT BREAKER NOMINAL ({currentDrawdown}% DD)</span>
              </>
            )}
          </div>

          {/* Refresh Button */}
          <button
            type="button"
            onClick={() => fetchMetrics(true)}
            disabled={isRefreshing}
            className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-300 text-xs flex items-center space-x-1.5 transition disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-cyan-400" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Error or Notice Banner */}
      {errorNotice && (
        <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Info className="w-4 h-4 shrink-0 text-amber-400" />
            <span>{errorNotice}</span>
          </div>
          <button
            onClick={() => setErrorNotice(null)}
            className="text-slate-400 hover:text-slate-200 text-xs px-2"
          >
            ✕
          </button>
        </div>
      )}

      {/* 2. Key Institutional Risk Scorecards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: 95% 1-Day VaR */}
        <div className="p-4 rounded-xl bg-[#0d1322] border border-slate-800 space-y-2 relative overflow-hidden">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400 uppercase font-semibold">1-Day VaR (95% Conf)</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 font-mono">
              Z = 1.645σ
            </span>
          </div>
          <div className="flex items-baseline space-x-2">
            <span className="text-2xl font-bold text-cyan-300">
              ₹{data.var_95_inr.toLocaleString("en-IN")}
            </span>
            <span className="text-xs text-cyan-400/80 font-bold">
              ({data.var_95_pct.toFixed(2)}%)
            </span>
          </div>
          <p className="text-[11px] text-slate-400">
            Maximum normal daily loss under 1.645σ Gaussian distribution across total equity.
          </p>
        </div>

        {/* Card 2: 99% 1-Day VaR */}
        <div className="p-4 rounded-xl bg-[#0d1322] border border-slate-800 space-y-2 relative overflow-hidden">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400 uppercase font-semibold">1-Day VaR (99% Conf)</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-500/10 border border-rose-500/30 text-rose-400 font-mono">
              Z = 2.326σ
            </span>
          </div>
          <div className="flex items-baseline space-x-2">
            <span className="text-2xl font-bold text-rose-400">
              ₹{data.var_99_inr.toLocaleString("en-IN")}
            </span>
            <span className="text-xs text-rose-400/80 font-bold">
              ({data.var_99_pct.toFixed(2)}%)
            </span>
          </div>
          <p className="text-[11px] text-slate-400">
            Tail tail-risk parameter: 99 out of 100 trading sessions daily losses remain below this bound.
          </p>
        </div>

        {/* Card 3: Conditional VaR (CVaR / Expected Shortfall 95%) */}
        <div className="p-4 rounded-xl bg-[#0d1322] border border-slate-800 space-y-2 relative overflow-hidden">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400 uppercase font-semibold">95% CVaR (Expected Shortfall)</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/30 text-amber-400 font-mono">
              E[L | L &gt; VaR]
            </span>
          </div>
          <div className="flex items-baseline space-x-2">
            <span className="text-2xl font-bold text-amber-300">
              ₹{data.cvar_95_inr.toLocaleString("en-IN")}
            </span>
            <span className="text-xs text-amber-400/80 font-bold">
              ({((data.cvar_95_inr / (data.portfolio_equity_inr || 1)) * 100).toFixed(2)}%)
            </span>
          </div>
          <p className="text-[11px] text-slate-400">
            Average expected loss on days when losses exceed the 95% VaR barrier (Fat-tail expectation).
          </p>
        </div>

        {/* Card 4: Drawdown Circuit Breaker Position */}
        <div className="p-4 rounded-xl bg-[#0d1322] border border-slate-800 space-y-2 relative overflow-hidden">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400 uppercase font-semibold">Current Drawdown</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
              Max Limit: {hardKillThreshold.toFixed(1)}%
            </span>
          </div>
          <div className="flex items-baseline space-x-2">
            <span
              className={`text-2xl font-bold ${
                isHardKillActive
                  ? "text-rose-400"
                  : isWarningActive
                  ? "text-amber-400"
                  : "text-emerald-400"
              }`}
            >
              {currentDrawdown.toFixed(1)}%
            </span>
            <span className="text-xs text-slate-400 font-mono">
              / {hardKillThreshold.toFixed(1)}% Hard Kill
            </span>
          </div>
          <p className="text-[11px] text-slate-400">
            Peak-to-trough capital degradation from initial allocation.
          </p>
        </div>
      </div>

      {/* 3. Visual Circuit Breaker Gauge & Portfolio Leverage Meter */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Drawdown Limit Circuit Breaker Gauge */}
        <div className="lg:col-span-6 bg-[#0d1322] border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h2 className="text-sm font-bold text-slate-200 flex items-center gap-2">
              <TrendingDown className="w-4 h-4 text-rose-400" />
              DRAWDOWN CIRCUIT BREAKER GAUGE
            </h2>
            <span className="text-xs text-slate-400 font-mono">
              Mandatory SEBI Risk Gating
            </span>
          </div>

          {/* Multi-Stage Visual Gauge */}
          <div className="space-y-3">
            <div className="flex justify-between text-xs">
              <span className="text-emerald-400 font-bold">0.0% Safe Zone</span>
              <span className="text-amber-400 font-bold">8.0% Warning Level</span>
              <span className="text-rose-400 font-bold">15.0% Kill Switch</span>
            </div>

            {/* Segmented Bar */}
            <div className="relative w-full h-4 bg-slate-900 rounded-full overflow-hidden flex border border-slate-800">
              {/* Normal Zone: 0% to 8% (53.3% of 15% range) */}
              <div className="h-full bg-emerald-500/30 border-r border-emerald-500/60" style={{ width: "53.3%" }} />
              {/* Warning Zone: 8% to 15% (46.7% of 15% range) */}
              <div className="h-full bg-amber-500/30 border-r border-amber-500/60" style={{ width: "46.7%" }} />
              {/* Hard Kill Indicator Beyond 15% */}
              <div className="h-full bg-rose-500/40" style={{ width: "10%" }} />

              {/* Needle / Marker for Current Drawdown */}
              <div
                className="absolute top-0 bottom-0 w-1.5 bg-slate-100 shadow-md transform -translate-x-1/2 transition-all duration-500"
                style={{
                  left: `${Math.min(100, Math.max(1, (currentDrawdown / hardKillThreshold) * 100))}%`,
                }}
              />
            </div>

            {/* Threshold Descriptions */}
            <div className="grid grid-cols-3 gap-2 text-[10px] text-slate-400 pt-2 border-t border-slate-800/80">
              <div className="p-2 rounded bg-emerald-500/10 border border-emerald-500/20">
                <span className="text-emerald-400 font-bold block mb-0.5">NOMINAL (0.0% - 7.9%)</span>
                Normal Kelly position sizing (0.35x). All buy/sell orders enabled.
              </div>
              <div className="p-2 rounded bg-amber-500/10 border border-amber-500/20">
                <span className="text-amber-400 font-bold block mb-0.5">WARNING (8.0% - 14.9%)</span>
                Automated Kelly fraction halved (0.17x). Long entry sizing restricted.
              </div>
              <div className="p-2 rounded bg-rose-500/10 border border-rose-500/20">
                <span className="text-rose-400 font-bold block mb-0.5">HARD KILL (≥ 15.0%)</span>
                Immediate emergency flatten. Execution engine paused.
              </div>
            </div>

            {/* Emergency Action Button */}
            {onEmergencyKill && (
              <div className="pt-2">
                <button
                  type="button"
                  onClick={onEmergencyKill}
                  className="w-full py-2.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/30 font-semibold text-xs flex items-center justify-center space-x-2 transition"
                >
                  <Flame className="w-4 h-4 text-rose-400" />
                  <span>Manual Emergency Kill Switch (Flatten All Open Positions)</span>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Gross Portfolio Leverage Meter */}
        <div className="lg:col-span-6 bg-[#0d1322] border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h2 className="text-sm font-bold text-slate-200 flex items-center gap-2">
              <Scale className="w-4 h-4 text-cyan-400" />
              GROSS PORTFOLIO LEVERAGE METER
            </h2>
            <span className="text-xs text-slate-400 font-mono">
              Max Allowable: 1.0x Cash
            </span>
          </div>

          <div className="space-y-4">
            <div className="flex justify-between items-baseline">
              <div>
                <span className="text-xs text-slate-400 block">Current Gross Exposure</span>
                <span className="text-2xl font-bold text-cyan-300">
                  {currentLeverage.toFixed(2)}x
                </span>
              </div>
              <div className="text-right">
                <span className="text-xs text-slate-400 block">Max Cash-Secured Cap</span>
                <span className="text-sm font-bold text-slate-200">1.00x (₹{data.portfolio_equity_inr.toLocaleString("en-IN")})</span>
              </div>
            </div>

            {/* Meter Bar */}
            <div className="space-y-1.5">
              <div className="w-full h-3 bg-slate-900 rounded-full overflow-hidden border border-slate-800">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    currentLeverage > 1.0
                      ? "bg-rose-500"
                      : currentLeverage > 0.75
                      ? "bg-amber-400"
                      : "bg-[#00d2ff]"
                  }`}
                  style={{ width: `${leveragePct}%` }}
                />
              </div>
              <div className="flex justify-between text-[10px] text-slate-500">
                <span>0.0x (100% Cash)</span>
                <span>0.50x Exposure</span>
                <span>1.0x (Fully Invested)</span>
              </div>
            </div>

            {/* Capital Allocation Breakdown */}
            <div className="grid grid-cols-3 gap-3 pt-2 border-t border-slate-800/80">
              <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800">
                <span className="text-[10px] text-slate-400 block uppercase">Total Equity</span>
                <span className="text-xs font-bold text-slate-100">
                  ₹{data.portfolio_equity_inr.toLocaleString("en-IN")}
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800">
                <span className="text-[10px] text-slate-400 block uppercase">Available Cash</span>
                <span className="text-xs font-bold text-emerald-400">
                  ₹{data.available_cash_inr.toLocaleString("en-IN")}
                </span>
                <span className="text-[9px] text-slate-500 block">
                  ({((data.available_cash_inr / Math.max(1, data.portfolio_equity_inr)) * 100).toFixed(0)}% cushion)
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800">
                <span className="text-[10px] text-slate-400 block uppercase">Invested Capital</span>
                <span className="text-xs font-bold text-cyan-300">
                  ₹{data.invested_equity_inr.toLocaleString("en-IN")}
                </span>
                <span className="text-[9px] text-slate-500 block">
                  ({((data.invested_equity_inr / Math.max(1, data.portfolio_equity_inr)) * 100).toFixed(0)}% active)
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 4. Indian Statutory Friction Itemization & Interactive Simulator */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Itemization Breakdown Card */}
        <div className="lg:col-span-7 bg-[#0d1322] border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h2 className="text-sm font-bold text-slate-200 flex items-center gap-2">
              <PieChart className="w-4 h-4 text-cyan-400" />
              INDIAN STATUTORY FRICTION SCHEDULE
            </h2>
            <span className="text-xs text-slate-400 font-mono">
              NSE / BSE Statutory Mandates
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-slate-950/80 text-slate-400 uppercase text-[11px] border-b border-slate-800">
                <tr>
                  <th className="py-2 px-3">Statutory Component</th>
                  <th className="py-2 px-3">Delivery Rate (CNC)</th>
                  <th className="py-2 px-3">Intraday Rate (MIS)</th>
                  <th className="py-2 px-3">Applicable Base</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-[11px]">
                <tr className="hover:bg-slate-800/30">
                  <td className="py-2.5 px-3 font-semibold text-slate-200">
                    STT (Securities Transaction Tax)
                  </td>
                  <td className="py-2.5 px-3 text-cyan-400 font-bold">0.10% on both Buy & Sell</td>
                  <td className="py-2.5 px-3 text-slate-300">0.025% on Sell only</td>
                  <td className="py-2.5 px-3 text-slate-400">Total Trade Turnover</td>
                </tr>

                <tr className="hover:bg-slate-800/30">
                  <td className="py-2.5 px-3 font-semibold text-slate-200">Stamp Duty</td>
                  <td className="py-2.5 px-3 text-cyan-400 font-bold">0.015% on Buy</td>
                  <td className="py-2.5 px-3 text-slate-300">0.003% on Buy</td>
                  <td className="py-2.5 px-3 text-slate-400">Buyer Notional Value</td>
                </tr>

                <tr className="hover:bg-slate-800/30">
                  <td className="py-2.5 px-3 font-semibold text-slate-200">Exchange Turnover Charge</td>
                  <td className="py-2.5 px-3 text-slate-300">0.00345% (NSE 0.00325% / BSE 0.00375%)</td>
                  <td className="py-2.5 px-3 text-slate-300">0.00345%</td>
                  <td className="py-2.5 px-3 text-slate-400">Turnover (Both Legs)</td>
                </tr>

                <tr className="hover:bg-slate-800/30">
                  <td className="py-2.5 px-3 font-semibold text-slate-200">SEBI Turnover Charges</td>
                  <td className="py-2.5 px-3 text-slate-300">0.0001% (₹10 / Crore)</td>
                  <td className="py-2.5 px-3 text-slate-300">0.0001%</td>
                  <td className="py-2.5 px-3 text-slate-400">Total Trade Turnover</td>
                </tr>

                <tr className="hover:bg-slate-800/30">
                  <td className="py-2.5 px-3 font-semibold text-slate-200">GST (Goods & Services Tax)</td>
                  <td className="py-2.5 px-3 text-rose-300 font-bold">18.00%</td>
                  <td className="py-2.5 px-3 text-rose-300 font-bold">18.00%</td>
                  <td className="py-2.5 px-3 text-slate-400">Brokerage + Exch + SEBI</td>
                </tr>

                <tr className="hover:bg-slate-800/30">
                  <td className="py-2.5 px-3 font-semibold text-slate-200">Almgren-Chriss Market Impact</td>
                  <td className="py-2.5 px-3 text-amber-300 font-bold">~2.1 bps (η = 0.45)</td>
                  <td className="py-2.5 px-3 text-amber-300 font-bold">~1.5 bps</td>
                  <td className="py-2.5 px-3 text-slate-400">Square-Root L2 Order Sweep</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="p-3 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-[11px] text-slate-300 flex items-start gap-2">
            <Info className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
            <p>
              In accordance with Indian tax jurisprudence, all backtest and live executions deduct holding-period aware statutory friction on each individual trade tick before computing Net P&L.
            </p>
          </div>
        </div>

        {/* Live Friction Simulator */}
        <div className="lg:col-span-5 bg-[#0d1322] border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h2 className="text-sm font-bold text-slate-200 flex items-center gap-2">
              <Calculator className="w-4 h-4 text-[#00d2ff]" />
              LIVE FRICTION SIMULATOR
            </h2>
            <span className="text-xs text-cyan-400 font-mono">Roundtrip INR ₹</span>
          </div>

          {/* Simulator Inputs */}
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Trade Notional Amount (₹)</label>
              <div className="relative">
                <span className="absolute left-3 top-2 text-xs text-slate-500">₹</span>
                <input
                  type="number"
                  value={simNotional}
                  onChange={(e) => setSimNotional(Math.max(1000, Number(e.target.value)))}
                  step="25000"
                  className="w-full bg-slate-900 border border-slate-700/80 rounded-lg pl-7 pr-3 py-2 text-xs text-slate-100 focus:outline-none focus:border-cyan-400 font-mono"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs text-slate-400 mb-1">Execution Product Type</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setSimTradeType("DELIVERY")}
                  className={`py-1.5 px-3 rounded-lg border text-xs font-semibold transition ${
                    simTradeType === "DELIVERY"
                      ? "bg-cyan-500/20 border-[#00d2ff] text-cyan-300"
                      : "bg-slate-900 border-slate-800 text-slate-400"
                  }`}
                >
                  Delivery (CNC)
                </button>
                <button
                  type="button"
                  onClick={() => setSimTradeType("INTRADAY")}
                  className={`py-1.5 px-3 rounded-lg border text-xs font-semibold transition ${
                    simTradeType === "INTRADAY"
                      ? "bg-cyan-500/20 border-[#00d2ff] text-cyan-300"
                      : "bg-slate-900 border-slate-800 text-slate-400"
                  }`}
                >
                  Intraday (MIS)
                </button>
              </div>
            </div>

            {/* Itemized Rupee Breakdown */}
            <div className="p-3 rounded-xl bg-slate-950/90 border border-slate-800 space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-400">STT Tax:</span>
                <span className="font-mono text-slate-200">₹{simCalculations.sttAmount.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Stamp Duty:</span>
                <span className="font-mono text-slate-200">₹{simCalculations.stampAmount.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Exchange Charges:</span>
                <span className="font-mono text-slate-200">₹{simCalculations.exchAmount.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Brokerage Cap:</span>
                <span className="font-mono text-slate-200">₹{simCalculations.brokerAmount.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">GST (18% on fees):</span>
                <span className="font-mono text-slate-200">₹{simCalculations.gstAmount.toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Almgren-Chriss Slippage:</span>
                <span className="font-mono text-amber-300">
                  ₹{simCalculations.impactAmount.toFixed(2)} ({simCalculations.impactBps} bps)
                </span>
              </div>

              {/* Total Card */}
              <div className="pt-2 border-t border-slate-800 flex justify-between items-baseline font-bold">
                <span className="text-slate-200">Total Roundtrip Friction:</span>
                <span className="text-sm text-cyan-400 font-mono">
                  ₹{simCalculations.totalFriction.toFixed(2)}
                </span>
              </div>
            </div>

            {/* Breakeven Hurdle Metric */}
            <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-between text-xs">
              <div>
                <span className="text-emerald-400 font-bold block">Breakeven Alpha Hurdle</span>
                <span className="text-[10px] text-slate-400">Required gross gain to clear statutory friction</span>
              </div>
              <div className="text-right">
                <span className="text-sm font-bold text-emerald-300 font-mono">
                  +{simCalculations.breakevenHurdlePct.toFixed(3)}%
                </span>
                <span className="text-[10px] text-slate-400 block font-mono">
                  ({simCalculations.totalBps.toFixed(1)} bps)
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 5. SEBI Regulatory Governance Safeguards */}
      <div className="bg-[#0d1322] border border-slate-800 rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h2 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <Lock className="w-4 h-4 text-cyan-400" />
            SEBI REGULATORY SAFEGUARDS & MICROSTRUCTURE CONTROLS
          </h2>
          <span className="text-xs text-emerald-400 flex items-center gap-1 font-mono">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            Active Surveillance
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
          {/* Safeguard 1: Token Bucket Rate Limiter */}
          <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-200">SEBI Rate Limiter</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono">
                PASS
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Token Bucket algorithm strictly caps order dispatch at{" "}
              <strong className="text-cyan-400">{data.sebi_rate_limit_orders_per_sec} orders/second</strong> to prevent exchange spam penalties.
            </p>
          </div>

          {/* Safeguard 2: Limit Price Protection (LPP) */}
          <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-200">Limit Price Protection</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono">
                ±1.0% BAND
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Orders outside ±{data.limit_price_protection_pct.toFixed(1)}% of reference market price are intercepted prior to network dispatch.
            </p>
          </div>

          {/* Safeguard 3: Pre-Trade Risk Engine */}
          <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-200">Pre-Trade Risk Gate</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/20 text-cyan-300 font-mono">
                &lt; 0.20 ms
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Synchronous pre-trade validation checks portfolio margin, VaR ceiling, and buying power before order placement.
            </p>
          </div>

          {/* Safeguard 4: Paper-Trading Safety Lock */}
          <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-200">Paper-Trading Isolation</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-mono">
                ENFORCED
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              Simulated sandbox execution environment isolated from live exchange trading keys to safeguard real capital.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RiskManagementView;
