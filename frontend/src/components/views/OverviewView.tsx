import React from "react";
import { MarketSessionRibbon } from "../MarketSessionRibbon";
import { KpiRibbon } from "../KpiRibbon";
import { AssetSelector } from "../AssetSelector";
import { ChartContainer } from "../ChartContainer";
import { PositionsTable } from "../PositionsTable";
import { OrderControls } from "../OrderControls";
import { ActivityLog } from "../ActivityLog";
import { SessionTelemetryBar } from "../session/SessionTelemetryBar";
import { SessionGatingBanner } from "../session/SessionGatingBanner";
import {
  DashboardState,
  PricePoint,
  TradingSession,
  BotTradeResponse,
} from "../../types";

export interface OverviewViewProps {
  state: DashboardState | null;
  selectedTicker: string;
  onSelectTicker: (ticker: string) => void;
  chartData: PricePoint[];
  boundedActivityLog: any[];
  pendingOrders: any[];
  activeSession: TradingSession | null;
  hasActiveSession: boolean;
  isSessionRunning: boolean;
  sessionCurrency: string;
  onOpenWizard: () => void;
  onOpenHistory: () => void;
  onStartSession: (sessionId: string) => Promise<any>;
  onPauseSession: (sessionId: string) => Promise<any>;
  onResumeSession: (sessionId: string) => Promise<any>;
  onStopSession: (sessionId: string, reason?: string) => Promise<any>;
  onToggleArm: (ticker: string) => void;
  onAddCustomTicker: (ticker: string) => void;
  onPlaceOrder: (
    ticker: string,
    direction: "LONG" | "SHORT" | "AUTO",
    allocWeight?: number,
    orderType?: "MARKET" | "LIMIT",
    limitPrice?: number,
    targetPrice?: number,
    stopPrice?: number
  ) => Promise<void>;
  onPlaceBotTrade: (
    ticker: string,
    direction?: "AUTO" | "LONG" | "SHORT",
    allocWeight?: number,
    orderType?: "MARKET" | "LIMIT",
    limitPrice?: number,
    targetPrice?: number,
    stopPrice?: number
  ) => Promise<BotTradeResponse>;
  onCancelPendingOrder: (orderId: string) => Promise<any>;
  onToggleBot: () => Promise<any>;
  onToggleMarketHours: () => Promise<any>;
  onStepTick: () => Promise<any>;
  onResetAccount: () => Promise<any>;
  onClosePosition: (id: number) => void;
  onFlattenAll: () => Promise<any>;
}

export const OverviewView: React.FC<OverviewViewProps> = ({
  state,
  selectedTicker,
  onSelectTicker,
  chartData,
  boundedActivityLog,
  pendingOrders,
  activeSession,
  hasActiveSession,
  isSessionRunning,
  sessionCurrency,
  onOpenWizard,
  onOpenHistory,
  onStartSession,
  onPauseSession,
  onResumeSession,
  onStopSession,
  onToggleArm,
  onAddCustomTicker,
  onPlaceOrder,
  onPlaceBotTrade,
  onCancelPendingOrder,
  onToggleBot,
  onToggleMarketHours,
  onStepTick,
  onResetAccount,
  onClosePosition,
  onFlattenAll,
}) => {
  const selectedAsset = state?.assets?.[selectedTicker];
  const armedTickers = state?.bot_status?.armed_tickers ?? [];

  return (
    <div className="space-y-4">
      {/* 1. Session Gating Banner or Session Telemetry */}
      {!hasActiveSession ? (
        <section aria-label="Session Gating Banner">
          <SessionGatingBanner onOpenWizard={onOpenWizard} onOpenHistory={onOpenHistory} />
        </section>
      ) : (
        <section aria-label="Session Telemetry">
          <SessionTelemetryBar
            session={activeSession}
            account={state?.account}
            feedHealth={state?.data_feed_status}
            selectedTicker={selectedTicker}
            onSelectTicker={onSelectTicker}
            onStartSession={onStartSession}
            onPauseSession={onPauseSession}
            onResumeSession={onResumeSession}
            onStopSession={onStopSession}
            onOpenWizard={onOpenWizard}
            onOpenHistory={onOpenHistory}
          />
        </section>
      )}

      {/* 2. Indian Market Sessions Ribbon */}
      <section aria-label="Exchange Sessions">
        <MarketSessionRibbon marketSessions={state?.market_sessions} sessions={state?.market_sessions} />
      </section>

      {/* 3. KPI Ribbon */}
      <section aria-label="Performance KPIs">
        <KpiRibbon account={state?.account} currency={sessionCurrency} />
      </section>

      {/* 4. Multi-Asset Watchlist & Sizing Bar */}
      <section aria-label="Watchlist & Asset Selection">
        <AssetSelector
          assets={state?.assets ?? {}}
          selectedTicker={selectedTicker}
          onSelectTicker={onSelectTicker}
          armedTickers={armedTickers}
          onToggleArm={onToggleArm}
          onAddCustomTicker={onAddCustomTicker}
          onPlaceBotTrade={onPlaceBotTrade}
        />
      </section>

      {/* 5. Main Split Cockpit Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left Column (Chart & Positions) */}
        <div className="lg:col-span-7 space-y-4">
          <ChartContainer asset={selectedAsset} selectedTicker={selectedTicker} chartData={chartData} />
          <PositionsTable
            positions={state?.open_positions ?? []}
            closedTrades={state?.closed_trades ?? []}
            currency={sessionCurrency}
            onClosePosition={onClosePosition}
            onFlattenAll={onFlattenAll}
          />
        </div>

        {/* Right Column (Controls & Decision Log) */}
        <div className="lg:col-span-5 space-y-4">
          <OrderControls
            selectedTicker={selectedTicker}
            selectedAsset={selectedAsset}
            botStatus={state?.bot_status}
            availableCash={
              state?.account?.available_cash ??
              state?.account?.cash ??
              state?.account?.current_cash ??
              500000
            }
            currentPrice={selectedAsset?.current_price ?? 0}
            pendingOrders={pendingOrders}
            isSessionGated={!isSessionRunning}
            currency={sessionCurrency}
            onPlaceOrder={onPlaceOrder}
            onPlaceBotTrade={onPlaceBotTrade}
            onCancelPendingOrder={onCancelPendingOrder}
            onToggleBot={onToggleBot}
            onToggleMarketHours={onToggleMarketHours}
            onStepTick={onStepTick}
            onResetAccount={onResetAccount}
          />
          <ActivityLog logs={boundedActivityLog} />
        </div>
      </div>
    </div>
  );
};
