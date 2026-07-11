"""
Phase 1 -- pure function tests for ingest_advanced_stats.py.

time_to_seconds() does zero validation of its own, so these tests also
document what it does when handed something other than a clean "MM:SS"
string -- that's current behavior, not a bug being introduced here.
"""

import pytest

from ingest_advanced_stats import time_to_seconds


class TestTimeToSeconds:
    def test_typical_period_time(self):
        assert time_to_seconds("05:09") == 309

    def test_full_regulation_period(self):
        assert time_to_seconds("20:00") == 1200

    def test_start_of_period_boundary(self):
        assert time_to_seconds("00:00") == 0

    def test_no_zero_padding_required(self):
        # NHL feeds are consistently zero-padded, but the function itself
        # doesn't require it -- int() parses "5" and "05" identically.
        assert time_to_seconds("5:9") == 309

    def test_overtime_minutes_beyond_a_single_period(self):
        # Not bounded to 0-20 -- e.g. a running elapsed-time clock, or a
        # multi-OT playoff game, would pass minutes > 20 through fine.
        assert time_to_seconds("65:30") == 3930

    def test_missing_colon_raises_value_error(self):
        # "2000".split(":") -> ["2000"], and unpacking one value into two
        # variables is a ValueError -- there's no graceful fallback here.
        with pytest.raises(ValueError):
            time_to_seconds("2000")

    def test_too_many_colons_raises_value_error(self):
        with pytest.raises(ValueError):
            time_to_seconds("1:02:03")

    def test_non_numeric_parts_raise_value_error(self):
        with pytest.raises(ValueError):
            time_to_seconds("ab:cd")

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            time_to_seconds("")
