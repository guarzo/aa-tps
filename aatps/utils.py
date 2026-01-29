"""Shared utilities for AA TPS."""

# Standard Library
from calendar import monthrange
from datetime import datetime
from datetime import timezone as dt_timezone
from decimal import Decimal
from typing import Any, Union


def get_current_month_range() -> tuple[datetime, datetime]:
    """
    Return (start_datetime, end_datetime) for current month in UTC.

    Returns:
        Tuple of (start, end) where:
        - start: First day of current month at 00:00:00.000000 UTC
        - end: Last day of current month at 23:59:59.999999 UTC
    """
    now = datetime.now(dt_timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    _, last_day = monthrange(now.year, now.month)
    end = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
    return start, end


def get_month_range(year: int, month: int) -> tuple[datetime, datetime]:
    """
    Return (start_datetime, end_datetime) for a specific month in UTC.

    Args:
        year: The year (e.g., 2024)
        month: The month (1-12)

    Returns:
        Tuple of (start, end) datetimes for the specified month

    Raises:
        ValueError: If month is not 1-12 or year/month combination is invalid
    """
    if not 1 <= month <= 12:
        raise ValueError(f"Month must be 1-12, got {month}")
    start = datetime(year, month, 1, 0, 0, 0, 0, tzinfo=dt_timezone.utc)
    _, last_day = monthrange(year, month)
    end = datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=dt_timezone.utc)
    return start, end


def format_isk(value: Union[Decimal, float, int] | None) -> str:
    """
    Format ISK value for display with appropriate suffix.

    Args:
        value: The ISK value to format. Can be Decimal, float, int, or None.

    Returns:
        Formatted string with T/B/M/K suffix as appropriate.

    Examples:
        >>> format_isk(1_500_000_000_000)
        '1.50T'
        >>> format_isk(2_500_000_000)
        '2.50B'
        >>> format_isk(None)
        '0'
    """
    if value is None:
        return "0"
    value = float(value)
    if value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}T"
    elif value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    elif value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return f"{value:.0f}"


def safe_int(value: Any, default: int, min_val: int = 0, max_val: int | None = None) -> int:
    """
    Safely parse an integer from user input with bounds checking.

    Args:
        value: The value to parse (typically from request.GET)
        default: Default value if parsing fails
        min_val: Minimum allowed value (default 0)
        max_val: Maximum allowed value (None for no limit)

    Returns:
        Parsed and bounded integer value

    Examples:
        >>> safe_int('10', default=5, max_val=100)
        10
        >>> safe_int('invalid', default=5, max_val=100)
        5
        >>> safe_int('999', default=5, max_val=100)
        100
    """
    try:
        result = int(value)
    except (ValueError, TypeError):
        return default

    result = max(min_val, result)
    if max_val is not None:
        result = min(max_val, result)
    return result
