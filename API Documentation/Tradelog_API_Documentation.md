# Tradelog API Documentation

## Overview

The **Tradelog** module is the core data layer of BitsOfTrade. It manages trade creation, retrieval, update, soft-delete, and bulk CSV/Excel import. Every trade save triggers the **Discipline Rule Engine** via a `post_save` signal, which evaluates active rules, logs violations, and escalates the session state automatically.

---

## Base URL

```
/api/tradelog/
```

---

## Authentication

All endpoints require JWT authentication:

```
Authorization: Bearer <access_token>
```

---

## Pagination

List endpoints use `StandardResultsSetPagination`:

| Parameter   | Default | Max  | Description          |
|-------------|---------|------|----------------------|
| `page`      | 1       | —    | Page number          |
| `page_size` | 5       | 100  | Results per page     |

```json
{
  "count": 120,
  "next": "http://localhost:13025/api/tradelog/trades/?page=2",
  "previous": null,
  "results": [ "...trades..." ]
}
```

---

## Endpoints

---

### 1. List / Create Trades

#### `GET /api/tradelog/trades/`

Returns all non-deleted trades for the authenticated user, ordered by most recent `trade_date` and `trade_time` first.

**Permissions:** Authenticated

**Query Parameters — all filters are combinable (ANDed together):**

| Parameter          | Type    | Values / Example                                                                                      | Description                                                        |
|--------------------|---------|-------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| `filter`           | string  | `wins` \| `losses` \| `disciplined` \| `violations`                                                  | Outcome quick-filter tab                                           |
| `broker`           | string  | `zerodha`, `upstox`, `groww` …                                                                        | Matches `broker_name` (case-insensitive)                           |
| `market_type`      | enum    | `indian_stocks` \| `forex` \| `crypto` \| `options`                                                  | Top-bar instrument filter                                          |
| `date_range`       | enum    | `today` \| `this_week` \| `this_month` \| `custom`                                                   | Date window shortcut                                               |
| `date_from`        | date    | `YYYY-MM-DD`                                                                                          | Used when `date_range=custom`                                      |
| `date_to`          | date    | `YYYY-MM-DD`                                                                                          | Used when `date_range=custom`                                      |
| `direction`        | enum    | `long` \| `short`                                                                                     | Trade direction                                                    |
| `outcome`          | enum    | `win` \| `loss` \| `open`                                                                             | `win` = pnl > 0, `loss` = pnl < 0, `open` = no exit price         |
| `instrument_type`  | enum    | `indian_stocks` \| `forex` \| `crypto` \| `options`                                                  | Alias for `market_type` — same field                               |
| `strategy`         | UUID    | `<strategy-uuid>`                                                                                     | Filter by linked strategy                                          |
| `emotional_state`  | enum    | `calm` \| `anxious` \| `confident` \| `fearful` \| `fomo` \| `angry` \| `overconfident` \| `uncertain` | Psychology tag                                                  |
| `discipline_status`| enum    | `disciplined` \| `violations`                                                                         | Maps to `is_disciplined` boolean                                   |
| `review_status`    | enum    | `tagged` \| `untagged`                                                                                | Maps to `is_tagged_complete` boolean                               |
| `rule_breach`      | string  | `fomo_entry,overtrading` (comma-separated)                                                            | Matches values inside `violation_modes` JSON array                 |
| `pnl_min`          | decimal | `-10000`                                                                                              | P&L range lower bound (₹)                                         |
| `pnl_max`          | decimal | `10000`                                                                                               | P&L range upper bound (₹)                                         |
| `mistakes`         | string  | `fomo_entry,revenge_trading,oversized_position,premature_exit,ignored_stop_loss,overtrading`          | Comma-separated — searches `violation_modes` JSON array            |
| `tags`             | string  | `tag1,tag2` (comma-separated)                                                                         | Searches `violation_modes` AND `rules_followed` JSON arrays        |
| `search`           | string  | `RELIANCE`                                                                                            | Free-text: matches `symbol`, `broker_name`, `lessons_learned`      |
| `page`             | integer | `1`                                                                                                   | Page number                                                        |
| `page_size`        | integer | `5` (max 100)                                                                                         | Results per page                                                   |

**Example combined query:**
```
GET /api/tradelog/trades/?market_type=indian_stocks&date_range=this_month&outcome=win&emotional_state=calm
GET /api/tradelog/trades/?broker=zerodha&review_status=untagged&pnl_max=0
GET /api/tradelog/trades/?mistakes=fomo_entry,revenge_trading&direction=long&date_range=this_week
```

**Success Response — `200 OK`:** paginated list of trade objects.

---

#### `POST /api/tradelog/trades/`

Creates a single trade manually. The session is checked for a lock **before** saving — if today's session is locked the request is blocked with `423`.

After a successful save the view automatically:
- Calculates `total_pnl` via `calculate_pnl()`
- Sets `is_tagged_complete = true` if `strategy`, `emotional_state`, and `entry_confidence` are all provided
- Triggers `strategy.update_maturity()` if a strategy is linked
- The `post_save` signal fires the Rule Engine for the trade's date

**Permissions:** Authenticated

**Request Body:**

| Field                 | Type    | Required | Description |
|-----------------------|---------|----------|-------------|
| `trade_date`          | date    | ✅        | `YYYY-MM-DD` |
| `symbol`              | string  | ✅        | Ticker symbol (max 100 chars) |
| `market_type`         | enum    | ✅        | `indian_stocks` / `forex` / `crypto` / `options` |
| `direction`           | enum    | ✅        | `long` / `short` |
| `quantity`            | decimal | ✅        | Number of units (up to 4 decimal places) |
| `entry_price`         | decimal | ✅        | Entry price (up to 4 decimal places) |
| `exit_price`          | decimal | ❌        | Exit price. Required for P&L calculation. If omitted, `total_pnl` stays `null`. |
| `fees`                | decimal | ❌        | Brokerage / transaction fees. Defaults to `0`. |
| `stop_loss`           | decimal | ❌        | Stop loss price (nullable) |
| `target`              | decimal | ❌        | Target price (nullable) |
| `leverage`            | decimal | ❌        | Leverage multiplier. Defaults to `1`. |
| `trade_time`          | time    | ❌        | Entry time `HH:MM:SS` (nullable) |
| `strategy`            | UUID    | ❌        | Linked strategy ID (nullable) |
| `entry_confidence`    | integer | ❌        | Pre-trade confidence 1–10 (nullable) |
| `satisfaction_rating` | integer | ❌        | Post-trade satisfaction 1–10 (nullable) |
| `emotional_state`     | enum    | ❌        | `calm` / `anxious` / `confident` / `fearful` / `fomo` / `angry` / `overconfident` / `uncertain` |
| `violation_modes`     | array   | ❌        | List of violation mode strings. Defaults to `[]`. |
| `lessons_learned`     | string  | ❌        | Free-text lessons |
| `rules_followed`      | array   | ❌        | List of rule strings followed. Defaults to `[]`. |
| `screenshot_urls`     | array   | ❌        | List of screenshot URL strings. Defaults to `[]`. |
| `broker_name`         | string  | ❌        | Broker name (nullable) |
| `import_source`       | enum    | ❌        | `manual` / `csv_import`. Defaults to `manual`. |

> **Read-only fields** (cannot be set in the request body): `id`, `user`, `total_pnl`, `is_disciplined`, `session`, `created_at`, `updated_at`.

**P&L Formula:**
```
Long:  total_pnl = (exit_price − entry_price) × quantity × leverage − fees
Short: total_pnl = (entry_price − exit_price) × quantity × leverage − fees
```

**Success Response — `201 Created`:** full trade object.

**Session Locked Response — `423 Locked`:**

```json
{
  "error": "Trading session is locked.",
  "detail": "Your trading session is locked (RED). Complete the required actions in the Discipline section to unlock."
}
```

---

### 2. Retrieve / Update / Delete Trade

#### `GET /api/tradelog/trades/<uuid:id>/`

Returns a single trade owned by the authenticated user.

#### `PUT /api/tradelog/trades/<uuid:id>/`

Fully updates the trade. After save, `total_pnl` and `is_tagged_complete` are recalculated automatically. `strategy.update_maturity()` is also called if a strategy is linked.

#### `PATCH /api/tradelog/trades/<uuid:id>/`

Partially updates the trade. Same post-save recalculation applies.

#### `DELETE /api/tradelog/trades/<uuid:id>/`

Soft-deletes the trade by setting `deleted_at` to now.

**Permissions:** Authenticated (owner only)

**Success Response:** `200 OK` (GET/PUT/PATCH) — full trade object. `204 No Content` (DELETE).

---

### 3. Import Trades

#### `POST /api/tradelog/trades/import/`

Bulk-imports trades from a CSV or Excel file. Automatically detects broker format (Zerodha, Upstox, Groww, or generic CSV). Rows are processed in chronological order. The Rule Engine fires after each row — if a session locks mid-import, all remaining rows for that date and all subsequent rows are stopped.

**Permissions:** Authenticated

**Content-Type:** `multipart/form-data`

**Request Body:**

| Field         | Type   | Required | Description |
|---------------|--------|----------|-------------|
| `file`        | file   | ✅        | `.csv`, `.xlsx`, or `.xls` file |
| `broker_name` | string | ❌        | Broker hint for format detection (e.g. `zerodha`, `upstox`, `groww`). If omitted, format is auto-detected. |

**Supported file types:** `.csv`, `.xlsx`, `.xls`

**Supported broker formats:** Zerodha, Upstox, Groww, Generic CSV

**Duplicate detection:** A trade is skipped (not errored) if an identical record already exists matching `(user, trade_date, symbol, direction, entry_price, quantity)` on a non-deleted trade.

**Session lock behaviour during import:**
- Before each row, the session lock is checked for that row's `trade_date`
- After each row saves, the lock is re-checked (the Rule Engine may have just locked it)
- Once any date locks, **all remaining rows** (including other dates) are stopped
- Duplicate rows are silently skipped and do **not** stop the import

**Success Response — `201 Created`:**

```json
{
  "imported": 18,
  "failed": 2,
  "skipped": 1,
  "detected_broker": "zerodha",
  "errors": [
    {
      "row": 5,
      "error": "Import stopped — session locked for 2025-01-10: Your trading session is locked (RED).",
      "data": { "...raw row..." }
    }
  ],
  "message": "18 trades imported successfully."
}
```

**Import stopped mid-way — `201 Created`** *(still 201, but with stop metadata)*:

```json
{
  "imported": 12,
  "failed": 8,
  "skipped": 0,
  "detected_broker": "upstox",
  "errors": [ "...first 10 errors..." ],
  "import_stopped": true,
  "stopped_at_date": "2025-01-10",
  "message": "12 trades imported. Import stopped at 2025-01-10 due to a rule violation. Unlock that session to import remaining trades."
}
```

**Error Response — `400 Bad Request`:**

```json
{ "error": "Unsupported file type. Upload CSV or Excel." }
{ "error": "File parsing failed: <detail>" }
{ "error": "Format normalization failed: <detail>" }
```

> **Note:** `errors` in the success response is capped at the first 10 failures to keep the response size manageable.

---

## Trade Model Reference

| Field                 | Type     | Writable | Description |
|-----------------------|----------|----------|-------------|
| `id`                  | UUID     | ❌        | Primary key |
| `user`                | FK       | ❌        | Trade owner — set from authenticated user |
| `session`             | FK       | ❌        | Linked `DisciplineSession` — set by the post_save signal |
| `strategy`            | FK       | ✅        | Linked `Strategy` (nullable) |
| `trade_date`          | date     | ✅        | Trade date |
| `trade_time`          | time     | ✅        | Entry time (nullable) |
| `symbol`              | string   | ✅        | Ticker symbol |
| `market_type`         | enum     | ✅        | `indian_stocks` / `forex` / `crypto` / `options` |
| `direction`           | enum     | ✅        | `long` / `short` |
| `quantity`            | decimal  | ✅        | Units traded |
| `entry_price`         | decimal  | ✅        | Entry price |
| `exit_price`          | decimal  | ✅        | Exit price (nullable — open trade if null) |
| `fees`                | decimal  | ✅        | Transaction fees. Defaults to `0`. |
| `stop_loss`           | decimal  | ✅        | Stop loss price (nullable) |
| `target`              | decimal  | ✅        | Target price (nullable) |
| `leverage`            | decimal  | ✅        | Leverage multiplier. Defaults to `1`. |
| `total_pnl`           | decimal  | ❌        | Calculated P&L — set automatically after save |
| `entry_confidence`    | integer  | ✅        | 1–10 pre-trade confidence (nullable) |
| `satisfaction_rating` | integer  | ✅        | 1–10 post-trade satisfaction (nullable) |
| `emotional_state`     | enum     | ✅        | `calm` / `anxious` / `confident` / `fearful` / `fomo` / `angry` / `overconfident` / `uncertain` (nullable) |
| `violation_modes`     | array    | ✅        | List of violation mode strings. Defaults to `[]`. |
| `lessons_learned`     | string   | ✅        | Free-text lessons |
| `rules_followed`      | array    | ✅        | List of rule strings followed. Defaults to `[]`. |
| `is_disciplined`      | boolean  | ❌        | Set by the Rule Engine signal — `true` if no hard violations |
| `is_tagged_complete`  | boolean  | ❌        | Auto-set to `true` when `strategy`, `emotional_state`, and `entry_confidence` are all present |
| `screenshot_urls`     | array    | ✅        | List of screenshot URL strings. Defaults to `[]`. |
| `import_source`       | enum     | ✅        | `manual` / `csv_import`. Defaults to `manual`. |
| `broker_name`         | string   | ✅        | Broker name (nullable) |
| `deleted_at`          | datetime | ❌        | Soft-delete timestamp (null = active) |
| `created_at`          | datetime | ❌        | Auto-set on creation |
| `updated_at`          | datetime | ❌        | Auto-updated on save |

### Computed Properties

| Property    | Type    | Description |
|-------------|---------|-------------|
| `is_winner` | boolean | `true` if `total_pnl` is not null and `total_pnl > 0` |

---

## `is_tagged_complete` Logic

A trade is automatically marked `is_tagged_complete = true` when all three of the following are present:

- `strategy` is set (not null)
- `emotional_state` is set (not null)
- `entry_confidence` is set (not null)

This is evaluated on every `POST` and `PUT`/`PATCH` save.

---

## Rule Engine Integration

Every trade save (manual or import) fires the `post_save` signal in `discipline/signals.py`, which:

1. Gets or creates a `DisciplineSession` for the trade's date
2. Sets `lock_cycle_started_at` to midnight of that date if not already set
3. Links the trade to the session via `trade.session`
4. Calls `rules.engine.evaluate_rules_for_user(user, session, trade)`
5. Sets `trade.is_disciplined = false` if a hard violation was logged for this trade

The signal is **skipped** when an `update_fields` save only touches: `total_pnl`, `is_tagged_complete`, `is_disciplined`, or `session`.

---

## URL Configuration

```python
# tradelog/urls.py
urlpatterns = [
    path('trades/',           TradeListCreateView.as_view(), name='trade-list-create'),
    path('trades/import/',    TradeImportView.as_view(),     name='trade-import'),
    path('trades/<uuid:pk>/', TradeDetailView.as_view(),     name='trade-detail'),
]
```

---

## Error Reference

| Status Code | Meaning |
|-------------|---------|
| `200`       | OK — request successful |
| `201`       | Created — trade(s) created or import completed |
| `204`       | No Content — trade soft-deleted |
| `400`       | Bad Request — validation error or unsupported file type |
| `401`       | Unauthorized — missing or invalid JWT token |
| `404`       | Not found — trade does not exist or belongs to another user |
| `423`       | Locked — trading session is locked, trade creation blocked |

---

## Dependencies

- `discipline` — `DisciplineSession` (session linking), `signals.py` (Rule Engine trigger)
- `rules` — `evaluate_rules_for_user`, `is_session_locked` (lock check before create/import)
- `strategies` — `Strategy` (FK link, `update_maturity()` called after trade save)
- `accounts` — `User` model
