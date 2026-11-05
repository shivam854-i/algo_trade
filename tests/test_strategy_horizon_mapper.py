"""Automated unit tests for HorizonMapper parameter binding and normalization."""

import pytest
from src.strategy.horizon_mapper import HorizonMapper, HorizonParameters


class TestHorizonMapper:
    """Tests for HorizonMapper and HorizonParameters."""

    def test_canonical_horizon_normalization(self):
        """Verifies normalization of varied string formats to canonical horizon names."""
        for raw in ["1h", "1hour", "intraday", "hourly", "1 hour", "1_hour", "1-hour", " 1H "]:
            assert HorizonMapper.normalize_horizon(raw) == "1 hour"

        for raw in ["1d", "1day", "daily", "eod", "1 day", "1_day", "1-day", " 1D "]:
            assert HorizonMapper.normalize_horizon(raw) == "1 day"

        for raw in ["1wk", "1w", "1week", "swing", "weekly", "1 week", "1_week", "1-week"]:
            assert HorizonMapper.normalize_horizon(raw) == "1 week"

        with pytest.raises(ValueError, match="Unsupported trading horizon"):
            HorizonMapper.normalize_horizon("1 month")

        with pytest.raises(ValueError, match="Unsupported trading horizon"):
            HorizonMapper.normalize_horizon("5m")

    def test_exact_annualization_factors(self):
        """Verifies exact analytical annualization factors across all horizons."""
        h_1h = HorizonMapper.get_parameters("1 hour")
        assert h_1h.annualization_factor == 140.2

        h_1d = HorizonMapper.get_parameters("1 day")
        assert h_1d.annualization_factor == 40.5

        h_1w = HorizonMapper.get_parameters("1 week")
        assert h_1w.annualization_factor == 15.87

    def test_bar_interval_and_lookback(self):
        """Verifies bar intervals, lookbacks, and min bars required."""
        h_1h = HorizonMapper.get_parameters("1h")
        assert h_1h.bar_interval == "5m"
        assert h_1h.secondary_interval == "1m"
        assert h_1h.lookback_period == "5d"
        assert h_1h.min_bars_required == 60

        h_1d = HorizonMapper.get_parameters("1d")
        assert h_1d.bar_interval == "1h"
        assert h_1d.secondary_interval == "15m"
        assert h_1d.lookback_period == "60d"
        assert h_1d.min_bars_required == 100

        h_1w = HorizonMapper.get_parameters("1wk")
        assert h_1w.bar_interval == "1d"
        assert h_1w.secondary_interval == "1h"
        assert h_1w.lookback_period == "2y"
        assert h_1w.min_bars_required == 150

    def test_triple_barrier_and_tcn_parameters(self):
        """Verifies barrier multipliers, TCN architectures, and holding bars."""
        h_1h = HorizonMapper.get_parameters("1 hour")
        assert h_1h.pt_vol_mult == 1.0
        assert h_1h.sl_vol_mult == 0.75
        assert h_1h.vol_floor_bar == 0.003
        assert h_1h.tcn_seq_len == 24
        assert h_1h.tcn_horizon_bars == 12
        assert h_1h.max_holding_bars == 12

        h_1d = HorizonMapper.get_parameters("1 day")
        assert h_1d.pt_vol_mult == 1.5
        assert h_1d.sl_vol_mult == 1.0
        assert h_1d.vol_floor_bar == 0.008
        assert h_1d.tcn_seq_len == 30
        assert h_1d.tcn_horizon_bars == 7
        assert h_1d.max_holding_bars == 7

        h_1w = HorizonMapper.get_parameters("1 week")
        assert h_1w.pt_vol_mult == 2.0
        assert h_1w.sl_vol_mult == 1.25
        assert h_1w.vol_floor_bar == 0.015
        assert h_1w.tcn_seq_len == 30
        assert h_1w.tcn_horizon_bars == 5
        assert h_1w.max_holding_bars == 5

    def test_session_end_policy_and_friction_mode(self):
        """Verifies session-end policy and friction mode distinctions."""
        h_1h = HorizonMapper.get_parameters("1 hour")
        assert h_1h.default_session_end_policy == "CLOSE_POSITIONS"
        assert h_1h.is_intraday_friction is True
        assert h_1h.quote_staleness_threshold_sec == 60.0

        h_1d = HorizonMapper.get_parameters("1 day")
        assert h_1d.default_session_end_policy == "CLOSE_POSITIONS"
        assert h_1d.is_intraday_friction is True
        assert h_1d.quote_staleness_threshold_sec == 300.0

        h_1w = HorizonMapper.get_parameters("1 week")
        assert h_1w.default_session_end_policy == "KEEP_OPEN"
        assert h_1w.is_intraday_friction is False
        assert h_1w.quote_staleness_threshold_sec == 1800.0

    def test_list_supported_horizons_and_serialization(self):
        """Verifies listing and dictionary serialization of parameters."""
        supported = HorizonMapper.list_supported_horizons()
        assert supported == ["1 hour", "1 day", "1 week"]

        params = HorizonMapper.get_parameters("1 day")
        d = params.to_dict()
        assert isinstance(d, dict)
        assert d["horizon_name"] == "1 day"
        assert d["annualization_factor"] == 40.5
