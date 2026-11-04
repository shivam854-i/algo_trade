"""Real-time Multi-Asset Market Observer Daemon & Signal Dispatcher.

Continuously monitors Equities, Forex, Commodities, and Crypto universes,
evaluating structural market regimes, fractional stationarity, and meta-labeling.
Dispatches instant actionable alerts via Windows Desktop Toasts, Discord/Telegram webhooks,
and persistent event logs.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Dict, List, Optional
import urllib.request

try:
    if sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from rich.console import Console
from rich.table import Table

from src.execution.broker import PaperBroker
from src.pipeline import MarketPredictionEngine, SingleAssetAnalysis

logger = logging.getLogger(__name__)
console = Console(force_terminal=True)


@dataclass
class AlertRecord:
    timestamp: str
    ticker: str
    signal: str
    probability: float
    current_price: float
    target_price: float
    stop_price: float
    regime: str
    net_alpha_pct: float
    friction_cost_pct: float
    authorized_weight_pct: float
    jurisdiction: str
    currency_symbol: str


class AlertDispatcher:
    """Dispatches real-time alerts to Desktop Toasts, Webhooks, and Disk Storage."""

    def __init__(
        self,
        alert_dir: Path,
        discord_webhook_url: Optional[str] = None,
        telegram_bot_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
    ):
        self.alert_dir = alert_dir
        self.alert_dir.mkdir(parents=True, exist_ok=True)
        self.alerts_file = self.alert_dir / "alerts.json"
        self.discord_webhook = discord_webhook_url
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id

    def persist_alert(self, alert: AlertRecord):
        """Appends alert to local JSON database."""
        existing = []
        if self.alerts_file.exists():
            try:
                with open(self.alerts_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        existing.insert(0, asdict(alert))
        # Keep latest 500 alerts
        existing = existing[:500]

        with open(self.alerts_file, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)

    def send_windows_toast(self, alert: AlertRecord):
        """Sends a native Windows notification banner."""
        title = f"SYNAPSE-TITAN: {alert.signal} {alert.ticker}"
        body = (
            f"Price: {alert.currency_symbol}{alert.current_price:.2f} | "
            f"Target: {alert.currency_symbol}{alert.target_price:.2f} | "
            f"Conf: {alert.probability * 100:.1f}% | Net Alpha: +{alert.net_alpha_pct:.2f}%"
        )
        ps_cmd = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $textNodes = $template.GetElementsByTagName('text')
        $textNodes.Item(0).AppendChild($template.CreateTextNode('{title}')) > $null
        $textNodes.Item(1).AppendChild($template.CreateTextNode('{body}')) > $null
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('TradeBot.SYNAPSE')
        $notification = [Windows.UI.Notifications.ToastNotification]::new($template)
        $notifier.Show($notification)
        """
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                timeout=5,
            )
        except Exception as e:
            logger.debug(f"Toast notification skipped or unavailable: {e}")

    def send_discord(self, alert: AlertRecord):
        """Dispatches rich embed to Discord webhook."""
        if not self.discord_webhook:
            return

        is_buy = "BUY" in alert.signal
        color = 0x2ECC71 if is_buy else 0xE74C3C

        payload = {
            "username": "SYNAPSE-TITAN Engine",
            "embeds": [
                {
                    "title": f"🚨 Market Signal: {alert.signal} on {alert.ticker}",
                    "color": color,
                    "fields": [
                        {"name": "Current Price", "value": f"{alert.currency_symbol}{alert.current_price:.2f}", "inline": True},
                        {"name": "Profit Target", "value": f"{alert.currency_symbol}{alert.target_price:.2f}", "inline": True},
                        {"name": "Stop Loss", "value": f"{alert.currency_symbol}{alert.stop_price:.2f}", "inline": True},
                        {"name": "Confidence", "value": f"{alert.probability * 100:.1f}%", "inline": True},
                        {"name": "Net Expected Alpha", "value": f"+{alert.net_alpha_pct:.2f}%", "inline": True},
                        {"name": "Kelly Allocation", "value": f"{alert.authorized_weight_pct:.1f}%", "inline": True},
                        {"name": "Market Regime", "value": alert.regime, "inline": False},
                    ],
                    "footer": {"text": f"Timestamp: {alert.timestamp} | Jurisdiction: {alert.jurisdiction}"},
                }
            ],
        }

        try:
            req = urllib.request.Request(
                self.discord_webhook,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            logger.warning(f"Discord webhook dispatch failed: {e}")

    def dispatch(self, alert: AlertRecord):
        """Persists to disk and sends out all enabled notifications."""
        self.persist_alert(alert)
        self.send_windows_toast(alert)
        self.send_discord(alert)


class MarketObserverDaemon:
    """Continuously observes market tickers, runs analytics, and triggers alerts."""

    def __init__(
        self,
        universe: Optional[List[str]] = None,
        poll_interval_seconds: int = 900,  # 15 minutes default
        min_probability: float = 0.60,
        data_period: str = "1y",
        data_interval: str = "1d",
        discord_webhook: Optional[str] = None,
        auto_trade: bool = False,
    ):
        self.universe = universe or [
            "GC=F",          # Gold Commodities
            "EURUSD=X",     # Forex FX
            "NVDA",          # US AI Equities
            "AAPL",          # US Tech
            "RELIANCE.NS",   # Indian NSE
            "BTC-USD",       # Crypto
        ]
        self.poll_interval = poll_interval_seconds
        self.min_prob = min_probability
        self.period = data_period
        self.interval = data_interval
        self.auto_trade = auto_trade
        self.broker = PaperBroker() if auto_trade else None

        self.engine = MarketPredictionEngine()
        alert_dir = Path("data/alerts")
        self.dispatcher = AlertDispatcher(
            alert_dir=alert_dir, discord_webhook_url=discord_webhook
        )

    def scan_once(self) -> List[AlertRecord]:
        """Performs a single complete scan across the monitored universe."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        console.rule(f"[bold cyan]SYNAPSE-TITAN Observation Scan | {now_str}")

        scan_table = Table(
            title=f"Monitored Universe Health & Signals ({len(self.universe)} Assets)",
            header_style="bold magenta",
        )
        scan_table.add_column("Ticker", style="bold white", width=12)
        scan_table.add_column("Price", justify="right", width=11)
        scan_table.add_column("Regime", style="cyan", width=18)
        scan_table.add_column("Signal", width=14)
        scan_table.add_column("Conf %", justify="right", width=9)
        scan_table.add_column("Target Price", justify="right", width=12)
        scan_table.add_column("Stop Price", justify="right", width=12)
        scan_table.add_column("Net Alpha", justify="right", width=10)
        scan_table.add_column("Kelly %", justify="right", width=9)

        new_alerts = []

        for ticker in self.universe:
            ticker = ticker.strip()
            try:
                res = self.engine.analyze_ticker(
                    ticker, period=self.period, interval=self.interval
                )
                pred = res.meta_prediction
                regime = res.regime

                # Currency symbol
                jur = res.market_jurisdiction
                sym = "INR " if jur == "NSE_CASH" else ("" if jur == "FOREX" else "$")

                # Signal style
                sig_style = (
                    "[bold green]"
                    if "BUY" in pred.direction_label
                    else ("[bold red]" if "SELL" in pred.direction_label else "[dim]")
                )
                formatted_sig = f"{sig_style}{pred.direction_label}[/]"

                kelly_pct = res.risk_decision.authorized_weight_pct
                net_alpha = res.net_expected_alpha_pct

                scan_table.add_row(
                    ticker,
                    f"{sym}{res.current_price:,.2f}",
                    regime.name,
                    formatted_sig,
                    f"{pred.success_probability * 100:.1f}%",
                    f"{sym}{pred.target_price:,.2f}",
                    f"{sym}{pred.stop_price:,.2f}",
                    f"{'+' if net_alpha > 0 else ''}{net_alpha:.2f}%",
                    f"{kelly_pct:.1f}%",
                )

                # Check Alert Conditions:
                # 1. Actionable direction (BUY / SELL)
                # 2. Probability meets or exceeds threshold
                # 3. Clears transaction friction hurdle
                # 4. Sizing authorized by guardrail
                is_actionable = pred.direction_label in [
                    "STRONG BUY",
                    "BUY",
                    "STRONG SELL",
                    "SELL",
                ]
                if (
                    is_actionable
                    and pred.success_probability >= self.min_prob
                    and res.friction_hurdle_passes
                    and res.risk_decision.authorized
                ):
                    alert = AlertRecord(
                        timestamp=now_str,
                        ticker=ticker,
                        signal=pred.direction_label,
                        probability=pred.success_probability,
                        current_price=round(res.current_price, 2),
                        target_price=round(pred.target_price, 2),
                        stop_price=round(pred.stop_price, 2),
                        regime=regime.name,
                        net_alpha_pct=round(net_alpha, 2),
                        friction_cost_pct=round(res.friction_cost_pct, 2),
                        authorized_weight_pct=round(kelly_pct, 1),
                        jurisdiction=jur,
                        currency_symbol=sym,
                    )
                    new_alerts.append(alert)
                    self.dispatcher.dispatch(alert)

                    # Automated broker order routing if enabled
                    if self.broker and is_actionable:
                        trade_dir = "LONG" if "BUY" in pred.direction_label else "SHORT"
                        self.broker.open_position(
                            ticker=ticker,
                            direction=trade_dir,
                            current_price=res.current_price,
                            target_price=pred.target_price,
                            stop_price=pred.stop_price,
                            allocation_weight_pct=kelly_pct or 10.0,
                        )

            except Exception as e:
                logger.error(f"Error scanning {ticker}: {e}")
                scan_table.add_row(ticker, "ERROR", "-", str(e)[:25], "-", "-", "-", "-", "-")

        console.print(scan_table)

        if new_alerts:
            console.print(
                f"[bold green][ALERT] {len(new_alerts)} Actionable Market Signal(s) Dispatched & Logged![/]"
            )
        else:
            console.print(
                "[dim yellow][INFO] All monitored assets evaluated. No signals currently clearing the hurdle.[/]"
            )

        return new_alerts

    def run_forever(self):
        """Runs the observer daemon indefinitely on scheduled intervals."""
        console.print(
            f"[bold green][*] SYNAPSE-TITAN Background Daemon Started![/]\n"
            f"Universe: {', '.join(self.universe)}\n"
            f"Cycle Interval: {self.poll_interval}s ({self.poll_interval / 60:.1f} mins)\n"
            f"Press Ctrl+C to terminate gracefully."
        )

        try:
            while True:
                self.scan_once()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            console.print("\n[bold red][STOP] Observer Daemon shutdown requested. Exiting cleanly.[/]")
