"""
Reports — Journal report data.

Returns four top-level sections:
  • psychology_report   — emotion frequency, confidence vs outcome scatter,
                          correlations, emotional P&L impact, insight string
  • mistake_report      — frequency, loss contribution, clustering flag
  • trigger_analysis    — per-trigger trades count and avg P&L
  • journal_discipline  — completion rate, streaks, missed days
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta

from django.db.models import Avg, Count


# Human-readable labels for pressure_source choices
PRESSURE_LABEL = {
    "money":        "Money pressure",
    "time":         "Time pressure",
    "missed_move":  "Missed move",
    "anger":        "Anger",
    "uncertainty":  "Uncertainty",
}

# Human-readable labels for Mistake.mistake_mode choices
MODE_LABEL = {
    "overtrading":         "Overtrading",
    "revenge_trading":     "Revenge Trading",
    "fomo":                "FOMO Entry",
    "early_exit":          "Premature Exit",
    "ignored_stop_loss":   "Missed Stop Loss",
    "late_exit":           "Late Exit",
    "no_plan":             "No Plan",
    "oversized_position":  "Oversized Position",
}


def get_journal_report_data(user, qs, filters) -> dict:
    from journal.models import DailyJournal, PsychologyLog, SessionRecap
    from mistakes.models import TradeMistake

    from_date = filters.get("from")
    to_date   = filters.get("to")

    # ── base querysets ──────────────────────────────────────────────────────
    journals   = _date_filter(DailyJournal.objects.filter(user=user),   "journal_date", from_date, to_date)
    psych_logs = _date_filter(PsychologyLog.objects.filter(user=user),  "log_date",     from_date, to_date)
    recaps     = _date_filter(SessionRecap.objects.filter(user=user),   "recap_date",   from_date, to_date)

    trade_ids = list(qs.values_list("id", flat=True))

    # ── 1. Psychology Report ────────────────────────────────────────────────
    psych_agg = psych_logs.aggregate(
        avg_confidence=Avg("confidence_before"),
        avg_satisfaction=Avg("satisfaction_after"),
    )

    emotion_counts = list(
        psych_logs.values("emotional_state").annotate(count=Count("id")).order_by("-count")
    )
    # Sorted list for bar chart
    emotion_frequency = [
        {"emotion": item["emotional_state"], "count": item["count"]}
        for item in emotion_counts
    ]
    most_common_emotion = emotion_counts[0]["emotional_state"] if emotion_counts else None

    (
        conf_corr,
        sat_corr,
        emotion_impact_pnl,
        confidence_vs_outcome,
    ) = _psychology_correlations(psych_logs)

    total_emotion_impact = round(sum(emotion_impact_pnl.values()), 2)

    psychology_insight = _generate_psychology_insight(psych_logs, emotion_impact_pnl)

    # ── 2. Mistake Report ───────────────────────────────────────────────────
    mistake_stats, total_cost, mistake_count = _aggregate_mistakes(trade_ids)
    if mistake_stats:
        top_mode_key = max(mistake_stats, key=lambda k: mistake_stats[k]["count"])
        most_frequent_mistake = MODE_LABEL.get(top_mode_key, top_mode_key.replace("_", " ").title())
    else:
        most_frequent_mistake = None
    avg_cost_per_mistake = round(total_cost / mistake_count, 2) if mistake_count else 0.0

    # ── 3. Trigger Analysis ─────────────────────────────────────────────────
    trigger_analysis = _aggregate_triggers(trade_ids, qs, psych_logs)

    # ── 4. Journal Discipline ───────────────────────────────────────────────
    traded_dates    = set(qs.values_list("trade_date", flat=True).distinct())
    journaled_dates = set(journals.values_list("journal_date", flat=True).distinct())
    days_traded     = len(traded_dates)
    days_journaled  = len(traded_dates & journaled_dates)
    completion_rate = round((days_journaled / days_traded * 100), 1) if days_traded else 0.0
    missed_days     = days_traded - days_journaled

    current_streak, longest_streak = _compute_journal_streaks(journals)

    # Build display-friendly mistake_frequency (label → count)
    mistake_frequency_display = {
        MODE_LABEL.get(mode, mode.replace("_", " ").title()): stats["count"]
        for mode, stats in mistake_stats.items()
    }
    loss_contribution_display = {
        MODE_LABEL.get(mode, mode.replace("_", " ").title()): round(stats["loss_contribution"], 2)
        for mode, stats in mistake_stats.items()
    }

    return {
        "psychology_report": {
            "emotion_frequency":        emotion_frequency,
            "confidence_vs_outcome":    confidence_vs_outcome,
            "most_common_emotion":      most_common_emotion,
            "confidence_correlation":   conf_corr,
            "satisfaction_correlation": sat_corr,
            "emotional_impact_pnl":     total_emotion_impact,
            "avg_confidence":           psych_agg["avg_confidence"],
            "avg_satisfaction":         psych_agg["avg_satisfaction"],
            "psychology_insight":       psychology_insight,
        },
        "mistake_report": {
            "mistake_frequency":            mistake_frequency_display,
            "loss_contribution":            loss_contribution_display,
            "most_frequent_mistake":        most_frequent_mistake,
            "total_mistake_cost":           round(total_cost, 2),
            "avg_cost_per_mistake":         avg_cost_per_mistake,
            "clustering_pattern_detected":  mistake_count > 3,
        },
        "trigger_analysis": trigger_analysis,
        "journal_discipline": {
            "completion_rate":        completion_rate,
            "current_streak":         current_streak,
            "longest_streak":         longest_streak,
            "missed_journaling_days": missed_days,
            "journal_count":          journals.count(),
        },
    }

# Private helpers

def _date_filter(qs, field: str, from_date, to_date):
    if from_date:
        qs = qs.filter(**{f"{field}__gte": from_date})
    if to_date:
        qs = qs.filter(**{f"{field}__lte": to_date})
    return qs


def _psychology_correlations(
    psych_logs,
) -> tuple[float, float, dict[str, float], list[dict]]:
    """
    Returns:
        (confidence_correlation, satisfaction_correlation,
         emotion_impact_pnl dict, confidence_vs_outcome scatter list)
    """
    logs_with_trades = (
        psych_logs.filter(trade__isnull=False).select_related("trade")
    )

    confidences:   list[float] = []
    satisfactions: list[float] = []
    pnls:          list[float] = []
    emotion_impact: dict[str, float] = {}
    confidence_vs_outcome: list[dict] = []

    for log in logs_with_trades:
        pnl   = float(log.trade.total_pnl or 0)
        state = log.emotional_state

        if log.confidence_before is not None:
            confidences.append(float(log.confidence_before))
            pnls.append(pnl)
            confidence_vs_outcome.append({
                "confidence": log.confidence_before,
                "pnl":        round(pnl, 2),
            })

        if log.satisfaction_after is not None:
            satisfactions.append(float(log.satisfaction_after))

        emotion_impact[state] = emotion_impact.get(state, 0.0) + pnl

    return (
        _pearson_correlation(confidences, pnls),
        _pearson_correlation(satisfactions, pnls[: len(satisfactions)]),
        {k: round(v, 2) for k, v in emotion_impact.items()},
        confidence_vs_outcome,
    )


def _generate_psychology_insight(psych_logs, emotion_impact_pnl: dict) -> str | None:
    """
    Build a plain-English insight based on emotion → avg P&L data.
    Falls back to None when there is insufficient data.
    """
    if not emotion_impact_pnl:
        return None

    logs_with_trades = (
        psych_logs.filter(trade__isnull=False).select_related("trade")
    )

    emotion_counts:  dict[str, int]   = defaultdict(int)
    emotion_totals:  dict[str, float] = defaultdict(float)

    for log in logs_with_trades:
        state = log.emotional_state
        emotion_counts[state]  += 1
        emotion_totals[state]  += float(log.trade.total_pnl or 0)

    if not emotion_counts:
        return None

    avg_by_emotion = {
        s: emotion_totals[s] / emotion_counts[s]
        for s in emotion_counts
    }

    best_state  = max(avg_by_emotion, key=avg_by_emotion.get)
    worst_state = min(avg_by_emotion, key=avg_by_emotion.get)

    if best_state == worst_state:
        return None

    best_avg  = round(avg_by_emotion[best_state],  2)
    worst_avg = round(avg_by_emotion[worst_state], 2)

    # Avoid division-by-zero for the percentage comparison
    if best_avg and best_avg != worst_avg:
        delta_pct = abs(round(((best_avg - worst_avg) / abs(best_avg)) * 100))
        insight = (
            f"Trades taken while '{worst_state}' show "
            f"{delta_pct}% lower expectancy than '{best_state}' trades. "
            f"Consider implementing pre-trade routines to stay in a "
            f"'{best_state}' mindset."
        )
    else:
        insight = (
            f"Your best emotional state for trading appears to be '{best_state}'. "
            f"Trades in a '{worst_state}' state tend to underperform."
        )

    return insight


def _aggregate_mistakes(trade_ids: list) -> tuple[dict, float, int]:
    """
    Aggregate mistake frequency and loss contribution for given trade IDs.

    Groups by ``mistake_mode`` (behavioural pattern) — the same axis used by
    the standalone mistakes analytics view.  Falls back to the raw mode value
    when ``mistake_mode`` is NULL (i.e. unclassified mistakes).
    """
    from mistakes.models import TradeMistake

    mistake_stats: dict[str, dict] = {}   # keyed by raw mistake_mode string
    total_cost    = 0.0
    mistake_count = 0

    if not trade_ids:
        return mistake_stats, total_cost, mistake_count

    for tm in (
        TradeMistake.objects
        .filter(trade__in=trade_ids)
        .select_related("mistake", "trade")
    ):
        # Group by mistake_mode; fall back to a sanitised mistake_name if mode is blank
        mode = tm.mistake.mistake_mode or "unclassified"
        pnl  = float(tm.trade.total_pnl or 0)

        stats = mistake_stats.setdefault(mode, {"count": 0, "loss_contribution": 0.0})
        stats["count"] += 1
        mistake_count   += 1

        if pnl < 0:
            loss = abs(pnl)
            stats["loss_contribution"] += loss
            total_cost                 += loss

    return mistake_stats, total_cost, mistake_count


def _aggregate_triggers(trade_ids: list, trade_qs, psych_logs) -> dict:
    """
    Return trigger analysis keyed by human-readable label.

    Sources:
      • PsychologyLog.pressure_source  → money / time / missed_move / anger / uncertainty
        Uses the full date-filtered psych_logs queryset so standalone logs
        (not linked to a specific trade) are also included.
      • Consecutive trade streaks       → losing_streak / winning_streak
    """
    trigger_data: dict[str, dict] = {}

    # ── pressure-source triggers ────────────────────────────────────────────
    # Use the full date-ranged psych_logs queryset (user + date already filtered).
    # When a log is linked to a trade, use that trade's PnL; otherwise use 0.
    for log in psych_logs.filter(pressure_source__isnull=False).select_related("trade"):
        raw_trigger = log.pressure_source
        label       = PRESSURE_LABEL.get(raw_trigger, raw_trigger.replace("_", " ").title())
        pnl         = float(log.trade.total_pnl or 0) if log.trade_id else 0.0

        entry = trigger_data.setdefault(label, {"trades": 0, "total_pnl": 0.0})
        entry["trades"]    += 1
        entry["total_pnl"] += pnl

    # ── streak-based triggers ───────────────────────────────────────────────
    trades_ordered = list(
        trade_qs.order_by("trade_date", "created_at").values("total_pnl")
    )
    losing_pnls:  list[float] = []
    winning_pnls: list[float] = []
    current_run: list[float]  = []
    run_sign = 0  # +1 winning, -1 losing

    def _flush_run():
        nonlocal current_run, run_sign
        if len(current_run) >= 2:
            target = losing_pnls if run_sign == -1 else winning_pnls
            target.extend(current_run)
        current_run = []
        run_sign    = 0

    for t in trades_ordered:
        pnl  = float(t["total_pnl"] or 0)
        sign = -1 if pnl < 0 else (1 if pnl > 0 else run_sign)
        if sign == 0:
            continue
        if sign != run_sign:
            _flush_run()
            run_sign = sign
        current_run.append(pnl)
    _flush_run()

    if losing_pnls:
        trigger_data["Losing streak"] = {
            "trades":    len(losing_pnls),
            "total_pnl": sum(losing_pnls),
        }
    if winning_pnls:
        trigger_data["Winning streak"] = {
            "trades":    len(winning_pnls),
            "total_pnl": sum(winning_pnls),
        }

    # ── compute avg_pnl and clean up total_pnl ──────────────────────────────
    result = {}
    for label, entry in trigger_data.items():
        avg_pnl = entry["total_pnl"] / entry["trades"] if entry["trades"] else 0.0
        result[label] = {
            "trades":  entry["trades"],
            "avg_pnl": round(avg_pnl, 2),
        }

    return result


def _compute_journal_streaks(journals) -> tuple[int, int]:
    """
    Compute current journaling streak and longest journaling streak
    from the filtered DailyJournal queryset.

    Returns (current_streak, longest_streak) as day counts.
    """
    from datetime import date as date_cls

    dates = sorted(journals.values_list("journal_date", flat=True).distinct(), reverse=True)
    if not dates:
        return 0, 0

    today = date_cls.today()
    longest = 1
    current = 0
    run     = 1

    # Walk forward (dates is sorted DESC) to compute longest and current streak
    for i in range(len(dates)):
        if i == 0:
            # Start current streak from today or yesterday
            delta = (today - dates[0]).days
            if delta <= 1:
                current = 1
            # check continuing run
            continue

        gap = (dates[i - 1] - dates[i]).days
        if gap == 1:
            run += 1
            longest = max(longest, run)
            if current > 0:
                current += 1
        else:
            run = 1
            # streak is broken; current streak cannot extend further back
            current = current  # freeze

    longest = max(longest, run)
    return current, longest


def _pearson_correlation(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    sum_x  = sum(x)
    sum_y  = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi * xi for xi in x)
    sum_y2 = sum(yi * yi for yi in y)
    numerator   = (n * sum_xy) - (sum_x * sum_y)
    denominator = math.sqrt((n * sum_x2 - sum_x**2) * (n * sum_y2 - sum_y**2))
    return round(numerator / denominator, 2) if denominator else 0.0