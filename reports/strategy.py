"""
Reports — Strategy report data.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Q, Sum

from .utils import profit_factor


def get_strategy_report_data(qs) -> list[dict]:
    from strategies.models import Strategy

    strategy_ids = qs.values_list("strategy_id", flat=True).distinct()
    results = []

    for sid in strategy_ids:
        if not sid:
            continue

        strategy_trades = qs.filter(strategy_id=sid)
        total = strategy_trades.count()
        agg = strategy_trades.aggregate(
            total_pnl=Sum("total_pnl"),
            gross_profit=Sum("total_pnl", filter=Q(total_pnl__gt=0)),
            gross_loss=Sum("total_pnl", filter=Q(total_pnl__lt=0)),
        )
        wins = strategy_trades.filter(total_pnl__gt=0).count()

        try:
            strategy_name = Strategy.objects.get(pk=sid).strategy_name
        except Strategy.DoesNotExist:
            strategy_name = "Unknown"

        results.append(
            {
                "strategy_id": sid,
                "strategy_name": strategy_name,
                "total_trades": total,
                "win_rate": round(wins / total * 100, 2) if total else 0,
                "total_pnl": agg["total_pnl"],
                "profit_factor": profit_factor(
                    agg["gross_profit"] or Decimal("0"),
                    agg["gross_loss"] or Decimal("0"),
                ),
            }
        )

    results.sort(key=lambda x: float(x["total_pnl"] or 0), reverse=True)
    return results