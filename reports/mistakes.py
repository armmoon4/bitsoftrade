"""
Reports — Mistakes report data.
"""
from __future__ import annotations


def get_mistakes_report_data(qs) -> dict:
    from journal.models import PsychologyLog
    from mistakes.models import TradeMistake

    trade_ids = list(qs.values_list("id", flat=True))
    if not trade_ids:
        return {"message": "No trades in the selected range."}

    mistake_stats, total_cost, mistake_count = _aggregate_mistakes(trade_ids)
    trigger_analysis = _aggregate_triggers(trade_ids)

    most_frequent = max(mistake_stats, key=lambda n: mistake_stats[n]["count"], default=None)
    avg_cost = total_cost / mistake_count if mistake_count else 0

    return {
        "mistake_frequency": {name: stats["count"] for name, stats in mistake_stats.items()},
        "loss_contribution": {
            name: round(stats["loss_contribution"], 2) for name, stats in mistake_stats.items()
        },
        "most_frequent_mistake": most_frequent,
        "total_mistake_cost": round(total_cost, 2),
        "avg_cost_per_mistake": round(avg_cost, 2),
        "clustering_pattern_detected": mistake_count > 3,
        "trigger_analysis": trigger_analysis,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _aggregate_mistakes(trade_ids) -> tuple[dict, float, int]:
    from mistakes.models import TradeMistake

    mistake_stats: dict[str, dict] = {}
    total_cost = 0.0
    mistake_count = 0

    for tm in TradeMistake.objects.filter(trade__in=trade_ids).select_related("mistake", "trade"):
        name = tm.mistake.mistake_name
        pnl = float(tm.trade.total_pnl or 0)

        stats = mistake_stats.setdefault(name, {"count": 0, "loss_contribution": 0.0})
        stats["count"] += 1
        mistake_count += 1

        if pnl < 0:
            loss = abs(pnl)
            stats["loss_contribution"] += loss
            total_cost += loss

    return mistake_stats, total_cost, mistake_count


def _aggregate_triggers(trade_ids) -> dict:
    from journal.models import PsychologyLog

    trigger_analysis: dict[str, dict] = {}

    for log in (
        PsychologyLog.objects.filter(trade__in=trade_ids, pressure_source__isnull=False)
        .select_related("trade")
    ):
        trigger = log.pressure_source
        pnl = float(log.trade.total_pnl or 0)

        entry = trigger_analysis.setdefault(trigger, {"trades": 0, "total_pnl": 0.0})
        entry["trades"] += 1
        entry["total_pnl"] += pnl

    for entry in trigger_analysis.values():
        entry["avg_pnl"] = round(entry["total_pnl"] / entry["trades"], 2)

    return trigger_analysis