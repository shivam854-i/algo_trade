"""Verification & Regression Test Suite for Phase 1 & Phase 2 Quantitative & GPU Fixes."""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.backtest.engine import BacktestEngine
from src.execution.frictions import FrictionEvaluator
from src.execution.guardrails import RiskGuardrailEngine
from src.features.fracdiff import FractionalDifferentiator
from src.models.gpu_acceleration import TorchSequenceForecaster
from src.models.hrp_allocator import HierarchicalRiskParity
from src.models.meta_labeler import MetaLabelingEngine
from src.models.regime_hmm import MarketRegimeClassifier


def run_all_tests():
    # 1. FracDiff analytical lookback & standardized burn-in calibration
    fd = FractionalDifferentiator()
    l_star = fd.compute_analytical_lookback(0.25, 1e-3)
    print(f"[PASS 1] FracDiff analytical lookback L*(0.25, 1e-3) = {l_star} bars")
    assert l_star >= 15

    # 2. Causal HMM Forward Filter Future-Invariance
    rng = np.random.default_rng(42)
    dates = pd.date_range("2024-01-01", periods=200, freq="D")
    prices = 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.01, 200)))
    df_normal = pd.DataFrame(
        {
            "Open": prices,
            "High": prices * 1.005,
            "Low": prices * 0.995,
            "Close": prices,
            "Volume": 1000.0,
        },
        index=dates,
    )
    df_crash = df_normal.copy()
    # Inject massive future crash at bar 150..199
    df_crash.iloc[150:, df_crash.columns.get_loc("Close")] *= 0.50
    df_crash.iloc[150:, df_crash.columns.get_loc("Low")] *= 0.45

    clf = MarketRegimeClassifier()
    clf.fit(df_normal.iloc[:100])
    s_normal = clf.filter_causal(df_normal)
    s_crash = clf.filter_causal(df_crash)
    diff_before_150 = int((s_normal.iloc[:150] != s_crash.iloc[:150]).sum())
    print(
        f"[PASS 2] Causal HMM Future-Invariance (state diffs before bar 150): {diff_before_150} (Expected: 0)"
    )
    assert diff_before_150 == 0, "Lookahead bias detected in HMM forward filter!"
    assert s_crash.iloc[150] == 2, "Crisis jump override failed to trigger on crash bar 150!"

    # 3. Triple-Barrier High/Low Wick Conservative Conflict Resolution & Rectified Sizing
    ml = MetaLabelingEngine()
    df_wick = df_normal.iloc[:30].copy()
    # Bar 1 hits BOTH PT (+5%) and SL (-6%) in High/Low wicks while Close is +5%
    df_wick.iloc[1, df_wick.columns.get_loc("High")] = df_wick.iloc[0]["Close"] * 1.05
    df_wick.iloc[1, df_wick.columns.get_loc("Low")] = df_wick.iloc[0]["Close"] * 0.94
    df_wick.iloc[1, df_wick.columns.get_loc("Close")] = df_wick.iloc[0]["Close"] * 1.05
    sig = pd.Series(1, index=df_wick.index)
    vol = pd.Series(0.02, index=df_wick.index)
    tb = ml.compute_triple_barrier_labels(df_wick, sig, vol)
    target_val = int(tb.iloc[0]["Target"])
    print(
        f"[PASS 3] Triple-Barrier Dual-Breach Wick Label (Conservative Conflict Resolution): {target_val} (Expected: 0)"
    )
    assert target_val == 0

    # Verify HRP Diagonal Preservation & Ward Linkage
    ret_df = pd.DataFrame(rng.normal(0, 0.01, (120, 5)), columns=["A", "B", "C", "D", "E"])
    raw_cov = ret_df.cov().values
    clean_cov = HierarchicalRiskParity.denoise_covariance(raw_cov, 120, 5)
    diag_err = float(np.max(np.abs(np.diag(raw_cov) - np.diag(clean_cov))))
    w_hrp = HierarchicalRiskParity.compute_hrp_weights(ret_df)
    print(
        f"[PASS 4] HRP RMT Diagonal Variance Preservation Error: {diag_err:.2e}, Ward Weights Sum: {w_hrp.sum():.4f}"
    )
    assert diag_err < 1e-12
    assert abs(w_hrp.sum() - 1.0) < 1e-3

    # 5. Statutory Frictions (Delivery vs Intraday NSE & US dimensional fix)
    nse_del_bps = FrictionEvaluator.calculate_round_trip_friction_bps(
        "RELIANCE.NS", is_intraday=False
    )
    nse_intra_bps = FrictionEvaluator.calculate_round_trip_friction_bps(
        "RELIANCE.NS", is_intraday=True
    )
    us_bps = FrictionEvaluator.calculate_round_trip_friction_bps(
        "AAPL", reference_price=200.0
    )
    print(
        f"[PASS 5] Frictions -> NSE Delivery: {nse_del_bps} bps, NSE Intraday: {nse_intra_bps} bps, US ($200): {us_bps} bps"
    )
    assert nse_del_bps > 25.0 and nse_intra_bps < 18.0

    # 6. Asymmetric CVaR-Kelly 20% Hard Leverage Ceiling
    guard = RiskGuardrailEngine()
    alloc_low_p = guard.evaluate_allocation(
        current_drawdown=0.0,
        model_bet_size=0.0,
        realized_annual_vol=0.15,
        win_probability=0.35,
        payoff_ratio_b=1.5,
    )
    alloc_high_p = guard.evaluate_allocation(
        current_drawdown=0.0,
        model_bet_size=0.95,
        realized_annual_vol=0.10,
        win_probability=0.90,
        payoff_ratio_b=2.0,
    )
    print(
        f"[PASS 6] Asymmetric CVaR-Kelly -> Low-Prob (p=0.35) Weight: {alloc_low_p.authorized_weight_pct}%, High-Prob Cap: {alloc_high_p.authorized_weight_pct}%"
    )
    assert alloc_low_p.authorized_weight_pct == 0.0
    assert alloc_high_p.authorized_weight_pct <= 20.0

    # 7. Supervised Pinball-Loss Causal TCN & Monotonic Quantiles (q10 <= q50 <= q90)
    tcn = TorchSequenceForecaster()
    loss = tcn.fit(df_normal, epochs=12)
    q10, q50, q90 = tcn.forecast_tensor(df_normal)
    print(
        f"[PASS 7] Supervised TCN Pinball Loss: {loss:.5f}, Monotonic Quantiles: q10={q10:.4f} <= q50={q50:.4f} <= q90={q90:.4f}"
    )
    assert tcn.is_trained
    assert q10 <= q50 <= q90, "Quantile crossing detected!"

    # 8. Phase 3 Microstructure Circuit Breakers (Forex 17:00 EST Rollover & CME LULD / Stop-Run)
    rollover_ts = pd.Timestamp("2026-06-15 21:15:00", tz="UTC")
    fx_ok, fx_msg = FrictionEvaluator.check_microstructure_execution_gate(
        "EURUSD=X", timestamp=rollover_ts
    )
    df_sweep = df_normal.iloc[:20].copy()
    # Inject a 3.5x range stop-run bar with 90% wick rejection on last bar
    df_sweep.iloc[-1, df_sweep.columns.get_loc("High")] = df_sweep.iloc[-1]["Close"] * 1.045
    df_sweep.iloc[-1, df_sweep.columns.get_loc("Low")] = df_sweep.iloc[-1]["Close"] * 0.995
    df_sweep.iloc[-1, df_sweep.columns.get_loc("Open")] = df_sweep.iloc[-1]["Close"] * 1.001
    gold_ok, gold_msg = FrictionEvaluator.check_microstructure_execution_gate(
        "GC=F", ohlcv_df=df_sweep
    )
    print(f"[PASS 8] Microstructure Gates -> FX Rollover Allowed: {fx_ok}, Gold Sweep Allowed: {gold_ok}")
    assert not fx_ok and not gold_ok

    print("\n=== ALL 8 PHASE 1, 2 & 3 MATHEMATICAL & MICROSTRUCTURE INVARIANTS VERIFIED ===")


if __name__ == "__main__":
    run_all_tests()
