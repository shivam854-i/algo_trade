import React, { useState } from "react";
import { Header } from "./components/Header";
import { MarketSessionRibbon } from "./components/MarketSessionRibbon";
import { KpiRibbon } from "./components/KpiRibbon";
import { AssetSelector } from "./components/AssetSelector";
import { ChartContainer } from "./components/ChartContainer";
import { PositionsTable } from "./components/PositionsTable";
import { OrderControls } from "./components/OrderControls";
import { ActivityLog } from "./components/ActivityLog";
import { TradingSessionWizardModal } from "./components/wizard/TradingSessionWizardModal";
import { SessionTelemetryBar } from "./components/session/SessionTelemetryBar";
import { SessionGatingBanner } from "./components/session/SessionGatingBanner";
import { useDashboardStream } from "./hooks/useDashboardStream";
import { ShieldCheck, HardDrive, Cpu, AlertCircle } from "lucide-react";

export const App: React.FC = () => {
  const {
    state,
    isLoading,
    error,
    isTabVisible,
    selectedTicker,
    setSelectedTicker,
    chartData,
    boundedActivityLog,
    pendingOrders,
    activeSession,
    hasActiveSession,
    isSessionRunning,
    sessionCurrency,
    startSession,
    pauseSession,
    resumeSession,
    stopSession,
    refreshState,
    stepTick,
    toggleBot,
    toggleMarketHours,
    closePosition,
    flattenAll,
    resetAccount,
    armTickers,
    placeOrder,
    placeBotTrade,
    cancelPendingOrder,
  } = useDashboardStream({ pollIntervalMs: 2500, chartCapacity: 500, logCapacity: 100 });

  const [isWizardOpen, setIsWizardOpen] = useState<boolean>(false);

  const selectedAsset = state?.assets?.[selectedTicker];
  const armedTickers = state?.bot_status?.armed_tickers ?? [];

  // Toggle arming for a single asset
  const handleToggleArm = (ticker: string) => {
    let nextArmed: string[];
    if (armedTickers.includes(ticker)) {
      nextArmed = armedTickers.filter((t) => t !== ticker);
    } else {
      nextArmed = [...armedTickers, ticker];
    }
    armTickers(nextArmed);
  };

  // Add custom ticker symbol
  const handleAddCustomTicker = (ticker: string) => {
    const nextArmed = Array.from(new Set([...armedTickers, ticker]));
    armTickers(nextArmed, [ticker]);
    setSelectedTicker(ticker);
  };

  return (
    <div className="min-h-screen bg-[#060911] text-slate-100 flex flex-col font-sans selection:bg-sky-500/30 selection:text-sky-200">
      {/* 1. Institutional Cockpit Top Navbar */}
      <Header
        botStatus={state?.bot_status}
        dataFeedStatus={state?.data_feed_status}
        isTabVisible={isTabVisible}
        isLoading={isLoading}
        onRefresh={refreshState}
      />

      {/* Main Body Container */}
      <main className="flex-1 p-3 sm:p-4 md:p-6 space-y-4 max-w-[1920px] mx-auto w-full">
        {/* Error Banner if API connection fails */}
        {error && (
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
              <span>Backend Connection Notice: {error}. Make sure server.py is running on port 8501.</span>
            </div>
            <button
              onClick={refreshState}
              className="px-2 py-0.5 rounded bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 border border-rose-500/40 text-[11px]"
            >
              Retry
            </button>
          </div>
        )}

        {/* 2. Session Gating Banner (High-visibility warning when execution is gated) */}
        {!hasActiveSession && (
          <section aria-label="Session Gating Banner">
            <SessionGatingBanner onOpenWizard={() => setIsWizardOpen(true)} />
          </section>
        )}

        {/* 3. Session Telemetry Bar (Live status, basket, countdown, and controls) */}
        {activeSession && (
          <section aria-label="Session Telemetry">
            <SessionTelemetryBar
              session={activeSession}
              account={state?.account}
              feedHealth={state?.data_feed_status}
              selectedTicker={selectedTicker}
              onSelectTicker={setSelectedTicker}
              onStartSession={async (id) => {
                await startSession(id);
              }}
              onPauseSession={async (id) => {
                await pauseSession(id);
              }}
              onResumeSession={async (id) => {
                await resumeSession(id);
              }}
              onStopSession={async (id, reason) => {
                await stopSession(id, reason);
              }}
              onOpenWizard={() => setIsWizardOpen(true)}
            />
          </section>
        )}

        {/* 4. Physical Exchange Session Ribbon with 1s Countdowns */}
        <section aria-label="Exchange Sessions">
          <MarketSessionRibbon
            marketSessions={state?.market_sessions}
            sessions={state?.market_sessions}
          />
        </section>

        {/* 5. KPI Performance & Alpha Metrics (Currency-aware ₹/$) */}
        <section aria-label="Performance KPIs">
          <KpiRibbon account={state?.account} currency={sessionCurrency} />
        </section>

        {/* 6. Multi-Asset Selector Bar */}
        <section aria-label="Watchlist & Asset Selection">
          <AssetSelector
            assets={state?.assets ?? {}}
            selectedTicker={selectedTicker}
            onSelectTicker={setSelectedTicker}
            armedTickers={armedTickers}
            onToggleArm={handleToggleArm}
            onAddCustomTicker={handleAddCustomTicker}
            onPlaceBotTrade={placeBotTrade}
          />
        </section>

        {/* 7. Core Cockpit Grid Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* Left Column (7/12 on large screens) */}
          <div className="lg:col-span-7 space-y-4">
            {/* TradingView Lightweight Chart */}
            <ChartContainer
              asset={selectedAsset}
              selectedTicker={selectedTicker}
              chartData={chartData}
            />

            {/* Positions & Closed Trades Table (Currency-aware ₹/$) */}
            <PositionsTable
              positions={state?.open_positions ?? []}
              closedTrades={state?.closed_trades ?? []}
              currency={sessionCurrency}
              onClosePosition={closePosition}
              onFlattenAll={flattenAll}
            />
          </div>

          {/* Right Column (5/12 on large screens) */}
          <div className="lg:col-span-5 space-y-4">
            {/* Order Controls & Pre-Market Pending Queue with Session Gating Locks */}
            <OrderControls
              selectedTicker={selectedTicker}
              selectedAsset={selectedAsset}
              botStatus={state?.bot_status}
              availableCash={
                state?.account?.available_cash ??
                state?.account?.cash ??
                state?.account?.current_cash ??
                100000
              }
              currentPrice={selectedAsset?.current_price ?? 0}
              pendingOrders={pendingOrders}
              isSessionGated={!isSessionRunning}
              currency={sessionCurrency}
              onPlaceOrder={placeOrder}
              onPlaceBotTrade={placeBotTrade}
              onCancelPendingOrder={cancelPendingOrder}
              onToggleBot={toggleBot}
              onToggleMarketHours={toggleMarketHours}
              onStepTick={stepTick}
              onResetAccount={resetAccount}
            />

            {/* Bounded Streaming Event Log with DECISION category and Net EV math cards */}
            <ActivityLog logs={boundedActivityLog} />
          </div>
        </div>
      </main>

      {/* 6-Step Setup Wizard Modal */}
      <TradingSessionWizardModal
        isOpen={isWizardOpen}
        marketSessions={state?.market_sessions}
        onClose={() => setIsWizardOpen(false)}
        onSessionStarted={(newSession) => {
          refreshState();
          if (newSession.instruments && newSession.instruments.length > 0) {
            setSelectedTicker(newSession.instruments[0]);
          }
        }}
      />

      {/* Institutional Status Footer */}
      <footer className="glass-panel border-t border-slate-800/80 px-4 py-2.5 text-[11px] font-mono text-slate-500 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-3">
          <span className="flex items-center text-slate-400">
            <ShieldCheck className="w-3.5 h-3.5 mr-1 text-emerald-400" />
            Memory Leak Shield Active
          </span>
          <span className="hidden sm:inline text-slate-600">•</span>
          <span className="hidden sm:inline">
            Bounded Ring Buffers (Max 500 Ticks / 100 Logs)
          </span>
          <span className="hidden sm:inline text-slate-600">•</span>
          <span className="hidden sm:inline">
            Page Visibility API Auto-Suspension
          </span>
        </div>

        <div className="flex items-center space-x-3 text-slate-400">
          <span className="flex items-center">
            <HardDrive className="w-3 h-3 mr-1 text-sky-400" />
            Heap Target &lt; 150 MB
          </span>
          <span>•</span>
          <span className="flex items-center">
            <Cpu className="w-3 h-3 mr-1 text-emerald-400" />
            Zero-GC Architecture
          </span>
        </div>
      </footer>
    </div>
  );
};

export default App;
