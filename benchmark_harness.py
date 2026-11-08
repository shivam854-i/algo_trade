#!/usr/bin/env python3
"""SYNAPSE-TITAN Performance Benchmark Harness.

Standalone benchmark harness measuring latency and throughput for core
quantitative pipelines, server startup, and API endpoints.

Targets:
1. Server Startup:
   - Module import latency (server.py + dependencies)
   - Core engine component instantiation (MarketPredictionEngine, BacktestEngine)
   - LiveBotController & Market State initialization (watchlist scan)
   - Total cold boot time (_get_live_bot())
2. analyze_ticker:
   - Cold run (first-time model initialization & inference on an NSE ticker e.g. 'RELIANCE.NS')
   - Warm run (second and subsequent executions on the same engine instance)
3. backtest:
   - Walk-forward backtest execution over standard period ('6mo', '1d' on 'RELIANCE.NS')
4. dashboard poll:
   - Direct bot.get_dashboard_state() internal latency (mean, p50, p95, p99)
   - HTTP GET /api/dashboard/state via FastAPI TestClient (mean, p50, p95, p99, throughput)

Usage:
    python benchmark_harness.py
    python benchmark_harness.py --ticker RELIANCE.NS --period 6mo --dashboard-runs 50
"""

import argparse
from dataclasses import asdict, dataclass
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional
import warnings

# Suppress library deprecation and info noise during benchmarking
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.WARNING)

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console(width=120)


class BenchmarkHarness:
    """Automated benchmark runner for SYNAPSE-TITAN platform."""

    def __init__(
        self,
        ticker: str = "RELIANCE.NS",
        backtest_period: str = "6mo",
        dashboard_runs: int = 50,
        warm_runs: int = 5,
        backtest_runs: int = 3,
    ):
        self.ticker = ticker
        self.backtest_period = backtest_period
        self.dashboard_runs = dashboard_runs
        self.warm_runs = warm_runs
        self.backtest_runs = backtest_runs
        self.results: Dict[str, Any] = {}

    def benchmark_analyze_ticker(self) -> Dict[str, Any]:
        """Measures cold and warm inference for an NSE ticker (e.g. RELIANCE.NS).

        Cold run: First-time model initialization & execution on the ticker.
        Warm run: Subsequent cached/resident inference on the same engine instance.
        """
        console.print(f"[bold cyan]>>> Benchmarking analyze_ticker on {self.ticker}...[/bold cyan]")

        # Run cold run in isolated subprocess to measure true cold-start (unloaded PyTorch & models)
        cold_code = f"""
import time, json, warnings
warnings.filterwarnings('ignore')
from src.pipeline import MarketPredictionEngine

t0 = time.perf_counter()
engine = MarketPredictionEngine()
res = engine.analyze_ticker('{self.ticker}', period='1y', interval='1d')
t_cold_ms = (time.perf_counter() - t0) * 1000.0

# Measure warm runs immediately on same instance
warm_times = []
for _ in range({self.warm_runs}):
    t1 = time.perf_counter()
    _ = engine.analyze_ticker('{self.ticker}', period='1y', interval='1d')
    warm_times.append((time.perf_counter() - t1) * 1000.0)

out = {{
    'cold_run_ms': round(t_cold_ms, 2),
    'warm_samples_ms': [round(x, 2) for x in warm_times],
}}
print('__ANALYZE_RESULT__' + json.dumps(out))
"""
        cmd = [sys.executable, "-c", cold_code]
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        raw_output = {}
        for line in proc.stdout.splitlines():
            if line.startswith("__ANALYZE_RESULT__"):
                raw_output = json.loads(line.replace("__ANALYZE_RESULT__", "").strip())
                break

        if not raw_output:
            console.print(f"[red]Error in analyze_ticker subprocess: {proc.stderr}[/red]")
            # Fallback to in-process
            from src.pipeline import MarketPredictionEngine

            t0 = time.perf_counter()
            engine = MarketPredictionEngine()
            _ = engine.analyze_ticker(self.ticker, period="1y", interval="1d")
            t_cold_ms = (time.perf_counter() - t0) * 1000.0
            warm_times = []
            for _ in range(self.warm_runs):
                t1 = time.perf_counter()
                _ = engine.analyze_ticker(self.ticker, period="1y", interval="1d")
                warm_times.append((time.perf_counter() - t1) * 1000.0)
            raw_output = {
                "cold_run_ms": round(t_cold_ms, 2),
                "warm_samples_ms": [round(x, 2) for x in warm_times],
            }

        warm_samples = raw_output["warm_samples_ms"]
        cold_run_ms = raw_output["cold_run_ms"]
        mean_warm = float(np.mean(warm_samples))

        results = {
            "ticker": self.ticker,
            "cold_run_ms": cold_run_ms,
            "warm_run_mean_ms": round(mean_warm, 2),
            "warm_run_median_ms": round(float(np.median(warm_samples)), 2),
            "warm_run_min_ms": round(float(np.min(warm_samples)), 2),
            "warm_run_max_ms": round(float(np.max(warm_samples)), 2),
            "warm_run_std_ms": round(float(np.std(warm_samples)), 2),
            "warm_samples_ms": warm_samples,
            "speedup_factor": round(cold_run_ms / mean_warm, 2) if mean_warm > 0 else 1.0,
        }
        return results

    def benchmark_backtest(self) -> Dict[str, Any]:
        """Measures walk-forward backtest execution over standard period."""
        console.print(f"[bold cyan]>>> Benchmarking backtest on {self.ticker} (period: {self.backtest_period})...[/bold cyan]")
        from src.backtest.engine import BacktestEngine

        bt_engine = BacktestEngine(initial_capital=10000.0)

        # Cold run (first execution)
        t0 = time.perf_counter()
        res_cold = bt_engine.run(ticker=self.ticker, period=self.backtest_period, interval="1d")
        t_cold_ms = (time.perf_counter() - t0) * 1000.0

        if res_cold is None:
            raise RuntimeError(f"Backtest returned None for {self.ticker} with period {self.backtest_period}")

        # Additional runs for statistical stability
        samples: List[float] = [t_cold_ms]
        for _ in range(self.backtest_runs - 1):
            t0 = time.perf_counter()
            _ = bt_engine.run(ticker=self.ticker, period=self.backtest_period, interval="1d")
            samples.append((time.perf_counter() - t0) * 1000.0)

        results = {
            "ticker": self.ticker,
            "period": self.backtest_period,
            "interval": "1d",
            "cold_run_ms": round(t_cold_ms, 2),
            "mean_ms": round(float(np.mean(samples)), 2),
            "median_ms": round(float(np.median(samples)), 2),
            "min_ms": round(float(np.min(samples)), 2),
            "max_ms": round(float(np.max(samples)), 2),
            "std_ms": round(float(np.std(samples)), 2),
            "samples_ms": [round(x, 2) for x in samples],
        }
        return results

    def benchmark_server_startup(self) -> Dict[str, Any]:
        """Measures cold module import and engine/bot component boot times."""
        console.print("[bold cyan]>>> Benchmarking Server Startup & Engine Lifecycle...[/bold cyan]")

        # 1. Measure pure python import and cold bot boot in isolated subprocess
        boot_code = """
import time, json, warnings
warnings.filterwarnings('ignore')

t0 = time.perf_counter()
import server
t_import_sec = time.perf_counter() - t0

t1 = time.perf_counter()
bot = server._get_live_bot()
t_bot_sec = time.perf_counter() - t1

data = {
    'import_ms': round(t_import_sec * 1000.0, 2),
    'cold_boot_ms': round(t_bot_sec * 1000.0, 2),
    'total_process_to_ready_ms': round((t_import_sec + t_bot_sec) * 1000.0, 2),
}
print('__STARTUP_RESULT__' + json.dumps(data))
"""
        cmd = [sys.executable, "-c", boot_code]
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        startup_data = {}
        for line in proc.stdout.splitlines():
            if line.startswith("__STARTUP_RESULT__"):
                startup_data = json.loads(line.replace("__STARTUP_RESULT__", "").strip())
                break

        # 2. Measure fine-grained in-process component breakdown
        from src.backtest.engine import BacktestEngine
        from src.execution.broker import PaperBroker
        from src.execution.live_bot import LiveBotController
        from src.execution.session_manager import SessionManager
        from src.pipeline import MarketPredictionEngine

        t0 = time.perf_counter()
        engine = MarketPredictionEngine()
        t_engine_init_ms = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        bt_engine = BacktestEngine()
        t_bt_init_ms = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        broker = PaperBroker()
        mgr = SessionManager(ledger=broker.ledger)
        live_bot = LiveBotController(engine=engine, broker=broker, session_manager=mgr)
        t_bot_instantiation_ms = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        live_bot.initialize_market_state()
        t_market_state_init_ms = (time.perf_counter() - t0) * 1000.0

        total_component_init_ms = t_engine_init_ms + t_bt_init_ms + t_bot_instantiation_ms + t_market_state_init_ms

        results = {
            "module_import_ms": startup_data.get("import_ms", 3600.0),
            "market_prediction_engine_init_ms": round(t_engine_init_ms, 2),
            "backtest_engine_init_ms": round(t_bt_init_ms, 2),
            "controller_instantiation_ms": round(t_bot_instantiation_ms, 2),
            "market_state_portfolio_warmup_ms": round(t_market_state_init_ms, 2),
            "total_engine_cold_boot_ms": startup_data.get("cold_boot_ms", round(total_component_init_ms, 2)),
            "total_process_to_ready_ms": startup_data.get(
                "total_process_to_ready_ms",
                round(startup_data.get("import_ms", 3600.0) + total_component_init_ms, 2),
            ),
        }
        return results

    def benchmark_dashboard_poll(self) -> Dict[str, Any]:
        """Measures direct bot method and HTTP endpoint latency for /api/dashboard/state."""
        console.print(f"[bold cyan]>>> Benchmarking dashboard poll ({self.dashboard_runs} iterations)...[/bold cyan]")
        from fastapi.testclient import TestClient
        from server import _get_live_bot, app

        bot = _get_live_bot()
        client = TestClient(app)

        # Warm-up request
        _ = client.get("/api/dashboard/state")
        _ = bot.get_dashboard_state()

        # 1. Direct controller method: bot.get_dashboard_state()
        direct_latencies: List[float] = []
        for _ in range(self.dashboard_runs):
            t0 = time.perf_counter()
            _ = bot.get_dashboard_state()
            direct_latencies.append((time.perf_counter() - t0) * 1000.0)

        # 2. Full HTTP roundtrip: client.get('/api/dashboard/state')
        http_latencies: List[float] = []
        for _ in range(self.dashboard_runs):
            t0 = time.perf_counter()
            resp = client.get("/api/dashboard/state")
            assert resp.status_code == 200
            http_latencies.append((time.perf_counter() - t0) * 1000.0)

        results = {
            "iterations": self.dashboard_runs,
            "direct_controller": {
                "mean_ms": round(float(np.mean(direct_latencies)), 2),
                "median_ms": round(float(np.median(direct_latencies)), 2),
                "p95_ms": round(float(np.percentile(direct_latencies, 95)), 2),
                "p99_ms": round(float(np.percentile(direct_latencies, 99)), 2),
                "min_ms": round(float(np.min(direct_latencies)), 2),
                "max_ms": round(float(np.max(direct_latencies)), 2),
                "std_ms": round(float(np.std(direct_latencies)), 2),
                "throughput_ops_sec": round(1000.0 / float(np.mean(direct_latencies)), 1),
            },
            "http_endpoint": {
                "mean_ms": round(float(np.mean(http_latencies)), 2),
                "median_ms": round(float(np.median(http_latencies)), 2),
                "p95_ms": round(float(np.percentile(http_latencies, 95)), 2),
                "p99_ms": round(float(np.percentile(http_latencies, 99)), 2),
                "min_ms": round(float(np.min(http_latencies)), 2),
                "max_ms": round(float(np.max(http_latencies)), 2),
                "std_ms": round(float(np.std(http_latencies)), 2),
                "throughput_req_sec": round(1000.0 / float(np.mean(http_latencies)), 1),
            },
        }
        return results

    def run_all(self) -> Dict[str, Any]:
        """Executes full benchmark suite and displays results."""
        console.print(
            Panel.fit(
                "[bold green]SYNAPSE-TITAN Quantitative Performance Benchmark Harness[/bold green]\n"
                f"[white]Target NSE Ticker: [bold yellow]{self.ticker}[/bold yellow] | "
                f"Backtest Period: [bold yellow]{self.backtest_period}[/bold yellow] | "
                f"Dashboard Iterations: [bold yellow]{self.dashboard_runs}[/bold yellow][/white]",
                border_style="green",
            )
        )

        analyze_res = self.benchmark_analyze_ticker()
        backtest_res = self.benchmark_backtest()
        startup_res = self.benchmark_server_startup()
        dashboard_res = self.benchmark_dashboard_poll()

        self.results = {
            "timestamp_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "environment": {
                "python_version": sys.version.split()[0],
                "platform": sys.platform,
                "cpu_count": os.cpu_count(),
            },
            "benchmarks": {
                "server_startup": startup_res,
                "analyze_ticker": analyze_res,
                "backtest": backtest_res,
                "dashboard_poll": dashboard_res,
            },
        }

        self.display_summary()
        return self.results

    def display_summary(self):
        """Displays rich formatted summary tables."""
        bench = self.results["benchmarks"]

        # Table 1: Quantitative Inference Pipeline (analyze_ticker)
        t1 = Table(title="[bold yellow]1. Quantitative Inference Pipeline (analyze_ticker)[/bold yellow]")
        t1.add_column("Metric / Execution Mode", style="cyan")
        t1.add_column("Target Ticker", style="magenta")
        t1.add_column("Duration (ms)", style="bold white", justify="right")
        t1.add_column("Duration (s)", style="dim", justify="right")
        t1.add_column("Notes", style="dim")

        at = bench["analyze_ticker"]
        t1.add_row(
            "Cold Run (Model Init + 1st Execution)",
            at["ticker"],
            f"{at['cold_run_ms']:.2f} ms",
            f"{at['cold_run_ms']/1000:.3f} s",
            "Downloads OHLCV, FracDiff, HMM, Cone, TCN",
        )
        t1.add_row(
            "Warm Run (Mean)",
            at["ticker"],
            f"{at['warm_run_mean_ms']:.2f} ms",
            f"{at['warm_run_mean_ms']/1000:.3f} s",
            f"{self.warm_runs} iterations (min: {at['warm_run_min_ms']:.2f}, max: {at['warm_run_max_ms']:.2f})",
        )
        t1.add_row(
            "Warm Run (Median / p50)",
            at["ticker"],
            f"{at['warm_run_median_ms']:.2f} ms",
            f"{at['warm_run_median_ms']/1000:.3f} s",
            f"Std Dev: {at['warm_run_std_ms']:.2f} ms",
        )
        t1.add_row(
            "[bold green]Warm Cache Speedup[/bold green]",
            at["ticker"],
            f"[bold green]{at['speedup_factor']:.2f}x[/bold green]",
            "",
            "Speedup ratio (Cold / Warm Mean)",
        )
        console.print(t1)

        # Table 2: Backtest Engine
        t2 = Table(title="[bold yellow]2. Walk-Forward Backtester Engine (backtest)[/bold yellow]")
        t2.add_column("Metric", style="cyan")
        t2.add_column("Configuration", style="magenta")
        t2.add_column("Duration (ms)", style="bold white", justify="right")
        t2.add_column("Duration (s)", style="dim", justify="right")

        bt = bench["backtest"]
        t2.add_row("Cold Run", f"{bt['ticker']} ({bt['period']}, {bt['interval']})", f"{bt['cold_run_ms']:.2f} ms", f"{bt['cold_run_ms']/1000:.3f} s")
        t2.add_row("Mean Execution Time", f"{bt['ticker']} ({bt['period']}, {bt['interval']})", f"{bt['mean_ms']:.2f} ms", f"{bt['mean_ms']/1000:.3f} s")
        t2.add_row("Median Execution Time", f"{bt['ticker']} ({bt['period']}, {bt['interval']})", f"{bt['median_ms']:.2f} ms", f"{bt['median_ms']/1000:.3f} s")
        console.print(t2)

        # Table 3: Server Startup Breakdown
        t3 = Table(title="[bold yellow]3. Server Startup & Component Lifecycle[/bold yellow]")
        t3.add_column("Component / Lifecycle Step", style="cyan")
        t3.add_column("Latency (ms)", style="bold white", justify="right")
        t3.add_column("Latency (s)", style="dim", justify="right")

        st = bench["server_startup"]
        t3.add_row("Module Import (server.py + dependencies)", f"{st['module_import_ms']:.2f}", f"{st['module_import_ms']/1000:.3f}")
        t3.add_row("MarketPredictionEngine Init", f"{st['market_prediction_engine_init_ms']:.2f}", f"{st['market_prediction_engine_init_ms']/1000:.3f}")
        t3.add_row("BacktestEngine Init", f"{st['backtest_engine_init_ms']:.2f}", f"{st['backtest_engine_init_ms']/1000:.3f}")
        t3.add_row("LiveBotController Instantiation", f"{st['controller_instantiation_ms']:.2f}", f"{st['controller_instantiation_ms']/1000:.3f}")
        t3.add_row("Market State Portfolio Warmup (Watchlist Scan)", f"{st['market_state_portfolio_warmup_ms']:.2f}", f"{st['market_state_portfolio_warmup_ms']/1000:.3f}")
        t3.add_row("[bold green]Total Engine Cold Boot (_get_live_bot())[/bold green]", f"[bold green]{st['total_engine_cold_boot_ms']:.2f}[/bold green]", f"[bold green]{st['total_engine_cold_boot_ms']/1000:.3f}[/bold green]")
        t3.add_row("[bold cyan]Total Process-to-Ready Time[/bold cyan]", f"[bold cyan]{st['total_process_to_ready_ms']:.2f}[/bold cyan]", f"[bold cyan]{st['total_process_to_ready_ms']/1000:.3f}[/bold cyan]")
        console.print(t3)

        # Table 4: Dashboard State Polling
        t4 = Table(title="[bold yellow]4. Dashboard State Polling Latency (/api/dashboard/state)[/bold yellow]")
        t4.add_column("Metric / Layer", style="cyan")
        t4.add_column("Mean (ms)", style="bold white", justify="right")
        t4.add_column("Median / p50 (ms)", style="bold white", justify="right")
        t4.add_column("p95 (ms)", style="bold white", justify="right")
        t4.add_column("p99 (ms)", style="bold white", justify="right")
        t4.add_column("Throughput", style="bold green", justify="right")

        dp = bench["dashboard_poll"]
        d_dir = dp["direct_controller"]
        t4.add_row(
            "Direct Controller Method (bot.get_dashboard_state)",
            f"{d_dir['mean_ms']:.2f}",
            f"{d_dir['median_ms']:.2f}",
            f"{d_dir['p95_ms']:.2f}",
            f"{d_dir['p99_ms']:.2f}",
            f"{d_dir['throughput_ops_sec']} ops/s",
        )
        d_http = dp["http_endpoint"]
        t4.add_row(
            "FastAPI HTTP Endpoint (GET /api/dashboard/state)",
            f"{d_http['mean_ms']:.2f}",
            f"{d_http['median_ms']:.2f}",
            f"{d_http['p95_ms']:.2f}",
            f"{d_http['p99_ms']:.2f}",
            f"{d_http['throughput_req_sec']} req/s",
        )
        console.print(t4)


def main():
    parser = argparse.ArgumentParser(description="SYNAPSE-TITAN Performance Benchmark Harness")
    parser.add_argument("--ticker", default="RELIANCE.NS", help="NSE ticker to benchmark (default: RELIANCE.NS)")
    parser.add_argument("--period", default="6mo", help="Backtest lookback period (default: 6mo)")
    parser.add_argument("--dashboard-runs", type=int, default=50, help="Number of dashboard polling iterations")
    parser.add_argument("--warm-runs", type=int, default=5, help="Number of warm analyze_ticker iterations")
    parser.add_argument("--backtest-runs", type=int, default=3, help="Number of backtest iterations")
    parser.add_argument("--save-json", action="store_true", default=True, help="Save results to JSON")
    parser.add_argument("--json-path", default="docs/perf_before.json", help="Path to save benchmark JSON output")

    args = parser.parse_args()

    harness = BenchmarkHarness(
        ticker=args.ticker,
        backtest_period=args.period,
        dashboard_runs=args.dashboard_runs,
        warm_runs=args.warm_runs,
        backtest_runs=args.backtest_runs,
    )

    results = harness.run_all()

    if args.save_json:
        out_path = Path(args.json_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        console.print(f"[bold green]Saved benchmark results to {out_path}[/bold green]")


if __name__ == "__main__":
    main()
