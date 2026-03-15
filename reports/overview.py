"""
Reports — Overview report data.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Avg, Q, Sum
from django.db.models.functions import TruncDate

from .utils import build_cumulative_and_daily_series, build_daily_rows, win_rate


def get_overview_report_data(user, qs, filters) -> dict:
    from django.utils.timezone import localdate

    from discipline.models import DisciplineSession
    from insights.services import calculate_metrics
    from mistakes.models import TradeMistake
    from tradelog.models import Trade

    today = localdate()

    this_period_qs, prev_period_qs, vs_label = _resolve_comparison_periods(user, filters, today)

    closed_qs = qs.filter(total_pnl__isnull=False)
    this_pnl = closed_qs.aggregate(total=Sum("total_pnl"))["total"] or Decimal("0")

    pnl_card = _pnl_card(this_pnl, this_period_qs, prev_period_qs, vs_label)
    wr_card = _win_rate_card(this_period_qs, prev_period_qs)

    # Core metrics
    total_trades = closed_qs.count()
    wins = closed_qs.filter(total_pnl__gt=0).count()
    wr = round(wins / total_trades * 100, 1) if total_trades else 0.0

    gross_profit = closed_qs.aggregate(gp=Sum("total_pnl", filter=Q(total_pnl__gt=0)))["gp"] or Decimal("0")
    gross_loss = abs(closed_qs.aggregate(gl=Sum("total_pnl", filter=Q(total_pnl__lt=0)))["gl"] or Decimal("0"))
    pf = round(float(gross_profit / gross_loss), 1) if gross_loss else 0.0

    avg_win = closed_qs.aggregate(avg=Avg("total_pnl", filter=Q(total_pnl__gt=0)))["avg"] or Decimal("0")
    avg_loss = abs(closed_qs.aggregate(avg=Avg("total_pnl", filter=Q(total_pnl__lt=0)))["avg"] or Decimal("0"))

    # Chart data
    daily_rows = build_daily_rows(closed_qs)
    cumulative, daily_series = build_cumulative_and_daily_series(daily_rows)
    winning_days = sum(1 for d in daily_rows if d["daily_pnl"] > 0)
    total_days = len(daily_rows)
    day_win_rate = round((winning_days / total_days) * 100, 1) if total_days else 0.0

    session_health = _session_health(user, today, Trade, TradeMistake, DisciplineSession)
    discipline_vs_performance = _discipline_vs_performance(user, qs)
    exclusive_metrics = _exclusive_metrics(calculate_metrics(user))

    return {
        "netPnl": pnl_card,
        "tradeWinPercent": wr_card,
        "profitFactor": pf,
        "dayWinPercent": day_win_rate,
        "avgWin": float(avg_win),
        "avgLoss": float(avg_loss),
        "chartData": {
            "netPnlCumulative": cumulative,
            "netDailyPnl": daily_series,
        },
        "sessionHealth": session_health,
        "disciplineVsPerformance": discipline_vs_performance,
        "exclusiveMetrics": exclusive_metrics,
    }

# Private helpers

def _resolve_comparison_periods(user, filters, today: date):
    """Return (this_period_qs, prev_period_qs, vs_label)."""
    from tradelog.models import Trade

    all_trades = Trade.objects.filter(user=user, deleted_at__isnull=True, total_pnl__isnull=False)

    from_str = filters.get("from")
    to_str = filters.get("to")

    if from_str and to_str:
        from datetime import datetime as dt_

        from_d = dt_.strptime(from_str, "%Y-%m-%d").date()
        to_d = dt_.strptime(to_str, "%Y-%m-%d").date()
        period_days = (to_d - from_d).days or 1
        prev_from = from_d - timedelta(days=period_days + 1)
        prev_to = from_d - timedelta(days=1)
        return (
            all_trades.filter(trade_date__gte=from_d, trade_date__lte=to_d),
            all_trades.filter(trade_date__gte=prev_from, trade_date__lte=prev_to),
            "vs previous period",
        )

    # Auto-detect most recent month with trades
    latest = all_trades.order_by("-trade_date").first()
    if latest:
        ref_first = latest.trade_date.replace(day=1)
        prev_first = _previous_month_first(ref_first)
        _, ref_days = calendar.monthrange(ref_first.year, ref_first.month)
        _, prev_days = calendar.monthrange(prev_first.year, prev_first.month)
        ref_last = ref_first.replace(day=ref_days)
        prev_last = prev_first.replace(day=prev_days)
    else:
        ref_first = today.replace(day=1)
        ref_last = today
        prev_first = _previous_month_first(ref_first)
        _, prev_days = calendar.monthrange(prev_first.year, prev_first.month)
        prev_last = prev_first.replace(day=prev_days)

    return (
        all_trades.filter(trade_date__gte=ref_first, trade_date__lte=ref_last),
        all_trades.filter(trade_date__gte=prev_first, trade_date__lte=prev_last),
        "vs last month",
    )


def _previous_month_first(d: date) -> date:
    if d.month == 1:
        return d.replace(year=d.year - 1, month=12)
    return d.replace(month=d.month - 1)


def _pnl_card(this_pnl, this_period_qs, prev_period_qs, vs_label: str) -> dict:
    this_period_pnl = this_period_qs.aggregate(total=Sum("total_pnl"))["total"] or Decimal("0")
    prev_pnl = prev_period_qs.aggregate(total=Sum("total_pnl"))["total"] or Decimal("0")

    if prev_pnl != 0:
        pct_change = round(((this_period_pnl - prev_pnl) / abs(prev_pnl)) * 100, 1)
    elif this_period_pnl > 0:
        pct_change = 100.0
    else:
        pct_change = 0

    return {"value": float(this_pnl), "percentChange": pct_change, "vsText": vs_label}


def _win_rate_card(this_period_qs, prev_period_qs) -> dict:
    this_wr = win_rate(this_period_qs)
    prev_wr = win_rate(prev_period_qs)
    change = round(this_wr - prev_wr, 1)
    return {
        "value": this_wr,
        "percentChange": change,
        "vsText": "improvement" if change >= 0 else "decline",
    }


def _session_health(user, today, Trade, TradeMistake, DisciplineSession) -> dict:
    active_session = (
        DisciplineSession.objects.filter(user=user, session_state="red").order_by("-session_date").first()
        or DisciplineSession.objects.filter(user=user, session_state="yellow").order_by("-session_date").first()
    )

    if active_session is None:
        from datetime import datetime as dt_, time as dtime_

        from django.utils import timezone as tz

        active_session, _ = DisciplineSession.objects.get_or_create(
            user=user,
            session_date=today,
            defaults={"session_state": "green"},
        )
        if active_session.lock_cycle_started_at is None:
            active_session.lock_cycle_started_at = tz.make_aware(dt_.combine(today, dtime_.min))
            active_session.save(update_fields=["lock_cycle_started_at"])
        active_session.refresh_from_db()

    color = active_session.session_state
    label_map = {"green": "Normal", "yellow": "Warning", "red": "Locked"}
    session_date = active_session.session_date

    return {
        "status": label_map.get(color, "Normal"),
        "color": color,
        "tradesToday": Trade.objects.filter(user=user, trade_date=session_date, deleted_at__isnull=True).count(),
        "rulesViolated": active_session.violations_count,
        "mistakesLogged": TradeMistake.objects.filter(
            trade__user=user, trade__trade_date=session_date
        ).count(),
        "journalCompleted": active_session.journal_completed,
    }


def _discipline_vs_performance(user, qs) -> dict:
    from discipline.models import DisciplineSession

    green_ids = list(
        DisciplineSession.objects.filter(user=user, peak_state="green").values_list("id", flat=True)
    )
    non_green_ids = list(
        DisciplineSession.objects.filter(user=user).exclude(peak_state="green").values_list("id", flat=True)
    )

    return {
        "disciplined": _performance_stats(user, qs.filter(session_id__in=green_ids)),
        "undisciplined": _performance_stats(user, qs.filter(session_id__in=non_green_ids)),
    }


def _performance_stats(user, t_qs) -> dict:
    total = t_qs.count()
    if not total:
        return {"winRate": 0.0, "avgReturn": 0.0, "drawdown": 0.0}

    wins = t_qs.filter(total_pnl__gt=0).count()
    wr = round((wins / total) * 100, 1)

    avg_p = t_qs.aggregate(total=Avg("total_pnl"))["total"] or Decimal("0")
    avg_loss_val = abs(
        t_qs.aggregate(avg_loss=Avg("total_pnl", filter=Q(total_pnl__lt=0)))["avg_loss"] or Decimal("1")
    )
    avg_r = round(float(avg_p / avg_loss_val) if avg_loss_val else float(avg_p), 1)

    # Drawdown
    peak = running = max_dd = 0.0
    for row in (
        t_qs.annotate(day=TruncDate("trade_date"))
        .values("day")
        .annotate(daily_pnl=Sum("total_pnl"))
        .order_by("day")
    ):
        running += float(row["daily_pnl"] or 0)
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd

    base_capital = float(user.trading_capital or 1)
    drawdown_pct = round((max_dd / base_capital) * 100, 1) if base_capital else 0.0

    return {"winRate": wr, "avgReturn": avg_r, "drawdown": -drawdown_pct if drawdown_pct else 0.0}


def _exclusive_metrics(snapshot) -> dict:
    return {
        "di": float(snapshot.di_score),
        "vmi": snapshot.vmi_level,
        "drt": float(snapshot.drt_days),
        "tpr": float(snapshot.tpr_score),
        "fie": float(snapshot.fie_amount),
        "ovr": float(snapshot.ovr_score),
        "eci": float(snapshot.eci_amount),
        "cas": float(snapshot.cas_score),
        "dae": float(snapshot.dae_r),
        "smi": snapshot.smi_status.capitalize() if snapshot.smi_status else "Dev",
        "ddr": snapshot.ddr_level,
        "cpi": float(snapshot.cpi_score) if snapshot.cpi_score else 100.0,
    }