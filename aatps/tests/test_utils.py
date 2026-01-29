"""Tests for aatps.utils module."""

from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from unittest import TestCase

from aatps.utils import safe_int

# Note: format_isk, get_current_month_range, and get_month_range are tested
# using the implementations from views.py. When Workstream 1 is completed and
# these functions are moved to utils.py, update the imports below.
from aatps.views import format_isk, get_current_month_range, get_month_range


class TestFormatIsk(TestCase):
    """Tests for format_isk function."""

    def test_format_isk_none(self):
        """Test formatting None value."""
        self.assertEqual(format_isk(None), "0")

    def test_format_isk_zero(self):
        """Test formatting zero."""
        self.assertEqual(format_isk(0), "0")

    def test_format_isk_small_value(self):
        """Test formatting small values (no suffix)."""
        self.assertEqual(format_isk(500), "500")

    def test_format_isk_thousands(self):
        """Test formatting thousands (K suffix)."""
        self.assertEqual(format_isk(5000), "5.00K")
        self.assertEqual(format_isk(999999), "1000.00K")

    def test_format_isk_millions(self):
        """Test formatting millions (M suffix)."""
        self.assertEqual(format_isk(1_000_000), "1.00M")
        self.assertEqual(format_isk(5_500_000), "5.50M")

    def test_format_isk_billions(self):
        """Test formatting billions (B suffix)."""
        self.assertEqual(format_isk(1_000_000_000), "1.00B")
        self.assertEqual(format_isk(2_500_000_000), "2.50B")

    def test_format_isk_trillions(self):
        """Test formatting trillions (T suffix)."""
        self.assertEqual(format_isk(1_000_000_000_000), "1.00T")
        self.assertEqual(format_isk(1_500_000_000_000), "1.50T")

    def test_format_isk_decimal(self):
        """Test formatting Decimal values."""
        self.assertEqual(format_isk(Decimal("1500000000")), "1.50B")

    def test_format_isk_float(self):
        """Test formatting float values."""
        self.assertEqual(format_isk(1500000000.0), "1.50B")


class TestGetCurrentMonthRange(TestCase):
    """Tests for get_current_month_range function."""

    def test_returns_tuple(self):
        """Test that function returns a tuple of two datetimes."""
        result = get_current_month_range()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], datetime)
        self.assertIsInstance(result[1], datetime)

    def test_start_is_first_day(self):
        """Test that start is the first day of the month at midnight."""
        start, _ = get_current_month_range()
        self.assertEqual(start.day, 1)
        self.assertEqual(start.hour, 0)
        self.assertEqual(start.minute, 0)
        self.assertEqual(start.second, 0)
        self.assertEqual(start.microsecond, 0)

    def test_end_is_last_day(self):
        """Test that end is the last day of the month at 23:59:59."""
        _, end = get_current_month_range()
        self.assertEqual(end.hour, 23)
        self.assertEqual(end.minute, 59)
        self.assertEqual(end.second, 59)
        self.assertEqual(end.microsecond, 999999)

    def test_same_month_and_year(self):
        """Test that start and end are in the same month."""
        start, end = get_current_month_range()
        self.assertEqual(start.month, end.month)
        self.assertEqual(start.year, end.year)

    def test_timezone_aware(self):
        """Test that returned datetimes are timezone-aware (UTC)."""
        start, end = get_current_month_range()
        self.assertIsNotNone(start.tzinfo)
        self.assertIsNotNone(end.tzinfo)


class TestGetMonthRange(TestCase):
    """Tests for get_month_range function."""

    def test_specific_month(self):
        """Test getting range for a specific month."""
        start, end = get_month_range(2024, 6)
        self.assertEqual(start.year, 2024)
        self.assertEqual(start.month, 6)
        self.assertEqual(start.day, 1)
        self.assertEqual(end.day, 30)  # June has 30 days

    def test_february_leap_year(self):
        """Test February in a leap year."""
        start, end = get_month_range(2024, 2)
        self.assertEqual(end.day, 29)  # 2024 is a leap year

    def test_february_non_leap_year(self):
        """Test February in a non-leap year."""
        start, end = get_month_range(2023, 2)
        self.assertEqual(end.day, 28)

    def test_january_31_days(self):
        """Test January has 31 days."""
        start, end = get_month_range(2024, 1)
        self.assertEqual(end.day, 31)

    def test_december_31_days(self):
        """Test December has 31 days."""
        start, end = get_month_range(2024, 12)
        self.assertEqual(end.day, 31)

    def test_timezone_aware(self):
        """Test that returned datetimes are timezone-aware."""
        start, end = get_month_range(2024, 6)
        self.assertIsNotNone(start.tzinfo)
        self.assertIsNotNone(end.tzinfo)

    def test_start_time_is_midnight(self):
        """Test that start time is midnight."""
        start, _ = get_month_range(2024, 6)
        self.assertEqual(start.hour, 0)
        self.assertEqual(start.minute, 0)
        self.assertEqual(start.second, 0)
        self.assertEqual(start.microsecond, 0)

    def test_end_time_is_end_of_day(self):
        """Test that end time is end of day."""
        _, end = get_month_range(2024, 6)
        self.assertEqual(end.hour, 23)
        self.assertEqual(end.minute, 59)
        self.assertEqual(end.second, 59)
        self.assertEqual(end.microsecond, 999999)


class TestSafeInt(TestCase):
    """Tests for safe_int function."""

    def test_valid_int_string(self):
        """Test parsing valid integer string."""
        self.assertEqual(safe_int("10", default=5), 10)

    def test_valid_int(self):
        """Test parsing actual integer."""
        self.assertEqual(safe_int(10, default=5), 10)

    def test_invalid_string_returns_default(self):
        """Test that invalid string returns default."""
        self.assertEqual(safe_int("abc", default=5), 5)

    def test_none_returns_default(self):
        """Test that None returns default."""
        self.assertEqual(safe_int(None, default=5), 5)

    def test_empty_string_returns_default(self):
        """Test that empty string returns default."""
        self.assertEqual(safe_int("", default=5), 5)

    def test_float_string_returns_default(self):
        """Test that float string returns default (not truncated)."""
        self.assertEqual(safe_int("10.5", default=5), 5)

    def test_min_val_enforced(self):
        """Test that minimum value is enforced."""
        self.assertEqual(safe_int("-5", default=0, min_val=0), 0)
        self.assertEqual(safe_int("3", default=0, min_val=5), 5)

    def test_max_val_enforced(self):
        """Test that maximum value is enforced."""
        self.assertEqual(safe_int("999", default=0, max_val=100), 100)

    def test_both_bounds(self):
        """Test both min and max bounds."""
        self.assertEqual(safe_int("50", default=0, min_val=10, max_val=100), 50)
        self.assertEqual(safe_int("5", default=0, min_val=10, max_val=100), 10)
        self.assertEqual(safe_int("150", default=0, min_val=10, max_val=100), 100)

    def test_negative_value_with_default_min(self):
        """Test that negative values are clamped to default min (0)."""
        self.assertEqual(safe_int("-10", default=5), 0)

    def test_no_max_val(self):
        """Test that no max_val means unlimited."""
        self.assertEqual(safe_int("1000000", default=5, min_val=0), 1000000)

    def test_whitespace_returns_default(self):
        """Test that whitespace-only string returns default."""
        self.assertEqual(safe_int("  ", default=5), 5)
