# Mistakes API Documentation

## Overview

The **Mistakes** module manages trading mistakes and their linkage to trades. Mistakes can be **admin-defined** (global, visible to all users) or **user-custom**. The module also provides a dedicated analytics endpoint that surfaces usage trends, P&L impact, clustering detection, and severity distribution.

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

| Field             | Type    | Required | Description |
|-------------------|---------|----------|-------------|
| `mistake_name`    | string  | ✅        | Display name (max 200 chars) |
| `category`        | enum    | ✅        | `execution` / `psychology` / `process` / `risk` |
| `description`     | string  | ❌        | Optional explanation |
| `severity_weight` | integer | ✅        | Severity score 1–10 |
| `user`            | —       | ❌        | Ignored — set from authenticated user |

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

Soft-deletes the custom mistake by setting `deleted_at` to now.

**Permissions:** Authenticated (owner only)

**Success Response:** `200 OK` (GET/PUT/PATCH) — full mistake object. `204 No Content` (DELETE).

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

| Field     | Type | Required | Description |
|-----------|------|----------|-------------|
| `trade`   | UUID | ✅        | ID of the trade to tag |
| `mistake` | UUID | ✅        | ID of the mistake to link |

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

> **Note:** There is no DELETE endpoint for `trade-links`. To unlink a mistake from a trade, use the Django admin or handle it directly at the database level.

---

### 4. Mistakes Analytics

#### `GET /api/mistakes/analytics/`

Returns a full analytics breakdown: per-mistake usage with 30-day trend, P&L impact metrics, clustering detection across the last 5 trades, and severity distribution.

**Permissions:** Authenticated

**Success Response — `200 OK`:**

```json
{
  "usage": [
    {
      "mistake__id": "uuid",
      "mistake__mistake_name": "Overtrading",
      "mistake__description": "Taking more trades than the plan allows.",
      "mistake__category": "psychology",
      "mistake__severity_weight": 7,
      "count": 12,
      "trend": "Increasing",
      "last_30": 8,
      "prev_30": 4
    }
  ],
  "impact": {
    "impacted_count": 18,
    "impacted_percentage": 36.0,
    "total_pnl_impact": -4200.50,
    "clean_trades_count": 32,
    "clean_success_rate": 68.8
  },
  "clustering": {
    "recent_mistakes_count": 4,
    "is_above_average": true,
    "average_per_5": 1.5
  },
  "severity_distribution": {
    "low": 3,
    "medium": 8,
    "high": 7
  }
}
```

---

## Analytics Field Reference

### `usage`

Ordered by `count` descending. One entry per mistake that has been tagged at least once.

| Field                      | Description |
|----------------------------|-------------|
| `mistake__id`              | Mistake UUID |
| `mistake__mistake_name`    | Mistake display name |
| `mistake__description`     | Mistake description |
| `mistake__category`        | Category: `execution` / `psychology` / `process` / `risk` |
| `mistake__severity_weight` | Severity 1–10 |
| `count`                    | Total times this mistake has been tagged across all trades |
| `trend`                    | `Increasing` / `Decreasing` / `Stable` — based on last 30 days vs prior 30 days |
| `last_30`                  | Tag count in the last 30 days |
| `prev_30`                  | Tag count in the 30 days before that |

**Trend logic:**

| Condition             | Trend          |
|-----------------------|----------------|
| `last_30 > prev_30`   | `Increasing`   |
| `last_30 < prev_30`   | `Decreasing`   |
| `last_30 == prev_30`  | `Stable`       |

---

### `impact`

Compares trades that have at least one mistake tagged ("impacted") against trades with no mistakes ("clean").

| Field                 | Description |
|-----------------------|-------------|
| `impacted_count`      | Number of trades with at least one mistake tagged |
| `impacted_percentage` | `impacted_count / total_trades × 100`, rounded to 1 decimal |
| `total_pnl_impact`    | Sum of `total_pnl` across all impacted trades (negative = net loss) |
| `clean_trades_count`  | Trades with no mistakes tagged |
| `clean_success_rate`  | Win rate % of clean trades (trades with `total_pnl > 0` / `clean_trades_count × 100`) |

---

### `clustering`

Detects whether mistakes are clustering in recent activity by comparing the last 5 trades against the historical average.

| Field                   | Description |
|-------------------------|-------------|
| `recent_mistakes_count` | Total mistake tags across the user's last 5 trades (by `trade_date` then `trade_time` desc) |
| `is_above_average`      | `true` if `recent_mistakes_count > average_per_5` |
| `average_per_5`         | Historical average mistakes expected per 5 trades: `(total_mistake_tags / total_trades) × 5`, rounded to 1 decimal |

---

### `severity_distribution`

Buckets all tagged mistakes by their `severity_weight`:

| Bucket   | Range              |
|----------|--------------------|
| `low`    | `severity_weight` ≤ 4 |
| `medium` | 5 ≤ `severity_weight` ≤ 7 |
| `high`   | `severity_weight` > 7 |

---

## Model Reference

### Mistake

| Field             | Type     | Writable | Description |
|-------------------|----------|----------|-------------|
| `id`              | UUID     | ❌        | Primary key |
| `created_by_admin`| FK       | ❌        | Admin who created it (null for user custom) |
| `user`            | FK       | ❌        | Owner user (null for admin-defined). Set server-side. |
| `mistake_name`    | string   | ✅        | Display name (max 200 chars) |
| `category`        | enum     | ✅        | `execution` / `psychology` / `process` / `risk` |
| `description`     | string   | ✅        | Optional description |
| `severity_weight` | integer  | ✅        | 1–10 severity score |
| `is_custom`       | boolean  | ❌        | Always `true` for user-created mistakes. Set server-side. |
| `is_admin_defined`| boolean  | ❌        | `true` = global admin mistake. Set server-side. |
| `deleted_at`      | datetime | ❌        | Soft-delete timestamp (null = active) |
| `created_at`      | datetime | ❌        | Auto-set on creation |

### TradeMistake

| Field             | Type     | Writable | Description |
|-------------------|----------|----------|-------------|
| `id`              | UUID     | ❌        | Primary key |
| `trade`           | FK       | ✅        | Linked trade |
| `mistake`         | FK       | ✅        | Linked mistake |
| `mistake_name`    | string   | ❌        | Denormalised from `mistake.mistake_name` |
| `severity_weight` | integer  | ❌        | Denormalised from `mistake.severity_weight` |
| `category`        | string   | ❌        | Denormalised from `mistake.category` |
| `tagged_at`       | datetime | ❌        | Auto-set when the link is created |

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

| Status Code | Meaning |
|-------------|---------|
| `200`       | OK — request successful |
| `201`       | Created — resource created |
| `204`       | No Content — soft-deleted |
| `400`       | Bad Request — validation error (e.g. duplicate trade+mistake link) |
| `401`       | Unauthorized — missing or invalid JWT token |
| `403`       | Forbidden — cannot delete an admin-defined mistake |
| `404`       | Not found — resource does not exist or belongs to another user |

---

## Dependencies

- `tradelog` — `Trade` model (linked by `TradeMistake`, used in analytics)
- `admin_panel` — `Admin` model (`created_by_admin` FK on `Mistake`)
- `accounts` — `User` model
