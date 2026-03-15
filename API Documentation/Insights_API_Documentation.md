# Insights API Documentation

## Overview

The **Insights** module calculates and serves all 12 proprietary BitsOfTrade metrics for the authenticated user. On every request the metrics are **recalculated fresh** and persisted into a `UserMetricSnapshot` (one per user per date, upserted). The response is structured for direct frontend consumption — no additional client-side mapping is needed.

---

## Base URL

```
/api/insights/
```

---

## Authentication

All endpoints require JWT authentication:

```
Authorization: Bearer <access_token>
```

---

## Endpoints

### 1. Get Metrics

**`GET /api/insights/metrics/`**

Calculates all 12 proprietary metrics for today, persists the result, and returns a fully-structured response with scorecard cards, category groupings, per-strategy health rows, and metadata.

**Permissions:** Authenticated

**Success Response — `200 OK`:**

```json
{
  "scorecard": [ "...12 metric card objects — see Scorecard Structure below..." ],
  "categories": [ "...4 category grouping objects — see Categories below..." ],
  "strategy_health": [ "...per-strategy SMI rows — see Strategy Health below..." ],
  "meta": {
    "snapshot_date": "2025-01-15",
    "calculated_at": "2025-01-15T10:30:00Z",
    "total_metrics": 12
  }
}
```

---

## Response Structure

### Scorecard

`scorecard` is an array of 12 metric card objects, always in this fixed order:
DIS → VMI → DRT → TPR → FIE → OVR → ECI → CAS → DAE → SMI → DDR → CPI.

Each card has this shape:

```json
{
  "code":          "DIS",
  "label":         "Discipline Integrity Score",
  "value":         84.5,
  "unit":          "%",
  "status":        "good",
  "trend":         "Improving",
  "what_it_means": "You follow your rules 84.5% of the time",
  "evidence":      "3 rule breaches in last 30 days",
  "cta": {
    "label": "Review Rules & Limits",
    "type":  "rules"
  }
}
```

#### Scorecard Fields

| Field           | Type           | Description |
|-----------------|----------------|-------------|
| `code`          | string         | Short metric identifier (e.g. `"DIS"`) |
| `label`         | string         | Full metric name |
| `value`         | float \| null  | Calculated metric value, rounded. `null` if metric cannot be calculated (e.g. CPI with no `trading_capital` set) |
| `unit`          | string         | Display unit: `"%"`, `"₹"`, `"/10"`, `"/100"`, `"sessions"`, or `""` |
| `status`        | string         | Health indicator — see Status Values per metric below |
| `trend`         | string         | Direction or level label — see per-metric details below |
| `what_it_means` | string         | Human-readable interpretation of the current value |
| `evidence`      | string         | Supporting data point drawn from recent activity |
| `cta`           | object         | Call-to-action with `label` (display text) and `type` (frontend route key) |

#### CTA Type Values

| `type`        | Navigates to              |
|---------------|---------------------------|
| `"rules"`     | Rules & limits screen     |
| `"journal"`   | Journal / quick journal   |
| `"learn"`     | Learning section          |
| `"discipline"`| Discipline Guard screen   |
| `"reports"`   | Reports section           |
| `"strategies"`| Strategy detail screen    |

---

## The 12 Metrics

### 1. DIS — Discipline Integrity Score

**Range:** 0–100 | **Unit:** `%` | **Higher is better**

Weighted penalty score starting at 100. Deducted for every rule breach across all sessions.

**Formula:**
```
DIS = 100 − (violations_count × 5) − (hard_violations × 3) − (sessions_with_gt1_violation × 2)
      capped at 0 (never negative)
```

| Status      | Condition       |
|-------------|-----------------|
| `good`      | score ≥ 80      |
| `improving` | score ≥ 60      |
| `warning`   | score < 60      |

**Trend:** `"Improving"` if score ≥ 60, `"Declining"` otherwise.

**Evidence:** Rule breach count in the last 30 days.

---

### 2. VMI — Violation Momentum Index

**Range:** 0–100 | **Unit:** none | **Lower is better**

Compares violations in the last 7 days against the prior 7 days.

**Formula:**
```
ratio = last_7_days_violations / prev_7_days_violations
VMI   = min(ratio × 50, 100)

Special cases:
  Both periods = 0  →  VMI = 0
  Prev period = 0 but current > 0  →  VMI = 100 (maximum momentum)
```

| Level    | VMI Score    | Status     |
|----------|-------------|------------|
| `Low`    | < 35        | `good`     |
| `Medium` | 35 – 74     | `warning`  |
| `High`   | ≥ 75        | `critical` |

**Trend:** The level string itself (`"Low"` / `"Medium"` / `"High"`).

**Evidence:** Violation count across the last 5 trades.

---

### 3. DRT — Discipline Recovery Time

**Range:** 0+ | **Unit:** `sessions` | **Lower is better**

Average number of sessions between a violation day and the next clean (GREEN) session.

**Formula:** Mean of all measured recovery spans across session history. Returns `0` if no recoveries recorded yet.

| Status     | Condition      |
|------------|----------------|
| `stable`   | days = 0 or < 2 |
| `warning`  | 2 ≤ days < 4   |
| `critical` | days ≥ 4       |

**Trend:** Always `"Stable"`.

**Evidence:** Average recovery duration in sessions.

---

### 4. TPR — Trading Permission Ratio

**Range:** 0–100 | **Unit:** `%` | **Higher is better**

Percentage of all sessions where `peak_state` was `green` (full trading permission).

**Formula:** `green_sessions / total_sessions × 100`

| Status     | Condition    |
|------------|--------------|
| `good`     | score ≥ 70   |
| `warning`  | score ≥ 50   |
| `critical` | score < 50   |

**Trend:** Always `"Stable"`.

**Evidence:** `"X% of your sessions are GREEN (tradeable)"`.

---

### 5. FIE — Forced Inactivity Effectiveness

**Range:** 0+ | **Unit:** `₹` | **Informational only**

Estimated capital protected by RED-session forced stops.

**Formula:** `avg_loss_on_red_session_dates × red_session_count`

Only losing trades (`total_pnl < 0`) on RED session dates are used for the average. Returns `0` if no RED sessions exist.

| Status    | Condition |
|-----------|-----------|
| `neutral` | Always    |

**Trend:** Always `"Neutral"`.

**Evidence:** Count of RED sessions that triggered forced inactivity.

---

### 6. OVR — Override Resistance Score

**Range:** 1–10 | **Unit:** `/10` | **Higher is better**

Measures how well the user respects the system lock. Proxy: trades taken during RED sessions subtract from 10.

**Formula:**
```
If no RED sessions ever  →  OVR = 10
Otherwise: OVR = max(10 − (red_session_trade_count × 0.5), 1)
```

| Status     | Condition    |
|------------|--------------|
| `good`     | score ≥ 8    |
| `warning`  | score ≥ 5    |
| `critical` | score < 5    |

**Trend:** Always `"Stable"`.

**Evidence:** Number of trades taken during RED sessions (or confirmation of perfect resistance).

---

### 7. ECI — Emotion Cost Index

**Range:** ≤ 0 | **Unit:** `₹` | **Closer to 0 is better**

Total P&L losses on trades tagged with negative emotional states. Value is always zero or negative.

**Negative emotions tracked:** `fomo`, `anxious`, `fearful`, `angry`, `overconfident`

**Formula:** `SUM(total_pnl) WHERE emotional_state IN negative_emotions AND total_pnl < 0`

| Status     | Condition             |
|------------|-----------------------|
| `stable`   | abs(amount) < ₹1,000  |
| `warning`  | abs(amount) < ₹5,000  |
| `critical` | abs(amount) ≥ ₹5,000  |

**Trend:** `"Critical"` if status is critical, `"Stable"` otherwise.

**Evidence:** Formatted INR loss amount from emotional trades.

---

### 8. CAS — Confidence Accuracy Score

**Range:** 0–100 | **Unit:** `%` | **Higher is better**

How accurately high-confidence predictions (rated 7–10) win and low-confidence predictions (rated 1–3) lose.

**Formula:**
```
numerator   = high_conf_wins (confidence ≥ 7 AND pnl > 0)
            + low_conf_losses (confidence ≤ 3 AND pnl < 0)
denominator = total_high_conf_trades + total_low_conf_trades
CAS         = numerator / denominator × 100
```

Returns `0` if no trades have `entry_confidence` set.

| Status     | Condition    |
|------------|--------------|
| `good`     | score ≥ 70   |
| `warning`  | score ≥ 50   |
| `critical` | score < 50   |

**Trend:** Always `"Stable"`.

**Evidence:** `"High-confidence calls were right X% of the time"`.

---

### 9. DAE — Discipline-Adjusted Expectancy

**Range:** any | **Unit:** `₹` | **Positive is better**

Compares average P&L per disciplined trade (GREEN sessions only) against overall average.

**Two stored values:**

| Field     | Description |
|-----------|-------------|
| `dae_r`   | Avg P&L of trades in GREEN `peak_state` sessions — the `value` returned in the card |
| `dae_raw` | Avg P&L across all trades — used in evidence text only |

| Status     | Condition       |
|------------|-----------------|
| `good`     | dae_r > 0       |
| `neutral`  | dae_r = 0       |
| `critical` | dae_r < 0       |

**Trend:** `"Positive"` if `dae_r > 0`, `"Negative"` otherwise.

**Evidence:** Difference between disciplined and raw avg P&L per trade.

---

### 10. SMI — Strategy Maturity Index

**Range:** 0–100 | **Unit:** `/100` | **Higher is better**

Weighted composite score for the user's **most-used strategy** (by trade count).

**Formula (applied to most-used strategy):**
```
sample_progress = min(trade_count / sample_size_threshold × 100, 100)
win_rate        = wins / trade_count × 100
calm_rate       = calm_or_confident_trades / trade_count × 100
disc_rate       = is_disciplined_trades / trade_count × 100

SMI = (sample_progress × 0.30)
    + (win_rate        × 0.25)
    + (calm_rate       × 0.25)
    + (disc_rate       × 0.20)
```

`sample_size_threshold` defaults to 30 if not set on the strategy.

**Maturity status** comes from `Strategy.maturity_status`:

| `smi_status`  | Status      |
|---------------|-------------|
| `mature`      | `good`      |
| `developing`  | `improving` |
| `testing`     | `warning`   |

**Trend:** `smi_status` capitalised (e.g. `"Mature"`, `"Testing"`).

**Evidence:** Top strategy name and trade count.

> If no strategy trades exist, `smi_score = 0` and `smi_status = "testing"`.

---

### 11. DDR — Discipline Dependency Ratio

**Range:** 0–100 | **Unit:** `%` | **Higher is better**

How much of the user's P&L edge comes from disciplined sessions vs undisciplined ones.

**Formula:**
```
If total_pnl ≠ 0:
  DDR = abs((green_sessions_pnl − non_green_sessions_pnl) / total_pnl × 100)

Fallback (total_pnl = 0):
  DDR = abs(green_win_rate − non_green_win_rate)
```

| Level    | DDR Score | Status     |
|----------|-----------|------------|
| `Low`    | < 10      | `critical` |
| `Medium` | 10 – 39   | `warning`  |
| `High`   | ≥ 40      | `good`     |

**Trend:** The level string (`"Low"` / `"Medium"` / `"High"`).

**Evidence:** `"Disciplined sessions contribute X% more to your P&L (Level dependency)"`.

---

### 12. CPI — Capital Protection Index

**Range:** 0–100 | **Unit:** `%` | **Higher is better**

Percentage of trading days where the user stayed within their active max-loss rule.

**Requirements:**
- `user.trading_capital` must be set
- An active risk rule with `trigger_condition.maxDailyPercent` must exist (admin or user-defined)

If either is missing, `value` is `null` and `status` is `"neutral"`.

**Formula:**
```
max_loss_allowed = trading_capital × maxDailyPercent / 100
compliant_days   = days where daily_pnl ≥ −max_loss_allowed (or no trades)
CPI              = compliant_days / total_trading_days × 100
```

If the rule exists but no trading days are on record, returns `0`.
If the rule does not exist, returns `100` (no rule to violate).

| Status     | Condition    |
|------------|--------------|
| `good`     | score ≥ 90   |
| `warning`  | score ≥ 70   |
| `critical` | score < 70   |

**Trend:** Always `"Stable"`.

**Evidence:** `"You stayed within max-loss rule on X% of trading days"`.

---

### Categories

`categories` is a fixed array of 4 objects grouping the 12 metrics thematically:

```json
[
  {
    "name": "Discipline & Behaviour",
    "metric_count": 3,
    "metrics": ["DIS", "DRT", "VMI"]
  },
  {
    "name": "Session & Control",
    "metric_count": 3,
    "metrics": ["TPR", "FIE", "OVR"]
  },
  {
    "name": "Psychology + Performance",
    "metric_count": 3,
    "metrics": ["ECI", "CAS", "DAE"]
  },
  {
    "name": "System Intelligence",
    "metric_count": 3,
    "metrics": ["SMI", "DDR", "CPI"]
  }
]
```

---

### Strategy Health

`strategy_health` is an array of SMI detail rows — one entry per strategy the user has trades for, ordered by `total_trades` descending.

```json
[
  {
    "strategy_id":     "uuid",
    "strategy_name":   "Breakout",
    "total_trades":    45,
    "smi_score":       72.4,
    "maturity_status": "developing",
    "maturity_label":  "Developing",
    "win_rate":        64.4,
    "sample_progress": 100.0
  }
]
```

| Field             | Description |
|-------------------|-------------|
| `strategy_id`     | UUID of the strategy |
| `strategy_name`   | Display name |
| `total_trades`    | Total non-deleted trades using this strategy |
| `smi_score`       | Composite SMI score (same formula as metric 10, applied per strategy) |
| `maturity_status` | Raw status from `Strategy.maturity_status` (`mature`/`developing`/`testing`) |
| `maturity_label`  | Capitalised version of `maturity_status` |
| `win_rate`        | Win rate % for this strategy |
| `sample_progress` | Progress toward `sample_size_threshold` (capped at 100%) |

---

### Meta

```json
{
  "snapshot_date": "2025-01-15",
  "calculated_at": "2025-01-15T10:30:00Z",
  "total_metrics": 12
}
```

| Field           | Description |
|-----------------|-------------|
| `snapshot_date` | The date the snapshot was calculated for (always today) |
| `calculated_at` | ISO timestamp of the most recent calculation (from `auto_now` on the model) |
| `total_metrics` | Always `12` |

---

## Snapshot Persistence

Each call to `GET /api/insights/metrics/` triggers `calculate_metrics(user, snapshot_date=today)` which **upserts** a `UserMetricSnapshot` row for today via `update_or_create`. Stale data is always overwritten — there is no caching.

The snapshot is also read by the Reports module (`behavior`, `overview`) and the Discipline Guard (`overview`'s `exclusiveMetrics` block) without recalculating.

---

## URL Configuration

```python
# insights/urls.py
urlpatterns = [
    path('metrics/', metrics_view, name='insights-metrics'),
]
```

---

## Error Reference

| Status Code | Meaning |
|-------------|---------|
| `200`       | OK — metrics calculated and returned |
| `401`       | Unauthorized — missing or invalid JWT token |
| `405`       | Method Not Allowed — endpoint is `GET` only |

---

## Dependencies

- `discipline` — `DisciplineSession`, `ViolationsLog` (session states, violation counts)
- `tradelog` — `Trade` (P&L, emotional state, confidence, `is_disciplined`, strategy tags)
- `rules` — `Rule` (active `maxDailyPercent` rule for CPI)
- `strategies` — `Strategy` (`maturity_status`, `sample_size_threshold`)
- `accounts` — `User` (`trading_capital` for FIE, OVR, CPI calculations)
