"""End-to-End Simulated Money Paper-Trading Test & Portfolio Seeder."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.execution.broker import PaperBroker
from src.pipeline import MarketPredictionEngine


def run_simulated_session():
    engine = MarketPredictionEngine()
    broker = PaperBroker()

    # 1. Reset simulated account to $100,000.00
    broker.reset_account(initial_capital=100000.0)
    print("[SIM 1] Initialized Simulated Account:", broker.get_account_summary())

    # 2. Analyze Global Macro Multi-Asset Watchlist on RTX 4060
    tickers = ["GC=F", "EURUSD=X", "NVDA", "BTC-USD"]
    portfolio = engine.analyze_portfolio(tickers, period="1y", interval="1d")

    # 3. Deploy simulated positions across watchlist
    for tk, res in portfolio.single_analyses.items():
        pred = res.meta_prediction
        hrp_w = portfolio.hrp_portfolio_weights.get(tk, 0.20)
        alloc_pct = max(res.risk_decision.authorized_weight_pct, round(hrp_w * 35.0, 1), 8.0)
        alloc_pct = min(alloc_pct, 18.0)
        direction = "LONG" if pred.primary_direction >= 0 else "SHORT"
        pos = broker.open_position(
            ticker=tk,
            direction=direction,
            current_price=res.current_price,
            target_price=pred.target_price,
            stop_price=pred.stop_price,
            allocation_weight_pct=alloc_pct,
        )
        print(
            f"[SIM 2] Opened {pos.direction} on {tk} | Entry: {pos.entry_price:.4f} | "
            f"Target: {pos.target_price:.4f} | Stop: {pos.stop_price:.4f} | Alloc: ${pos.allocated_capital:,.2f}"
        )

    # 4. Simulate forward market step (Gold hits Profit Target, others accrue MTM Unrealized PnL)
    open_pos = broker.get_open_positions()
    step1_prices = {}
    for p in open_pos:
        if p.ticker == "GC=F":
            step1_prices[p.ticker] = p.target_price * (1.002 if p.direction == "LONG" else 0.998)
        elif p.ticker == "NVDA":
            step1_prices[p.ticker] = p.entry_price * (1.018 if p.direction == "LONG" else 0.982)
        elif p.ticker == "EURUSD=X":
            step1_prices[p.ticker] = p.entry_price * (1.004 if p.direction == "LONG" else 0.996)
        else:
            step1_prices[p.ticker] = p.entry_price * (1.012 if p.direction == "LONG" else 0.988)

    still_open, auto_closed = broker.update_and_audit_positions(step1_prices)
    print(f"\n[SIM 3] Auto-Closed Trades on Barrier Hit: {len(auto_closed)}")
    for tr in auto_closed:
        print(
            f"   -> CLOSED #{tr.id} {tr.ticker} ({tr.direction}) @ {tr.exit_price:.4f} | "
            f"Net PnL: ${tr.net_pnl:+,.2f} ({tr.return_pct:+.2f}%) | Fee: ${tr.friction_fee:.2f} | Reason: {tr.exit_reason}"
        )

    print("\n[SIM 4] Active Open Positions MTM:")
    for p in still_open:
        print(
            f"   -> OPEN #{p.id} {p.ticker} ({p.direction}) | Entry: {p.entry_price:.4f} -> Now: {p.current_price:.4f} | "
            f"Unrealized: ${p.unrealized_pnl:+,.2f} ({p.unrealized_return_pct:+.2f}%)"
        )

    print("\n[SIM 5] Final Simulated Account Summary:", broker.get_account_summary())


if __name__ == "__main__":
    run_simulated_session()
