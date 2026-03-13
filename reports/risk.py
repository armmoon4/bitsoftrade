"""
Reports — Risk report data.
"""
from __future__ import annotations

from django.db.models import Avg, F, Max, Min, Sum
from django.db.models.functions import TruncDate

from .utils import build_daily_rows, fmt_date


def get_risk_report_data(qs, capital_base_fallback=None) -> dict:
    if not qs.count():
        return {"message": "No trades in the selected range."}

    # Capital / quantity aggregates
    tr_cap = qs.annotate(capital=F("entry_price") * F("quantity"))
    cap_agg = tr_cap.aggregate(
        max_capital_used=Max("capital"),
        min_capital_used=Min("capital"),
        avg_capital_used=Avg("capital"),
        max_qty=Max("quantity"),
        avg_qty=Avg("quantity"),
    )

    # Daily P&L series
    daily_rows = build_daily_rows(qs)
    daily_pnls = [
        {"date": fmt_date(row["day"]), "pnl": float(row["daily_pnl"] or 0)}
        for row in daily_rows
    ]

    worst_losing_day = min((d["pnl"] for d in daily_pnls), default=0)

    # Cumulative + drawdown
    drawdown_curve, drawdowns, recovery_times = _compute_drawdown(daily_pnls)

    max_dd = max(drawdowns, default=0)
    avg_dd = sum(drawdowns) / len(drawdowns) if drawdowns else 0
    avg_recovery_time = round(sum(recovery_times) / len(recovery_times)) if recovery_times else 0

    base_capital = float(capital_base_fallback or cap_agg["max_capital_used"] or 1)
    volatility_pct = _return_volatility(daily_pnls, base_capital)

    max_dd_pct = (max_dd / base_capital) * 100 if base_capital else 0
    avg_dd_pct = (avg_dd / base_capital) * 100 if base_capital else 0

    return {
        "max_drawdown": {
            "amount": round(max_dd, 2),
            "percentage": round(max_dd_pct, 2),
        },
        "average_drawdown": {
            "amount": round(avg_dd, 2),
            "percentage": round(avg_dd_pct, 2),
        },
        "worst_losing_day": round(worst_losing_day, 2),
        "recovery_time": avg_recovery_time,
        "return_volatility": round(volatility_pct, 2),
        "drawdown_curve": drawdown_curve,
        "max_capital_used": cap_agg["max_capital_used"],
        "min_capital_used": cap_agg["min_capital_used"],
        "avg_capital_used": cap_agg["avg_capital_used"],
        "max_quantity": cap_agg["max_qty"],
        "avg_quantity": cap_agg["avg_qty"],
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _compute_drawdown(
    daily_pnls: list[dict],
) -> tuple[list[dict], list[float], list[int]]:
    """
    Walk through cumulative P&L and compute per-day drawdown.

    Returns:
        drawdown_curve   – [{'date': str, 'drawdown': float}, ...]
        drawdowns        – list of non-zero drawdown values (for avg calculation)
        recovery_times   – list of session counts spent in each drawdown
    """
    peak = running = 0.0
    drawdown_curve: list[dict] = []
    drawdowns: list[float] = []
    recovery_times: list[int] = []
    in_drawdown = False
    current_recovery = 0

    for row in daily_pnls:
        running += row["pnl"]

        if running > peak:
            peak = running
            if in_drawdown:
                recovery_times.append(current_recovery)
                in_drawdown = False
                current_recovery = 0
        else:
            in_drawdown = True
            current_recovery += 1

        dd = peak - running
        drawdown_curve.append({"date": row["date"], "drawdown": round(dd, 2)})
        if dd > 0:
            drawdowns.append(dd)

    return drawdown_curve, drawdowns, recovery_times


def _return_volatility(daily_pnls: list[dict], base_capital: float) -> float:
    returns = [d["pnl"] / base_capital for d in daily_pnls]
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return (variance ** 0.5) * 100