"""Statutory Friction, Almgren-Chriss L2 Slippage & Microstructure Hurdle Module.

Models real-world transaction costs, exchange fees, statutory taxes (holding-period
aware NSE STT/GST, SEC Section 31, Stamp Duty), dynamic Almgren-Chriss square-root
market impact, Forex 17:00 EST rollover spread-spike gates, and CME Gold LULD /
stop-run liquidity-sweep protections.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class MarketFrictionProfile:
    jurisdiction: str
    stt_rate: float  # Primary statutory tax rate (intraday sell for NSE, SEC fee for US)
    exchange_fee_rate: float
    stamp_duty_rate: float
    gst_rate: float
    brokerage_per_share: float  # Rate or per-share fee (dimensionally separated in evaluator)
    taker_fee_rate: float
    delivery_stt_rate: float = 0.0  # Multi-day delivery STT rate (0.10% on both legs for NSE)
    delivery_stamp_rate: float = 0.0  # Multi-day delivery stamp duty (0.015% on buy for NSE)
    slippage_bps: float = 1.5  # Baseline L2 order-book sweep half-spread slippage (bps per leg)
    impact_eta: float = 0.35  # Almgren-Chriss temporary market impact coefficient


PROFILES = {
    "US": MarketFrictionProfile(
        jurisdiction="US",
        stt_rate=0.0000278,  # SEC Section 31 (sell leg)
        exchange_fee_rate=0.000015,  # FINRA TAF + clearing
        stamp_duty_rate=0.0,
        gst_rate=0.0,
        brokerage_per_share=0.005,  # $0.005 per share (normalized by share price)
        taker_fee_rate=0.0002,  # 2 bps taker
        slippage_bps=1.0,
        impact_eta=0.30,
    ),
    "NSE_CASH": MarketFrictionProfile(
        jurisdiction="NSE_CASH",
        stt_rate=0.00025,  # 0.025% STT on intraday sell
        exchange_fee_rate=0.0000325,  # NSE turnover charge (0.00325%)
        stamp_duty_rate=0.00003,  # 0.003% intraday Stamp duty on buy
        gst_rate=0.18,  # 18% GST on brokerage + exchange + SEBI
        brokerage_per_share=0.0003,  # 0.03% (3 bps) brokerage rate cap
        taker_fee_rate=0.0,
        delivery_stt_rate=0.001,  # 0.10% STT on BOTH buy and sell for multi-day delivery
        delivery_stamp_rate=0.00015,  # 0.015% Stamp duty on buy for delivery
        slippage_bps=2.0,
        impact_eta=0.45,
    ),
    "BSE_CASH": MarketFrictionProfile(
        jurisdiction="BSE_CASH",
        stt_rate=0.00025,  # 0.025% STT on intraday sell
        exchange_fee_rate=0.0000375,  # BSE turnover charge (0.00375%)
        stamp_duty_rate=0.00003,  # 0.003% intraday Stamp duty on buy
        gst_rate=0.18,  # 18% GST on brokerage + exchange + SEBI
        brokerage_per_share=0.0003,  # 0.03% (3 bps) brokerage rate cap
        taker_fee_rate=0.0,
        delivery_stt_rate=0.001,  # 0.10% STT on BOTH buy and sell for multi-day delivery
        delivery_stamp_rate=0.00015,  # 0.015% Stamp duty on buy for delivery
        slippage_bps=2.2,
        impact_eta=0.48,
    ),
    "CRYPTO": MarketFrictionProfile(
        jurisdiction="CRYPTO",
        stt_rate=0.0,
        exchange_fee_rate=0.0,
        stamp_duty_rate=0.0,
        gst_rate=0.0,
        brokerage_per_share=0.0,
        taker_fee_rate=0.0004,  # 4 bps taker per leg
        slippage_bps=2.5,
        impact_eta=0.50,
    ),
    "FOREX": MarketFrictionProfile(
        jurisdiction="FOREX",
        stt_rate=0.0,
        exchange_fee_rate=0.0,
        stamp_duty_rate=0.0,
        gst_rate=0.0,
        brokerage_per_share=0.0,
        taker_fee_rate=0.0001,  # ~1.0 bps ECN commission per leg
        slippage_bps=0.8,  # ~0.8 bps institutional Top-of-Book half-spread
        impact_eta=0.25,
    ),
    "COMMODITY": MarketFrictionProfile(
        jurisdiction="COMMODITY",
        stt_rate=0.0,
        exchange_fee_rate=0.00005,  # CME COMEX clearing/exchange fee
        stamp_duty_rate=0.0,
        gst_rate=0.0,
        brokerage_per_share=0.00005,  # 0.5 bps futures brokerage equivalent
        taker_fee_rate=0.0001,  # 1.0 bps taker fee
        slippage_bps=1.2,  # CME Gold/Crude tick sweep slippage
        impact_eta=0.35,
    ),
}


class FrictionEvaluator:
    """Calculates dimensionally consistent round-trip transaction costs, Almgren-Chriss impact, and microstructure gates."""

    @classmethod
    def get_profile(cls, ticker: str) -> MarketFrictionProfile:
        ticker = ticker.upper()
        if ticker.endswith(".BO") or ticker.startswith(("^BS", "BSE:")):
            return PROFILES.get("BSE_CASH", PROFILES["NSE_CASH"])
        elif (
            ticker.endswith(".NS")
            or ticker.startswith("^NSE")
        ):
            return PROFILES["NSE_CASH"]
        elif ticker.endswith("=X") or ticker in ["DX-Y.NYB", "UUP"]:
            return PROFILES["FOREX"]
        elif ticker.endswith("=F") or ticker in ["GLD", "SLV", "USO", "UNG"]:
            return PROFILES["COMMODITY"]
        elif "-USD" in ticker or "-USDT" in ticker:
            return PROFILES["CRYPTO"]
        else:
            return PROFILES["US"]

    @classmethod
    def compute_almgren_chriss_slippage_bps(
        cls,
        ticker: str,
        order_notional: float = 10000.0,
        daily_dollar_volume: float = 5e7,
        annualized_vol: float = 0.20,
        is_rollover_trough: bool = False,
    ) -> float:
        """Computes dynamic round-trip L2 book sweep + Almgren-Chriss square-root market impact (bps).

        Formula:
            Slippage_RT = 2 * [ half_spread_bps * rollover_mult + eta * sigma_daily * sqrt(Q / ADV) * 10000 ]
        """
        p = cls.get_profile(ticker)
        adv = max(float(daily_dollar_volume), 1e5)
        q_order = max(float(order_notional), 100.0)
        sigma_daily = max(float(annualized_vol), 0.05) / np.sqrt(252.0)

        participation_rate = min(q_order / adv, 0.25)
        sqrt_impact_bps = p.impact_eta * sigma_daily * np.sqrt(participation_rate) * 10000.0

        # Forex 17:00 EST rollover liquidity trough widens ECN spreads by 4x
        spread_mult = 4.0 if (is_rollover_trough and p.jurisdiction == "FOREX") else 1.0
        per_leg_bps = (p.slippage_bps * spread_mult) + sqrt_impact_bps
        return round(float(per_leg_bps * 2.0), 2)

    @classmethod
    def check_microstructure_execution_gate(
        cls,
        ticker: str,
        ohlcv_df: Optional[pd.DataFrame] = None,
        timestamp: Optional[pd.Timestamp] = None,
    ) -> Tuple[bool, str]:
        """Evaluates Phase 3 high-volatility microstructure circuit breakers for Gold (GC=F) & Forex (EURUSD=X).

        Checks:
            1. Forex 17:00 EST (21:00-22:00 UTC) daily settlement rollover trough (400% spread widening).
            2. CME Gold / Commodity LULD price band halt (>5.5% single-bar shock).
            3. Liquidity-Sweep / Stop-Run Exhaustion Filter (extreme single-bar rejection wick >75% of range
               on >2.5x normal bar range).

        Returns:
            (allowed_to_trade: bool, status_reason: str)
        """
        p = cls.get_profile(ticker)

        if timestamp is None and ohlcv_df is not None and not ohlcv_df.empty:
            last_idx = ohlcv_df.index[-1]
            if isinstance(last_idx, pd.Timestamp):
                timestamp = last_idx

        # 1. Forex 17:00 EST (21:00-22:00 UTC) Intraday Rollover Gate
        if p.jurisdiction == "FOREX" and timestamp is not None:
            # Only applies to intraday bars that carry hour granularity
            if getattr(timestamp, "hour", 0) != 0 or getattr(timestamp, "minute", 0) != 0:
                ts_utc = timestamp.tz_convert("UTC") if timestamp.tzinfo is not None else timestamp
                if ts_utc.hour == 21 or (ts_utc.hour == 22 and ts_utc.minute <= 15):
                    return (
                        False,
                        "MICROSTRUCTURE VETO: Forex 17:00 EST (21:00 UTC) rollover liquidity trough (400% spread widening).",
                    )

        # 2. CME Commodity / Gold LULD & Stop-Run Liquidity Sweep Checks
        if ohlcv_df is not None and len(ohlcv_df) >= 15:
            closes = ohlcv_df["Close"].values.astype(np.float64)
            highs = ohlcv_df["High"].values.astype(np.float64)
            lows = ohlcv_df["Low"].values.astype(np.float64)
            opens = ohlcv_df["Open"].values.astype(np.float64)

            last_ret = abs((closes[-1] - closes[-2]) / max(closes[-2], 1e-8))
            if p.jurisdiction == "COMMODITY" and last_ret >= 0.055:
                return (
                    False,
                    f"MICROSTRUCTURE VETO: CME LULD price velocity limit breached ({last_ret:.2%} bar shock).",
                )

            # Check single-bar liquidity sweep / stop-run wick exhaustion
            ranges = np.maximum(highs - lows, 1e-8)
            avg_range = float(np.median(ranges[-15:-1]))
            curr_range = float(ranges[-1])
            body = abs(closes[-1] - opens[-1])
            wick_fraction = (curr_range - body) / curr_range

            if curr_range > 2.6 * max(avg_range, 1e-8) and wick_fraction > 0.78:
                return (
                    False,
                    f"MICROSTRUCTURE VETO: Stop-run liquidity sweep detected (range {curr_range / max(avg_range, 1e-8):.1f}x median, {wick_fraction:.0%} wick rejection).",
                )

        return True, "MICROSTRUCTURE_CLEAR"

    @classmethod
    def calculate_round_trip_friction_bps(
        cls,
        ticker: str,
        is_intraday: bool = False,
        reference_price: float = 100.0,
        include_slippage: bool = True,
        order_notional: float = 10000.0,
        daily_dollar_volume: float = 5e7,
        annualized_vol: float = 0.20,
    ) -> float:
        """Computes total round-trip statutory + Almgren-Chriss L2 slippage hurdle in basis points (bps).

        Corrects dimensional unit addition (converting $/share brokerage by reference_price)
        and distinguishes multi-day delivery vs. intraday NSE STT schedules.
        """
        p = cls.get_profile(ticker)
        ref_p = max(float(reference_price), 1.0)
        slippage_round_trip_bps = (
            cls.compute_almgren_chriss_slippage_bps(
                ticker,
                order_notional=order_notional,
                daily_dollar_volume=daily_dollar_volume,
                annualized_vol=annualized_vol,
            )
            if include_slippage
            else 0.0
        )

        if p.jurisdiction == "NSE_CASH":
            sebi_fee_rate = 0.000001  # ₹10 per crore (0.1 bps)
            if is_intraday:
                buy_frictions = (
                    p.stamp_duty_rate
                    + p.exchange_fee_rate
                    + sebi_fee_rate
                    + p.brokerage_per_share
                    + (p.exchange_fee_rate + sebi_fee_rate + p.brokerage_per_share) * p.gst_rate
                )
                sell_frictions = (
                    p.stt_rate
                    + p.exchange_fee_rate
                    + sebi_fee_rate
                    + p.brokerage_per_share
                    + (p.exchange_fee_rate + sebi_fee_rate + p.brokerage_per_share) * p.gst_rate
                )
            else:
                buy_frictions = (
                    p.delivery_stt_rate
                    + p.delivery_stamp_rate
                    + p.exchange_fee_rate
                    + sebi_fee_rate
                    + p.brokerage_per_share
                    + (p.exchange_fee_rate + sebi_fee_rate + p.brokerage_per_share) * p.gst_rate
                )
                sell_frictions = (
                    p.delivery_stt_rate
                    + p.exchange_fee_rate
                    + sebi_fee_rate
                    + p.brokerage_per_share
                    + (p.exchange_fee_rate + sebi_fee_rate + p.brokerage_per_share) * p.gst_rate
                )
            total_bps = (buy_frictions + sell_frictions) * 10000.0 + slippage_round_trip_bps
            return round(total_bps, 2)

        elif p.jurisdiction == "US":
            per_share_rate_round_trip = (p.brokerage_per_share * 2.0) / ref_p
            statutory_and_fees = (
                p.stt_rate + (p.exchange_fee_rate + p.taker_fee_rate) * 2.0 + per_share_rate_round_trip
            )
            total_bps = statutory_and_fees * 10000.0 + slippage_round_trip_bps
            return round(total_bps, 2)

        elif p.jurisdiction == "CRYPTO":
            total_bps = (p.taker_fee_rate * 2.0) * 10000.0 + slippage_round_trip_bps
            return round(total_bps, 2)

        elif p.jurisdiction == "FOREX":
            total_bps = (p.taker_fee_rate * 2.0) * 10000.0 + slippage_round_trip_bps
            return round(total_bps, 2)

        elif p.jurisdiction == "COMMODITY":
            total_bps = (
                (p.exchange_fee_rate + p.brokerage_per_share + p.taker_fee_rate) * 2.0 * 10000.0
                + slippage_round_trip_bps
            )
            return round(total_bps, 2)

        return 5.0

    @classmethod
    def validate_alpha_hurdle(
        cls,
        ticker: str,
        gross_expected_alpha_pct: float,
        hurdle_safety_mult: float = 1.5,
        is_intraday: bool = False,
        reference_price: float = 100.0,
    ) -> Tuple[bool, float, float]:
        """Checks if gross expected alpha exceeds 1.5x (statutory friction + Almgren-Chriss L2 slippage).

        Returns:
            (passes_hurdle, friction_pct, net_expected_alpha_pct)
        """
        friction_bps = cls.calculate_round_trip_friction_bps(
            ticker, is_intraday=is_intraday, reference_price=reference_price
        )
        friction_pct = friction_bps / 100.0  # Convert bps to percent (100 bps = 1.0%)

        net_alpha_pct = gross_expected_alpha_pct - friction_pct
        passes = gross_expected_alpha_pct >= (hurdle_safety_mult * friction_pct)

        return bool(passes), round(friction_pct, 4), round(net_alpha_pct, 3)
