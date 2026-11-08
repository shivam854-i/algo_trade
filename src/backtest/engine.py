"""Institutional Walk-Forward Backtesting Engine.

Simulates strategy execution with zero lookahead bias:
- Causal Fractional Differentiation calibration
- Online Causal Forward-Filtering HMM (alpha_t(j)) with Parkinson range volatility
- Purged High/Low Triple-Barrier Meta-Labeling with Conservative Conflict Resolution
- Supervised Pinball-Loss Causal TCN Neural Forecaster ensemble fusion (65% LGBM + 35% TCN)
- Dimensionally consistent holding-period-aware statutory frictions + L2 slippage
- Asymmetric CVaR-Kelly position sizing and Bailey-López de Prado Deflated Sharpe Ratio (DSR)
"""

from dataclasses import dataclass, field
import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

from src.data.downloader import MarketDataDownloader
from src.data.normalizer import MarketDataNormalizer
from src.execution.frictions import FrictionEvaluator
from src.execution.guardrails import RiskGuardrailEngine
from src.features.fracdiff import FractionalDifferentiator
from src.features.technical import TechnicalFeaturePipeline
from src.models.gpu_acceleration import TorchSequenceForecaster
from src.models.meta_labeler import MetaLabelingEngine
from src.models.regime_hmm import MarketRegimeClassifier

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    ticker: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    exit_price: float
    return_pct: float
    net_pnl: float
    exit_reason: str  # "PROFIT_TARGET", "STOP_LOSS", "HOLDING_EXPIRED", "CRISIS_EXIT"
    duration_bars: int


@dataclass
class BacktestResult:
    ticker: str
    period: str
    interval: str
    initial_capital: float
    final_equity: float
    total_return_pct: float
    buy_hold_return_pct: float
    cagr_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    calmar_ratio: float
    win_rate_pct: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_trade_return_pct: float
    equity_curve: pd.Series
    drawdown_series: pd.Series
    trades: List[TradeRecord]
    deflated_sharpe: float
    jurisdiction: str


def get_annualization_factor(interval: str, market_type: str = "US") -> float:
    """Computes exact bar annualization factor based on asset market hours."""
    if market_type == "CRYPTO":
        daily_bars = 365.0
        hours_per_day = 24.0
    elif market_type in ["FOREX", "COMMODITY"]:
        daily_bars = 260.0
        hours_per_day = 23.0
    else:  # US, NSE
        daily_bars = 252.0
        hours_per_day = 6.5

    if interval == "1d":
        return daily_bars
    elif interval in ["1h", "60m"]:
        return daily_bars * hours_per_day
    elif interval == "30m":
        return daily_bars * hours_per_day * 2.0
    elif interval == "15m":
        return daily_bars * hours_per_day * 4.0
    elif interval == "5m":
        return daily_bars * hours_per_day * 12.0
    elif interval == "1m":
        return daily_bars * hours_per_day * 60.0
    return daily_bars


class BacktestEngine:
    """Strictly causal walk-forward backtesting simulator for Synapse Titan strategies."""

    def __init__(
        self,
        initial_capital: float = 10000.0,
        risk_free_rate: float = 0.04,
        kelly_fraction: float = 0.30,
        target_vol: float = 0.15,
        holding_period: int = 5,
        pt_mult: float = 1.8,
        sl_mult: float = 1.25,
    ):
        self.initial_capital = initial_capital
        self.rf = risk_free_rate
        self.holding_period = holding_period
        self.pt_mult = pt_mult
        self.sl_mult = sl_mult

        self.downloader = MarketDataDownloader()
        self.normalizer = MarketDataNormalizer()
        self.fracdiff = FractionalDifferentiator()
        self.tech_pipeline = TechnicalFeaturePipeline()
        self.regime_clf = MarketRegimeClassifier()
        self.meta_engine = MetaLabelingEngine(
            pt_vol_mult=pt_mult,
            sl_vol_mult=sl_mult,
            holding_period=holding_period,
        )
        self.neural_forecaster = TorchSequenceForecaster(horizon=holding_period)
        self.guardrail = RiskGuardrailEngine(
            kelly_fraction=kelly_fraction, target_annual_vol=target_vol
        )

    def run(
        self,
        ticker: str,
        period: str = "2y",
        interval: str = "1d",
        warmup_bars: int = 60,
        refit_interval: int = 15,
    ) -> Optional[BacktestResult]:
        """Executes strictly causal walk-forward backtest across historical bars."""
        # 1. Download & Clean
        df_raw = self.downloader.download_ticker(ticker, period=period, interval=interval)
        if df_raw.empty or len(df_raw) < warmup_bars + 30:
            logger.error(f"Insufficient historical data for {ticker} backtest.")
            return None

        df = self.normalizer.clean_ohlcv(df_raw)
        jurisdiction = self.downloader.get_market_type(ticker)

        # 2. Extract Features (Calibrate d* strictly on initial warmup slice to avoid lookahead)
        calib_win = min(max(warmup_bars * 2, 90), len(df) // 2)
        d_opt, s_fracdiff = self.fracdiff.find_min_d(
            df["Close"], calibration_window=calib_win
        )
        feats = self.tech_pipeline.compute_features(df)
        if not s_fracdiff.empty:
            common = feats.index.intersection(s_fracdiff.index)
            feats = feats.loc[common].copy()
            feats["FracDiff_Price"] = s_fracdiff.loc[common]

        # Align df with features
        valid_idx = feats.index
        df_aligned = df.loc[valid_idx].copy()
        n_bars = len(df_aligned)

        if n_bars < warmup_bars + 20:
            return None

        # 3. Initial Causal HMM Regime Calibration on Warmup Slice Only
        self.regime_clf.fit(df_aligned.iloc[:warmup_bars])
        regime_series = self.regime_clf.filter_causal(df_aligned)

        # 4. Holding-Period-Aware Statutory Friction + Slippage (converted from bps to fraction)
        is_intraday = interval != "1d"
        ref_price = float(df_aligned["Close"].iloc[warmup_bars])
        friction_pct = (
            FrictionEvaluator.calculate_round_trip_friction_bps(
                ticker, is_intraday=is_intraday, reference_price=ref_price
            )
            / 10000.0
        )
        annual_factor = get_annualization_factor(interval, jurisdiction)

        # State Tracking
        equity = self.initial_capital
        peak_equity = self.initial_capital
        cash = self.initial_capital
        position_shares = 0.0
        position_direction = 0  # 1 = Long, -1 = Short, 0 = Flat
        entry_price = 0.0
        entry_bar = 0
        entry_date = None
        target_price = 0.0
        stop_price = 0.0

        trades: List[TradeRecord] = []

        # Vectorized Input Arrays for zero-overhead loop access
        close_arr = df_aligned["Close"].to_numpy(dtype=np.float64)
        high_arr = df_aligned["High"].to_numpy(dtype=np.float64)
        low_arr = df_aligned["Low"].to_numpy(dtype=np.float64)
        dates_arr = df_aligned.index
        regime_arr = regime_series.to_numpy(dtype=np.int64)
        has_atr = "ATR_Pct" in feats.columns
        atr_arr = feats["ATR_Pct"].to_numpy(dtype=np.float64) if has_atr else None

        # Preallocate portfolio valuation buffer
        sim_bars = n_bars - warmup_bars
        equity_vals = np.empty(sim_bars, dtype=np.float64)

        # Walk-forward loop
        for t in range(warmup_bars, n_bars):
            curr_date = dates_arr[t]
            curr_close = close_arr[t]
            curr_high = high_arr[t]
            curr_low = low_arr[t]
            curr_regime = regime_arr[t]

            # Local volatility for barriers
            if has_atr and np.isfinite(atr_arr[t]):
                local_vol = float(atr_arr[t])
            else:
                local_vol = 0.02

            # --- Check Active Trade Exits (Conservative Conflict Resolution: Stop-Loss Priority) ---
            if position_direction != 0:
                holding_bars = t - entry_bar
                exit_price = None
                exit_reason = None

                # Check High-Vol Crisis circuit breaker
                if curr_regime == 2:
                    exit_price = curr_close
                    exit_reason = "CRISIS_EXIT"

                # Check Long Exit (Stop-Loss evaluated BEFORE Profit-Target on intrabar wicks)
                elif position_direction == 1:
                    if curr_low <= stop_price:
                        exit_price = stop_price
                        exit_reason = "STOP_LOSS"
                    elif curr_high >= target_price:
                        exit_price = target_price
                        exit_reason = "PROFIT_TARGET"
                    elif holding_bars >= self.holding_period:
                        exit_price = curr_close
                        exit_reason = "HOLDING_EXPIRED"

                # Check Short Exit (Stop-Loss evaluated BEFORE Profit-Target on intrabar wicks)
                elif position_direction == -1:
                    if curr_high >= stop_price:
                        exit_price = stop_price
                        exit_reason = "STOP_LOSS"
                    elif curr_low <= target_price:
                        exit_price = target_price
                        exit_reason = "PROFIT_TARGET"
                    elif holding_bars >= self.holding_period:
                        exit_price = curr_close
                        exit_reason = "HOLDING_EXPIRED"

                # Process Exit
                if exit_price is not None:
                    gross_ret = (
                        (exit_price - entry_price) / entry_price
                        if position_direction == 1
                        else (entry_price - exit_price) / entry_price
                    )
                    net_ret = gross_ret - friction_pct
                    trade_pnl = position_shares * entry_price * net_ret

                    equity += trade_pnl
                    cash = equity
                    if equity > peak_equity:
                        peak_equity = equity

                    trades.append(
                        TradeRecord(
                            entry_date=entry_date,
                            exit_date=curr_date,
                            ticker=ticker,
                            direction="LONG" if position_direction == 1 else "SHORT",
                            entry_price=round(entry_price, 2),
                            exit_price=round(exit_price, 2),
                            return_pct=round(net_ret * 100, 2),
                            net_pnl=round(trade_pnl, 2),
                            exit_reason=exit_reason,
                            duration_bars=holding_bars,
                        )
                    )

                    position_direction = 0
                    position_shares = 0.0

            # --- Periodic Model Refit (Strictly Causal & Horizon-Purged) ---
            if t == warmup_bars or (t % refit_interval == 0):
                sub_feats = feats.iloc[:t]
                sub_df = df_aligned.iloc[:t]

                # Refit HMM parameters causally and update forward-filtered regime states from t onward
                if t % (refit_interval * 2) == 0:
                    self.regime_clf.fit(sub_df)
                    regime_series = self.regime_clf.filter_causal(df_aligned)
                    curr_regime = int(regime_series.iloc[t])

                # Refit Tabular Meta-Labeler (purges last `holding_period` bars automatically)
                if hasattr(self.meta_engine, "fit"):
                    self.meta_engine.fit(sub_feats, sub_df)
                else:
                    current_meta_pred = self.meta_engine.train_and_predict(sub_feats, sub_df)

                # Refit Supervised Pinball-Loss Causal TCN Forecaster on historical window
                if t == warmup_bars or (t % (refit_interval * 3) == 0):
                    self.neural_forecaster.fit(sub_df, epochs=8)

            # --- Unified Ensemble Prediction & Entry Logic (65% LGBM + 35% Neural TCN) ---
            if position_direction == 0 and curr_regime != 2:
                if hasattr(self.meta_engine, "predict_bar"):
                    pred = self.meta_engine.predict_bar(
                        feats.iloc[[t]], df_aligned.iloc[[t]]
                    )
                else:
                    pred = locals().get("current_meta_pred") or self.meta_engine.train_and_predict(
                        feats.iloc[: t + 1], df_aligned.iloc[: t + 1]
                    )

                # Evaluate Causal TCN geometric conviction on causal slice up to bar t
                seq_slice = df_aligned.iloc[max(0, t - self.neural_forecaster.seq_len - 5) : t + 1]
                _, neural_prob = self.neural_forecaster.evaluate_directional_conviction(seq_slice)

                lgbm_prob = pred.success_probability
                fused_prob = round(0.65 * lgbm_prob + 0.35 * neural_prob, 3)

                # Apply Geometric False-Breakout, Bear-Trap & Microstructure Veto Filters
                micro_ok, _ = FrictionEvaluator.check_microstructure_execution_gate(
                    ticker, ohlcv_df=seq_slice, timestamp=curr_date
                )
                vetoed = not micro_ok
                if pred.primary_direction == 1 and neural_prob < 0.42:
                    vetoed = True
                elif pred.primary_direction == -1 and neural_prob > 0.58:
                    vetoed = True

                if not vetoed and pred.direction_label in ["BUY", "STRONG BUY", "SELL", "STRONG SELL"]:
                    current_dd = ((peak_equity - equity) / peak_equity) if peak_equity > 0 else 0.0
                    payoff_b = getattr(self.meta_engine, "payoff_ratio_b", self.pt_mult / max(self.sl_mult, 1e-4))
                    alloc = self.guardrail.evaluate_allocation(
                        current_drawdown=current_dd,
                        model_bet_size=pred.bet_size,
                        realized_annual_vol=local_vol * np.sqrt(252.0),
                        win_probability=fused_prob,
                        payoff_ratio_b=payoff_b,
                    )

                    if alloc.authorized and alloc.authorized_weight_pct > 0:
                        position_direction = pred.primary_direction
                        allocated_capital = equity * (alloc.authorized_weight_pct / 100.0)
                        position_shares = allocated_capital / curr_close
                        entry_price = curr_close
                        entry_bar = t
                        entry_date = curr_date

                        if position_direction == 1:
                            target_price = curr_close * (1.0 + self.pt_mult * local_vol)
                            stop_price = curr_close * (1.0 - self.sl_mult * local_vol)
                        else:
                            target_price = curr_close * (1.0 - self.pt_mult * local_vol)
                            stop_price = curr_close * (1.0 + self.sl_mult * local_vol)

            # Mark to Market Equity & Uninvested Cash Sweep Yield
            daily_rf = self.rf / annual_factor
            if position_direction != 0:
                invested_notional = position_shares * entry_price
                uninvested_cash = max(0.0, equity - invested_notional)
                cash_yield = uninvested_cash * daily_rf
                equity += cash_yield
                cash = equity
                unrealized = (
                    position_shares * (curr_close - entry_price)
                    if position_direction == 1
                    else position_shares * (entry_price - curr_close)
                )
                current_bar_equity = equity + unrealized
            else:
                cash_yield = equity * daily_rf
                equity += cash_yield
                cash = equity
                current_bar_equity = equity

            equity_vals[t - warmup_bars] = current_bar_equity

        # --- Compute Final Metrics (Vectorized) ---
        eq_series = pd.Series(equity_vals, index=dates_arr[warmup_bars:], name="Equity")

        final_equity = float(equity_vals[-1])
        total_return_pct = ((final_equity - self.initial_capital) / self.initial_capital) * 100.0

        # Benchmark Buy & Hold (Vectorized)
        first_p = float(close_arr[warmup_bars])
        last_p = float(close_arr[-1])
        bnh_return_pct = ((last_p - first_p) / first_p) * 100.0

        # Drawdown Series (Vectorized cumulative max)
        peak_vals = np.maximum.accumulate(equity_vals)
        drawdown_vals = (peak_vals - equity_vals) / peak_vals
        max_dd_pct = float(np.max(drawdown_vals) * 100.0)
        drawdowns = pd.Series(drawdown_vals, index=dates_arr[warmup_bars:], name="Drawdown")

        # Daily returns of equity curve
        daily_rets = eq_series.pct_change().dropna()

        if len(daily_rets) > 5 and daily_rets.std() > 1e-6:
            excess_rets = daily_rets - (self.rf / annual_factor)
            raw_sharpe = float((excess_rets.mean() / daily_rets.std()) * np.sqrt(annual_factor))
            sharpe = float(np.clip(raw_sharpe, -10.0, 10.0))

            neg_rets = daily_rets[daily_rets < 0]
            downside_std = neg_rets.std() if len(neg_rets) > 2 else daily_rets.std()
            raw_sortino = float((excess_rets.mean() / (downside_std + 1e-8)) * np.sqrt(annual_factor))
            sortino = float(np.clip(raw_sortino, -15.0, 15.0))
        else:
            sharpe = 0.0
            sortino = 0.0

        # CAGR
        days_span = max((dates_arr[-1] - dates_arr[warmup_bars]).days, 1)
        years = days_span / 365.25
        cagr = (
            float(((final_equity / self.initial_capital) ** (1.0 / max(years, 0.1)) - 1.0) * 100.0)
            if final_equity > 0
            else -100.0
        )

        calmar = (cagr / max_dd_pct) if max_dd_pct > 0 else 0.0

        # Trade Analytics (Vectorized)
        total_trades = len(trades)
        if total_trades > 0:
            rets_arr = np.array([tr.return_pct for tr in trades], dtype=np.float64)
            pnl_arr = np.array([tr.net_pnl for tr in trades], dtype=np.float64)
            winning_trades = int(np.count_nonzero(rets_arr > 0))
            losing_trades = int(np.count_nonzero(rets_arr <= 0))
            win_rate = (winning_trades / total_trades) * 100.0

            gross_wins = float(np.sum(pnl_arr[pnl_arr > 0])) if np.any(pnl_arr > 0) else 0.0
            gross_losses = float(np.abs(np.sum(pnl_arr[pnl_arr < 0]))) if np.any(pnl_arr < 0) else 0.0
            profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else (2.5 if gross_wins > 0 else 1.0)
            avg_trade_ret = float(np.mean(rets_arr))
        else:
            winning_trades = 0
            losing_trades = 0
            win_rate = 0.0
            profit_factor = 1.0
            avg_trade_ret = 0.0

        # Bailey & López de Prado (2014) Deflated Sharpe Ratio with Multiple-Testing Haircut (N_trials=10)
        if len(daily_rets) > 20 and daily_rets.std() > 1e-5:
            sk = float(skew(daily_rets))
            kt = float(kurtosis(daily_rets, fisher=False))
            sr_per_bar = sharpe / np.sqrt(annual_factor)
            # Expected max Sharpe under null across N=10 independent parameter trials
            n_trials = 10
            euler_gamma = 0.5772156649
            z1 = norm.ppf(1.0 - 1.0 / n_trials)
            z2 = norm.ppf(1.0 - 1.0 / (n_trials * np.e))
            sr0_per_bar = np.sqrt(1.0 / max(len(daily_rets) - 1, 1)) * (
                (1.0 - euler_gamma) * z1 + euler_gamma * z2
            )
            sr_var = (
                1.0
                - sk * sr_per_bar
                + ((kt - 1.0) / 4.0) * (sr_per_bar**2)
            ) / max(len(daily_rets) - 1, 1)
            dsr = float(norm.cdf((sr_per_bar - sr0_per_bar) / np.sqrt(max(sr_var, 1e-8))))
        else:
            dsr = 0.50

        return BacktestResult(
            ticker=ticker.upper(),
            period=period,
            interval=interval,
            initial_capital=self.initial_capital,
            final_equity=round(final_equity, 2),
            total_return_pct=round(total_return_pct, 2),
            buy_hold_return_pct=round(bnh_return_pct, 2),
            cagr_pct=round(cagr, 2),
            sharpe_ratio=round(sharpe, 2),
            sortino_ratio=round(sortino, 2),
            max_drawdown_pct=round(max_dd_pct, 2),
            calmar_ratio=round(calmar, 2),
            win_rate_pct=round(win_rate, 1),
            profit_factor=round(profit_factor, 2),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_trade_return_pct=round(avg_trade_ret, 2),
            equity_curve=eq_series,
            drawdown_series=drawdowns * 100.0,
            trades=trades,
            deflated_sharpe=round(dsr, 3),
            jurisdiction=jurisdiction,
        )
