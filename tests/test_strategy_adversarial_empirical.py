"""Adversarial Empirical Stress-Testing Harness for Quantitative Strategy Engine (Milestone 1).

Authored by Empirical Strategy Challenger 1 (teamwork_challenger).
Rigorously stress-tests and challenges the quantitative modules in `src/strategy/`:
1. TradeEvaluator:
   - Adversarial probability & barrier geometry (inverted barriers, zero prob, extreme quantile spreads).
   - Strict mathematical monotonicity wrt win probability and payoff odds.
   - Absolute rejection invariant: EV <= 0 or EV < hurdle (+0.20%) ALWAYS rejected.
2. PortfolioSelector:
   - 100% Cash Allocation Guarantee under 0 qualifying opportunities.
   - Drawdown kill switch (>= 15%) absolute cash freeze override.
   - 20% single-position leverage ceiling under extreme Kelly scenarios.
   - Dynamic capital scaling invariance across orders of magnitude.
3. Systemic Stress Tests across UniverseSelector, TradeRanker, HorizonMapper, DecisionExplainer.
"""

import math
from unittest.mock import patch
import numpy as np
import pandas as pd
import pytest

from src.execution.frictions import FrictionEvaluator
from src.models.foundation_prior import VolatilityCone
from src.models.meta_labeler import MetaPrediction
from src.models.regime_hmm import REGIME_DEFINITIONS, RegimeState
from src.pipeline import SingleAssetAnalysis
from src.strategy.decision_explainer import DecisionExplainer
from src.strategy.horizon_mapper import HorizonMapper, HorizonParameters
from src.strategy.portfolio_selector import (
    AllocationItem,
    PortfolioAllocationResult,
    PortfolioSelector,
)
from src.strategy.trade_evaluator import TradeEvaluationResult, TradeEvaluator
from src.strategy.trade_ranker import RankedOpportunity, TradeRanker
from src.strategy.universe_selector import (
    CandidateEvaluation,
    UniverseSelectionCriteria,
    UniverseSelectionResult,
    UniverseSelector,
)


# ============================================================================
# HELPER FIXTURES & BUILDERS
# ============================================================================

def make_mock_analysis(
    ticker: str = "TEST",
    entry: float = 100.0,
    target: float = 103.0,
    stop: float = 98.5,
    prob: float = 0.65,
    direction: int = 1,
    vol: float = 0.20,
    q10_offset: float = -2.0,
    q50_offset: float = 0.0,
    q90_offset: float = 2.0,
    n_bars: int = 100,
    jurisdiction: str = "US",
    regime_state_id: int = 0,
    adv: float = 5e7,
) -> SingleAssetAnalysis:
    """Builds a realistic SingleAssetAnalysis for adversarial evaluation."""
    cone = VolatilityCone(
        periods=[1, 2, 3, 4, 5],
        q10_prices=[entry + q10_offset] * 5,
        q50_prices=[entry + q50_offset] * 5,
        q90_prices=[entry + q90_offset] * 5,
        expected_vol_annualized=vol,
        forward_skew=0.0,
    )
    meta = MetaPrediction(
        primary_direction=direction,
        direction_label="BUY" if direction > 0 else ("SELL" if direction < 0 else "NEUTRAL"),
        success_probability=prob,
        bet_size=0.10,
        target_price=target,
        stop_price=stop,
        feature_importances={},
    )
    df = pd.DataFrame(
        {
            "Close": [entry] * n_bars,
            "High": [entry * 1.01] * n_bars,
            "Low": [entry * 0.99] * n_bars,
            "Open": [entry] * n_bars,
            "Volume": [adv / max(entry, 1.0)] * n_bars,
        }
    )
    regime = REGIME_DEFINITIONS.get(regime_state_id, REGIME_DEFINITIONS[0])
    return SingleAssetAnalysis(
        ticker=ticker,
        current_price=entry,
        market_jurisdiction=jurisdiction,
        regime=regime,
        meta_prediction=meta,
        volatility_cone=cone,
        friction_hurdle_passes=True,
        friction_cost_pct=0.05,
        net_expected_alpha_pct=1.0,
        risk_decision=None,
        optimal_d_star=0.3,
        recent_ohlcv=df,
        features_df=df,
    )


def make_mock_opportunity(
    ticker: str,
    net_ev: float = 1.0,
    win_prob: float = 0.60,
    vol: float = 0.20,
    entry: float = 100.0,
    target: float = 103.0,
    stop: float = 98.5,
    is_eligible: bool = True,
    regime_mult: float = 1.25,
) -> RankedOpportunity:
    """Builds a RankedOpportunity for portfolio allocation stress testing."""
    ev = TradeEvaluationResult(
        ticker=ticker,
        direction="LONG",
        entry_price=entry,
        target_price=target,
        stop_price=stop,
        raw_win_prob=win_prob,
        epistemic_uncertainty=0.02,
        conservative_win_prob=max(0.0, win_prob - 0.02),
        loss_probability=1.0 - max(0.0, win_prob - 0.02),
        expected_win_return_pct=max(0.0, (target - entry) / entry * 100.0),
        expected_loss_return_pct=max(0.0, (entry - stop) / entry * 100.0) + 0.1,
        gap_risk_buffer_pct=0.1,
        round_trip_friction_pct=0.15,
        gross_expectancy_pct=net_ev + 0.15,
        net_expectancy_pct=net_ev,
        min_ev_hurdle_pct=0.20,
        is_positive_ev=(net_ev >= 0.20 and is_eligible),
        rejection_reason=None if (net_ev >= 0.20 and is_eligible) else "INELIGIBLE",
        payoff_ratio=max(0.0, (target - entry) / max(entry - stop, 1e-4)),
        evaluation_metadata={"annualized_vol": vol},
    )
    return RankedOpportunity(
        rank=1,
        ticker=ticker,
        direction="LONG",
        evaluation=ev,
        risk_adjusted_value=net_ev / max(vol, 0.05),
        regime_multiplier=regime_mult,
        synergy_boost=1.0,
        composite_score=(net_ev / max(vol, 0.05)) * regime_mult,
        is_eligible=is_eligible and (net_ev >= 0.20) and (regime_mult > 0.0),
        ineligible_reason=None if (is_eligible and net_ev >= 0.20 and regime_mult > 0.0) else (ev.rejection_reason or "Ineligible candidate"),
        rank_justification=f"Rank #1 {ticker}",
    )


# ============================================================================
# 1. TRADE EVALUATOR EMPIRICAL STRESS TESTS
# ============================================================================

class TestTradeEvaluatorAdversarialStress:
    """Adversarial stress-testing suite for TradeEvaluator."""

    def test_adversarial_barrier_geometry_inversions(self):
        """Probes all inverted, coincident, and degenerated target/stop geometries for LONG and SHORT."""
        evaluator = TradeEvaluator()

        # LONG permutations
        long_cases = [
            (95.0, 98.0, "Target below entry"),
            (100.0, 98.0, "Target equal to entry"),
            (105.0, 102.0, "Stop above entry"),
            (105.0, 100.0, "Stop equal to entry"),
            (100.0, 100.0, "Target and stop both equal to entry"),
            (95.0, 105.0, "Completely inverted (target < entry and stop > entry)"),
        ]

        for target, stop, desc in long_cases:
            analysis = make_mock_analysis(entry=100.0, target=target, stop=stop, direction=1)
            res = evaluator.evaluate(analysis)
            assert not res.is_positive_ev, f"LONG case failed to reject: {desc}"
            assert res.rejection_reason is not None
            assert "INVALID BARRIERS" in res.rejection_reason, f"Expected INVALID BARRIERS for: {desc}"

        # SHORT permutations (for SHORT: valid target < entry, valid stop > entry)
        short_cases = [
            (105.0, 102.0, "SHORT: Target above entry"),
            (100.0, 102.0, "SHORT: Target equal to entry"),
            (95.0, 98.0, "SHORT: Stop below entry"),
            (95.0, 100.0, "SHORT: Stop equal to entry"),
            (100.0, 100.0, "SHORT: Target and stop equal to entry"),
            (105.0, 95.0, "SHORT: Completely inverted (target > entry and stop < entry)"),
        ]

        for target, stop, desc in short_cases:
            analysis = make_mock_analysis(entry=100.0, target=target, stop=stop, direction=-1)
            res = evaluator.evaluate(analysis)
            assert not res.is_positive_ev, f"SHORT case failed to reject: {desc}"
            assert res.rejection_reason is not None
            assert "INVALID BARRIERS" in res.rejection_reason, f"Expected INVALID BARRIERS for: {desc}"

    def test_adversarial_extreme_price_regimes(self):
        """Tests micro-penny ($0.0001) and ultra-high price ($500,000) stability without overflow or div-by-zero."""
        evaluator = TradeEvaluator()

        # Micro-penny crypto/penny stock: Entry = 0.0001, Target = 0.00015 (+50%), Stop = 0.00008 (-20%)
        penny_analysis = make_mock_analysis(
            ticker="PENNY",
            entry=0.0001,
            target=0.00015,
            stop=0.00008,
            prob=0.70,
            direction=1,
            q10_offset=-0.00002,
            q50_offset=0.0,
            q90_offset=0.00005,
        )
        res_penny = evaluator.evaluate(penny_analysis)
        assert not math.isnan(res_penny.net_expectancy_pct)
        assert not math.isinf(res_penny.net_expectancy_pct)
        assert res_penny.expected_win_return_pct == 50.0
        assert res_penny.expected_loss_return_pct > 20.0

        # Ultra-expensive stock (e.g. Berkshire Hathaway Class A): Entry = 650,000
        brk_analysis = make_mock_analysis(
            ticker="BRK.A",
            entry=650000.0,
            target=663000.0,  # +2%
            stop=643500.0,    # -1%
            prob=0.65,
            direction=1,
            q10_offset=-6500.0,
            q50_offset=0.0,
            q90_offset=13000.0,
        )
        res_brk = evaluator.evaluate(brk_analysis)
        assert not math.isnan(res_brk.net_expectancy_pct)
        assert not math.isinf(res_brk.net_expectancy_pct)
        assert res_brk.expected_win_return_pct == 2.0

    def test_adversarial_zero_and_extreme_probability_inputs(self):
        """Verifies zero probability, out-of-bounds probability, and high epistemic decay."""
        evaluator = TradeEvaluator()

        # 1. Zero win probability: raw_p = 0.0
        zero_p_analysis = make_mock_analysis(prob=0.0)
        res_zero = evaluator.evaluate(zero_p_analysis)
        assert not res_zero.is_positive_ev
        assert res_zero.conservative_win_prob == 0.0
        assert "EPISTEMIC UNCERTAINTY VETO" in res_zero.rejection_reason

        # 2. Epistemic uncertainty blowing up conservative win prob to <= 0.0
        # raw_p = 0.15, tiny sample size (n=10), massive quantile dispersion -> sigma_p ~ 0.16 > 0.15
        wild_cone_analysis = make_mock_analysis(
            prob=0.15,
            n_bars=10,
            q10_offset=-50.0,
            q50_offset=0.0,
            q90_offset=150.0,
        )
        res_wild = evaluator.evaluate(wild_cone_analysis)
        assert not res_wild.is_positive_ev
        assert res_wild.conservative_win_prob == 0.0
        assert "EPISTEMIC UNCERTAINTY VETO" in res_wild.rejection_reason

        # 3. Direct function clamping on raw_p < 0.0 and raw_p > 1.0
        sigma_neg = evaluator.compute_epistemic_uncertainty(-0.5, 100, 98.0, 100.0, 102.0)
        assert sigma_neg == 0.0  # sqrt(0 * 1) = 0
        sigma_over = evaluator.compute_epistemic_uncertainty(1.5, 100, 98.0, 100.0, 102.0)
        assert sigma_over == 0.0  # sqrt(1 * 0) = 0

    def test_adversarial_extreme_quantile_spreads(self):
        """Tests flat quantiles, inverted quantiles, zero median, and asymmetric spreads."""
        evaluator = TradeEvaluator()

        # A. Flat quantiles (zero dispersion): q10 == q50 == q90
        sigma_flat = evaluator.compute_epistemic_uncertainty(0.60, 100, 100.0, 100.0, 100.0)
        # Dispersion multiplier = 1.0 + 0.2 * 0.0 = 1.0
        expected_se = math.sqrt(0.60 * 0.40 / 100)
        assert abs(sigma_flat - expected_se) < 1e-5

        # B. Inverted quantiles: q90 < q10 (e.g. q10=110, q90=90)
        # Must clamp dispersion to 0.0, never producing negative dispersion multiplier
        sigma_inv = evaluator.compute_epistemic_uncertainty(0.60, 100, 110.0, 100.0, 90.0)
        assert abs(sigma_inv - expected_se) < 1e-5

        # C. Zero median: q50 = 0.0
        # Denominator protection max(abs(0.0), 1e-4) must prevent ZeroDivisionError
        sigma_zero_q50 = evaluator.compute_epistemic_uncertainty(0.60, 100, -10.0, 0.0, 10.0)
        assert not math.isnan(sigma_zero_q50)
        assert not math.isinf(sigma_zero_q50)
        assert sigma_zero_q50 > 0.0

        # D. Giant dispersion: (q90 - q10) = 1,000,000
        sigma_huge = evaluator.compute_epistemic_uncertainty(0.60, 100, 0.0, 100.0, 1_000_000.0)
        assert not math.isnan(sigma_huge)
        assert not math.isinf(sigma_huge)
        assert sigma_huge > sigma_flat

    def test_strict_monotonicity_wrt_win_probability(self):
        """Verifies that Net Expectancy is strictly non-decreasing across the entire win probability sweep [0.0, 1.0]."""
        evaluator = TradeEvaluator()

        probabilities = np.linspace(0.01, 0.99, 99)
        net_evs = []

        for p in probabilities:
            analysis = make_mock_analysis(
                entry=100.0,
                target=104.0,  # +4%
                stop=98.0,     # -2%
                prob=float(p),
                direction=1,
            )
            res = evaluator.evaluate(analysis)
            net_evs.append(res.net_expectancy_pct)

        # Monotonicity check: EV(p_{i+1}) >= EV(p_i) for all i
        for i in range(len(net_evs) - 1):
            assert net_evs[i + 1] >= net_evs[i] - 1e-6, (
                f"Monotonicity violation at p={probabilities[i]:.2f} -> EV={net_evs[i]:.4f} "
                f"vs p={probabilities[i+1]:.2f} -> EV={net_evs[i+1]:.4f}"
            )

        # Check strict inequality for probabilities where conservative win prob is strictly positive
        # From p=0.30 to p=0.90, EV must be strictly increasing
        for i in range(30, 90):
            assert net_evs[i + 1] > net_evs[i], (
                f"Strict increase violated between p={probabilities[i]:.2f} and p={probabilities[i+1]:.2f}"
            )

    def test_strict_monotonicity_wrt_payoff_odds(self):
        """Verifies that Net Expectancy strictly increases as target price increases (higher payoff ratio b)."""
        evaluator = TradeEvaluator()

        targets = np.linspace(101.0, 115.0, 29)  # +1% to +15%
        ev_by_target = []

        for tgt in targets:
            analysis = make_mock_analysis(
                entry=100.0,
                target=float(tgt),
                stop=98.0,  # constant stop loss
                prob=0.60,
                direction=1,
            )
            res = evaluator.evaluate(analysis)
            ev_by_target.append(res.net_expectancy_pct)

        for i in range(len(ev_by_target) - 1):
            assert ev_by_target[i + 1] > ev_by_target[i], (
                f"Payoff monotonicity violation: Target {targets[i]:.1f} (EV={ev_by_target[i]:.4f}) "
                f"vs Target {targets[i+1]:.1f} (EV={ev_by_target[i+1]:.4f})"
            )

    def test_invariant_all_ev_le_zero_or_sub_hurdle_rejected(self):
        """Invariant: Across 500 randomized parameter configurations, EV <= 0 is NEVER approved."""
        evaluator = TradeEvaluator(default_min_ev_hurdle_pct=0.20)
        rng = np.random.default_rng(seed=2026)

        rejections_verified = 0
        approvals_verified = 0

        for _ in range(500):
            entry = rng.uniform(10.0, 500.0)
            target = entry * rng.uniform(0.90, 1.20)
            stop = entry * rng.uniform(0.80, 1.10)
            prob = rng.uniform(0.10, 0.90)
            direction = rng.choice([-1, 0, 1])

            analysis = make_mock_analysis(
                ticker="MC_TEST",
                entry=entry,
                target=target,
                stop=stop,
                prob=prob,
                direction=int(direction),
            )
            res = evaluator.evaluate(analysis)

            # Invariant 1: If net EV <= 0.0, MUST NOT be positive EV
            if res.net_expectancy_pct <= 0.0:
                assert not res.is_positive_ev, (
                    f"Invariant 1 violated: Approved trade with non-positive EV ({res.net_expectancy_pct}%)"
                )
                assert res.rejection_reason is not None

            # Invariant 2: If net EV < hurdle (+0.20%), MUST NOT be positive EV
            if res.net_expectancy_pct < 0.20:
                assert not res.is_positive_ev, (
                    f"Invariant 2 violated: Approved trade below hurdle ({res.net_expectancy_pct}% < 0.20%)"
                )
                assert res.rejection_reason is not None
                rejections_verified += 1

            # Invariant 3: If approved, net EV MUST be >= hurdle (+0.20%)
            if res.is_positive_ev:
                assert res.net_expectancy_pct >= 0.20
                assert res.rejection_reason is None
                assert res.conservative_win_prob > 0.0
                assert res.direction in ["LONG", "SHORT"]
                approvals_verified += 1

        assert rejections_verified > 0
        assert approvals_verified > 0


# ============================================================================
# 2. PORTFOLIO SELECTOR EMPIRICAL STRESS TESTS
# ============================================================================

class TestPortfolioSelectorAdversarialStress:
    """Adversarial stress-testing suite for PortfolioSelector."""

    def test_adversarial_zero_qualifying_opportunities_matrix(self):
        """Verifies 100% Cash Guarantee across all permutations of non-qualifying candidate baskets."""
        selector = PortfolioSelector()
        capital = 250_000.0

        # Matrix of non-qualifying test scenarios:
        scenarios = {
            "empty_list": [],
            "all_negative_ev": [
                make_mock_opportunity("NEG_1", net_ev=-1.2, is_eligible=False),
                make_mock_opportunity("NEG_2", net_ev=-0.05, is_eligible=False),
            ],
            "all_sub_hurdle_ev": [
                make_mock_opportunity("SUB_1", net_ev=0.05, is_eligible=False),
                make_mock_opportunity("SUB_2", net_ev=0.19, is_eligible=False),
            ],
            "all_regime_crisis_vetoed": [
                make_mock_opportunity("CRISIS_1", net_ev=3.5, is_eligible=False, regime_mult=0.0),
                make_mock_opportunity("CRISIS_2", net_ev=2.0, is_eligible=False, regime_mult=0.0),
            ],
            "all_zero_kelly_fraction": [
                # Positive EV, but win_prob=0.30, b=1.0 -> f* = 0.30 - (0.70/1.0) = -0.40 <= 0
                make_mock_opportunity("NO_EDGE_1", net_ev=0.5, win_prob=0.30, entry=100.0, target=101.0, stop=99.0),
            ],
        }

        for name, opps in scenarios.items():
            res = selector.allocate(opps, total_virtual_equity=capital, method="KELLY")
            assert res.is_100_percent_cash is True, f"Failed 100% cash guarantee for: {name}"
            assert res.cash_weight == 1.0, f"Cash weight not 1.0 for: {name}"
            assert res.weights == {"CASH": 1.0}, f"Weights not {{'CASH': 1.0}} for: {name}"
            assert res.allocated_capital == {}
            assert res.shares == {}
            assert res.allocations == []
            assert res.total_allocated_capital == 0.0
            assert res.residual_cash_capital == capital

    def test_extreme_drawdown_kill_switch_matrix(self):
        """Verifies drawdown kill switch (>= 15%) forces 100% Cash even with exceptional alpha opportunities."""
        selector = PortfolioSelector(max_kill_drawdown=0.15, warning_drawdown=0.08)
        capital = 100_000.0

        # God-tier opportunities (+10% Net EV, 90% win prob)
        super_opps = [
            make_mock_opportunity("GOD_1", net_ev=10.0, win_prob=0.90, target=120.0, stop=98.0),
            make_mock_opportunity("GOD_2", net_ev=8.0, win_prob=0.85, target=115.0, stop=98.0),
        ]

        drawdown_levels = [0.1500, 0.1501, 0.20, 0.50, 0.99]
        for dd in drawdown_levels:
            res = selector.allocate(super_opps, total_virtual_equity=capital, current_drawdown=dd)
            assert res.is_100_percent_cash is True, f"Kill switch breached at drawdown {dd:.1%}"
            assert res.cash_weight == 1.0
            assert res.weights == {"CASH": 1.0}
            assert res.total_allocated_capital == 0.0
            assert "breached kill limit" in res.explanation

        # Verify warning drawdown dampening (dd between 8% and 15% smoothly scales down allocations)
        res_warn = selector.allocate(super_opps, total_virtual_equity=capital, current_drawdown=0.12)
        assert not res_warn.is_100_percent_cash
        # At 12% DD (excess = 4%, range = 7%, dampening = (1 - 4/7)^2 = (3/7)^2 ~ 0.1837)
        # Sizing must be dampended significantly below the 20% cap
        for alloc in res_warn.allocations:
            assert alloc.weight < 0.20
            assert alloc.dd_scalar < 1.0

    def test_single_position_20_percent_leverage_ceiling_stress(self):
        """Verifies that under extreme Kelly values and multiple market regimes, no position exceeds 20%."""
        selector = PortfolioSelector(max_position_cap=0.20, kelly_fraction=1.0)  # Aggressive Full Kelly
        capital = 500_000.0

        # Unconstrained Kelly f* ~ 0.999
        extreme_opps = [
            make_mock_opportunity("EXTREME_1", net_ev=50.0, win_prob=0.99, vol=0.05, target=200.0, stop=99.9),
            make_mock_opportunity("EXTREME_2", net_ev=40.0, win_prob=0.95, vol=0.08, target=180.0, stop=99.5),
            make_mock_opportunity("EXTREME_3", net_ev=30.0, win_prob=0.90, vol=0.10, target=150.0, stop=99.0),
        ]

        # 1. Test in KELLY mode
        res_kelly = selector.allocate(extreme_opps, total_virtual_equity=capital, method="KELLY")
        assert not res_kelly.is_100_percent_cash
        for alloc in res_kelly.allocations:
            assert alloc.weight <= 0.20001, f"Kelly position {alloc.ticker} breached 20% cap: {alloc.weight:.4f}"
            assert alloc.allocated_capital <= (capital * 0.20) + 0.01

        # 2. Test in HRP mode with highly skewed returns
        np.random.seed(1337)
        returns = pd.DataFrame({
            "EXTREME_1": np.random.normal(0.005, 0.001, 60),  # near zero vol, high return
            "EXTREME_2": np.random.normal(0.001, 0.05, 60),
            "EXTREME_3": np.random.normal(0.001, 0.08, 60),
        })
        res_hrp = selector.allocate(extreme_opps, total_virtual_equity=capital, method="HRP", returns_df=returns)
        assert not res_hrp.is_100_percent_cash
        for alloc in res_hrp.allocations:
            assert alloc.weight <= 0.2001, f"HRP position {alloc.ticker} breached 20% cap: {alloc.weight:.4f}"

    def test_dynamic_capital_scaling_invariance_stress(self):
        """Stress tests capital scaling across 6 orders of magnitude ($100 to $100M).

        Invariant:
        - Allocation weights w_i and cash_weight must be invariant to account size.
        - Model prediction outputs (win prob, target, stop, net EV) must not alter.
        - Capital and shares must scale strictly linearly with total virtual equity.
        """
        selector = PortfolioSelector()
        opp1 = make_mock_opportunity("AAPL", net_ev=1.5, win_prob=0.65, entry=150.0, target=156.0, stop=147.0)
        opp2 = make_mock_opportunity("MSFT", net_ev=1.1, win_prob=0.60, entry=300.0, target=310.0, stop=295.0)
        opps = [opp1, opp2]

        capital_tiers = [1_000.0, 5_000.0, 10_000.0, 50_000.0, 100_000.0, 1_000_000.0, 10_000_000.0]
        results = [selector.allocate(opps, total_virtual_equity=cap, method="KELLY") for cap in capital_tiers]

        base_res = results[2]  # $10,000 baseline
        base_weights = base_res.weights

        for idx, (cap, res) in enumerate(zip(capital_tiers, results)):
            # 1. Weights invariance
            for ticker in ["AAPL", "MSFT", "CASH"]:
                assert abs(res.weights[ticker] - base_weights[ticker]) < 1e-4, (
                    f"Weight altered at capital ${cap:,.0f} for {ticker}: {res.weights[ticker]} vs {base_weights[ticker]}"
                )

            # 2. Linear scaling of allocated dollars
            scale_ratio = cap / 10_000.0
            for ticker in ["AAPL", "MSFT"]:
                expected_cap = round(base_res.allocated_capital[ticker] * scale_ratio, 2)
                assert abs(res.allocated_capital[ticker] - expected_cap) <= 1.0, (
                    f"Capital scaling non-linear for {ticker} at ${cap:,.0f}"
                )

            # 3. Model prediction outputs decoupling
            assert opp1.evaluation.net_expectancy_pct == 1.5
            assert opp1.evaluation.raw_win_prob == 0.65
            assert opp1.evaluation.target_price == 156.0


# ============================================================================
# 3. UNIVERSE SELECTOR, RANKER, HORIZON MAPPER & EXPLAINER STRESS TESTS
# ============================================================================

class TestAuxiliaryStrategyModulesAdversarial:
    """Stress tests UniverseSelector, TradeRanker, HorizonMapper, and DecisionExplainer."""

    def test_universe_selector_corrupt_data_robustness(self):
        """Verifies UniverseSelector handles completely corrupt dataframes without crashing."""
        selector = UniverseSelector()

        # 1. Empty dataframe
        q_empty, r_miss, r_zero = selector.evaluate_data_quality(pd.DataFrame(), "US_EQUITIES")
        assert q_empty == 0.0
        assert r_miss == 1.0

        # 2. Inverted High/Low (High < Low)
        inverted_df = pd.DataFrame({
            "Open": [100.0] * 30,
            "High": [90.0] * 30,   # High < Low!
            "Low": [100.0] * 30,
            "Close": [95.0] * 30,
            "Volume": [1e6] * 30,
        })
        q_inv, r_miss_inv, _ = selector.evaluate_data_quality(inverted_df, "US_EQUITIES")
        assert r_miss_inv == 1.0  # 100% corrupted bars
        assert q_inv < 0.90

        # 3. Auto-select basket on completely empty candidates
        result = selector.auto_select_basket(market="US", candidate_tickers=[])
        assert isinstance(result, UniverseSelectionResult)
        # Fallback to default catalog or empty
        assert len(result.selected_instruments) <= 6

    def test_trade_ranker_crisis_quarantine_veto(self):
        """Verifies TradeRanker completely suppresses and quarantines State 2 Crisis opportunities."""
        ranker = TradeRanker()

        ev_normal = TradeEvaluationResult(
            ticker="NORM", direction="LONG", entry_price=100.0, target_price=103.0, stop_price=98.5,
            raw_win_prob=0.60, epistemic_uncertainty=0.02, conservative_win_prob=0.58, loss_probability=0.42,
            expected_win_return_pct=3.0, expected_loss_return_pct=1.5, gap_risk_buffer_pct=0.1,
            round_trip_friction_pct=0.15, gross_expectancy_pct=1.1, net_expectancy_pct=0.95,
            min_ev_hurdle_pct=0.20, is_positive_ev=True, rejection_reason=None, payoff_ratio=2.0,
            evaluation_metadata={"annualized_vol": 0.20},
        )
        ev_crisis = TradeEvaluationResult(
            ticker="CRISIS_STOCK", direction="LONG", entry_price=100.0, target_price=110.0, stop_price=95.0,
            raw_win_prob=0.80, epistemic_uncertainty=0.02, conservative_win_prob=0.78, loss_probability=0.22,
            expected_win_return_pct=10.0, expected_loss_return_pct=5.0, gap_risk_buffer_pct=0.1,
            round_trip_friction_pct=0.15, gross_expectancy_pct=6.5, net_expectancy_pct=6.35,
            min_ev_hurdle_pct=0.20, is_positive_ev=True, rejection_reason=None, payoff_ratio=2.0,
            evaluation_metadata={"annualized_vol": 0.35},
        )

        regimes = {
            "NORM": REGIME_DEFINITIONS[0],    # Trending
            "CRISIS_STOCK": REGIME_DEFINITIONS[2],  # State 2 Crisis
        }

        ranked = ranker.rank_opportunities([ev_crisis, ev_normal], regimes=regimes)
        assert len(ranked) == 2

        # Normal trade must be ranked #1 and eligible
        assert ranked[0].ticker == "NORM"
        assert ranked[0].is_eligible is True
        assert ranked[0].composite_score > 0.0

        # Crisis trade must be ranked #2 and ineligible
        assert ranked[1].ticker == "CRISIS_STOCK"
        assert ranked[1].is_eligible is False
        assert ranked[1].regime_multiplier == 0.0
        assert ranked[1].composite_score == 0.0
        assert "Crisis" in (ranked[1].ineligible_reason or "")

    def test_horizon_mapper_boundary_normalization_and_invariants(self):
        """Verifies HorizonMapper canonical normalization, unsupported exception, and exact annualization."""
        # 1. Normalization variations
        assert HorizonMapper.normalize_horizon("1h") == "1 hour"
        assert HorizonMapper.normalize_horizon("1-hour") == "1 hour"
        assert HorizonMapper.normalize_horizon("INTRADAY") == "1 hour"
        assert HorizonMapper.normalize_horizon("1d") == "1 day"
        assert HorizonMapper.normalize_horizon("daily") == "1 day"
        assert HorizonMapper.normalize_horizon("1wk") == "1 week"
        assert HorizonMapper.normalize_horizon("SWING") == "1 week"

        # 2. Unsupported horizon
        with pytest.raises(ValueError, match="Unsupported trading horizon"):
            HorizonMapper.normalize_horizon("1 month")

        # 3. Invariant mathematical annualization factors
        p_1h = HorizonMapper.get_parameters("1 hour")
        p_1d = HorizonMapper.get_parameters("1 day")
        p_1w = HorizonMapper.get_parameters("1 week")

        assert p_1h.annualization_factor == 140.2
        assert p_1d.annualization_factor == 40.5
        assert p_1w.annualization_factor == 15.87

    def test_decision_explainer_robustness_on_all_permutations(self):
        """Verifies DecisionExplainer produces non-empty, well-formed narratives for all actions."""
        # 1. 100% Cash Fallback
        cash_exp = DecisionExplainer.explain_portfolio_cash_fallback(
            total_candidates_evaluated=12,
            rejection_summary="Zero opportunities met hurdle",
            active_regime="State 1 Choppy",
            current_drawdown_pct=5.2,
        )
        assert cash_exp.action == "HELD_IN_CASH"
        assert cash_exp.ticker == "PORTFOLIO"
        assert "Zero Opportunities" in cash_exp.headline
        assert cash_exp.metrics["cash_weight_pct"] == 100.0

        # 2. Rejected trade explanations
        opp_neg = make_mock_opportunity("REJ", net_ev=-0.8, is_eligible=False)
        rej_exp = DecisionExplainer.explain_rejected_trade(opp_neg)
        assert rej_exp.action == "REJECTED"
        assert rej_exp.ticker == "REJ"
        assert "Negative Net Expectancy" in rej_exp.headline

        # 3. Accepted trade explanations
        opp_acc = make_mock_opportunity("ACC", net_ev=2.5, is_eligible=True)
        alloc_item = AllocationItem(
            ticker="ACC", direction="LONG", weight=0.15, weight_pct=15.0,
            allocated_capital=15000.0, entry_price=100.0, shares=150.0,
            target_price=103.0, stop_price=98.5, expected_net_ev_pct=2.5,
            kelly_optimal_f=0.5, vol_scalar=1.0, dd_scalar=1.0, sizing_rationale="Kelly",
        )
        acc_exp = DecisionExplainer.explain_accepted_trade(opp_acc, alloc_item, currency_symbol="$")
        assert acc_exp.action == "ACCEPTED"
        assert acc_exp.ticker == "ACC"
        assert "BUY ACC" in acc_exp.headline
        assert acc_exp.metrics["allocation_weight_pct"] == 15.0
