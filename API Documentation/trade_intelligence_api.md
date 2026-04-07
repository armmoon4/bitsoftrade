# Trade Intelligence API Documentation

## Overview

The Trade Intelligence API analyses a trader's historical performance and behavioural data to produce a structured intelligence report. It combines trade logs, discipline sessions, psychology journals, violations, and rule data to surface actionable insights across five dimensions.

---

## Endpoint

```
POST /api/trade-intelligence/analyze/
```

### Authentication

**Required.** All requests must be made by an authenticated user. The response is scoped strictly to the requesting user's data.

---

## Request

### Headers

| Header | Value |
|---|---|
| `Content-Type` | `application/json` |
| `Authorization` | `Bearer <token>` (or session cookie) |

### Body Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `timeRange` | `string` | Yes | Predefined period. One of: `all`, `last7`, `last30`, `last90`, `last365`, `custom`. Defaults to `last30`. |
| `fromDate` | `string` | Conditional | Start date in `YYYY-MM-DD` format. Required when `timeRange` is `custom`. |
| `toDate` | `string` | Conditional | End date in `YYYY-MM-DD` format. Required when `timeRange` is `custom`. |
| `market` | `string` | No | Filter trades by market type (e.g. `forex`, `crypto`). Pass `all` or omit to include all markets. |
| `broker` | `string` | No | Filter trades by broker name (case-insensitive). Pass `all` or omit to include all brokers. |

### `timeRange` Values

| Value | Period |
|---|---|
| `all` | All available trade history |
| `last7` | Last 7 days |
| `last30` | Last 30 days *(default)* |
| `last90` | Last 90 days |
| `last365` | Last 365 days |
| `custom` | Date range defined by `fromDate` and `toDate` |

### Example Request

```json
{
  "timeRange": "last30",
  "market": "forex",
  "broker": "IC Markets"
}
```

```json
{
  "timeRange": "custom",
  "fromDate": "2025-01-01",
  "toDate": "2025-03-31"
}
```

---

## Response

### 200 OK — No Trades Found

When no trades exist in the selected period, a minimal response is returned.

```json
{
  "period": "Last 30 Days",
  "total_trades": 0,
  "message": "No trades found in the selected period."
}
```

### 200 OK — Full Intelligence Report

```json
{
  "period": "Last 30 Days",
  "total_trades": 142,
  "intelligence_summary": { ... },
  "doing_well": [ ... ],
  "holding_back": [ ... ],
  "repeating_patterns": [ ... ],
  "discipline_health": { ... }
}
```

---

## Response Sections

### Top-Level Fields

| Field | Type | Description |
|---|---|---|
| `period` | `string` | Human-readable label for the analysed period (e.g. `"Last 30 Days"`, `"2025-01-01 – 2025-03-31"`). |
| `total_trades` | `integer` | Total number of trades in scope after filters. |

---

### 1. `intelligence_summary`

A high-level narrative and core performance metrics for the period.

| Field | Type | Description |
|---|---|---|
| `text` | `string` | Auto-generated narrative summarising overall performance and discipline. |
| `performance` | `string` | `"positive"` or `"negative"` based on total P&L. |
| `discipline_consistency` | `string` | `"strong and consistent"` (discipline score ≥ 80), `"improving but fragile"` (score ≥ 65), or `"unstable and needs work"` (score < 65). Note: these thresholds differ from the `health_rating` thresholds in `discipline_health`. |
| `best_profit_session_state` | `string` | Session state with the highest cumulative P&L — `GREEN`, `YELLOW`, or `RED`. |
| `loss_cluster_session_state` | `string` | Session state with the lowest (worst) cumulative P&L — `GREEN`, `YELLOW`, or `RED`. |
| `total_pnl` | `float` | Net P&L across all filtered trades, rounded to 2 decimal places. |
| `wins` | `integer` | Number of trades with positive P&L. |
| `losses` | `integer` | Number of trades with negative P&L. |
| `win_rate_pct` | `float` | Percentage of winning trades out of total trades. |

**Example:**
```json
"intelligence_summary": {
  "text": "Over the Last 30 Days, your performance is positive, but discipline consistency is improving but fragile. Most profits came from trend-following trades executed during GREEN sessions. Losses cluster during RED sessions driven by FOMO and early entries.",
  "performance": "positive",
  "discipline_consistency": "improving but fragile",
  "best_profit_session_state": "GREEN",
  "loss_cluster_session_state": "RED",
  "total_pnl": 1240.50,
  "wins": 89,
  "losses": 53,
  "win_rate_pct": 62.7
}
```

---

### 2. `doing_well`

An array of positive behaviour metrics — things the trader is executing correctly.

Each item has the following shape:

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Unique identifier for the metric. |
| `label` | `string` | Human-readable metric name. |
| `value` | `number` | The measured value (count or percentage depending on metric). |
| `out_of` | `number \| null` | The denominator or maximum, if applicable. |
| `pct` | `float \| null` | Percentage representation, if applicable. |
| `description` | `string` | Plain-English explanation of the result. |
| `view_in_plan` | `boolean` | Whether the metric links to a trading plan rule. |

**Metrics included:**

| `id` | Description |
|---|---|
| `confirmation_rate` | Trades where `entry_confidence >= 7`, indicating the trader waited for a confirmed setup. Percentage is out of all trades. |
| `strategy_adherence` | Trades where `is_disciplined = True` and a strategy is assigned, out of all trades that have a strategy assigned. Measures rule-following within strategy trades only. |
| `rr_improvement` | Change in P&L-based risk-to-reward ratio (avg winning P&L ÷ avg losing P&L) from the first half to the second half of the period, by trade count. |
| `avg_loss_vs_threshold` | Average losing trade size as a percentage of notional value (`entry_price × quantity`), compared against the `maxLossPercent`, `maxLoss`, or `maxDailyPercent` rule threshold (defaults to `3.0%` if no matching rule is found). |
| `best_entry_window` | Win rate during the single highest-performing trading hour of the day, determined dynamically by average P&L per hour. |

**Example:**
```json
"doing_well": [
  {
    "id": "confirmation_rate",
    "label": "Waited for confirmation",
    "value": 101,
    "out_of": 142,
    "pct": 71.1,
    "description": "You waited for confirmation 101 out of 142 times",
    "view_in_plan": false
  },
  {
    "id": "rr_improvement",
    "label": "Risk-to-reward improved",
    "value": 0.34,
    "out_of": null,
    "pct": null,
    "description": "Your risk-to-reward improved by +0.34x comparing first vs second half",
    "view_in_plan": false
  }
]
```

---

### 3. `holding_back`

An array of negative behaviour metrics — friction points preventing consistent profitability.

Each item follows the same shape as `doing_well`, with an additional optional field:

| Field | Type | Description |
|---|---|---|
| `avg_session_pnl_after` | `float` | *(FOMO after loss only)* Average session P&L across all sessions that contained at least one FOMO-tagged trade. |

**Metrics included:**

| `id` | Description |
|---|---|
| `fomo_after_loss` | Count and percentage of FOMO-tagged trades that occurred immediately after a losing trade (consecutive trade pairs, same or different day). |
| `fomo_days` | Total trades tagged with `emotional_state = "fomo"` across the period. |
| `risk_after_losses` | Maximum consecutive calendar days with negative net P&L. Signals increasing risk exposure during drawdown. |
| `position_size_violations` | Violations linked to rules whose `rule_name` contains `"position"` (case-insensitive). |
| `premature_exits` | Trades linked to a `TradeMistake` record where `mistake_mode` is `"early_exit"` or `"late_exit"`. |

**Example:**
```json
"holding_back": [
  {
    "id": "fomo_after_loss",
    "label": "FOMO entries after a loss",
    "value": 18,
    "out_of": 53,
    "pct": 34.0,
    "description": "FOMO entries appear 34.0% after a loss",
    "avg_session_pnl_after": -312.40
  },
  {
    "id": "premature_exits",
    "label": "Premature exit trades",
    "value": 22,
    "out_of": 142,
    "pct": 15.5,
    "description": "15.5% of trades had premature exits, causing avg profit left on table"
  }
]
```

---

### 4. `repeating_patterns`

An array of recurring behavioural patterns detected across the period, positive or negative.

Each item shape:

| Field | Type | Description |
|---|---|---|
| `id` | `string` | Unique identifier for the pattern. |
| `label` | `string` | Human-readable pattern name. |
| `value` | `number` | Primary measured value. |
| `out_of` | `number \| null` | Denominator, if applicable. |
| `description` | `string` | Plain-English explanation. |
| `stat` | `string` | Short statistical summary shown in UI. |
| `journal_mention_pct` | `float` | *(revenge trading only)* Revenge trade count as a percentage of total daily journal entries in the period. |

**Patterns included:**

| `id` | Description |
|---|---|
| `revenge_trading` | Consecutive trade pairs on the **same calendar day** where the prior trade was a loss and the next trade's `emotional_state` is `angry`, `fomo`, or `overconfident`. |
| `consecutive_losses` | Maximum consecutive calendar days with negative net P&L. |
| `emotional_clarity` | Longest consecutive streak of trades where `emotional_state` was `calm` or `confident`. |
| `nervous_before_violations` | Percentage of `PsychologyLog` entries in the period where `emotional_state = "anxious"`. |
| `red_day_discipline` | Count of RED-state discipline sessions, and count of those sessions that contained at least one trade with an `emotional_state` of `angry`, `fomo`, or `overconfident`. |

**Example:**
```json
"repeating_patterns": [
  {
    "id": "revenge_trading",
    "label": "Revenge trading after loss",
    "value": 11,
    "out_of": 142,
    "description": "Revenge trading (angry/FOMO/overconfident) appears after losses — 11 occurrences",
    "stat": "11 occurrences detected",
    "journal_mention_pct": 22.0
  },
  {
    "id": "emotional_clarity",
    "label": "Emotional clarity streak (calm/confident)",
    "value": 14,
    "out_of": 142,
    "description": "Emotional clarity held for 14 straight trades",
    "stat": "14 consecutive calm/confident trades"
  }
]
```

---

### 5. `discipline_health`

A holistic view of the trader's discipline scoring, session quality, violations, and trend.

| Field | Type | Description |
|---|---|---|
| `discipline_score` | `float` | Score from 0–100. See formula below. |
| `health_rating` | `string` | Label derived from `discipline_score`: `"Excellent"` (≥ 85), `"Improving but fragile"` (≥ 70), `"Needs Attention"` (≥ 50), `"Critical"` (< 50). |
| `violated_boundaries` | `integer` | Total violations in the period. |
| `hard_violations` | `integer` | Subset of violations classified as `violation_type = "hard"`. |
| `sessions_count` | `integer` | Total discipline sessions in the period. |
| `sessions_per_violation` | `float` | `total_sessions ÷ max(total_violations, 1)`. Higher is better. Returns `total_sessions` when there are zero violations. |
| `trend` | `string` | `"Improving"` if the discipline score of the second half of sessions ≥ first half; `"Declining"` if lower; `"Stable"` if fewer than 2 sessions exist in the period. |
| `green_sessions` | `integer` | Sessions with state `"green"`. |
| `yellow_sessions` | `integer` | Sessions with state `"yellow"`. |
| `red_sessions` | `integer` | Sessions with state `"red"`. |
| `reminder` | `string` | Contextual coaching message. Fragile message shown when `discipline_score < 80`; excellent message shown when `discipline_score >= 80`. |
| `session_pnl_summary` | `object` | Net P&L grouped by session state. |
| `session_pnl_summary.green_pnl` | `float` | Net P&L across all trades in GREEN sessions. |
| `session_pnl_summary.yellow_pnl` | `float` | Net P&L across all trades in YELLOW sessions. |
| `session_pnl_summary.red_pnl` | `float` | Net P&L across all trades in RED sessions. |

**Example:**
```json
"discipline_health": {
  "discipline_score": 73.4,
  "health_rating": "Improving but fragile",
  "violated_boundaries": 9,
  "hard_violations": 3,
  "sessions_count": 28,
  "sessions_per_violation": 3.1,
  "trend": "Improving",
  "green_sessions": 17,
  "yellow_sessions": 7,
  "red_sessions": 4,
  "reminder": "Your discipline is improving, but fragile. One uncommitted session could trigger a cascade. Focus on the 3-second pause before every entry.",
  "session_pnl_summary": {
    "green_pnl": 1820.00,
    "yellow_pnl": -210.50,
    "red_pnl": -369.00
  }
}
```

---

## Discipline Score Formula

```
base  = (green_sessions / total_sessions) × 100
score = max(0, base − (hard_violations × 2))
score = min(score, 100)
```

---

## `discipline_consistency` vs `health_rating` Thresholds

These are two separate labels derived from the same `discipline_score` but using **different thresholds**:

### `discipline_consistency` (in `intelligence_summary`)

| Score Range | Value |
|---|---|
| ≥ 80 | `"strong and consistent"` |
| 65 – 79 | `"improving but fragile"` |
| < 65 | `"unstable and needs work"` |

### `health_rating` (in `discipline_health`)

| Score Range | Rating |
|---|---|
| ≥ 85 | `"Excellent"` |
| 70 – 84 | `"Improving but fragile"` |
| 50 – 69 | `"Needs Attention"` |
| < 50 | `"Critical"` |

---

## Error Responses

| Status | Condition |
|---|---|
| `401 Unauthorized` | Request made without valid authentication credentials. |
| `405 Method Not Allowed` | Endpoint called with a method other than `POST`. |

---

## Notes

- All P&L values are expressed in the user's account currency and rounded to 2 decimal places.
- `market` and `broker` filters are case-insensitive and ignored when set to `"all"`.
- The `custom` time range requires both `fromDate` and `toDate` in `YYYY-MM-DD` format; if either is missing, the API falls back to `last30`.
- Soft-deleted trades (`deleted_at` is not null) are always excluded.
- The `rr_improvement` value is a P&L-based ratio (avg winning P&L ÷ avg losing P&L), not a risk-defined R:R from entry parameters.
- The `best_entry_window` is determined dynamically as the hour with the highest average P&L across all trades with a recorded `trade_time` — it is not fixed to the first 30 minutes of the session.
- Emotional state values used internally: `fomo`, `angry`, `overconfident`, `anxious`, `calm`, `confident`.
