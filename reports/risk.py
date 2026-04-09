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
    from collections import defaultdict
    import math

    daily_pnls = []
    for row in daily_rows:
        daily_pnls.append({
            "date": fmt_date(row["day"]),
            "pnl": float(row["daily_pnl"] or 0),
            "day_obj": row["day"],
        })

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


    # Risk Statistics & Exposure Analysis additions
    from .utils import consecutive_streaks
    _, max_consecutive_losing_days = consecutive_streaks([d["pnl"] for d in daily_pnls])

    losing_days = [d["pnl"] for d in daily_pnls if d["pnl"] < 0]
    avg_losing_day = sum(losing_days) / len(losing_days) if losing_days else 0

    # Monthly Average Loss
    monthly_losses = defaultdict(list)
    for row in daily_pnls:
        if row["pnl"] < 0:
            month_name = row["day_obj"].strftime("%b")
            monthly_losses[month_name].append(row["pnl"])
    
    monthly_average_loss = []
    for month, losses in monthly_losses.items():
        avg = sum(losses) / len(losses)
        monthly_average_loss.append({
            "month": month,
            "loss": round(avg, 2)
        })

    # R-Multiple and Risk per trade
    r_multiples = []
    risks_pct = []
    for t in qs.exclude(stop_loss__isnull=True):
        if t.stop_loss and t.quantity and t.entry_price:
            risk = abs(float(t.entry_price) - float(t.stop_loss)) * float(t.quantity)
            if risk > 0:
                if t.total_pnl is not None:
                    r_multiples.append(float(t.total_pnl) / risk)
                risks_pct.append((risk / base_capital) * 100)
    
    avg_realized_r_multiple = sum(r_multiples) / len(r_multiples) if r_multiples else 0.0
    max_risk_pct = max(risks_pct) if risks_pct else 0.0
    avg_risk_pct = sum(risks_pct) / len(risks_pct) if risks_pct else 0.0

    # Sharpe, Sortino, VaR, Risk Adjusted Return
    returns = [d["pnl"] for d in daily_pnls]
    returns_pct = [r / base_capital for r in returns]
    
    # VaR 95%
    sorted_returns = sorted(returns)
    var_95 = abs(sorted_returns[int(0.05 * len(sorted_returns))]) if sorted_returns else 0.0

    if len(returns_pct) > 1:
        mean_ret = sum(returns_pct) / len(returns_pct)
        variance = sum((r - mean_ret) ** 2 for r in returns_pct) / (len(returns_pct) - 1)
        std_dev = variance ** 0.5
        risk_adjusted_return = mean_ret / std_dev if std_dev > 0 else 0.0
        sharpe_ratio = risk_adjusted_return * math.sqrt(252)
        
        downside_returns = [r for r in returns_pct if r < 0]
        downside_variance = sum(r ** 2 for r in downside_returns) / len(returns_pct) if returns_pct else 0
        downside_std = downside_variance ** 0.5
        sortino_ratio = (mean_ret / downside_std) * math.sqrt(252) if downside_std > 0 else 0.0
    else:
        risk_adjusted_return = 0.0
        sharpe_ratio = 0.0
        sortino_ratio = 0.0

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
        "monthly_average_loss": monthly_average_loss,
        "risk_statistics": {
            "max_drawdown_pct": round(-max_dd_pct, 1),
            "avg_drawdown_pct": round(-avg_dd_pct, 1),
            "largest_losing_day": round(worst_losing_day, 2),
            "avg_losing_day": round(avg_losing_day, 2),
            "avg_realized_r_multiple": round(avg_realized_r_multiple, 1),
            "max_consecutive_losing_days": max_consecutive_losing_days,
            "risk_adjusted_return": round(risk_adjusted_return, 2),
            "volatility_index": round(volatility_pct, 1)
        },
        "risk_exposure_analysis": {
            "value_at_risk_95": round(var_95, 2),
            "sharpe_ratio": round(sharpe_ratio, 2),
            "sortino_ratio": round(sortino_ratio, 2),
            "max_risk_per_trade": round(max_risk_pct, 1),
            "avg_risk_per_trade": round(avg_risk_pct, 1)
        }
    }


# Private helpers

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
        drawdown_curve.append({"date": row["date"], "drawdown": round(-dd, 2)})
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