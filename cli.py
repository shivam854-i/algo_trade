"""Command Line Interface (CLI) Scanner for TradeBot.

Usage:
    python cli.py --tickers "AAPL,NVDA,RELIANCE.NS,BTC-USD" --period "2y"
"""

import argparse
import sys
import warnings

warnings.filterwarnings("ignore")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.pipeline import MarketPredictionEngine

console = Console(width=120)


def run_cli_scan(tickers: list, period: str = "2y", interval: str = "1d"):
    console.print(
        Panel.fit(
            "[bold cyan]TradeBot: SYNAPSE-TITAN Market Prediction Engine[/bold cyan]\n"
            f"[dim]Scanning {len(tickers)} asset(s) on timeframe: {interval}[/dim]",
            border_style="cyan",
        )
    )

    engine = MarketPredictionEngine()
    analysis = engine.analyze_portfolio(
        tickers, period=period, interval=interval
    )

    if not analysis.single_analyses:
        console.print("[bold red]No valid data returned for given tickers.[/bold red]")
        sys.exit(1)

    table = Table(title="[bold yellow]Multi-Asset Predictive Intelligence[/bold yellow]")
    table.add_column("Ticker", style="bold white", justify="left")
    table.add_column("Price", justify="right")
    table.add_column("Regime", justify="center")
    table.add_column("Decision", justify="center")
    table.add_column("Confidence", justify="right")
    table.add_column("Target ($)", justify="right", style="green")
    table.add_column("Stop ($)", justify="right", style="red")
    table.add_column("HRP Weight", justify="right", style="magenta")
    table.add_column("Auth Size", justify="right", style="bold cyan")

    for ticker, res in analysis.single_analyses.items():
        pred = res.meta_prediction
        regime = res.regime
        hrp_wt = analysis.hrp_portfolio_weights.get(ticker, 0.0)
        auth_size = res.risk_decision.authorized_weight_pct

        # Decision color
        if "STRONG BUY" in pred.direction_label:
            dec_styled = f"[bold green]{pred.direction_label}[/bold green]"
        elif "BUY" in pred.direction_label:
            dec_styled = f"[green]{pred.direction_label}[/green]"
        elif "STRONG SELL" in pred.direction_label:
            dec_styled = f"[bold red]{pred.direction_label}[/bold red]"
        elif "SELL" in pred.direction_label:
            dec_styled = f"[red]{pred.direction_label}[/red]"
        else:
            dec_styled = f"[dim yellow]{pred.direction_label}[/dim yellow]"

        # Regime color
        if regime.is_crisis:
            reg_styled = f"[bold red]{regime.name}[/bold red]"
        elif "Trending" in regime.name:
            reg_styled = f"[cyan]{regime.name}[/cyan]"
        else:
            reg_styled = f"[dim]{regime.name}[/dim]"

        price_prefix = "$" if "USD" in ticker or res.market_jurisdiction == "US" else "INR "
        table.add_row(
            ticker,
            f"{price_prefix}{res.current_price:.2f}",
            reg_styled,
            dec_styled,
            f"{pred.success_probability * 100:.1f}%",
            f"{pred.target_price:.2f}",
            f"{pred.stop_price:.2f}",
            f"{hrp_wt * 100:.1f}%",
            f"{auth_size:.1f}%",
        )

    console.print(table)
    console.print("\n[dim]Analysis complete. Launch the web dashboard via: [bold]streamlit run app.py[/bold][/dim]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TradeBot CLI Scanner")
    parser.add_argument(
        "--tickers",
        type=str,
        default="AAPL,NVDA,RELIANCE.NS,BTC-USD",
        help="Comma-separated ticker list",
    )
    parser.add_argument(
        "--period", type=str, default="2y", help="Lookback window (e.g. 1y, 2y)"
    )
    parser.add_argument(
        "--interval", type=str, default="1d", help="Interval (1d, 1h, 15m)"
    )

    args = parser.parse_args()
    ticker_list = [t.strip() for t in args.tickers.split(",") if t.strip()]
    run_cli_scan(ticker_list, period=args.period, interval=args.interval)
