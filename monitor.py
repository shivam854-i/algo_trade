"""CLI entry point for running the background market observer daemon.

Examples:
    # Run a single immediate scan of standard universe:
    python monitor.py --once

    # Run continuous observer daemon checking every 5 minutes:
    python monitor.py --interval 300

    # Custom universe and confidence threshold:
    python monitor.py --universe "GC=F,EURUSD=X,NVDA,BTC-USD" --min-prob 0.55
"""

import argparse
import sys

from src.observer.monitor import MarketObserverDaemon


def main():
    parser = argparse.ArgumentParser(
        description="SYNAPSE-TITAN Background Market Observer & Alert Dispatcher"
    )
    parser.add_argument(
        "--universe",
        type=str,
        default="GC=F,EURUSD=X,NVDA,AAPL,RELIANCE.NS,BTC-USD",
        help="Comma-separated list of symbols to monitor",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=900,
        help="Polling cycle interval in seconds (default: 900s = 15m)",
    )
    parser.add_argument(
        "--min-prob",
        type=float,
        default=0.55,
        help="Minimum calibrated probability to fire an alert (default: 0.55)",
    )
    parser.add_argument(
        "--period",
        type=str,
        default="1y",
        help="Historical lookback window (default: 1y)",
    )
    parser.add_argument(
        "--data-interval",
        type=str,
        default="1d",
        help="Bar resolution (default: 1d)",
    )
    parser.add_argument(
        "--discord-webhook",
        type=str,
        default=None,
        help="Optional Discord webhook URL for notifications",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan cycle and exit immediately (useful for cron jobs)",
    )
    parser.add_argument(
        "--auto-trade",
        action="store_true",
        help="Automatically execute paper orders in the live ledger when actionable signals fire",
    )

    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.universe.split(",") if s.strip()]

    daemon = MarketObserverDaemon(
        universe=symbols,
        poll_interval_seconds=args.interval,
        min_probability=args.min_prob,
        data_period=args.period,
        data_interval=args.data_interval,
        discord_webhook=args.discord_webhook,
        auto_trade=args.auto_trade,
    )

    if args.once:
        daemon.scan_once()
    else:
        daemon.run_forever()


if __name__ == "__main__":
    main()
