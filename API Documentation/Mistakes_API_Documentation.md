# Mistakes API Documentation

## Overview

The **Mistakes** module manages trading mistakes and their linkage to trades. Mistakes can be **admin-defined** (global, visible to all users) or **user-custom**. The module also provides a dedicated analytics endpoint that surfaces mistake frequency trends, P&L impact metrics, and severity distribution.

---

## Base URL

```
/api/mistakes/
```

---

## Authentication

All endpoints require JWT authentication:

```
Authorization: Bearer <access_token>
```

---

## Endpoints

---

### 1. List / Create Mistakes

#### `GET /api/mistakes/`

Returns all non-deleted mistakes visible to the authenticated user: **admin-defined global mistakes** + **the user's own custom mistakes**. Results are ordered: admin-defined first, then by `category`.

**Permissions:** Authenticated

**Success Response — `200 OK`:**

```json
[
  {
    "id": "uuid",
    "created_by_admin": null,
    "user": null,
    "mistake_name": "Overtrading",
    "mistake_mode": "overtrading",
    "category": "psychology",
    "description": "Taking more trades than the plan allows.",
    "severity_weight": 7,
    "is_custom": false,
    "is_admin_defined": true,
    "deleted_at": null,
    "created_at": "2025-01-01T00:00:00Z"
  }
]
```

---

#### `POST /api/mistakes/`

Creates a new user-custom mistake. `is_admin_defined` is always forced to `false` and `is_custom` to `true` server-side — these cannot be set in the request body.

**Permissions:** Authenticated

**Request Body:**

| Field             | Type    | Required | Description                                          |
|-------------------|---------|----------|------------------------------------------------------|
| `mistake_name`    | string  | ✅        | Display name (max 200 chars)                         |
| `category`        | enum    | ✅        | `execution` / `psychology` / `process` / `risk`      |
| `mistake_mode`    | enum    | ❌        | Behavioural pattern — see Mistake Mode choices below |
| `description`     | string  | ❌        | Optional explanation                                 |
| `severity_weight` | integer | ✅        | Severity score 1–10                                  |
| `user`            | —       | ❌        | Ignored — set from authenticated user server-side    |

**Mistake Mode choices:**

| Value               | Label               |
|---------------------|---------------------|
| `overtrading`       | Overtrading         |
| `revenge_trading`   | Revenge Trading     |
| `fomo`              | FOMO                |
| `early_exit`        | Early Exit          |
| `ignored_stop_loss` | Ignored Stop Loss   |
| `late_exit`         | Late Exit           |
| `no_plan`           | No Plan             |
| `oversized_position`| Oversized Position  |

**Success Response — `201 Created`:** full mistake object.

---

### 2. Retrieve / Update / Delete Mistake

> Detail endpoints only access the **user's own custom mistakes**. Admin-defined mistakes return `404` on detail endpoints.

#### `GET /api/mistakes/<uuid:id>/`

Returns a single custom mistake owned by the authenticated user.

#### `PUT /api/mistakes/<uuid:id>/`

Fully updates the custom mistake. All writable fields required.

#### `PATCH /api/mistakes/<uuid:id>/`

Partially updates the custom mistake.

#### `DELETE /api/mistakes/<uuid:id>/`

Soft-deletes the custom mistake by setting `deleted_at` to the current timestamp. The record is **not removed** from the database.

**Permissions:** Authenticated (owner only)

**Success Response:** `200 OK` (GET / PUT / PATCH) — full mistake object. `204 No Content` (DELETE).

**Error Response — `403 Forbidden`** *(if an admin-defined mistake is somehow reached)*:

```json
{
  "error": "Admin-defined mistakes cannot be deleted."
}
```

---

### 3. List / Create Trade Mistake Links

#### `GET /api/mistakes/trade-links/`

Returns all `TradeMistake` junction records for the authenticated user's trades, with denormalised `mistake_name`, `severity_weight`, and `category` fields included.

**Permissions:** Authenticated

**Success Response — `200 OK`:**

```json
[
  {
    "id": "uuid",
    "trade": "trade-uuid",
    "mistake": "mistake-uuid",
    "mistake_name": "Overtrading",
    "severity_weight": 7,
    "category": "psychology",
    "tagged_at": "2025-01-15T10:30:00Z"
  }
]
```

---

#### `POST /api/mistakes/trade-links/`

Links a mistake to a trade. Each `(trade, mistake)` pair must be unique — attempting to link the same mistake to the same trade twice returns a `400`.

**Permissions:** Authenticated

**Request Body:**

| Field     | Type | Required | Description                    |
|-----------|------|----------|--------------------------------|
| `trade`   | UUID | ✅        | ID of the trade to tag         |
| `mistake` | UUID | ✅        | ID of the mistake to link      |

**Success Response — `201 Created`:**

```json
{
  "id": "uuid",
  "trade": "trade-uuid",
  "mistake": "mistake-uuid",
  "mistake_name": "Overtrading",
  "severity_weight": 7,
  "category": "psychology",
  "tagged_at": "2025-01-15T10:30:00Z"
}
```

**Error Response — `400 Bad Request`** *(duplicate link)*:

```json
{
  "non_field_errors": ["The fields trade, mistake must make a unique set."]
}
```

> **Note:** There is no DELETE endpoint for `trade-links`. To unlink a mistake from a trade, handle it directly via the Django admin or at the database level.

---

### 4. Mistakes Analytics

#### `GET /api/mistakes/analytics/`

Returns a three-section analytics breakdown for the authenticated user:

| Section                      | Scope       | Description                                                    |
|------------------------------|-------------|----------------------------------------------------------------|
| `mistake_frequency_last_30`  | Last 30 days| Ranked list of behavioural patterns (`mistake_mode`) by occurrence count |
| `impact`                     | All time    | P&L and trade-count comparison between impacted and clean trades |
| `severity_distribution`      | All time    | High / medium / low bucket counts across all tagged mistakes   |

**Permissions:** Authenticated

**Success Response — `200 OK`:**

```json
{
  "mistake_frequency_last_30": [
    {
      "rank": 1,
      "mistake_mode": "overtrading",
      "label": "Overtrading",
      "count": 8
    },
    {
      "rank": 2,
      "mistake_mode": "fomo",
      "label": "FOMO",
      "count": 5
    },
    {
      "rank": 3,
      "mistake_mode": null,
      "label": "Unclassified",
      "count": 2
    }
  ],
  "impact": {
    "trades_with_mistakes": 18,
    "trades_with_mistakes_percentage": 36.0,
    "loss_from_mistake_trades": -4200.50,
    "clean_trades_count": 32,
    "clean_success_rate": 68.8
  },
  "severity_distribution": {
    "high": {
      "count": 7,
      "range": "8-10",
      "label": "Critical mistakes to eliminate"
    },
    "medium": {
      "count": 8,
      "range": "5-7",
      "label": "Needs improvement"
    },
    "low": {
      "count": 3,
      "range": "1-4",
      "label": "Minor issues"
    }
  }
}
```

---

## Analytics Field Reference

---

### `mistake_frequency_last_30`

A **dynamically ranked list** of behavioural patterns (`mistake_mode`) that occurred in the **last 30 days**, ordered by `count` descending. The list is built entirely from real data — only modes that were actually tagged appear. Modes with zero tags in the window are **omitted entirely**.

---

#### How the data is built

1. All `TradeMistake` records for the user where `tagged_at` date ≥ today − 30 days are collected.
2. They are grouped by `mistake__mistake_mode`.
3. Each group is counted (`Count('id')`) and sorted highest-to-lowest.
4. The server loops over the sorted results and assigns `rank` starting at `1`.
5. The human-readable `label` is resolved from the `Mistake.MISTAKE_MODE` choices dict. If `mistake_mode` is `null`, the label is hardcoded to `"Unclassified"`.

---

#### Field reference

| Field          | Type             | Description |
|----------------|------------------|-------------|
| `rank`         | integer          | 1-based position in the list. Rank 1 = most-tagged pattern this period. **Changes every time the endpoint is called** as new tags are added or the 30-day window rolls forward. |
| `mistake_mode` | string or `null` | Raw `mistake_mode` value stored on the `Mistake` record. `null` means the mistake was created without a mode. |
| `label`        | string           | Display name for the mode, resolved from server-side choices. Never `null` — falls back to the raw value if unrecognised, or `"Unclassified"` for `null` modes. |
| `count`        | integer          | Number of `TradeMistake` tags with this mode in the last 30 days. Always ≥ 1 (zero-count modes are not returned). |

---

#### All possible entries

The list can contain **up to 9 entries** — one per distinct `mistake_mode` value (8 named modes + 1 `null`/Unclassified group). Only modes tagged at least once in the window appear.

| `mistake_mode`        | `label`              | Appears when… |
|-----------------------|----------------------|---------------|
| `overtrading`         | Overtrading          | ≥1 mistake with this mode was tagged in last 30 days |
| `revenge_trading`     | Revenge Trading      | same |
| `fomo`                | FOMO                 | same |
| `early_exit`          | Early Exit           | same |
| `ignored_stop_loss`   | Ignored Stop Loss    | same |
| `late_exit`           | Late Exit            | same |
| `no_plan`             | No Plan              | same |
| `oversized_position`  | Oversized Position   | same |
| `null`                | Unclassified         | ≥1 mistake with `mistake_mode = null` was tagged in last 30 days |

---

#### Rank is dynamic — not fixed

Rank is **not** a stable identifier for a mode. It is purely a position number assigned at query time based on the current `count` ordering. This means:

- A mode ranked `#1` today could be `#3` tomorrow if the user tags other modes more.
- As the 30-day window rolls forward, old tags drop off, counts decrease, and ranks shift.
- A mode can disappear from the list entirely once its last tag falls outside the 30-day window.

**Frontend must not hardcode or cache ranks.** Always re-render from the latest API response.

---

#### Edge cases and frontend handling

| Scenario | What the API returns | How frontend should handle |
|---|---|---|
| No tags at all in last 30 days | `"mistake_frequency_last_30": []` | Show an empty state: *"No mistakes tagged in the last 30 days"* |
| Only one mode tagged | Single-item array, `rank: 1` | Render normally |
| All 8 named modes tagged | 8 entries, ranks 1–8 | Render full list |
| Some modes have equal `count` | Tied modes appear in **DB-determined order** — no secondary sort is applied server-side | Do not imply an ordering between tied entries; treat them as equal |
| Mistakes with no `mistake_mode` set (`null`) were tagged | One entry with `"mistake_mode": null, "label": "Unclassified"` | Render as its own row — do not skip `null` mode entries |
| New tags are added mid-session | Ranks and counts will change on the next API call | Always fetch fresh data before rendering; do not persist rank values in local state |

---

#### Full example — 5 modes tagged

If the user tagged 5 different behavioural patterns in the last 30 days:

```json
[
  { "rank": 1, "mistake_mode": "overtrading",       "label": "Overtrading",         "count": 8 },
  { "rank": 2, "mistake_mode": "fomo",              "label": "FOMO",                "count": 5 },
  { "rank": 3, "mistake_mode": "revenge_trading",   "label": "Revenge Trading",     "count": 4 },
  { "rank": 4, "mistake_mode": null,                "label": "Unclassified",        "count": 2 },
  { "rank": 5, "mistake_mode": "ignored_stop_loss", "label": "Ignored Stop Loss",   "count": 1 }
]
```

The 3 modes not tagged (`early_exit`, `late_exit`, `no_plan`, `oversized_position`) are **absent from the response** — they do not appear with `count: 0`.

---

#### Recommended frontend rendering pattern

```js
// Safe pattern — always iterate what the server returns, never assume fixed ranks
mistakeFrequency.map((entry) => ({
  position:  entry.rank,          // display as "#1", "#2", etc.
  modeName:  entry.label,         // always use label for display, not mistake_mode
  modeKey:   entry.mistake_mode,  // use as React key or for icon mapping; handle null
  count:     entry.count,
}))

// Empty state guard
if (mistakeFrequency.length === 0) {
  return <EmptyState message="No mistakes tagged in the last 30 days" />
}
```

> **Never use `rank` as a stable key or array index.** Use `mistake_mode` as the key (treating `null` as `"unclassified"` for key purposes).

---

### `impact`

Compares **all non-deleted trades** for the user split into two groups:

- **Impacted trades** — trades that have at least one `TradeMistake` record linked to them (all time).
- **Clean trades** — trades with no `TradeMistake` records linked (all time).

`deleted_at__isnull=True` is applied to trades before all calculations, so soft-deleted trades are excluded entirely.

| Field                           | Type    | Description                                                                                                              |
|---------------------------------|---------|--------------------------------------------------------------------------------------------------------------------------|
| `trades_with_mistakes`          | integer | Number of non-deleted trades that have at least one mistake tagged.                                                      |
| `trades_with_mistakes_percentage` | float | `(trades_with_mistakes / total_non_deleted_trades) × 100`, rounded to 1 decimal place. Returns `0` if no trades exist.  |
| `loss_from_mistake_trades`      | float   | Sum of `total_pnl` across all impacted trades, rounded to 2 decimal places. Can be positive or negative depending on actual P&L. Returns `0` if there are no impacted trades. |
| `clean_trades_count`            | integer | Number of non-deleted trades with no mistakes tagged.                                                                    |
| `clean_success_rate`            | float   | Win rate of clean trades: `(clean trades with total_pnl > 0 / clean_trades_count) × 100`, rounded to 1 decimal. Returns `0` if `clean_trades_count` is `0`. |

**Important notes:**

- `loss_from_mistake_trades` is **not filtered to only losses** — it is the raw sum of `total_pnl` for all impacted trades. A positive value means impacted trades were, on net, profitable. The field name indicates the intent (measuring the cost of mistakes) but the value reflects actual P&L.
- `trades_with_mistakes_percentage` uses the **total count of all non-deleted trades** as the denominator, not just impacted trades.
- `clean_success_rate` is `0` (not `null`) when there are no clean trades — handle this in the UI to avoid showing a misleading 0%.

**Example — interpreting the response:**

```json
{
  "trades_with_mistakes": 18,
  "trades_with_mistakes_percentage": 36.0,
  "loss_from_mistake_trades": -4200.50,
  "clean_trades_count": 32,
  "clean_success_rate": 68.8
}
```

18 out of 50 total trades (36%) had at least one mistake tagged. Those impacted trades produced a net P&L of −$4,200.50. The remaining 32 clean trades had a 68.8% win rate.

---

### `severity_distribution`

Buckets **all `TradeMistake` records for the user (all time)** into three severity tiers based on the linked `mistake.severity_weight`. Each bucket is an object containing `count`, the score `range`, and a human-readable `label`.

| Bucket   | Condition                              | `range` | `label`                        |
|----------|----------------------------------------|---------|--------------------------------|
| `high`   | `severity_weight > 7` (i.e. 8, 9, 10) | `"8-10"`| `"Critical mistakes to eliminate"` |
| `medium` | `severity_weight > 4` and `≤ 7` (i.e. 5, 6, 7) | `"5-7"` | `"Needs improvement"` |
| `low`    | `severity_weight ≤ 4` (i.e. 1, 2, 3, 4) | `"1-4"` | `"Minor issues"`           |

> The buckets are **mutually exclusive and exhaustive** — every tagged mistake falls into exactly one bucket.

**Response shape:**

```json
{
  "severity_distribution": {
    "high":   { "count": 7, "range": "8-10", "label": "Critical mistakes to eliminate" },
    "medium": { "count": 8, "range": "5-7",  "label": "Needs improvement" },
    "low":    { "count": 3, "range": "1-4",  "label": "Minor issues" }
  }
}
```

---

## Model Reference

### Mistake

| Field              | Type     | Writable | Description                                                          |
|--------------------|----------|----------|----------------------------------------------------------------------|
| `id`               | UUID     | ❌        | Primary key, auto-generated                                          |
| `created_by_admin` | FK       | ❌        | Admin who created it (`null` for user-custom mistakes)               |
| `user`             | FK       | ❌        | Owner user (`null` for admin-defined). Set server-side on create.    |
| `mistake_name`     | string   | ✅        | Display name (max 200 chars)                                         |
| `mistake_mode`     | enum     | ✅        | Behavioural pattern. See Mistake Mode choices above. Nullable.       |
| `category`         | enum     | ✅        | `execution` / `psychology` / `process` / `risk`                      |
| `description`      | string   | ✅        | Optional explanation                                                 |
| `severity_weight`  | integer  | ✅        | 1–10 severity score                                                  |
| `is_custom`        | boolean  | ❌        | Always `true` for user-created mistakes. Set server-side.            |
| `is_admin_defined` | boolean  | ❌        | `true` = global admin mistake. Set server-side.                      |
| `deleted_at`       | datetime | ❌        | Soft-delete timestamp (`null` = active)                              |
| `created_at`       | datetime | ❌        | Auto-set on creation                                                 |

### TradeMistake

| Field            | Type     | Writable | Description                                           |
|------------------|----------|----------|-------------------------------------------------------|
| `id`             | UUID     | ❌        | Primary key, auto-generated                           |
| `trade`          | FK       | ✅        | Linked trade                                          |
| `mistake`        | FK       | ✅        | Linked mistake                                        |
| `mistake_name`   | string   | ❌        | Denormalised read-only from `mistake.mistake_name`    |
| `severity_weight`| integer  | ❌        | Denormalised read-only from `mistake.severity_weight` |
| `category`       | string   | ❌        | Denormalised read-only from `mistake.category`        |
| `tagged_at`      | datetime | ❌        | Auto-set when the link is created                     |

---

## URL Configuration

```python
# mistakes/urls.py
urlpatterns = [
    path('',             MistakeListCreateView.as_view(),      name='mistake-list-create'),
    path('<uuid:pk>/',   MistakeDetailView.as_view(),          name='mistake-detail'),
    path('trade-links/', TradeMistakeListCreateView.as_view(), name='trade-mistake-list'),
    path('analytics/',   mistakes_analytics_view,              name='mistake-analytics'),
]
```

---

## Error Reference

| Status Code | Meaning                                                                      |
|-------------|------------------------------------------------------------------------------|
| `200`       | OK — request successful                                                      |
| `201`       | Created — resource created                                                   |
| `204`       | No Content — soft-deleted                                                    |
| `400`       | Bad Request — validation error (e.g. duplicate trade + mistake link)         |
| `401`       | Unauthorized — missing or invalid JWT token                                  |
| `403`       | Forbidden — cannot delete an admin-defined mistake                           |
| `404`       | Not Found — resource does not exist or belongs to another user               |

---

## Dependencies

- `tradelog` — `Trade` model (linked by `TradeMistake`, used in analytics impact calculations)
- `admin_panel` — `Admin` model (`created_by_admin` FK on `Mistake`)
- `accounts` — `User` model
