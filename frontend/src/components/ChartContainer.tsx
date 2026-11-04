import React, { useEffect, useRef } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  LineData,
  UTCTimestamp,
} from "lightweight-charts";
import { TrendingUp, TrendingDown, ShieldAlert, Crosshair } from "lucide-react";
import { AssetTelemetry, PricePoint } from "../types";

interface ChartContainerProps {
  asset?: AssetTelemetry;
  selectedTicker: string;
  chartData: PricePoint[];
}

export const ChartContainer: React.FC<ChartContainerProps> = ({
  asset,
  selectedTicker,
  chartData,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const priceSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const targetSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const stopSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const entrySeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  const decimals = asset?.decimals ?? 2;
  const currentPrice = asset?.current_price ?? 0;
  const movePct = asset?.move_pct ?? 0;
  const isPositive = movePct >= 0;

  // Initialize and tear down chart with explicit chart.remove() lifecycle
  useEffect(() => {
    if (!containerRef.current) return;

    // Create chart
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 380,
      layout: {
        background: { color: "transparent" },
        textColor: "#94a3b8",
        fontSize: 11,
        fontFamily: "'JetBrains Mono', monospace",
      },
      grid: {
        vertLines: { color: "rgba(30, 41, 59, 0.3)" },
        horzLines: { color: "rgba(30, 41, 59, 0.3)" },
      },
      rightPriceScale: {
        borderColor: "rgba(148, 163, 184, 0.12)",
        autoScale: true,
      },
      timeScale: {
        borderColor: "rgba(148, 163, 184, 0.12)",
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        vertLine: { color: "#38bdf8", width: 1, style: 2 },
        horzLine: { color: "#38bdf8", width: 1, style: 2 },
      },
    });

    // Primary Price Line Series
    const priceSeries = chart.addLineSeries({
      color: "#38bdf8",
      lineWidth: 2,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 4,
      crosshairMarkerBorderColor: "#0284c7",
      crosshairMarkerBackgroundColor: "#38bdf8",
      priceFormat: {
        type: "price",
        precision: decimals,
        minMove: 1 / Math.pow(10, decimals),
      },
    });

    // Target Line Series (Emerald Dashed)
    const targetSeries = chart.addLineSeries({
      color: "#10b981",
      lineWidth: 1,
      lineStyle: 2, // Dashed
      crosshairMarkerVisible: false,
      priceFormat: {
        type: "price",
        precision: decimals,
        minMove: 1 / Math.pow(10, decimals),
      },
    });

    // Stop Loss Line Series (Rose Dashed)
    const stopSeries = chart.addLineSeries({
      color: "#f43f5e",
      lineWidth: 1,
      lineStyle: 2, // Dashed
      crosshairMarkerVisible: false,
      priceFormat: {
        type: "price",
        precision: decimals,
        minMove: 1 / Math.pow(10, decimals),
      },
    });

    // Entry Price Line Series (Amber Dotted)
    const entrySeries = chart.addLineSeries({
      color: "#f59e0b",
      lineWidth: 1,
      lineStyle: 3, // Dotted
      crosshairMarkerVisible: false,
      priceFormat: {
        type: "price",
        precision: decimals,
        minMove: 1 / Math.pow(10, decimals),
      },
    });

    chartRef.current = chart;
    priceSeriesRef.current = priceSeries;
    targetSeriesRef.current = targetSeries;
    stopSeriesRef.current = stopSeries;
    entrySeriesRef.current = entrySeries;

    // Handle responsive resize with ResizeObserver
    const resizeObserver = new ResizeObserver((entries) => {
      if (!entries || entries.length === 0 || !entries[0].contentRect) return;
      const { width } = entries[0].contentRect;
      if (width > 0 && chartRef.current) {
        chartRef.current.applyOptions({ width });
      }
    });

    resizeObserver.observe(containerRef.current);

    // Teardown / Cleanup: Explicitly invoke chart.remove() to free WebGL/Canvas buffers!
    return () => {
      resizeObserver.disconnect();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
      priceSeriesRef.current = null;
      targetSeriesRef.current = null;
      stopSeriesRef.current = null;
      entrySeriesRef.current = null;
    };
  }, [selectedTicker, decimals]);

  // Update Series Data without rebuilding chart
  useEffect(() => {
    if (!priceSeriesRef.current || !chartData || chartData.length === 0) return;

    // Map bounded chartData to Lightweight Charts LineData
    // Use sequential synthetic timestamps (offset by index in seconds) to guarantee unique ascending times
    const baseTime = 1700000000;
    const formattedData: LineData[] = chartData.map((pt, idx) => ({
      time: (baseTime + idx * 60) as UTCTimestamp,
      value: pt.price,
    }));

    if (formattedData.length > 0) {
      priceSeriesRef.current.setData(formattedData);

      // Target Line
      if (asset?.target_price && targetSeriesRef.current) {
        targetSeriesRef.current.setData(
          formattedData.map((d) => ({ time: d.time, value: asset.target_price }))
        );
      }

      // Stop Line
      if (asset?.stop_price && stopSeriesRef.current) {
        stopSeriesRef.current.setData(
          formattedData.map((d) => ({ time: d.time, value: asset.stop_price }))
        );
      }

      // Entry Line
      if (asset?.has_open_position && asset.entry_price && entrySeriesRef.current) {
        entrySeriesRef.current.applyOptions({ visible: true });
        entrySeriesRef.current.setData(
          formattedData.map((d) => ({ time: d.time, value: asset.entry_price! }))
        );
      } else if (entrySeriesRef.current) {
        entrySeriesRef.current.applyOptions({ visible: false });
      }

      chartRef.current?.timeScale().fitContent();
    }
  }, [chartData, asset]);

  return (
    <div className="glass-panel rounded-xl p-4 flex flex-col space-y-3">
      {/* Chart Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
        <div className="flex items-center space-x-3">
          <div className="px-2.5 py-1 rounded bg-sky-500/10 border border-sky-500/30 text-sky-400 font-mono font-bold text-sm tracking-wide">
            {selectedTicker}
          </div>
          <div>
            <div className="text-xl font-bold font-mono text-slate-100 flex items-center space-x-2">
              <span>{currentPrice.toFixed(decimals)}</span>
              <span
                className={`text-xs font-semibold px-1.5 py-0.5 rounded flex items-center ${
                  isPositive
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-rose-500/10 text-rose-400"
                }`}
              >
                {isPositive ? (
                  <TrendingUp className="w-3 h-3 mr-0.5" />
                ) : (
                  <TrendingDown className="w-3 h-3 mr-0.5" />
                )}
                {isPositive ? "+" : ""}
                {movePct.toFixed(2)}%
              </span>
            </div>
            <div className="text-[11px] text-slate-400">
              {asset?.exchange_name || "Exchange"} • {asset?.exchange_clock || "Live"}
            </div>
          </div>
        </div>

        {/* Quant Badges */}
        <div className="flex flex-wrap items-center gap-2">
          {asset?.regime && (
            <span
              className={`text-xs px-2 py-0.5 rounded border font-mono ${
                asset.is_crisis
                  ? "bg-rose-500/10 border-rose-500/30 text-rose-400 flex items-center"
                  : "bg-slate-800 border-slate-700 text-slate-300"
              }`}
            >
              {asset.is_crisis && <ShieldAlert className="w-3 h-3 mr-1 text-rose-400" />}
              {asset.regime}
            </span>
          )}

          {asset?.signal && (
            <span
              className={`text-xs px-2.5 py-0.5 rounded border font-mono font-semibold ${
                asset.signal.toUpperCase() === "BUY"
                  ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-300"
                  : asset.signal.toUpperCase() === "SELL"
                  ? "bg-rose-500/20 border-rose-500/40 text-rose-300"
                  : "bg-slate-800 border-slate-700 text-slate-400"
              }`}
            >
              {asset.signal} ({asset.confidence_pct}% Conf)
            </span>
          )}

          {/* Target & Stop Badges */}
          {asset?.target_price ? (
            <div className="hidden sm:flex items-center space-x-1.5 text-[11px] font-mono">
              <span className="px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
                PT: {asset.target_price.toFixed(decimals)}
              </span>
              <span className="px-2 py-0.5 rounded bg-rose-500/10 border border-rose-500/20 text-rose-400">
                SL: {asset.stop_price.toFixed(decimals)}
              </span>
              {asset.has_open_position && asset.entry_price && (
                <span className="px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-400">
                  Entry: {asset.entry_price.toFixed(decimals)}
                </span>
              )}
            </div>
          ) : null}
        </div>
      </div>

      {/* Lightweight Chart Container */}
      <div className="relative w-full h-[380px] bg-slate-950/40 rounded-lg overflow-hidden border border-slate-800/60">
        <div ref={containerRef} className="w-full h-full" />
        {(!chartData || chartData.length === 0) && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm text-slate-400 text-xs font-mono">
            <Crosshair className="w-4 h-4 mr-2 animate-spin text-sky-400" />
            Connecting to tick stream for {selectedTicker}...
          </div>
        )}
      </div>

      {/* Legend / Status line */}
      <div className="flex flex-wrap items-center justify-between text-[11px] text-slate-400 font-mono pt-1">
        <div className="flex items-center space-x-4">
          <span className="flex items-center">
            <span className="w-2.5 h-0.5 bg-sky-400 inline-block mr-1.5"></span>
            Price Stream (RingBuffer max 500)
          </span>
          <span className="flex items-center">
            <span className="w-2.5 h-0.5 border-t border-dashed border-emerald-400 inline-block mr-1.5"></span>
            Profit Target
          </span>
          <span className="flex items-center">
            <span className="w-2.5 h-0.5 border-t border-dashed border-rose-400 inline-block mr-1.5"></span>
            Stop Loss
          </span>
          {asset?.has_open_position && (
            <span className="flex items-center text-amber-400">
              <span className="w-2.5 h-0.5 border-t border-dotted border-amber-400 inline-block mr-1.5"></span>
              Open Position Entry
            </span>
          )}
        </div>
        <div>
          Points: <span className="text-sky-400 font-bold">{chartData.length}</span> / 500
        </div>
      </div>
    </div>
  );
};
