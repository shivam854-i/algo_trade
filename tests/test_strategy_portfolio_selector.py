"""Unit tests for PortfolioSelector (Fractional Kelly, 20% Cap, HRP, 100% Cash Guarantee, Capital Invariant)."""

import numpy as np
import pandas as pd
import pytest

from src.strategy.portfolio_selector import (
    AllocationItem,
    PortfolioAllocationResult,
    PortfolioSelector,
)
from src.strategy.trade_evaluator import TradeEvaluationResult
from src.strategy.trade_ranker import RankedOpportunity


class TestPortfolioSelector:
    """Comprehensive tests for portfolio sizing, capital allocation, and 100% Cash Guarantee."""

    def _make_opp(
        self,
        ticker: str,
        net_ev: float = 1.0,
        win_prob: float = 0.60,
        vol: float = 0.20,
        entry: float = 100.0,
        target: float = 103.0,
        stop: float = 98.5,
        is_eligible: bool = True,
    ) -> RankedOpportunity:
        ev = TradeEvaluationResult(
            ticker=ticker,
            direction="LONG",
            entry_price=entry,
            target_price=target,
            stop_price=stop,
            raw_win_prob=win_prob,
            epistemic_uncertainty=0.03,
            conservative_win_prob=win_prob - 0.03,
            loss_probability=1.0 - (win_prob - 0.03),
            expected_win_return_pct=3.0,
            expected_loss_return_pct=1.5,
            gap_risk_buffer_pct=0.1,
            round_trip_friction_pct=0.15,
            gross_expectancy_pct=net_ev + 0.15,
            net_expectancy_pct=net_ev,
            min_ev_hurdle_pct=0.20,
            is_positive_ev=(net_ev >= 0.20),
            rejection_reason=None if (net_ev >= 0.20 and is_eligible) else "NEGATIVE EV",
            payoff_ratio=2.0,
            evaluation_metadata={"annualized_vol": vol},
        )
        return RankedOpportunity(
            rank=1,
            ticker=ticker,
            direction="LONG",
            evaluation=ev,
            risk_adjusted_value=net_ev / vol,
            regime_multiplier=1.25 if is_eligible else 0.0,
            synergy_boost=1.0,
            composite_score=net_ev / vol * (1.25 if is_eligible else 0.0),
            is_eligible=is_eligible and (net_ev >= 0.20),
            ineligible_reason=None if (is_eligible and net_ev >= 0.20) else "Ineligible",
            rank_justification="Rank #1",
        )

    def test_mandatory_100_percent_cash_allocation_when_zero_positive_ev_trades(self):
        """Verifies: MANDATORY 100% Cash Guarantee returns weights={'CASH': 1.0}, cash_weight=1.0, is_100_percent_cash=True."""
        selector = PortfolioSelector()

        # 1. Empty opportunity list
        res_empty = selector.allocate([], total_virtual_equity=100_000.0)
        assert res_empty.is_100_percent_cash is True
        assert res_empty.cash_weight == 1.0
        assert res_empty.weights == {"CASH": 1.0}
        assert res_empty.allocated_capital == {}
        assert res_empty.shares == {}
        assert res_empty.allocations == []
        assert res_empty.total_allocated_capital == 0.0
        assert res_empty.residual_cash_capital == 100_000.0
        assert "Zero candidate opportunities" in res_empty.explanation

        # 2. Opportunities all have negative or sub-hurdle EV
        opp_neg = self._make_opp("BAD_1", net_ev=-0.50, is_eligible=False)
        opp_sub = self._make_opp("BAD_2", net_ev=0.10, is_eligible=False)
        res_neg = selector.allocate([opp_neg, opp_sub], total_virtual_equity=50_000.0)
        assert res_neg.is_100_percent_cash is True
        assert res_neg.cash_weight == 1.0
        assert res_neg.weights == {"CASH": 1.0}
        assert res_neg.total_allocated_capital == 0.0

    def test_mandatory_100_percent_cash_allocation_under_drawdown_kill(self):
        """Verifies: Drawdown >= 15% freezes 100% in cash even with positive EV opportunities."""
        selector = PortfolioSelector(max_kill_drawdown=0.15)
        good_opp = self._make_opp("AAPL", net_ev=1.5, is_eligible=True)

        res_kill = selector.allocate(
            [good_opp],
            total_virtual_equity=100_000.0,
            current_drawdown=0.16,  # 16% > 15% kill threshold
        )
        assert res_kill.is_100_percent_cash is True
        assert res_kill.cash_weight == 1.0
        assert "kill limit" in res_kill.explanation

    def test_fractional_kelly_sizing_and_single_position_20_percent_cap(self):
        """Verifies: Fractional Kelly sizes edge properly and strictly caps single positions at 20%."""
        selector = PortfolioSelector(max_position_cap=0.20, kelly_fraction=0.30)
        # Even with massive edge (win prob 90%, win 10%, loss 1%), position must be capped at 20%
        super_opp = self._make_opp("SUPER", net_ev=8.0, win_prob=0.90, vol=0.10)
        normal_opp = self._make_opp("NORMAL", net_ev=0.8, win_prob=0.55, vol=0.25)

        res = selector.allocate(
            [super_opp, normal_opp],
            total_virtual_equity=100_000.0,
            method="KELLY",
        )
        assert not res.is_100_percent_cash
        assert len(res.allocations) >= 1

        # Check single position 20% ceiling
        super_alloc = next(a for a in res.allocations if a.ticker == "SUPER")
        assert super_alloc.weight <= 0.20
        assert res.weights["SUPER"] <= 0.20
        assert super_alloc.allocated_capital <= 20_000.0

        # Cash weight should balance the unallocated portfolio
        total_equity_weight = sum(res.weights[t] for t in res.allocated_capital)
        assert abs((total_equity_weight + res.cash_weight) - 1.0) < 1e-3

    def test_dynamic_capital_scaling_invariant(self):
        """Verifies: Predictions remain decoupled from account size while dollars and shares scale linearly with virtual capital."""
        selector = PortfolioSelector()
        opp1 = self._make_opp("AAPL", net_ev=1.2, win_prob=0.62, entry=150.0)
        opp2 = self._make_opp("MSFT", net_ev=0.9, win_prob=0.58, entry=300.0)

        # Baseline: $10,000 capital
        res_small = selector.allocate([opp1, opp2], total_virtual_equity=10_000.0, method="KELLY")
        # Scaled: $100,000 capital (10x)
        res_large = selector.allocate([opp1, opp2], total_virtual_equity=100_000.0, method="KELLY")

        # 1. Weights must be identical
        for ticker in ["AAPL", "MSFT"]:
            assert res_small.weights[ticker] == res_large.weights[ticker]
        assert res_small.cash_weight == res_large.cash_weight

        # 2. Capital and shares must scale by factor of 10.0x (allowing float rounding)
        for ticker in ["AAPL", "MSFT"]:
            assert abs(res_large.allocated_capital[ticker] - (res_small.allocated_capital[ticker] * 10.0)) < 1.0
            assert abs(res_large.shares[ticker] - (res_small.shares[ticker] * 10.0)) < 0.1

        # 3. Model prediction outputs (win prob, target, stop, net EV) are completely unchanged
        assert opp1.evaluation.net_expectancy_pct == 1.2
        assert opp1.evaluation.raw_win_prob == 0.62

    def test_hrp_allocation_mode_and_iterative_capping(self):
        """Verifies: Marchenko-Pastur RMT de-noised HRP allocates with 20% cap."""
        selector = PortfolioSelector(max_position_cap=0.20)
        opps = [
            self._make_opp("A", net_ev=1.0),
            self._make_opp("B", net_ev=0.9),
            self._make_opp("C", net_ev=0.8),
            self._make_opp("D", net_ev=0.7),
        ]

        np.random.seed(42)
        dates = pd.date_range("2025-01-01", periods=60)
        returns = pd.DataFrame(
            np.random.normal(0.001, 0.02, (60, 4)),
            index=dates,
            columns=["A", "B", "C", "D"],
        )

        res_hrp = selector.allocate(opps, total_virtual_equity=100_000.0, method="HRP", returns_df=returns)
        assert not res_hrp.is_100_percent_cash
        assert res_hrp.method == "HRP"
        assert len(res_hrp.allocations) == 4

        # Verify all positions capped at 20%
        for alloc in res_hrp.allocations:
            assert alloc.weight <= 0.2001
            assert alloc.allocated_capital <= 20_000.0 + 1.0

    def test_integer_shares_in_nse_market(self):
        """Verifies integer shares rounding for Indian NSE Cash market."""
        selector = PortfolioSelector()
        opp_nse = self._make_opp("RELIANCE.NS", net_ev=1.5, entry=2500.0)

        res_nse = selector.allocate(
            [opp_nse],
            total_virtual_equity=100_000.0,
            market_type="INDIAN_NSE",
        )
        assert not res_nse.is_100_percent_cash
        shares = res_nse.shares["RELIANCE.NS"]
        assert float(shares).is_integer()
        assert shares > 0

    def test_small_capital_insufficient_for_single_share_falls_to_cash(self):
        """Verifies that if allocated capital < 1 share price in integer market, 100% cash is held."""
        selector = PortfolioSelector()
        # Expensive stock at 50,000 with 1,000 total capital
        opp_pricey = self._make_opp("MRF.NS", net_ev=1.5, entry=150_000.0)

        res = selector.allocate(
            [opp_pricey],
            total_virtual_equity=1_000.0,  # Cannot afford even 1 share of ₹150,000
            market_type="INDIAN_NSE",
        )
        assert res.is_100_percent_cash is True
        assert res.cash_weight == 1.0
        assert "insufficient to buy minimum unit shares" in res.explanation

    def test_invalid_virtual_equity_raises_value_error(self):
        """Verifies zero or negative capital raises ValueError."""
        selector = PortfolioSelector()
        with pytest.raises(ValueError, match="Total virtual equity must be positive"):
            selector.allocate([], total_virtual_equity=0.0)

        with pytest.raises(ValueError, match="Total virtual equity must be positive"):
            selector.allocate([], total_virtual_equity=-1000.0)

    def test_serialization(self):
        """Verifies PortfolioAllocationResult dictionary serialization."""
        selector = PortfolioSelector()
        res = selector.allocate([], total_virtual_equity=10_000.0)
        d = res.to_dict()
        assert d["is_100_percent_cash"] is True
        assert d["total_virtual_equity"] == 10000.0
        assert "weights" in d
