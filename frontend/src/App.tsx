import React, { useState } from "react";
import { Navbar } from "./components/layout/Navbar";
import { StatusFooter } from "./components/layout/StatusFooter";
import {
  OverviewView,
  MarketIntelligenceView,
  QuantitativeScannerView,
  TradingEngineView,
  PortfolioView,
  PositionsOrdersView,
  StrategyLabView,
  RiskManagementView,
  AnalyticsPerformanceView,
  SystemMonitoringView,
  SettingsView,
} from "./components/views";
import { TradingSessionWizardModal } from "./components/wizard/TradingSessionWizardModal";
import { SessionHistoryModal } from "./components/session/SessionHistoryModal";
import { useDashboardStream } from "./hooks/useDashboardStream";
import { NavigationTab } from "./types";
import { AlertCircle } from "lucide-react";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<NavigationTab>("overview");
  const [isWizardOpen, setIsWizardOpen] = useState<boolean>(false);
  const [isHistoryOpen, setIsHistoryOpen] = useState<boolean>(false);

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
    <div className="min-h-screen bg-[#060911] text-slate-100 flex flex-col font-sans selection:bg-cyan-500/30 selection:text-cyan-200">
      {/* 1. Global Navigation Bar with 11 Workspaces */}
      <Navbar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        botStatus={state?.bot_status}
        account={state?.account}
        isLoading={isLoading}
        onRefresh={refreshState}
        onEmergencyKill={flattenAll}
      />

      {/* Main Workspace Body */}
      <main className="flex-1 p-3 sm:p-4 md:p-6 max-w-[1920px] mx-auto w-full">
        {/* Connection Notice */}
        {error && (
          <div className="mb-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono flex items-center justify-between">
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

        {/* View Switcher: 11 Dedicated Institutional Quant Workspaces */}
        {activeTab === "overview" && (
          <OverviewView
            state={state}
            selectedTicker={selectedTicker}
            onSelectTicker={setSelectedTicker}
            chartData={chartData}
            boundedActivityLog={boundedActivityLog}
            pendingOrders={pendingOrders}
            activeSession={activeSession}
            hasActiveSession={hasActiveSession}
            isSessionRunning={isSessionRunning}
            sessionCurrency={sessionCurrency}
            onOpenWizard={() => setIsWizardOpen(true)}
            onOpenHistory={() => setIsHistoryOpen(true)}
            onStartSession={startSession}
            onPauseSession={pauseSession}
            onResumeSession={resumeSession}
            onStopSession={stopSession}
            onToggleArm={handleToggleArm}
            onAddCustomTicker={handleAddCustomTicker}
            onPlaceOrder={placeOrder}
            onPlaceBotTrade={placeBotTrade}
            onCancelPendingOrder={cancelPendingOrder}
            onToggleBot={toggleBot}
            onToggleMarketHours={toggleMarketHours}
            onStepTick={stepTick}
            onResetAccount={resetAccount}
            onClosePosition={closePosition}
            onFlattenAll={flattenAll}
          />
        )}

        {activeTab === "market-intelligence" && <MarketIntelligenceView />}

        {activeTab === "scanner" && (
          <QuantitativeScannerView
            onSelectTicker={setSelectedTicker}
            chartData={chartData}
            assets={state?.assets ?? {}}
            onPlaceBotTrade={placeBotTrade}
          />
        )}

        {activeTab === "trading-engine" && (
          <TradingEngineView
            state={state}
            activeSession={activeSession}
            onOpenWizard={() => setIsWizardOpen(true)}
            onOpenHistory={() => setIsHistoryOpen(true)}
            onPauseSession={pauseSession}
            onResumeSession={resumeSession}
            onStopSession={stopSession}
            onFlattenAll={flattenAll}
            onPlaceOrder={placeOrder}
            selectedTicker={selectedTicker}
          />
        )}

        {activeTab === "portfolio" && (
          <PortfolioView
            state={state}
            account={state?.account}
            positions={state?.open_positions ?? []}
            closedTrades={state?.closed_trades ?? []}
            onClosePosition={closePosition}
            onFlattenAll={flattenAll}
          />
        )}

        {activeTab === "positions-orders" && (
          <PositionsOrdersView
            state={state}
            positions={state?.open_positions ?? []}
            pendingOrders={pendingOrders}
            closedTrades={state?.closed_trades ?? []}
            onClosePosition={closePosition}
            onCancelPendingOrder={cancelPendingOrder}
            onFlattenAll={flattenAll}
          />
        )}

        {activeTab === "strategy-lab" && (
          <StrategyLabView
            initialTicker={selectedTicker}
            onSelectTicker={setSelectedTicker}
          />
        )}

        {activeTab === "risk-management" && (
          <RiskManagementView
            onEmergencyKill={flattenAll}
          />
        )}

        {activeTab === "analytics" && (
          <AnalyticsPerformanceView
            onRefresh={refreshState}
          />
        )}

        {activeTab === "monitoring" && (
          <SystemMonitoringView
            botStatus={state?.bot_status}
            dataFeedStatus={state?.data_feed_status}
          />
        )}

        {activeTab === "settings" && <SettingsView />}
      </main>

      {/* 6-Step Setup Wizard Modal */}
      {isWizardOpen && (
        <TradingSessionWizardModal
          key={isWizardOpen ? "open" : "closed"}
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
      )}

      {/* Historical Audit Drawer */}
      <SessionHistoryModal
        isOpen={isHistoryOpen}
        onClose={() => setIsHistoryOpen(false)}
      />

      {/* Institutional Status Footer */}
      <StatusFooter
        latencyMs={state?.data_feed_status?.average_latency_ms ?? 0}
        dataMode={state?.data_feed_status?.data_mode ?? "LIVE_MARKET_DATA"}
        isTabVisible={isTabVisible}
      />
    </div>
  );
};

export default App;
