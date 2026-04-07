"""
Reports — Strategy report data.

Response shape
--------------
{
  "strategies": [ ...strategy cards... ],
  "comparison": {
      "metrics": ["Win Rate", "Avg Return", "Consistency", "Risk-Reward", "Execution"],
      "series": [
          {
              "strategy_name": "Momentum Breakout",
              "scores": {
                  "win_rate":    72,   # 0-100 scaled
                  "avg_return":  60,
                  "consistency": 55,
                  "risk_reward": 70,
                  "execution":   80,
              }
          },
          ...
      ]
  },
  "radar": [
      {
          "metric": "Win Rate",
          "values": {"Momentum Breakout": 72, "Reversal Scalp": 65, ...}
      },
      ...
  ],
  "evolution": [
      {
          "strategy_name": "Momentum Breakout",
          "total_trades":  18,
          "win_rate":      72.0,
          "avg_return":    2.4,
      },
      ...sorted by total_trades desc
  ]
}
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Q, Sum


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _score_win_rate(win_rate: float) -> float:
    """Win-rate is already 0-100 — clamp only."""
    return _clamp(win_rate)


def _score_avg_return(profit_factor: float) -> float:
    """
    Score avg-return quality via profit_factor (dimensionless ratio).
    PF 1.0 = break-even  → ~33
    PF 2.0 = good         → ~67
    PF 3.0+ = excellent   → 100
    This avoids near-zero scores caused by normalising raw monetary values.
    """
    return _clamp(round(profit_factor / 3.0 * 100, 1))


def _score_consistency(win_rate: float, profit_factor: float) -> float:
    """
    Consistency = blended signal of win-rate stability and profit factor.
    profit_factor 2+ → excellent consistency.
    """
    pf_score = _clamp(profit_factor / 2.0 * 100)   # 2.0 PF = 100 pts
    return _clamp(round((win_rate * 0.55 + pf_score * 0.45), 1))


def _score_risk_reward(risk_reward_ratio: str) -> float:
    """
    Parse '1:X' string → score.  X ≥ 3 → 100.  X < 0.5 → 10.
    """
    if not risk_reward_ratio or risk_reward_ratio in ("N/A", "1:∞"):
        return 100.0 if risk_reward_ratio == "1:∞" else 20.0
    try:
        parts = risk_reward_ratio.split(":")
        ratio = float(parts[1])
        # Map [0, 3] → [0, 100]
        return _clamp(round(ratio / 3.0 * 100, 1))
    except (IndexError, ValueError):
        return 20.0


def _score_execution(
    sample_size_progress: float,
    total_trades: int,
) -> float:
    """
    Execution score ≈ how mature/complete the sample is.
    A trader who has executed more trades (relative to their target) scores higher.
    """
    return _clamp(sample_size_progress)


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def get_strategy_report_data(qs) -> dict:
    from strategies.models import Strategy

    strategy_ids = qs.values_list("strategy_id", flat=True).distinct()
    strategies = []

    for sid in strategy_ids:
        if not sid:
            continue

        strategy_trades = qs.filter(strategy_id=sid)
        total = strategy_trades.count()

        # Only closed trades count toward performance metrics
        closed_trades_qs = strategy_trades.filter(exit_price__isnull=False)
        closed_count = closed_trades_qs.count()

        agg = closed_trades_qs.aggregate(
            gross_profit=Sum("total_pnl", filter=Q(total_pnl__gt=0)),
            gross_loss=Sum("total_pnl", filter=Q(total_pnl__lt=0)),
        )

        gross_profit = agg["gross_profit"] or Decimal("0")
        gross_loss = abs(agg["gross_loss"] or Decimal("0"))
        total_pnl = gross_profit - gross_loss

        wins = closed_trades_qs.filter(total_pnl__gt=0).count()
        losses = closed_trades_qs.filter(total_pnl__lt=0).count()

        win_rate = round(wins / closed_count * 100, 2) if closed_count else 0.0
        profit_factor = round(float(gross_profit / gross_loss), 2) if gross_loss else 0.0
        avg_return = round(float(total_pnl / closed_count), 2) if closed_count else 0.0

        # Risk:Reward ratio string
        avg_win = (gross_profit / wins) if wins else Decimal("0")
        avg_loss = (gross_loss / losses) if losses else Decimal("0")
        if avg_win > 0 and avg_loss > 0:
            rr = round(float(avg_win / avg_loss), 2)
            risk_reward_ratio = f"1:{rr}"
        elif avg_win > 0:
            risk_reward_ratio = "1:∞"
        else:
            risk_reward_ratio = "N/A"

        # Max drawdown
        pnl_list = list(
            closed_trades_qs.order_by("trade_date", "created_at")
            .values_list("total_pnl", flat=True)
        )
        max_drawdown = Decimal("0")
        max_drawdown_pct = 0.0
        if pnl_list:
            equity = Decimal("0")
            peak = Decimal("0")
            for pnl in pnl_list:
                pnl = Decimal(str(pnl or "0"))
                equity += pnl
                if equity > peak:
                    peak = equity
                drawdown = peak - equity
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                    max_drawdown_pct = (
                        round(float(drawdown / peak) * 100, 2) if peak > 0 else 0.0
                    )

        # Strategy meta
        try:
            strategy_obj = Strategy.objects.get(pk=sid)
            strategy_name = strategy_obj.strategy_name
            market_types = strategy_obj.market_types or []
            trade_type = strategy_obj.trade_type or ""
            maturity_status = strategy_obj.maturity_status
            sample_size_threshold = strategy_obj.sample_size_threshold or 0
        except Strategy.DoesNotExist:
            strategy_name = "Unknown"
            market_types = []
            trade_type = ""
            maturity_status = "testing"
            sample_size_threshold = 0

        sample_size_progress = (
            min(round((total / sample_size_threshold) * 100, 2), 100)
            if sample_size_threshold
            else 0.0
        )

        strategies.append(
            {
                "strategy_id": str(sid),
                "strategy_name": strategy_name,
                "market_types": market_types,
                "trade_type": trade_type,
                "maturity_status": maturity_status,
                "total_trades": total,
                "closed_trades": closed_count,
                "win_rate": win_rate,
                "avg_return": avg_return,
                "total_pnl": float(total_pnl),
                "profit_factor": profit_factor,
                "risk_reward_ratio": risk_reward_ratio,
                "max_drawdown": float(max_drawdown),
                "max_drawdown_pct": max_drawdown_pct,
                "sample_size_progress": sample_size_progress,
                # kept internally for scoring — popped before response if needed
                "_profit_factor": profit_factor,
            }
        )

    strategies.sort(key=lambda x: x["total_pnl"], reverse=True)

    # Remove internal-only keys before sending to client
    for s in strategies:
        s.pop("_profit_factor", None)

    # -----------------------------------------------------------------------
    # Comparison — bar chart scores (0-100 per metric per strategy)
    # -----------------------------------------------------------------------
    METRIC_KEYS = ["win_rate", "avg_return", "consistency", "risk_reward", "execution"]
    METRIC_LABELS = ["Win Rate", "Avg Return", "Consistency", "Risk-Reward", "Execution"]

    comparison_series = []
    for s in strategies:
        pf = s.get("profit_factor", 0)
        scores = {
            "win_rate":    round(_score_win_rate(s["win_rate"]), 1),
            "avg_return":  round(_score_avg_return(pf), 1),
            "consistency": round(_score_consistency(s["win_rate"], pf), 1),
            "risk_reward": round(_score_risk_reward(s["risk_reward_ratio"]), 1),
            "execution":   round(_score_execution(s["sample_size_progress"], s["total_trades"]), 1),
        }
        comparison_series.append(
            {
                "strategy_name": s["strategy_name"],
                "strategy_id":   s["strategy_id"],
                "scores":        scores,
            }
        )

    comparison = {
        "metrics": METRIC_LABELS,
        "metric_keys": METRIC_KEYS,
        "series": comparison_series,
    }

    # -----------------------------------------------------------------------
    # Radar — spider/radar chart (metric × strategy)
    # -----------------------------------------------------------------------
    radar = []
    for label, key in zip(METRIC_LABELS, METRIC_KEYS):
        entry = {"metric": label}
        for cs in comparison_series:
            entry[cs["strategy_name"]] = cs["scores"][key]
        radar.append(entry)

    # -----------------------------------------------------------------------
    # Evolution — simplified cards sorted by total_trades desc
    # Only the 4 fields shown on the frontend timeline cards
    # -----------------------------------------------------------------------
    evolution = sorted(
        [
            {
                "strategy_name": s["strategy_name"],
                "total_trades":  s["total_trades"],
                "win_rate":      s["win_rate"],
                "avg_return":    s["avg_return"],
            }
            for s in strategies
        ],
        key=lambda x: x["total_trades"],
        reverse=True,
    )

    return {
        "strategies": strategies,
        "comparison": comparison,
        "radar":      radar,
        "evolution":  evolution,
    }