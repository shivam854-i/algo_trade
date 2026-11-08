import { useCallback, useEffect, useRef, useState } from "react";
import {
  BotTradeResponse,
  DashboardState,
  LogItem,
  PendingOrder,
  PricePoint,
  TradingSession,
} from "../types";
import { RingBuffer } from "../utils/ringBuffer";
import { usePageVisibility } from "./usePageVisibility";
import { sessionApi } from "../services/sessionApi";

interface UseDashboardStreamOptions {
  pollIntervalMs?: number;
  chartCapacity?: number;
  logCapacity?: number;
}

export interface UseDashboardStreamResult {
  state: DashboardState | null;
  isLoading: boolean;
  error: string | null;
  isTabVisible: boolean;
  isPollingActive: boolean;
  selectedTicker: string;
  setSelectedTicker: (ticker: string) => void;
  chartData: PricePoint[];
  boundedActivityLog: LogItem[];
  pendingOrders: PendingOrder[];
  // Session State & Telemetry
  activeSession: TradingSession | null;
  hasActiveSession: boolean;
  isSessionRunning: boolean;
  isSessionPaused: boolean;
  sessionCurrency: string;
  // Session Lifecycle Actions
  startSession: (sessionId: string) => Promise<TradingSession>;
  pauseSession: (sessionId: string) => Promise<TradingSession>;
  resumeSession: (sessionId: string) => Promise<TradingSession>;
  stopSession: (sessionId: string, reason?: string) => Promise<TradingSession>;
  // Existing Actions
  refreshState: () => Promise<void>;
  stepTick: (shockPct?: number) => Promise<void>;
  toggleBot: () => Promise<void>;
  toggleMarketHours: () => Promise<void>;
  closePosition: (positionId: number) => Promise<void>;
  flattenAll: () => Promise<void>;
  resetAccount: () => Promise<void>;
  armTickers: (tickers: string[], addTickers?: string[]) => Promise<void>;
  placeOrder: (
    ticker: string,
    direction: "LONG" | "SHORT" | "AUTO",
    allocWeight?: number,
    orderType?: "MARKET" | "LIMIT",
    limitPrice?: number,
    targetPrice?: number,
    stopPrice?: number
  ) => Promise<void>;
  placeBotTrade: (
    ticker: string,
    direction?: "AUTO" | "LONG" | "SHORT",
    allocWeight?: number,
    orderType?: "MARKET" | "LIMIT",
    limitPrice?: number,
    targetPrice?: number,
    stopPrice?: number
  ) => Promise<BotTradeResponse>;
  cancelPendingOrder: (orderId: string) => Promise<void>;
}

export function useDashboardStream({
  pollIntervalMs = 2500,
  chartCapacity = 500,
  logCapacity = 100,
}: UseDashboardStreamOptions = {}): UseDashboardStreamResult {
  const [state, setState] = useState<DashboardState | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTicker, setSelectedTicker] = useState<string>("NVDA");
  const [pendingOrders, setPendingOrders] = useState<PendingOrder[]>([]);
  const [chartData, setChartData] = useState<PricePoint[]>([]);
  const [boundedActivityLog, setBoundedActivityLog] = useState<LogItem[]>([]);

  const isTabVisible = usePageVisibility();
  const pollTimerRef = useRef<number | null>(null);
  const isFetchingRef = useRef<boolean>(false);
  const stateRef = useRef<DashboardState | null>(null);

  // Persistent Ring Buffers to eliminate GC churn
  // Chart ring buffer holds up to chartCapacity (500) items per selected ticker
  const chartBufferRef = useRef<RingBuffer<PricePoint>>(new RingBuffer<PricePoint>(chartCapacity));
  // Activity log ring buffer holds up to logCapacity (100) items
  const logBufferRef = useRef<RingBuffer<LogItem>>(new RingBuffer<LogItem>(logCapacity));

  // Sync state data into bounded Ring Buffers
  const ingestStateIntoBuffers = useCallback(
    (newState: DashboardState, tickerToInspect: string) => {
      // 1. Ingest Activity Log into bounded ring buffer
      if (newState.activity_log && Array.isArray(newState.activity_log)) {
        // Feed in reverse or forward to maintain order
        logBufferRef.current.clear();
        // Backend returns latest first ([:40]); reverse to store chronologically
        const chronological = [...newState.activity_log].reverse();
        logBufferRef.current.pushMany(chronological);
        setBoundedActivityLog(logBufferRef.current.toArray().reverse());
      }

      // 2. Ingest Chart Data for selected ticker
      const asset = newState.assets?.[tickerToInspect];
      if (asset?.price_series && Array.isArray(asset.price_series)) {
        chartBufferRef.current.clear();
        chartBufferRef.current.pushMany(asset.price_series);
        setChartData(chartBufferRef.current.toArray());
      } else if (newState.comparison_series && Array.isArray(newState.comparison_series)) {
        // Fallback to comparison series if asset series is unavailable
        chartBufferRef.current.clear();
        const fallbackPoints: PricePoint[] = newState.comparison_series.map((p) => ({
          tick: p.tick,
          time: p.time,
          price: p.equity,
        }));
        chartBufferRef.current.pushMany(fallbackPoints);
        setChartData(chartBufferRef.current.toArray());
      }
    },
    []
  );

  // Fetch pending orders from endpoint or state
  const fetchPendingOrders = useCallback(async () => {
    try {
      const res = await fetch("/api/dashboard/orders/pending");
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setPendingOrders(data);
          return;
        } else if (data.orders && Array.isArray(data.orders)) {
          setPendingOrders(data.orders);
          return;
        }
      }
    } catch {
      // Silently fall back if backend pending orders endpoint is not yet active
    }
  }, []);

  // Fetch full dashboard snapshot
  const fetchState = useCallback(async () => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    try {
      const res = await fetch("/api/dashboard/state");
      if (!res.ok) {
        throw new Error(`HTTP Error ${res.status}: ${res.statusText}`);
      }
      const data: DashboardState = await res.json();
      stateRef.current = data;
      setState(data);
      setError(null);
      let activeTk = selectedTicker;
      if (data.assets && !data.assets[activeTk]) {
        const firstAvailable = Object.keys(data.assets)[0];
        if (firstAvailable) {
          activeTk = firstAvailable;
          setSelectedTicker(firstAvailable);
        }
      }
      ingestStateIntoBuffers(data, activeTk);
      if (Array.isArray(data.pending_orders)) {
        setPendingOrders(data.pending_orders);
      } else {
        fetchPendingOrders();
      }
    } catch (err) {
      console.warn("Failed to fetch dashboard state:", err);
      setError(err instanceof Error ? err.message : "Network error");
    } finally {
      setIsLoading(false);
      isFetchingRef.current = false;
    }
  }, [selectedTicker, ingestStateIntoBuffers, fetchPendingOrders]);

  // Step simulation tick
  const stepTick = useCallback(
    async (shockPct?: number) => {
      if (isFetchingRef.current) return;
      isFetchingRef.current = true;
      try {
        const url =
          shockPct !== undefined
            ? `/api/dashboard/step?shock_pct=${shockPct}`
            : "/api/dashboard/step";
        const res = await fetch(url, { method: "POST" });
        if (!res.ok) throw new Error(`Step tick failed: ${res.status}`);
        const data: DashboardState = await res.json();
        stateRef.current = data;
        setState(data);
        setError(null);
        ingestStateIntoBuffers(data, selectedTicker);
        if (Array.isArray(data.pending_orders)) {
          setPendingOrders(data.pending_orders);
        } else {
          fetchPendingOrders();
        }
      } catch (err) {
        console.warn("Error stepping tick:", err);
        setError(err instanceof Error ? err.message : "Step tick failed");
      } finally {
        isFetchingRef.current = false;
      }
    },
    [selectedTicker, ingestStateIntoBuffers, fetchPendingOrders]
  );

  // Update selected ticker and update chart buffer
  const handleSelectTicker = useCallback(
    (tk: string) => {
      setSelectedTicker(tk);
      if (state?.assets?.[tk]) {
        chartBufferRef.current.clear();
        chartBufferRef.current.pushMany(state.assets[tk].price_series || []);
        setChartData(chartBufferRef.current.toArray());
      }
    },
    [state]
  );

  // Page Visibility-governed polling lifecycle
  useEffect(() => {
    // If tab is hidden, suspend all intervals and network requests immediately
    if (!isTabVisible) {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      return;
    }

    // Tab became visible: fetch a single clean snapshot to resync
    fetchState();

    // Start background polling timer
    pollTimerRef.current = window.setInterval(() => {
      const curr = stateRef.current;
      const sessStatus = curr?.active_session?.status;
      if (
        (curr?.bot_status?.is_running && sessStatus === "RUNNING") ||
        sessStatus === "PAUSED"
      ) {
        stepTick();
      } else {
        fetchState();
      }
    }, pollIntervalMs);

    return () => {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [isTabVisible, pollIntervalMs, fetchState, stepTick]);

  // Action: Toggle Bot
  const toggleBot = useCallback(async () => {
    try {
      const res = await fetch("/api/dashboard/toggle", { method: "POST" });
      if (!res.ok) throw new Error("Toggle bot failed");
      const data: DashboardState = await res.json();
      setState(data);
      ingestStateIntoBuffers(data, selectedTicker);
    } catch (err) {
      console.error(err);
    }
  }, [selectedTicker, ingestStateIntoBuffers]);

  // Action: Toggle Market Hours enforcement
  const toggleMarketHours = useCallback(async () => {
    try {
      const res = await fetch("/api/dashboard/toggle-hours", { method: "POST" });
      if (!res.ok) throw new Error("Toggle hours failed");
      const data: DashboardState = await res.json();
      setState(data);
      ingestStateIntoBuffers(data, selectedTicker);
    } catch (err) {
      console.error(err);
    }
  }, [selectedTicker, ingestStateIntoBuffers]);

  // Action: Close Position
  const closePosition = useCallback(
    async (positionId: number) => {
      try {
        const res = await fetch(`/api/dashboard/close/${positionId}`, { method: "POST" });
        if (!res.ok) throw new Error("Close position failed");
        const data: DashboardState = await res.json();
        setState(data);
        ingestStateIntoBuffers(data, selectedTicker);
      } catch (err) {
        console.error(err);
      }
    },
    [selectedTicker, ingestStateIntoBuffers]
  );

  // Action: Flatten All
  const flattenAll = useCallback(async () => {
    try {
      const res = await fetch("/api/dashboard/flatten", { method: "POST" });
      if (!res.ok) throw new Error("Flatten failed");
      const data: DashboardState = await res.json();
      setState(data);
      ingestStateIntoBuffers(data, selectedTicker);
    } catch (err) {
      console.error(err);
    }
  }, [selectedTicker, ingestStateIntoBuffers]);

  // Action: Reset Account
  const resetAccount = useCallback(async () => {
    try {
      const res = await fetch("/api/dashboard/reset", { method: "POST" });
      if (!res.ok) throw new Error("Reset account failed");
      const data: DashboardState = await res.json();
      setState(data);
      ingestStateIntoBuffers(data, selectedTicker);
      fetchPendingOrders();
    } catch (err) {
      console.error(err);
    }
  }, [selectedTicker, ingestStateIntoBuffers, fetchPendingOrders]);

  // Action: Arm Tickers
  const armTickers = useCallback(
    async (tickers: string[], addTickers?: string[]) => {
      try {
        const res = await fetch("/api/dashboard/select-assets", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            armed_tickers: tickers,
            add_custom_tickers: addTickers || null,
          }),
        });
        if (!res.ok) throw new Error("Arm tickers failed");
        const data: DashboardState = await res.json();
        setState(data);
        ingestStateIntoBuffers(data, selectedTicker);
      } catch (err) {
        console.error(err);
      }
    },
    [selectedTicker, ingestStateIntoBuffers]
  );

  // Action: Place Order
  const placeOrder = useCallback(
    async (
      ticker: string,
      direction: "LONG" | "SHORT" | "AUTO",
      allocWeight = 10,
      orderType: "MARKET" | "LIMIT" = "MARKET",
      limitPrice?: number,
      targetPrice?: number,
      stopPrice?: number
    ) => {
      try {
        const res = await fetch("/api/dashboard/order", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ticker,
            direction,
            allocation_weight_pct: allocWeight,
            order_type: orderType,
            limit_price: limitPrice,
            target_price: targetPrice,
            stop_price: stopPrice,
          }),
        });
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || "Failed to place order");
        }
        const payload = await res.json();
        const dashState: DashboardState = payload.dashboard_state ? payload.dashboard_state : payload;
        setState(dashState);
        setSelectedTicker(ticker.toUpperCase());
        ingestStateIntoBuffers(dashState, ticker.toUpperCase());
        fetchPendingOrders();
      } catch (err) {
        console.error("Order error:", err);
        throw err;
      }
    },
    [ingestStateIntoBuffers, fetchPendingOrders]
  );

  // Action: Place Bot-Managed Trade (Search & 1-Click Bot Execution)
  const placeBotTrade = useCallback(
    async (
      ticker: string,
      direction: "AUTO" | "LONG" | "SHORT" = "AUTO",
      allocWeight?: number,
      orderType: "MARKET" | "LIMIT" = "MARKET",
      limitPrice?: number,
      targetPrice?: number,
      stopPrice?: number
    ): Promise<BotTradeResponse> => {
      const res = await fetch("/api/dashboard/bot-trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker,
          direction,
          allocation_weight_pct: allocWeight,
          order_type: orderType,
          limit_price: limitPrice,
          target_price: targetPrice,
          stop_price: stopPrice,
          auto_arm: true,
          execution_mode: "PAPER",
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to place bot trade for ${ticker}`);
      }
      const payload: BotTradeResponse = await res.json();
      if (payload.dashboard_state) {
        setState(payload.dashboard_state);
        setSelectedTicker(payload.ticker);
        ingestStateIntoBuffers(payload.dashboard_state, payload.ticker);
      } else {
        await fetchState();
      }
      fetchPendingOrders();
      return payload;
    },
    [ingestStateIntoBuffers, fetchPendingOrders, fetchState]
  );

  // Action: Cancel Pending Order
  const cancelPendingOrder = useCallback(
    async (orderId: string) => {
      try {
        const res = await fetch(`/api/dashboard/orders/cancel/${orderId}`, {
          method: "DELETE",
        });
        if (res.ok) {
          fetchPendingOrders();
          fetchState();
        }
      } catch (err) {
        console.error("Cancel order error:", err);
      }
    },
    [fetchPendingOrders, fetchState]
  );

  // Derived Session Helper Properties
  const activeSession = state?.active_session ?? null;
  const hasActiveSession = Boolean(
    activeSession && !["COMPLETED", "STOPPED"].includes(activeSession.status)
  );
  const isSessionRunning = activeSession?.status === "RUNNING";
  const isSessionPaused = activeSession?.status === "PAUSED";
  const sessionCurrency = activeSession?.currency ?? state?.currency ?? "INR";

  // Session Action Handlers
  const startSession = useCallback(
    async (sessionId: string): Promise<TradingSession> => {
      const sess = await sessionApi.startSession(sessionId);
      await fetchState();
      return sess;
    },
    [fetchState]
  );

  const pauseSession = useCallback(
    async (sessionId: string): Promise<TradingSession> => {
      const sess = await sessionApi.pauseSession(sessionId);
      await fetchState();
      return sess;
    },
    [fetchState]
  );

  const resumeSession = useCallback(
    async (sessionId: string): Promise<TradingSession> => {
      const sess = await sessionApi.resumeSession(sessionId);
      await fetchState();
      return sess;
    },
    [fetchState]
  );

  const stopSession = useCallback(
    async (sessionId: string, reason?: string): Promise<TradingSession> => {
      const sess = await sessionApi.stopSession(sessionId, reason);
      await fetchState();
      return sess;
    },
    [fetchState]
  );

  return {
    state,
    isLoading,
    error,
    isTabVisible,
    isPollingActive: isTabVisible,
    selectedTicker,
    setSelectedTicker: handleSelectTicker,
    chartData,
    boundedActivityLog,
    pendingOrders,
    activeSession,
    hasActiveSession,
    isSessionRunning,
    isSessionPaused,
    sessionCurrency,
    startSession,
    pauseSession,
    resumeSession,
    stopSession,
    refreshState: fetchState,
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
  };
}
