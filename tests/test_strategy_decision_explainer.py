"""Unit tests for DecisionExplainer (Accepted, Rejected, and 100% Cash Narrative Explanations)."""

import pytest

from src.strategy.decision_explainer import DecisionExplainer, PlainLanguageExplanation
from src.strategy.portfolio_selector import AllocationItem, PortfolioAllocationResult
from src.strategy.trade_evaluator import TradeEvaluationResult
from src.strategy.trade_ranker import RankedOpportunity


class TestDecisionExplainer:
    """Tests for DecisionExplainer plain-language narrative generation."""

    def _make_eval(self, ticker: str, net_ev: float = 1.25, win_prob: float = 0.65, direction: str = "LONG"):
        return TradeEvaluationResult(
            ticker=ticker,
            direction=direction,
            entry_price=150.0,
            target_price=155.0,
            stop_price=147.0,
            raw_win_prob=win_prob,
            epistemic_uncertainty=0.03,
            conservative_win_prob=win_prob - 0.03,
            loss_probability=1.0 - (win_prob - 0.03),
            expected_win_return_pct=3.33,
            expected_loss_return_pct=2.00,
            gap_risk_buffer_pct=0.10,
            round_trip_friction_pct=0.12,
            gross_expectancy_pct=net_ev + 0.12,
            net_expectancy_pct=net_ev,
            min_ev_hurdle_pct=0.20,
            is_positive_ev=(net_ev >= 0.20),
            rejection_reason=None if net_ev >= 0.20 else "NEGATIVE EV",
            payoff_ratio=1.67,
            evaluation_metadata={"annualized_vol": 0.20},
        )

    def _make_opp(self, ticker: str, net_ev: float = 1.25, is_eligible: bool = True, direction: str = "LONG", regime_mult: float = 1.25):
        ev = self._make_eval(ticker, net_ev=net_ev, direction=direction)
        return RankedOpportunity(
            rank=1,
            ticker=ticker,
            direction=direction,
            evaluation=ev,
            risk_adjusted_value=net_ev / 0.20,
            regime_multiplier=regime_mult,
            synergy_boost=1.0,
            composite_score=(net_ev / 0.20) * regime_mult,
            is_eligible=is_eligible and (net_ev >= 0.20) and (regime_mult > 0.0),
            ineligible_reason=None if is_eligible and (net_ev >= 0.20) and (regime_mult > 0.0) else "Vetoed",
            rank_justification="Rank #1 High Net Expectancy",
        )

    def _make_alloc(self, ticker: str, weight: float = 0.15, capital: float = 15_000.0, shares: float = 100.0):
        return AllocationItem(
            ticker=ticker,
            direction="LONG",
            weight=weight,
            weight_pct=weight * 100.0,
            allocated_capital=capital,
            entry_price=150.0,
            shares=shares,
            target_price=155.0,
            stop_price=147.0,
            expected_net_ev_pct=1.25,
            kelly_optimal_f=0.45,
            vol_scalar=1.0,
            dd_scalar=1.0,
            sizing_rationale="Fractional Kelly 15.0%",
        )

    def test_explain_accepted_trade(self):
        """Verifies clear narrative explanation for accepted trade."""
        opp = self._make_opp("NVDA", net_ev=1.25)
        alloc = self._make_alloc("NVDA", weight=0.15, capital=15_000.0, shares=100.0)

        exp = DecisionExplainer.explain_accepted_trade(opp, alloc, currency_symbol="$")
        assert exp.action == "ACCEPTED"
        assert exp.ticker == "NVDA"
        assert "BUY NVDA" in exp.headline
        assert "+1.25%" in exp.headline
        assert "15.0%" in exp.summary
        assert "$15,000.00" in exp.summary
        assert "statutory exchange fees" in exp.summary

        # Check factors
        assert "net_expectancy" in exp.factors
        assert "win_probability" in exp.factors
        assert "statutory_frictions" in exp.factors
        assert "position_sizing" in exp.factors

        # Check metrics
        assert exp.metrics["net_expectancy_pct"] == 1.25
        assert exp.metrics["allocated_capital"] == 15000.0
        assert exp.metrics["shares"] == 100.0

    def test_explain_rejected_trade_negative_ev(self):
        """Verifies explanation for rejected negative EV trade."""
        opp = self._make_opp("BAD_STOCK", net_ev=-0.45, is_eligible=False)
        exp = DecisionExplainer.explain_rejected_trade(opp)

        assert exp.action == "REJECTED"
        assert exp.ticker == "BAD_STOCK"
        assert "REJECTED BAD_STOCK: Negative Net Expectancy" in exp.headline
        assert "-0.45%" in exp.headline
        assert "net mathematical expectancy is negative" in exp.summary

    def test_explain_rejected_trade_crisis_regime(self):
        """Verifies explanation for trade rejected due to Crisis regime."""
        opp = self._make_opp("CRISIS_STOCK", net_ev=1.5, is_eligible=False, regime_mult=0.0)
        opp.ineligible_reason = "HARD VETO: Market regime is State 2 (Crisis) with elevated tail risk"

        exp = DecisionExplainer.explain_rejected_trade(opp)
        assert exp.action == "REJECTED"
        assert "Crisis Regime Quarantine" in exp.headline
        assert "High-Vol Crisis regime" in exp.summary

    def test_explain_rejected_trade_microstructure(self):
        """Verifies explanation for trade rejected due to microstructure circuit breaker."""
        opp = self._make_opp("MICRO_FAIL", net_ev=1.0, is_eligible=False)
        opp.ineligible_reason = "MICROSTRUCTURE VETO: Forex 17:00 EST rollover liquidity trough"

        exp = DecisionExplainer.explain_rejected_trade(opp)
        assert exp.action == "REJECTED"
        assert "Microstructure Circuit Breaker" in exp.headline
        assert "rollover liquidity trough" in exp.summary

    def test_explain_portfolio_cash_fallback(self):
        """Verifies narrative explanation when 100% cash guarantee is triggered."""
        exp = DecisionExplainer.explain_portfolio_cash_fallback(
            total_candidates_evaluated=10,
            rejection_summary="Zero candidate opportunities met positive Net Expectancy hurdle",
            active_regime="Normal",
        )
        assert exp.action == "HELD_IN_CASH"
        assert exp.ticker == "PORTFOLIO"
        assert "100% CASH PRESERVED" in exp.headline
        assert "10 candidate instruments" in exp.summary
        assert exp.metrics["cash_weight_pct"] == 100.0
        assert exp.metrics["qualifying_count"] == 0

    def test_explain_allocation_result_comprehensive(self):
        """Verifies explanation generator translates entire PortfolioAllocationResult."""
        opp_good = self._make_opp("GOOD", net_ev=1.5, is_eligible=True)
        opp_bad = self._make_opp("BAD", net_ev=-0.2, is_eligible=False)
        alloc_good = self._make_alloc("GOOD", weight=0.15)

        # 1. Partial allocation
        res_mixed = PortfolioAllocationResult(
            weights={"GOOD": 0.15, "CASH": 0.85},
            cash_weight=0.85,
            allocated_capital={"GOOD": 15000.0},
            shares={"GOOD": 100.0},
            is_100_percent_cash=False,
            method="KELLY",
            allocations=[alloc_good],
            total_virtual_equity=100000.0,
            total_allocated_capital=15000.0,
            residual_cash_capital=85000.0,
            explanation="Allocated 1 position via Fractional Kelly.",
        )

        exps_mixed = DecisionExplainer.explain_allocation_result(res_mixed, [opp_good, opp_bad])
        assert len(exps_mixed) == 2
        assert exps_mixed[0].action == "ACCEPTED"
        assert exps_mixed[0].ticker == "GOOD"
        assert exps_mixed[1].action == "REJECTED"
        assert exps_mixed[1].ticker == "BAD"

        # 2. 100% Cash fallback
        res_cash = PortfolioAllocationResult(
            weights={"CASH": 1.0},
            cash_weight=1.0,
            allocated_capital={},
            shares={},
            is_100_percent_cash=True,
            method="KELLY",
            allocations=[],
            total_virtual_equity=100000.0,
            total_allocated_capital=0.0,
            residual_cash_capital=100000.0,
            explanation="100% Cash Allocation: Zero candidate opportunities met positive Net Expectancy hurdle",
        )
        exps_cash = DecisionExplainer.explain_allocation_result(res_cash, [opp_bad])
        assert len(exps_cash) == 1
        assert exps_cash[0].action == "HELD_IN_CASH"
        assert exps_cash[0].ticker == "PORTFOLIO"

    def test_serialization(self):
        """Verifies PlainLanguageExplanation dictionary serialization."""
        opp = self._make_opp("AAPL")
        alloc = self._make_alloc("AAPL")
        exp = DecisionExplainer.explain_accepted_trade(opp, alloc)
        d = exp.to_dict()
        assert d["ticker"] == "AAPL"
        assert d["action"] == "ACCEPTED"
        assert "headline" in d
        assert "factors" in d
        assert "metrics" in d
