# Strategies API Documentation

## Overview

The **Strategies** module manages trading strategies for BitsOfTrade. Strategies can be **user-created**, **admin templates**, or **community-shared** (public). Every list and detail response includes live-calculated performance metrics (win rate, P&L, profit factor, sample progress) computed directly from linked trades.

---

## Base URL

```
/api/strategies/
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

### 1. List / Create Strategies

#### `GET /api/strategies/`

Returns all non-deleted strategies belonging to the authenticated user. Each strategy object includes live-calculated performance metrics.

**Permissions:** Authenticated

**Success Response — `200 OK`:**

```json
[
  {
    "id": "uuid",
    "user": 1,
    "created_by_admin": null,
    "source_strategy": null,
    "strategy_name": "Breakout Momentum",
    "description": "Buy breakouts above resistance with volume confirmation.",
    "tags": ["#momentum", "#breakout"],
    "market_types": ["Indian Stocks"],
    "trade_type": "intraday",
    "entry_rules": ["Price breaks above 20-day high", "Volume > 1.5x average"],
    "exit_rules": ["Trail stop by 1 ATR", "Exit at end of day"],
    "risk_management_rules": ["Max 2% risk per trade"],
    "is_public": false,
    "is_template": false,
    "maturity_status": "developing",
    "sample_size_threshold": 30,
    "deleted_at": null,
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-15T10:00:00Z",
    "total_trades": 18,
    "closed_trades": 15,
    "win_rate": 66.67,
    "total_pnl": 8400.00,
    "profit_factor": 2.10,
    "sample_size_progress": 60.00
  }
]
```

---

#### `POST /api/strategies/`

Creates a new strategy for the authenticated user. `user`, `created_by_admin`, `id`, `created_at`, `updated_at`, and `deleted_at` are always set server-side.

**Permissions:** Authenticated

**Request Body:**

| Field                   | Type    | Required | Description |
|-------------------------|---------|----------|-------------|
| `strategy_name`         | string  | ✅        | Display name (max 200 chars) |
| `description`           | string  | ❌        | Free-text strategy description |
| `tags`                  | array   | ❌        | List of tag strings, e.g. `["#momentum"]`. Defaults to `[]`. |
| `market_types`          | array   | ❌        | List of market strings, e.g. `["Indian Stocks", "Options"]`. Defaults to `[]`. |
| `trade_type`            | enum    | ❌        | `intraday` / `swing` / `positional` |
| `entry_rules`           | array   | ❌        | List of entry rule strings. Defaults to `[]`. |
| `exit_rules`            | array   | ❌        | List of exit rule strings. Defaults to `[]`. |
| `risk_management_rules` | array   | ❌        | List of risk rule strings. Defaults to `[]`. |
| `is_public`             | boolean | ❌        | Whether to share to the community. Defaults to `false`. |
| `maturity_status`       | enum    | ❌        | `testing` / `developing` / `mature`. Defaults to `testing`. |
| `sample_size_threshold` | integer | ❌        | Number of trades needed for full maturity assessment. Defaults to `30`. |

**Success Response — `201 Created`:** full strategy object (without performance metrics — use GET to retrieve them).

---

### 2. Retrieve / Update / Delete Strategy

#### `GET /api/strategies/<uuid:id>/`

Returns a single strategy with live-calculated performance metrics. Only the authenticated user's own strategies are accessible.

#### `PUT /api/strategies/<uuid:id>/`

Fully updates the strategy. All writable fields required.

#### `PATCH /api/strategies/<uuid:id>/`

Partially updates the strategy.

#### `DELETE /api/strategies/<uuid:id>/`

Soft-deletes the strategy by setting `deleted_at` to now.

**Permissions:** Authenticated (owner only)

**Success Response:** `200 OK` (GET/PUT/PATCH) — full strategy object with metrics. `204 No Content` (DELETE).

---

### 3. Community Strategies

#### `GET /api/strategies/community/`

Returns all public (`is_public=true`) non-deleted strategies from **other users** (the authenticated user's own public strategies are excluded). Includes live performance metrics calculated across all users' trades for each strategy.

**Permissions:** Authenticated

**Success Response — `200 OK`:** list of strategy objects with performance metrics.

> Performance metrics for community strategies are calculated across **all trades** linked to the strategy (not filtered to the requesting user), so they reflect the original author's results.

---

### 4. Template Strategies

#### `GET /api/strategies/templates/`

Returns all admin-created template strategies (`is_template=true`). Templates are not filtered by user and are visible to everyone. Performance metrics are **not** included — templates are returned as plain serialized objects.

**Permissions:** Authenticated

**Success Response — `200 OK`:** list of strategy objects (no metrics).

---

### 5. Add Community Strategy to Mine

#### `POST /api/strategies/<uuid:id>/add-to-mine/`

Copies a public community strategy into the authenticated user's own strategy library. The copy is a full deep copy of all rules and settings, linked back to the original via `source_strategy`.

**Permissions:** Authenticated

**Request Body:** none required.

**Copied fields:**

| Field                   | Behaviour on copy |
|-------------------------|-------------------|
| `strategy_name`         | Original name + `" (Copy)"` suffix |
| `description`           | Copied as-is |
| `tags`                  | Copied as-is |
| `market_types`          | Copied as-is |
| `entry_rules`           | Copied as-is |
| `exit_rules`            | Copied as-is |
| `risk_management_rules` | Copied as-is |
| `trade_type`            | Copied as-is |
| `sample_size_threshold` | Copied as-is |
| `is_public`             | Always set to `false` |
| `is_template`           | Always set to `false` |
| `maturity_status`       | Always reset to `testing` |
| `source_strategy`       | Set to the original strategy's UUID |
| `user`                  | Set to the requesting user |

**Success Response — `201 Created`:** full strategy object of the new copy.

**Error Response — `404 Not Found`** *(strategy not found or not public)*:

```json
{
  "error": "Strategy not found or not public."
}
```

---

### 6. Assign Trades to Strategy

#### `POST /api/strategies/<uuid:id>/assign-trades/`

Assigns one or more of the authenticated user's trades to this strategy. Three mutually exclusive modes — the first matching key in the request body wins.

**Permissions:** Authenticated (owner only)

**Request Body:**

| Field                 | Type    | Required | Description |
|-----------------------|---------|----------|-------------|
| `trade_ids`           | array   | —        | List of specific trade UUIDs to assign |
| `assign_all_untagged` | boolean | —        | If `true`, assigns all user trades that have no strategy set |
| `assign_all`          | boolean | —        | If `true`, assigns every non-deleted trade for this user to this strategy |

> Exactly one of the three fields must be provided. Providing none returns a `400`.

**After assignment the view also:**
- Recalculates `total_pnl` for any newly assigned closed trades that are missing it
- Calls `strategy.update_maturity(total_trades)` to recalculate `maturity_status` based on current sample progress

**Maturity thresholds (based on `sample_size_progress`):**

| Progress         | `maturity_status` |
|------------------|-------------------|
| < 50%            | `testing`         |
| 50% – < 90%      | `developing`      |
| ≥ 90%            | `mature`          |

**Success Response — `200 OK`:**

```json
{
  "assigned": 12,
  "strategy": {
    "...full strategy object with updated metrics..."
  }
}
```

**Error Responses:**

```json
{ "error": "Strategy not found or does not belong to you." }
```

```json
{ "error": "Provide trade_ids, assign_all_untagged: true, or assign_all: true." }
```

---

## Performance Metrics

All GET responses from `/api/strategies/`, `/api/strategies/<id>/`, `/api/strategies/community/`, and `/api/strategies/<id>/assign-trades/` include these computed fields:

| Field                 | Type    | Description |
|-----------------------|---------|-------------|
| `total_trades`        | integer | All non-deleted trades linked to this strategy (open + closed) |
| `closed_trades`       | integer | Trades with `exit_price` set |
| `win_rate`            | decimal | `wins / closed_trades × 100`, rounded to 2 decimal places. `0` if no closed trades. |
| `total_pnl`           | decimal | Sum of P&L across all closed trades. Calculated on the fly for trades missing `total_pnl`. |
| `profit_factor`       | decimal | `gross_profit / gross_loss`, rounded to 2 decimal places. `0` if no losses. |
| `sample_size_progress`| decimal | `total_trades / sample_size_threshold × 100`, capped at `100`. `0` if threshold is `0`. |

> **P&L fallback:** If `total_pnl` is `null` on a trade, it is calculated on the fly as: `(exit_price − entry_price) × quantity × leverage − fees` for long trades, reversed for short trades.

> **Template strategies** do not include performance metrics (the `template_strategies_view` returns plain serialized objects without calling `_annotate_strategy_metrics`).

---

## Model Reference

### Strategy

| Field                   | Type     | Writable | Description |
|-------------------------|----------|----------|-------------|
| `id`                    | UUID     | ❌        | Primary key |
| `user`                  | FK       | ❌        | Owner user. Set from authenticated user on create. |
| `created_by_admin`      | FK       | ❌        | Admin who created it (null for user-created strategies) |
| `source_strategy`       | FK (self)| ❌        | Points to the original if copied from community |
| `strategy_name`         | string   | ✅        | Display name (max 200 chars) |
| `description`           | string   | ✅        | Free-text description |
| `tags`                  | array    | ✅        | List of tag strings. Defaults to `[]`. |
| `market_types`          | array    | ✅        | List of market type strings. Defaults to `[]`. |
| `trade_type`            | enum     | ✅        | `intraday` / `swing` / `positional` (nullable) |
| `entry_rules`           | array    | ✅        | List of entry rule strings. Defaults to `[]`. |
| `exit_rules`            | array    | ✅        | List of exit rule strings. Defaults to `[]`. |
| `risk_management_rules` | array    | ✅        | List of risk rule strings. Defaults to `[]`. |
| `is_public`             | boolean  | ✅        | `true` = visible in community feed |
| `is_template`           | boolean  | ✅        | `true` = admin-created template |
| `maturity_status`       | enum     | ✅        | `testing` / `developing` / `mature`. Auto-updated by `update_maturity()`. |
| `sample_size_threshold` | integer  | ✅        | Trade count target for maturity assessment. Defaults to `30`. |
| `deleted_at`            | datetime | ❌        | Soft-delete timestamp (null = active) |
| `created_at`            | datetime | ❌        | Auto-set on creation |
| `updated_at`            | datetime | ❌        | Auto-updated on save |

---

## URL Configuration

```python
# strategies/urls.py
urlpatterns = [
    path('',                          StrategyListCreateView.as_view(),  name='strategy-list-create'),
    path('community/',                community_strategies_view,         name='strategy-community'),
    path('templates/',                template_strategies_view,          name='strategy-templates'),
    path('<uuid:pk>/',                StrategyDetailView.as_view(),      name='strategy-detail'),
    path('<uuid:pk>/add-to-mine/',    add_to_mine_view,                  name='strategy-add-to-mine'),
    path('<uuid:pk>/assign-trades/',  assign_trades_view,                name='strategy-assign-trades'),
]
```

---

## Error Reference

| Status Code | Meaning |
|-------------|---------|
| `200`       | OK — request successful |
| `201`       | Created — strategy or copy created |
| `204`       | No Content — soft-deleted |
| `400`       | Bad Request — missing required body field (assign-trades) |
| `401`       | Unauthorized — missing or invalid JWT token |
| `404`       | Not found — strategy does not exist, is deleted, or does not belong to the user |

---

## Dependencies

- `tradelog` — `Trade` model (linked trades for performance metrics and assign-trades)
- `admin_panel` — `Admin` model (`created_by_admin` FK)
- `accounts` — `User` model
