"""Institutional Walk-Forward Backtester CLI.

Usage:
    python backtest.py --ticker "GC=F" --period "2y"
    python backtest.py --ticker "NVDA" --period "2y" --capital 25000
    python backtest.py --ticker "EURUSD=X" --period "1y"
"""

import argparse
import warnings

warnings.filterwarnings("ignore")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.backtest.engine import BacktestEngine

console = Console(width=120)


def run_backtest_cli(
    ticker: str,
    period: str = "2y",
    interval: str = "1d",
    capital: float = 10000.0,
):
    console.print(
        Panel.fit(
            f"[bold cyan]TradeBot Walk-Forward Backtester[/bold cyan]\n"
            f"[white]Asset: [bold yellow]{ticker}[/bold yellow] | Period: {period} | Interval: {interval} | Capital: ${capital:,.2f}[/white]",
            border_style="cyan",
        )
    )

    engine = BacktestEngine(initial_capital=capital)
    with console.status(f"[bold green]Executing walk-forward simulation for {ticker}...[/bold green]"):
        result = engine.run(ticker=ticker, period=period, interval=interval)

    if result is None:
        console.print(f"[bold red]Backtest failed or insufficient data points for {ticker}.[/bold red]")
        return

    # 1. Executive Performance Metrics Table
    summary_table = Table(title=f"[bold]Executive Performance Summary: {ticker}[/bold]")
    summary_table.add_column("Performance Metric", style="cyan", justify="left")
    summary_table.add_column("Strategy Value", style="bold white", justify="right")
    summary_table.add_column("Benchmark / Target", style="dim", justify="right")

    # Colors
    ret_color = "bold green" if result.total_return_pct > 0 else "bold red"
    bnh_color = "green" if result.buy_hold_return_pct > 0 else "red"

    summary_table.add_row(
        "Total Net Return",
        f"[{ret_color}]{result.total_return_pct:+.2f}%[/{ret_color}]",
        f"[{bnh_color}]Buy & Hold: {result.buy_hold_return_pct:+.2f}%[/{bnh_color}]",
    )
    summary_table.add_row(
        "Final Portfolio Equity",
        f"${result.final_equity:,.2f}",
        f"Starting: ${result.initial_capital:,.2f}",
    )
    summary_table.add_row(
        "Annualized Return (CAGR)",
        f"{result.cagr_pct:+.2f}%",
        "-",
    )
    summary_table.add_row(
        "Annualized Sharpe Ratio",
        f"[bold]{result.sharpe_ratio:.2f}[/bold]",
        "Target: > 1.50",
    )
    summary_table.add_row(
        "Sortino Ratio (Downside Risk)",
        f"{result.sortino_ratio:.2f}",
        "Target: > 2.00",
    )
    summary_table.add_row(
        "Maximum Peak-to-Trough Drawdown",
        f"[bold red]{result.max_drawdown_pct:.2f}%[/bold red]",
        "Limit: < 15.00%",
    )
    summary_table.add_row(
        "Calmar Ratio (CAGR / Max DD)",
        f"{result.calmar_ratio:.2f}",
        "Target: > 1.00",
    )
    summary_table.add_row(
        "Strategy Win Rate",
        f"[bold green]{result.win_rate_pct:.1f}%[/bold green]",
        f"Wins: {result.winning_trades} | Losses: {result.losing_trades}",
    )
    summary_table.add_row(
        "Profit Factor",
        f"{result.profit_factor:.2f}",
        "Target: > 1.40",
    )
    summary_table.add_row(
        "Total Completed Trades",
        str(result.total_trades),
        f"Avg Ret/Trade: {result.avg_trade_return_pct:+.2f}%",
    )
    summary_table.add_row(
        "Deflated Sharpe Ratio (DSR)",
        f"[bold magenta]{result.deflated_sharpe:.1%}[/bold magenta]",
        "Anti-Overfit: >= 95.0%",
    )

    console.print(summary_table)

    # 2. Recent Completed Trades Table
    if result.trades:
        trades_table = Table(title="[bold yellow]Recent Completed Trades (Sample)[/bold yellow]")
        trades_table.add_column("Entry Date", justify="center")
        trades_table.add_column("Exit Date", justify="center")
        trades_table.add_column("Type", justify="center")
        trades_table.add_column("Entry Price", justify="right")
        trades_table.add_column("Exit Price", justify="right")
        trades_table.add_column("Return %", justify="right")
        trades_table.add_column("Net P&L ($)", justify="right")
        trades_table.add_column("Exit Reason", justify="left")

        # Show up to last 10 trades
        sample_trades = result.trades[-10:]
        for tr in sample_trades:
            pnl_color = "green" if tr.net_pnl > 0 else "red"
            trades_table.add_row(
                str(tr.entry_date.strftime("%Y-%m-%d")),
                str(tr.exit_date.strftime("%Y-%m-%d")),
                f"[bold cyan]{tr.direction}[/bold cyan]",
                f"{tr.entry_price:.2f}",
                f"{tr.exit_price:.2f}",
                f"[{pnl_color}]{tr.return_pct:+.2f}%[/{pnl_color}]",
                f"[{pnl_color}]${tr.net_pnl:+,.2f}[/{pnl_color}]",
                tr.exit_reason.replace("_", " ").title(),
            )
        console.print(trades_table)

    console.print("\n[dim]To view interactive equity charts and trade logs in browser, run: [bold]streamlit run app.py[/bold][/dim]\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TradeBot Walk-Forward Backtester")
    parser.add_argument("--ticker", type=str, default="GC=F", help="Ticker symbol (e.g. GC=F, NVDA, AAPL)")
    parser.add_argument("--period", type=str, default="2y", help="Historical window (1y, 2y, 5y)")
    parser.add_argument("--interval", type=str, default="1d", help="Bar interval (1d, 1h)")
    parser.add_argument("--capital", type=float, default=10000.0, help="Initial simulation capital")

    args = parser.parse_args()
    run_backtest_cli(
        ticker=args.ticker,
        period=args.period,
        interval=args.interval,
        capital=args.capital,
    )
