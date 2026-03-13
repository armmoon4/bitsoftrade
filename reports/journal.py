"""
Reports — Journal / psychology report data.
"""
from __future__ import annotations

import math

from django.db.models import Avg, Count


def get_journal_report_data(user, qs, filters) -> dict:
    from journal.models import DailyJournal, PsychologyLog, SessionRecap

    from_date = filters.get("from")
    to_date = filters.get("to")

    journals = _date_filter(DailyJournal.objects.filter(user=user), "journal_date", from_date, to_date)
    psych_logs = _date_filter(PsychologyLog.objects.filter(user=user), "log_date", from_date, to_date)
    recaps = _date_filter(SessionRecap.objects.filter(user=user), "recap_date", from_date, to_date)

    psych_agg = psych_logs.aggregate(
        avg_confidence=Avg("confidence_before"),
        avg_satisfaction=Avg("satisfaction_after"),
    )

    emotion_counts = list(
        psych_logs.values("emotional_state").annotate(count=Count("id")).order_by("-count")
    )
    emotion_frequency = {item["emotional_state"]: item["count"] for item in emotion_counts}
    most_common_emotion = emotion_counts[0]["emotional_state"] if emotion_counts else None

    # Correlations and emotion P&L impact
    conf_corr, sat_corr, emotion_impact = _psychology_correlations(psych_logs)

    # Journal completion rate
    traded_dates = set(qs.values_list("trade_date", flat=True).distinct())
    journaled_dates = set(journals.values_list("journal_date", flat=True).distinct())
    days_traded = len(traded_dates)
    days_journaled = len(traded_dates & journaled_dates)
    completion_rate = round((days_journaled / days_traded * 100), 1) if days_traded else 0
    missed_days = days_traded - days_journaled

    # Session recap distribution
    recap_dist = {r["outcome"]: r["count"] for r in recaps.values("outcome").annotate(count=Count("id"))}

    return {
        "journal_discipline": {
            "completion_rate": completion_rate,
            "current_streak": user.current_streak,
            "longest_streak": user.longest_streak,
            "missed_journaling_days": missed_days,
            "journal_count": journals.count(),
        },
        "psychology_summary": {
            "avg_confidence": psych_agg["avg_confidence"],
            "avg_satisfaction": psych_agg["avg_satisfaction"],
            "most_common_emotion": most_common_emotion,
            "confidence_correlation": conf_corr,
            "satisfaction_correlation": sat_corr,
            "emotion_frequency": emotion_frequency,
            "emotional_impact_pnl": emotion_impact,
        },
        "session_recap_summary": {
            "good": recap_dist.get("good", 0),
            "neutral": recap_dist.get("neutral", 0),
            "bad": recap_dist.get("bad", 0),
        },
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _date_filter(qs, field: str, from_date, to_date):
    if from_date:
        qs = qs.filter(**{f"{field}__gte": from_date})
    if to_date:
        qs = qs.filter(**{f"{field}__lte": to_date})
    return qs


def _psychology_correlations(psych_logs) -> tuple[float, float, dict]:
    """Return (confidence_correlation, satisfaction_correlation, emotion_impact_pnl)."""
    logs_with_trades = psych_logs.filter(trade__isnull=False).select_related("trade")

    confidences: list[float] = []
    satisfactions: list[float] = []
    pnls: list[float] = []
    emotion_impact: dict[str, float] = {}

    for log in logs_with_trades:
        pnl = float(log.trade.total_pnl or 0)
        state = log.emotional_state

        if log.confidence_before is not None:
            confidences.append(log.confidence_before)
            pnls.append(pnl)
        if log.satisfaction_after is not None:
            satisfactions.append(log.satisfaction_after)

        emotion_impact[state] = emotion_impact.get(state, 0) + pnl

    return (
        _pearson_correlation(confidences, pnls),
        _pearson_correlation(satisfactions, pnls[: len(satisfactions)]),
        emotion_impact,
    )


def _pearson_correlation(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi * xi for xi in x)
    sum_y2 = sum(yi * yi for yi in y)
    numerator = (n * sum_xy) - (sum_x * sum_y)
    denominator = math.sqrt((n * sum_x2 - sum_x**2) * (n * sum_y2 - sum_y**2))
    return round(numerator / denominator, 2) if denominator else 0.0