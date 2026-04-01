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
    "total_metrics": 12,
    "active_metrics": 9
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
  "data_state":    "active",
  "status":        "good",
  "trend":         "Improving",
  "what_it_means": "You follow your rules 84.5% of the time",
  "evidence":      "2 hard + 1 soft violations across 30 sessions",
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
| `value`         | float \| null  | Calculated metric value, rounded. `null` if minimum data threshold not met |
| `unit`          | string         | Display unit: `"%"`, `"₹"`, `"/10"`, `"/100"`, `"sessions"`, or `""` |
| `data_state`    | string         | Data availability — see **Data State Values** below |
| `status`        | string         | Health indicator — see Status Values per metric below |
| `trend`         | string         | Direction or level label — see per-metric details below |
| `what_it_means` | string         | Human-readable interpretation. Shows an unlock message if data threshold not met |
| `evidence`      | string         | Supporting data point drawn from recent activity |
| `cta`           | object         | Call-to-action with `label` (display text) and `type` (frontend route key) |

#### Data State Values

| `data_state`       | Meaning |
|--------------------|---------|
| `"active"`         | Minimum data threshold met; `value` is valid |
| `"not_enough_data"`| Below minimum threshold; `value` is `null` |

> **Note:** FIE always returns `data_state: "active"` because it defaults to `0` when no RED sessions exist.

#### Special Fields (present only on certain metrics)

| Field            | Metric | Description |
|------------------|--------|-------------|
| `is_estimated`   | FIE, CPI | `true` — frontend must label the value as estimated |
| `raw_expectancy` | DAE    | Raw avg P&L across all trades (float), shown side-by-side with disciplined expectancy |

#### CTA Type Values

| `type`         | Navigates to              |
|----------------|---------------------------|
| `"rules"`      | Rules & limits screen     |
| `"journal"`    | Journal / quick journal   |
| `"learn"`      | Learning section          |
| `"discipline"` | Discipline Guard screen   |
| `"reports"`    | Reports section           |
| `"strategies"` | Strategy detail screen    |

---

## The 12 Metrics

### 1. DIS — Discipline Integrity Score

**Range:** 0–100 | **Unit:** `%` | **Higher is better**

All-time cumulative weighted penalty score starting at 100.

**Formula:**
```
DIS = 100
    − (hard_violations        × 10)
    − (soft_violations        × 5)
    − (sessions_with_gt1_rule × 5)   ← "repeated same mistake"
    − (red_days_journal_skipped × 8)
    − (override_proxy_sessions × 12)
    capped at 0 (never negative)
```

`override_proxy_sessions` = YELLOW/RED sessions where `unlocked_at` is set but `required_actions_completed` is False.

**Minimum data:** 1 session (all-time).

| Status      | Condition       |
|-------------|-----------------|
| `good`      | score ≥ 80      |
| `improving` | score ≥ 60      |
| `warning`   | score < 60      |

**Trend:** `"Improving"` if score ≥ 60, `"Declining"` otherwise.

**Evidence:** `"{hard} hard + {soft} soft violations across {n} sessions"`

**CTA:** `"Review Rules & Limits"` → `rules`

**Unlock message:** `"Log at least 1 session to unlock DIS"`

---

### 2. VMI — Violation Momentum Index

**Range:** integer | **Unit:** none (no display unit) | **Lower is better**

Compares rule-engine violations across the last 10 trades, split into two windows of 5.

**Data source:** `ViolationsLog` — one row per rule breach per trade, auto-populated by the engine.
> ⚠️ Do **not** use `Trade.violation_modes` (user psychology tag) or `Trade.is_disciplined` for VMI.

**Formula:**
```
last_10_trades = most recent 10 trades ordered by trade_date, created_at desc
window_A       = last 5 trades (most recent)
window_B       = prev 5 trades
count_A        = trades in window_A that have ≥1 ViolationsLog entry
count_B        = trades in window_B that have ≥1 ViolationsLog entry
VMI            = count_A − count_B
```

**Minimum data:** 10 trades (no manual tagging required).

| Level       | VMI Value | Status     |
|-------------|-----------|------------|
| `Improving` | < 0       | `good`     |
| `Stable`    | = 0       | `stable`   |
| `Warning`   | 1 – 2     | `warning`  |
| `Critical`  | ≥ 3       | `critical` |

**Trend:** The level string (`"Improving"` / `"Stable"` / `"Warning"` / `"Critical"`).

**`what_it_means` per level:**

| Level       | Message |
|-------------|---------|
| `Improving` | `"Mistakes are reducing — good momentum"` |
| `Stable`    | `"No change in violation pattern"` |
| `Warning`   | `"Mistakes are starting to cluster"` |
| `Critical`  | `"Violations are snowballing — act now"` |

**Evidence:** `"{n} of last 5 trades had rule violation(s)"`

**CTA:** `"Complete Quick Journal"` → `journal`

**Unlock message:** `"Log at least 10 trades to unlock VMI"`

---

### 3. DRT — Discipline Recovery Time

**Range:** 0+ | **Unit:** `sessions` | **Lower is better**

Average number of sessions between a RED session and the next clean GREEN session (zero violations).

**Formula:** Mean of all measured recovery spans across ordered session history. Returns `null` if no recoveries recorded yet.

**Minimum data:** 1 RED session that has been followed by a GREEN recovery.

| Status     | Condition       |
|------------|-----------------|
| `good`     | days < 2        |
| `warning`  | 2 ≤ days < 4    |
| `critical` | days ≥ 4        |

**Trend:** Always `"Stable"`.

**Evidence:** `"You recover discipline in {avg} session(s) after RED violations"`

**CTA:** `"Watch Recovery Lesson"` → `learn`

**Unlock message:** `"Complete at least 1 RED session recovery to unlock DRT"`

---

### 4. TPR — Trading Permission Ratio

**Range:** 0–100 | **Unit:** `%` | **Higher is better**

Percentage of sessions in the last 30 days where `peak_state` was `green`.

**Formula:** `green_sessions / total_sessions × 100` (rolling 30 days)

**Minimum data:** 10 sessions in the last 30 days.

| Status     | Condition    |
|------------|--------------|
| `good`     | score ≥ 80   |
| `warning`  | score ≥ 50   |
| `critical` | score < 50   |

**Trend:** Always `"Stable"`.

**Evidence:** `"{score}% of your sessions in the last 30 days were GREEN (fully tradeable)"`

**CTA:** `"View Session History"` → `discipline`

**Unlock message:** `"Log at least 10 sessions in the last 30 days to unlock TPR"`

---

### 5. FIE — Forced Inactivity Effectiveness

**Range:** 0+ | **Unit:** `₹` | **Informational / estimated**

Estimated capital protected by RED-session forced stops where the user did **not** override.

**Formula:**
```
respected_red_sessions = RED sessions where required_actions_completed = True
FIE = avg_loss_per_trade × avg_trades_per_session × respected_red_sessions
```

`avg_loss_per_trade` = mean of all-time losing trades (`total_pnl < 0`), made positive.

Returns `0` if no respected RED sessions exist.

> `data_state` is always `"active"` for FIE. `is_estimated: true` is always set — frontend must label it as estimated.

| Status    | Condition |
|-----------|-----------|
| `neutral` | Always    |

**Trend:** Always `"Neutral"`.

**Evidence:** `"{n} RED session(s) blocked — estimated {₹amount} in losses avoided"`

**CTA:** `"View RED Sessions"` → `discipline`

---

### 6. OVR — Override Resistance Score

**Range:** 0–10 | **Unit:** `/10` | **Higher is better**

Measures how well the user respects the system lock in the last 30 days.

> ⚠️ **Implementation note:** A dedicated `session_override_attempts` table is not yet built. OVR currently uses `ViolationsLog` hard-violation count during YELLOW/RED sessions in the last 30 days as the closest proxy. Replace `_calc_ovr()` once the override_attempts table exists.

**Formula:**
```
override_attempts = ViolationsLog hard violations in YELLOW/RED sessions in last 30 days
OVR = max(10 − override_attempts, 0)
```

**Minimum data:** Always calculable (returns `0` if no sessions exist).

| Status     | Condition    |
|------------|--------------|
| `good`     | score ≥ 9    |
| `warning`  | score ≥ 6    |
| `critical` | score < 6    |

**Trend:** Always `"Stable"`.

**Evidence:**
- If no trades during RED sessions: `"No trades forced through RED sessions — excellent system trust"`
- Otherwise: `"{n} trade(s) taken during RED sessions"`

**CTA:** `"Review Override Events"` → `discipline`

**Unlock message:** `"Override resistance will calculate once you have RED sessions"`

---

### 7. ECI — Emotion Cost Index

**Range:** any (typically ≤ 0) | **Unit:** `₹` | **Closer to 0 is better**

Total P&L (including wins and losses) on all trades tagged with non-calm emotional states.

**Non-calm emotions tracked:** `fomo`, `anxious`, `fearful`, `angry`, `overconfident`, `uncertain`

> Unlike the original spec (losses only), ECI sums **all** P&L on emotional trades — wins included — to show the full opportunity cost.

**Formula:** `SUM(total_pnl) WHERE emotional_state IN non_calm_emotions AND is_tagged_complete = True`

**Minimum data:** 10 tagged trades (`is_tagged_complete = True`).

| Status     | Condition             |
|------------|-----------------------|
| `stable`   | abs(amount) < ₹1,000  |
| `warning`  | abs(amount) < ₹5,000  |
| `critical` | abs(amount) ≥ ₹5,000  |

**Trend:** `"Critical"` if status is `critical`, `"Stable"` otherwise.

**Evidence:** `"Worst emotional state: {EMOTION} costs you {₹amount} in total P&L"` (or fallback total if no per-state data).

**CTA:** `"Review Emotional Patterns"` → `journal`

**Unlock message:** `"Tag emotional states on at least 10 trades to unlock ECI"`

---

### 8. CAS — Confidence Accuracy Score

**Range:** 0–100 | **Unit:** `%` | **Higher is better**

Percentage of high-confidence trades (rated 8–10) that were profitable.

**Formula:**
```
high_conf_trades = trades with entry_confidence ≥ 8
high_conf_wins   = high_conf_trades with total_pnl > 0
CAS              = high_conf_wins / high_conf_trades × 100
```

Returns `null` if no trades have `entry_confidence ≥ 8`.

**Minimum data:** 10 trades with `entry_confidence` set (any band).

| Status     | Condition    |
|------------|--------------|
| `good`     | score ≥ 70   |
| `warning`  | score ≥ 50   |
| `critical` | score < 50   |

**Trend:** Always `"Stable"`.

**Evidence:** `"High-confidence calls (8-10) were profitable {score}% of the time"`

**CTA:** `"View Confidence Analysis"` → `reports`

**Unlock message:** `"Rate confidence on at least 10 trades to unlock CAS"`

---

### 9. DAE — Discipline-Adjusted Expectancy

**Range:** any | **Unit:** `₹` | **Positive is better**

True expectancy formula applied separately to disciplined and undisciplined tagged trades.

**Expectancy formula (per group):**
```
expectancy = (win_rate × avg_win) + (loss_rate × avg_loss)
```
(`avg_loss` is already negative, so this correctly subtracts it.)

**Disciplined trade** = `is_disciplined = True AND is_tagged_complete = True`
**Undisciplined trade** = `is_disciplined = False AND is_tagged_complete = True`

**Minimum data:** 20 tagged trades.

**Two values returned:**

| Field            | Description |
|------------------|-------------|
| `value`          | Disciplined expectancy (`dae_r`) — avg expectancy per GREEN-discipline trade |
| `raw_expectancy` | Raw expectancy across all tagged trades (`dae_raw`) — shown side-by-side |

| Status     | Condition       |
|------------|-----------------|
| `good`     | dae_r > 0       |
| `neutral`  | dae_r = 0       |
| `critical` | dae_r < 0       |

**Trend:** `"Positive"` if `dae_r > 0`, `"Negative"` otherwise.

**Evidence:**
- Disciplined earns more: `"Disciplined trades earn {₹diff} more per trade than your average"`
- Disciplined earns less: `"Disciplined trades earn {₹diff} less per trade — review discipline criteria"`
- Equal: `"Disciplined and average expectancy are equal — keep building sample size"`

**CTA:** `"View Expectancy Report"` → `reports`

**Unlock message:** `"Tag at least 20 trades as disciplined/undisciplined to unlock DAE"`

---

### 10. SMI — Strategy Maturity Index

**Range:** 0–100 | **Unit:** `/100` | **Higher is better**

Weighted composite score per strategy. The snapshot stores the **most-used strategy** only; `strategy_health` returns all strategies.

**Formula (per strategy):**
```
sample_pct    = min(trade_count / threshold × 100, 100)         [40%]
adherence_pct = is_disciplined_trades / trade_count × 100       [30%]
consistency   = max(100 − (coeff_of_variation × 50), 0)         [20%]
calm_pct      = calm_or_confident_tagged_trades / total × 100   [10%]

SMI = (sample_pct × 0.40) + (adherence_pct × 0.30)
    + (consistency × 0.20) + (calm_pct × 0.10)
```

`threshold` defaults to `30` if not set on the strategy. Consistency uses the coefficient of variation of trade P&L (lower variance = higher score). When `mean_pnl = 0`, consistency defaults to `50`.

**Minimum data:** 10 trades per strategy.

**Maturity thresholds (from `_smi_status`):**

| Score    | `smi_status`  | Status      |
|----------|---------------|-------------|
| ≥ 71     | `mature`      | `good`      |
| 41 – 70  | `developing`  | `improving` |
| < 41     | `testing`     | `warning`   |

**Trend:** `smi_status` capitalised (e.g. `"Mature"`, `"Testing"`).

**Evidence:**
- `"Top strategy '{name}' — {n} trades logged"`
- `"No strategy trades yet — tag your trades to build SMI"`

**CTA:** `"View Strategy Details"` → `strategies`

**Unlock message:** `"Tag a strategy on at least 10 trades to unlock SMI"`

---

### 11. DDR — Discipline Dependency Ratio

**Range:** 0–100 | **Unit:** `%` | **Higher is better**

How much of the P&L edge is driven by disciplined vs undisciplined trading. Reuses DAE values.

**Formula:**
```
DDR = abs((dae_disciplined − dae_undisciplined) / dae_disciplined) × 100
```

Returns `null` if `dae_disciplined = 0` (to avoid division by zero).

**Minimum data:** Same as DAE (20 tagged trades).

| Level    | DDR Score | Status     |
|----------|-----------|------------|
| `High`   | ≥ 70      | `good`     |
| `Medium` | 30 – 69   | `warning`  |
| `Low`    | < 30      | `critical` |

**Trend:** The level string (`"Low"` / `"Medium"` / `"High"`).

**Evidence:** `"Disciplined expectancy {₹disc} vs undisciplined {₹undisc} — {Level} discipline dependency"`

**CTA:** `"View Behaviour Report"` → `reports`

**Unlock message:** `"Unlock DAE first — DDR is calculated from DAE data"`

---

### 12. CPI — Capital Protection Index

**Range:** 0–100 | **Unit:** `%` | **Higher is better**

Measures how effectively trading rules have reduced drawdown. Two calculation branches exist.

> `is_estimated: true` is always set — frontend must label it as estimated.

**Minimum data:** 30 days of trade history.

**Branch A — rules_enabled_at date exists on the user profile:**
```
dd_before = peak-to-trough drawdown of cumulative P&L before rules_enabled_at
dd_after  = peak-to-trough drawdown of cumulative P&L after rules_enabled_at
CPI       = max((dd_before − dd_after) / dd_before × 100, 0)
```

**Branch B — new user (no before/after split):**
```
red_blocked        = RED sessions where required_actions_completed = True
max_possible_loss  = avg_trades_per_session × avg_loss_per_trade × red_blocked
CPI                = (max_possible_loss − actual_total_losses) / max_possible_loss × 100
                     clamped to [0, 100]
```

Returns `0` if rule exists but no RED sessions blocked. Returns `null` if < 30 days of data.

| Status     | Condition    |
|------------|--------------|
| `good`     | score ≥ 30   |
| `warning`  | score ≥ 10   |
| `critical` | score < 10   |

**Trend:** Always `"Stable"`.

**Evidence:** `"Capital protection score: {score}% — based on drawdown before vs after rules"`

**CTA:** `"Set Capital & Rules"` → `rules`

**Unlock message:** `"Log 30 days of trade data to unlock CPI"`

---

## Categories

`categories` is a fixed array of 4 objects grouping the 12 metrics thematically:

```json
[
  {
    "name": "Discipline & Behaviour",
    "metric_count": 3,
    "metrics": ["DIS", "VMI", "DRT"]
  },
  {
    "name": "Session & Control",
    "metric_count": 3,
    "metrics": ["TPR", "FIE", "OVR"]
  },
  {
    "name": "Psychology & Performance",
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

> **Note:** The third category name is `"Psychology & Performance"` (ampersand, not plus sign).

---

## Strategy Health

`strategy_health` is an array of SMI detail rows — one per strategy the user has trades for, ordered by `total_trades` descending.

```json
[
  {
    "strategy_id":       "uuid",
    "strategy_name":     "Breakout",
    "total_trades":      45,
    "smi_score":         72.4,
    "data_state":        "active",
    "maturity_status":   "mature",
    "maturity_label":    "Mature",
    "win_rate":          64.4,
    "sample_progress":   100.0,
    "min_trades_needed": 0
  }
]
```

| Field               | Description |
|---------------------|-------------|
| `strategy_id`       | UUID of the strategy |
| `strategy_name`     | Display name |
| `total_trades`      | Total non-deleted trades using this strategy |
| `smi_score`         | Composite SMI score (same formula, applied per strategy) |
| `data_state`        | `"active"` if ≥ 10 trades, `"not_enough_data"` otherwise |
| `maturity_status`   | Raw status: `mature` / `developing` / `testing` |
| `maturity_label`    | Capitalised version of `maturity_status` |
| `win_rate`          | Win rate % for this strategy |
| `sample_progress`   | Progress toward `sample_size_threshold`, capped at 100% |
| `min_trades_needed` | Trades still needed to reach the 10-trade minimum (0 once met) |

---

## Meta

```json
{
  "snapshot_date":  "2025-01-15",
  "calculated_at":  "2025-01-15T10:30:00.000000+00:00",
  "total_metrics":  12,
  "active_metrics": 9
}
```

| Field            | Description |
|------------------|-------------|
| `snapshot_date`  | The date the snapshot was calculated for (always today) |
| `calculated_at`  | ISO timestamp (from `auto_now` on the model). May include timezone offset |
| `total_metrics`  | Always `12` |
| `active_metrics` | Count of scorecard cards where `data_state == "active"` |

---

## Minimum Data Thresholds

| Metric | Threshold |
|--------|-----------|
| DIS    | 1 session (all-time) |
| VMI    | 10 trades (no tagging required — ViolationsLog is auto-populated) |
| DRT    | 1 RED session followed by a GREEN recovery |
| TPR    | 10 sessions in last 30 days |
| FIE    | Always calculable — returns `0` if no RED sessions |
| OVR    | Always calculable |
| ECI    | 10 `is_tagged_complete = True` trades |
| CAS    | 10 trades with `entry_confidence` set (any band) |
| DAE    | 20 tagged trades |
| SMI    | 10 trades per strategy |
| DDR    | Same as DAE (20 tagged trades) |
| CPI    | 30 days of trade history |

---

## Snapshot Persistence

Each call to `GET /api/insights/metrics/` triggers `calculate_metrics(user, snapshot_date=today)` which **upserts** a `UserMetricSnapshot` row for today via `update_or_create`. Stale data is always overwritten — there is no caching layer.

The snapshot is also consumed by:
- **Reports** module (`behavior`, `overview` reports)
- **Discipline Guard** (`overview`'s `exclusiveMetrics` block)

These consumers read the stored snapshot without recalculating.

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

- `discipline` — `DisciplineSession`, `ViolationsLog` (session states, peak_state, violation counts, hard/soft splits)
- `tradelog` — `Trade` (P&L, emotional state, entry_confidence, `is_disciplined`, `is_tagged_complete`, strategy tags)
- `rules` — consulted by the violation engine; `rules_enabled_at` on the user profile is used by CPI Branch A
- `strategies` — `Strategy` (`maturity_status`, `sample_size_threshold`)
- `accounts` — `User` (`rules_enabled_at` for CPI Branch A)

---

## Known Implementation Notes

| # | Note |
|---|------|
| 1 | **OVR proxy** — A dedicated `session_override_attempts` table is not yet built. OVR uses hard violations from `ViolationsLog` in YELLOW/RED sessions (last 30 days) as a proxy. Replace `_calc_ovr()` once the table exists. |
| 2 | **ECI scope** — ECI sums all P&L (wins + losses) on non-calm emotional trades, not losses only. This shows total opportunity cost including profitable emotional trades. |
| 3 | **CAS band** — CAS uses high-confidence band `entry_confidence ≥ 8` (not `≥ 7` as in the original spec). Evidence copy also reflects this: `"High-confidence calls (8-10)"`. |
| 4 | **TPR threshold** — Status thresholds are `≥ 80 → good`, `≥ 50 → warning`, `< 50 → critical` (not `≥ 70` as in the original spec). |
| 5 | **DDR levels** — DDR thresholds are `≥ 70 → High`, `30–69 → Medium`, `< 30 → Low` (not the `≥ 40` boundary in the original spec). |
| 6 | **SMI weights** — Actual formula weights are `40/30/20/10` (sample/adherence/consistency/emotion). Consistency uses P&L coefficient of variation, not win rate. |
