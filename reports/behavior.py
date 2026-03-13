"""
Reports — Behavior / discipline report data.
"""
from __future__ import annotations

from django.db.models import Count
from django.db.models.functions import TruncDate

from .utils import fmt_date


def get_behavior_report_data(user, qs, filters) -> dict:
    from discipline.models import ViolationsLog
    from insights.serializers import MetricsSnapshotSerializer
    from insights.services import calculate_metrics
    from mistakes.models import TradeMistake

    snapshot = calculate_metrics(user)
    snapshot_data = MetricsSnapshotSerializer(snapshot).data

    kpis = _build_kpis(user, qs, snapshot, filters)
    violations_timeline = _violations_timeline(user, filters)
    formatted_heatmap, top_recurring, total_mistake_losses = _mistake_analysis(qs)
    insight_text = _behavior_insight(kpis["ECI"]["value"], total_mistake_losses, top_recurring)
    rule_adherence = _rule_adherence(user, qs, filters)

    return {
        "kpis": kpis,
        "snapshot": snapshot_data,
        "violations_timeline": violations_timeline,
        "mistake_heatmap": formatted_heatmap,
        "top_recurring_mistakes": top_recurring,
        "behavior_insight": insight_text,
        "rule_adherence": rule_adherence,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_kpis(user, qs, snapshot, filters) -> dict:
    from discipline.models import ViolationsLog

    total_trades = qs.count()

    violated_count = (
        ViolationsLog.objects.filter(user=user, trade__in=qs, violation_type="hard")
        .values("trade_id")
        .distinct()
        .count()
    )
    eci = round(((total_trades - violated_count) / total_trades * 100), 1) if total_trades else 100.0

    return {
        "DIS": {"value": snapshot.di_score, "trend": "Stable"},
        "VMI": {"value": snapshot.vmi_score, "trend": snapshot.vmi_level},
        "DRT": {"value": float(snapshot.drt_days), "trend": "Stable"},
        "ECI": {"value": eci, "trend": "Stable"},
    }


def _violations_timeline(user, filters) -> list[dict]:
    from discipline.models import ViolationsLog

    from_date = filters.get("from")
    to_date = filters.get("to")

    vqs = ViolationsLog.objects.filter(user=user)
    if from_date:
        vqs = vqs.filter(violated_at__gte=from_date)
    if to_date:
        vqs = vqs.filter(violated_at__lte=to_date)

    rows = (
        vqs.annotate(date=TruncDate("violated_at"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("date")
    )
    return [{"date": fmt_date(row["date"]), "violations": row["count"]} for row in rows]


def _mistake_analysis(qs) -> tuple[list[dict], list[dict], float]:
    from mistakes.models import TradeMistake

    trade_ids = qs.values_list("id", flat=True)
    mistakes_qs = TradeMistake.objects.filter(trade__in=trade_ids).select_related("mistake", "trade")

    heatmap_data: dict[str, dict[str, int]] = {}
    mistake_stats: dict[str, dict] = {}
    total_mistake_losses = 0.0

    for tm in mistakes_qs:
        name = tm.mistake.mistake_name
        day_str = fmt_date(tm.trade.trade_date)
        pnl = float(tm.trade.total_pnl or 0)

        heatmap_data.setdefault(name, {})
        heatmap_data[name][day_str] = heatmap_data[name].get(day_str, 0) + 1

        stats = mistake_stats.setdefault(name, {"count": 0, "loss": 0.0})
        stats["count"] += 1
        if pnl < 0:
            loss = abs(pnl)
            stats["loss"] += loss
            total_mistake_losses += loss

    formatted_heatmap = [
        {"mistake_type": name, "occurrences": dates}
        for name, dates in heatmap_data.items()
    ]

    top_recurring = sorted(
        [
            {
                "name": name,
                "occurrences": stats["count"],
                "loss_percent": round(stats["loss"] / total_mistake_losses * 100, 1)
                if total_mistake_losses
                else 0,
            }
            for name, stats in mistake_stats.items()
        ],
        key=lambda x: x["loss_percent"],
        reverse=True,
    )

    return formatted_heatmap, top_recurring, total_mistake_losses


def _behavior_insight(eci: float, total_mistake_losses: float, top_recurring: list[dict]) -> str:
    if eci < 80:
        return (
            "ECI has dropped below 80%. Most losses occurred on days with multiple rule violations. "
            "Pause trading after your first hard violation."
        )
    if total_mistake_losses > 0 and top_recurring:
        top = top_recurring[0]
        return (
            f"Mistakes cluster heavily around {top['name']}, contributing to "
            f"{top['loss_percent']}% of your losses. "
            "Review your triggers before the next session."
        )
    return "Discipline is stable. Keep focusing on executing your edge."


def _rule_adherence(user, qs, filters) -> dict:
    from discipline.models import ViolationsLog

    from_date = filters.get("from")
    to_date = filters.get("to")

    vqs = ViolationsLog.objects.filter(user=user)
    if from_date:
        vqs = vqs.filter(violated_at__gte=from_date)
    if to_date:
        vqs = vqs.filter(violated_at__lte=to_date)

    total_trades = qs.count()
    categories = ["risk", "entry", "exit", "process", "psychology"]
    adherence = {cat.capitalize(): 100.0 for cat in categories}

    if not total_trades:
        return adherence

    for row in vqs.values("rule__category").annotate(count=Count("id")):
        cat_name = (row["rule__category"] or "Unknown").capitalize()
        pct_violated = (row["count"] / total_trades) * 100
        adherence[cat_name] = max(0.0, round(100.0 - pct_violated, 1))

    return adherence