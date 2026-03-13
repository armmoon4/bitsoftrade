"""
Reports — shared helpers used across multiple report modules.
"""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.db.models import F

if TYPE_CHECKING:
    from django.db.models import QuerySet


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def fmt_date(d) -> str:
    """Format a date as 'Mon D' without zero-padding (cross-platform)."""
    if hasattr(d, "strftime"):
        return d.strftime("%b ") + str(d.day)
    return str(d)


# ---------------------------------------------------------------------------
# Streak calculation
# ---------------------------------------------------------------------------

def consecutive_streaks(values: list[float]) -> tuple[int, int]:
    """Return (max_winning_streak, max_losing_streak) from a list of daily P&Ls."""
    max_win = max_loss = cur_win = cur_loss = 0
    for v in values:
        if v > 0:
            cur_win += 1
            cur_loss = 0
        elif v < 0:
            cur_loss += 1
            cur_win = 0
        else:
            cur_win = cur_loss = 0
        max_win = max(max_win, cur_win)
        max_loss = max(max_loss, cur_loss)
    return max_win, max_loss


# ---------------------------------------------------------------------------
# Daily aggregation
# ---------------------------------------------------------------------------

def build_daily_rows(qs: "QuerySet") -> list[dict]:
    """
    Aggregate a trade queryset to one row per calendar day.

    Returns a list of dicts sorted by day:
        [{'day': date, 'daily_pnl': Decimal, 'daily_volume': Decimal}, ...]
    """
    rows = (
        qs.filter(total_pnl__isnull=False)
        .annotate(day=TruncDate("trade_date"))
        .values("day")
        .annotate(
            daily_pnl=Sum("total_pnl"),
            daily_volume=Sum(F("entry_price") * F("quantity")),
        )
        .order_by("day")
    )
    return list(rows)


def build_cumulative_and_daily_series(
    daily_rows: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Convert raw daily rows into two chart-ready series.

    Returns:
        net_pnl_cumulative  – [{'date': str, 'pnl': float}, ...]
        net_daily_pnl       – [{'date': str, 'pnl': float}, ...]
    """
    cumulative: list[dict] = []
    daily: list[dict] = []
    running = 0.0

    for row in daily_rows:
        label = fmt_date(row["day"])
        val = float(row["daily_pnl"] or 0)
        running += val
        cumulative.append({"date": label, "pnl": round(running, 2)})
        daily.append({"date": label, "pnl": round(val, 2)})

    return cumulative, daily


# ---------------------------------------------------------------------------
# Win-rate helper
# ---------------------------------------------------------------------------

def win_rate(qs: "QuerySet") -> float:
    """Return win-rate percentage (0-100) for a trade queryset."""
    total = qs.count()
    if not total:
        return 0.0
    wins = qs.filter(total_pnl__gt=0).count()
    return round((wins / total) * 100, 1)


# ---------------------------------------------------------------------------
# Profit-factor helper
# ---------------------------------------------------------------------------

def profit_factor(gross_profit: Decimal, gross_loss: Decimal, ndigits: int = 2) -> float:
    """Return profit factor, safe against zero gross_loss."""
    gl = abs(gross_loss or Decimal("0"))
    gp = gross_profit or Decimal("0")
    return round(float(gp / gl), ndigits) if gl else 0.0