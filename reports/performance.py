"""
Reports — Performance report data.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.db.models.functions import ExtractHour

from .utils import (
    build_cumulative_and_daily_series,
    build_daily_rows,
    consecutive_streaks,
    fmt_date,
    profit_factor,
    win_rate,
)


def get_performance_report_data(qs) -> dict:
    total = qs.count()
    if not total:
        return {"message": "No trades in the selected range."}

    agg = qs.aggregate(
        net_pnl=Sum("total_pnl"),
        avg_trade_pnl=Avg("total_pnl"),
        largest_win=Max("total_pnl"),
        largest_loss=Min("total_pnl"),
        gross_profit=Sum("total_pnl", filter=Q(total_pnl__gt=0)),
        gross_loss=Sum("total_pnl", filter=Q(total_pnl__lt=0)),
        avg_win=Avg("total_pnl", filter=Q(total_pnl__gt=0)),
        avg_loss=Avg("total_pnl", filter=Q(total_pnl__lt=0)),
    )

    wr = win_rate(qs)
    pf = profit_factor(agg["gross_profit"] or Decimal("0"), agg["gross_loss"] or Decimal("0"))
    expectancy = round(float(agg["net_pnl"] / total), 2) if total else 0

    # ------------------------------------------------------------------ daily
    daily_rows = build_daily_rows(qs)
    net_pnl_cumulative, net_daily_pnl = build_cumulative_and_daily_series(daily_rows)

    total_days = len(daily_rows)
    winning_days = sum(1 for d in daily_rows if d["daily_pnl"] > 0)
    losing_days = sum(1 for d in daily_rows if d["daily_pnl"] < 0)
    breakeven_days = total_days - winning_days - losing_days

    avg_daily_pnl = round(float(agg["net_pnl"]) / total_days, 2) if total_days else 0
    total_vol = sum((d["daily_volume"] or 0) for d in daily_rows)
    avg_daily_volume = float(total_vol / total_days) if total_days else 0

    daily_pnl_values = [float(d["daily_pnl"]) for d in daily_rows]
    consecutive_wins, consecutive_losses = consecutive_streaks(daily_pnl_values)

    # --------------------------------------------------------- best/worst day
    if daily_rows:
        sorted_days = sorted(daily_rows, key=lambda x: x["daily_pnl"] or 0)
        most_profitable_day = fmt_date(sorted_days[-1]["day"])
        least_profitable_day = fmt_date(sorted_days[0]["day"])
    else:
        most_profitable_day = least_profitable_day = "N/A"

    # ----------------------------------------------------- best trading hour
    best_hour = _best_trading_hour(qs)

    # ------------------------------------------------- market session breakdown
    market_session_breakdown, best_session = _session_breakdown(qs)

    # -------------------------------------------- strategy effectiveness
    strategy_effectiveness = _strategy_effectiveness(qs)

    # ------------------------------------------------- capital / quantity
    capital_usage = _capital_usage(qs)
    quantity_analysis = _quantity_analysis(qs)

    # ------------------------------------------------- symbol frequency
    symbol_frequency = _symbol_frequency(qs)

    return {
        "performance": {
            "total_pnl": agg["net_pnl"],
            "win_rate": wr,
            "profit_factor": pf,
            "trade_expectancy": expectancy,
            "avg_trade_pnl": agg["avg_trade_pnl"],
            "total_trades": total,
        },
        "net_pnl_cumulative": net_pnl_cumulative,
        "net_daily_pnl": net_daily_pnl,
        "performance_breakdown": {
            "trade_based_metrics": {
                "total_pnl": agg["net_pnl"],
                "average_winning_trade": agg["avg_win"],
                "average_losing_trade": agg["avg_loss"],
                "largest_winning_trade": agg["largest_win"],
                "largest_losing_trade": agg["largest_loss"],
                "profit_factor": pf,
                "trade_expectancy": expectancy,
            },
            "day_based_metrics": {
                "total_trading_days": total_days,
                "winning_days": winning_days,
                "losing_days": losing_days,
                "breakeven_days": breakeven_days,
                "avg_daily_pnl": avg_daily_pnl,
                "avg_daily_volume": avg_daily_volume,
                "avg_holding_time": "N/A",
            },
        },
        "time_metrics": {
            "trading_days": total_days,
            "consecutive_win_days": consecutive_wins,
            "consecutive_loss_days": consecutive_losses,
            "most_profitable_day": most_profitable_day,
            "least_profitable_day": least_profitable_day,
        },
        "duration_insights": {
            "avg_holding_duration": "N/A",
            "best_session": best_session,
            "best_hour": best_hour,
            "most_common_duration": "N/A",
            "trades_count": total,
        },
        "hold_time_vs_win_rate": [],
        "market_session_breakdown": market_session_breakdown,
        "strategy_effectiveness": strategy_effectiveness,
        "symbol_frequency": symbol_frequency,
        "capital_usage": capital_usage,
        "quantity_analysis": quantity_analysis,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_SESSIONS = [
    ("Early Morning", 555, 660),
    ("Late Morning", 660, 750),
    ("Midday", 750, 810),
    ("Afternoon", 810, 870),
    ("Closing", 870, 931),  # inclusive upper bound kept as < 931
]


def _best_trading_hour(qs) -> str:
    hour_pnl = (
        qs.filter(trade_time__isnull=False)
        .annotate(hour=ExtractHour("trade_time"))
        .values("hour")
        .annotate(avg_pnl=Avg("total_pnl"))
        .order_by("-avg_pnl")
    )
    best = hour_pnl.first()
    if not best or best["hour"] is None:
        return "N/A"
    hr = best["hour"]
    ampm = "AM" if hr < 12 else "PM"
    hr12 = hr if hr <= 12 else hr - 12
    hr12 = 12 if hr12 == 0 else hr12
    return f"{hr12}:00 {ampm}"


def _session_breakdown(qs) -> tuple[list[dict], str]:
    counts = {name: 0 for name, *_ in _SESSIONS}
    trades_with_time = list(qs.filter(trade_time__isnull=False).values("trade_time"))

    for t in trades_with_time:
        tt = t["trade_time"]
        if not tt:
            continue
        mins = tt.hour * 60 + tt.minute
        for name, lo, hi in _SESSIONS:
            if lo <= mins < hi:
                counts[name] += 1
                break

    total_timed = len(trades_with_time)
    breakdown = [
        {
            "session": name,
            "percent_trades": round(count / total_timed * 100) if total_timed else 0,
        }
        for name, count in counts.items()
    ]
    best_session = max(counts, key=counts.get) if total_timed else "N/A"
    return breakdown, best_session


def _strategy_effectiveness(qs) -> list[dict]:
    rows = (
        qs.filter(strategy__isnull=False)
        .values("strategy__strategy_name")
        .annotate(total_trades=Count("id"), wins=Count("id", filter=Q(total_pnl__gt=0)))
    )
    return [
        {
            "strategy": row["strategy__strategy_name"] or "Unknown",
            "win_rate": round(row["wins"] / row["total_trades"] * 100, 2) if row["total_trades"] else 0,
        }
        for row in rows
    ]


def _capital_usage(qs) -> dict:
    from django.db.models import F as F_
    tr_cap = qs.annotate(capital=F_("entry_price") * F_("quantity"))
    agg = tr_cap.aggregate(max=Max("capital"), min=Min("capital"), avg=Avg("capital"))

    max_val = agg["max"] or 0
    min_val = agg["min"] or 0

    pnl_at_max = getattr(tr_cap.filter(capital=max_val).first(), "total_pnl", 0) or 0
    pnl_at_min = getattr(tr_cap.filter(capital=min_val).first(), "total_pnl", 0) or 0

    return {
        "max_capital_used": float(max_val),
        "min_capital_used": float(min_val),
        "average_capital_used": round(float(agg["avg"] or 0), 2),
        "pnl_at_max_capital": float(pnl_at_max),
        "pnl_at_min_capital": float(pnl_at_min),
    }


def _quantity_analysis(qs) -> dict:
    agg = qs.aggregate(max=Max("quantity"), min=Min("quantity"), avg=Avg("quantity"))

    max_val = agg["max"] or 0
    min_val = agg["min"] or 0

    pnl_at_max = getattr(qs.filter(quantity=max_val).first(), "total_pnl", 0) or 0
    pnl_at_min = getattr(qs.filter(quantity=min_val).first(), "total_pnl", 0) or 0

    return {
        "max_quantity": float(max_val),
        "min_quantity": float(min_val),
        "average_quantity": round(float(agg["avg"] or 0), 2),
        "pnl_at_max_quantity": float(pnl_at_max),
        "pnl_at_min_quantity": float(pnl_at_min),
    }


def _symbol_frequency(qs) -> dict:
    sym_qs = list(
        qs.values("symbol").annotate(
            count=Count("id"),
            pnl=Sum("total_pnl"),
            wins=Count("id", filter=Q(total_pnl__gt=0)),
        )
    )
    if not sym_qs:
        return {}

    for s in sym_qs:
        s["win_rate"] = float(s["wins"] / s["count"] * 100) if s["count"] else 0
        s["pnl"] = s["pnl"] or Decimal("0")

    return {
        "most_traded_symbol": max(sym_qs, key=lambda x: x["count"])["symbol"],
        "most_profitable_symbol": max(sym_qs, key=lambda x: x["pnl"])["symbol"],
        "least_profitable_symbol": min(sym_qs, key=lambda x: x["pnl"])["symbol"],
        "highest_win_rate_symbol": max(sym_qs, key=lambda x: x["win_rate"])["symbol"],
        "lowest_win_rate_symbol": min(sym_qs, key=lambda x: x["win_rate"])["symbol"],
    }