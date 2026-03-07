# Trade Log API Documentation

## Overview

The **Trade Log** module is the core data layer of BitsOfTrade. It manages individual trade records, supports manual entry, CSV/Excel import, P&L auto-calculation, and triggers the rule evaluation engine after every save.

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

## Endpoints

### 1. List Trades

**`GET /api/tradelog/trades/`**

Returns a paginated list of the authenticated user's trades (soft-deleted excluded).

**Permissions:** Authenticated

**Query Parameters:**

| Parameter | Values                              | Description                     |
|-----------|-------------------------------------|---------------------------------|
| `filter`  | `wins` / `losses` / `disciplined` / `violations` | Filter trade list |
| `page`    | integer                             | Pagination page number          |

**Success Response — `200 OK`:**

```json
{
  "count": 42,
  "next": "/api/tradelog/trades/?page=2",
  "previous": null,
  "results": [
    {
      "id": "uuid",
      "symbol": "RELIANCE",
      "direction": "long",
      "trade_date": "2025-01-15",
      "trade_time": "09:30:00",
      "quantity": "100.0000",
      "entry_price": "2450.0000",
      "exit_price": "2500.0000",
      "fees": "25.00",
      "total_pnl": "4975.00",
      "market_type": "indian_stocks",
      "is_disciplined": true,
      "is_tagged_complete": false,
      "emotional_state": "calm",
      "entry_confidence": 8,
      "import_source": "manual"
    }
  ]
}
```

---

### 2. Create Trade (Manual)

**`POST /api/tradelog/trades/`**

Creates a new trade manually. Automatically calculates P&L and triggers rule evaluation.

**Permissions:** Authenticated

> ⚠️ **Returns `423 Locked`** if the user's discipline session is currently locked (RED state or YELLOW with active cooldown).

**Request Body:**

| Field               | Type    | Required | Description                                       |
|---------------------|---------|----------|---------------------------------------------------|
| `symbol`            | string  | ✅        | Ticker/instrument name                            |
| `trade_date`        | date    | ✅        | Format: `YYYY-MM-DD`                              |
| `direction`         | enum    | ✅        | `long` or `short`                                 |
| `quantity`          | decimal | ✅        | Units traded                                      |
| `entry_price`       | decimal | ✅        | Entry price per unit                              |
| `exit_price`        | decimal | ❌        | Exit price per unit (null = open trade)           |
| `fees`              | decimal | ❌        | Brokerage/fees (default: 0)                       |
| `market_type`       | enum    | ❌        | `indian_stocks` / `forex` / `crypto` / `options`  |
| `trade_time`        | time    | ❌        | Format: `HH:MM:SS`                                |
| `stop_loss`         | decimal | ❌        | Stop loss price                                   |
| `target`            | decimal | ❌        | Target price                                      |
| `leverage`          | decimal | ❌        | Leverage multiplier (default: 1)                  |
| `emotional_state`   | enum    | ❌        | `calm` / `anxious` / `confident` / `fearful` / `fomo` / `angry` / `overconfident` / `uncertain` |
| `entry_confidence`  | integer | ❌        | Confidence rating 1-10                            |
| `satisfaction_rating` | integer | ❌      | Satisfaction rating 1-10                          |
| `strategy`          | uuid    | ❌        | Strategy ID to tag this trade to                  |
| `rules_followed`    | array   | ❌        | List of rule IDs followed                         |
| `violation_modes`   | array   | ❌        | List of violation modes                           |
| `lessons_learned`   | string  | ❌        | Free text                                         |

**Success Response — `201 Created`:** full trade object

**Error Response — `423 Locked`:**

```json
{
  "error": "Trading session is locked.",
  "detail": "Your trading session is locked (RED). Complete the required actions in the Discipline section to unlock."
}
```

---

### 3. Retrieve Trade

**`GET /api/tradelog/trades/<uuid:id>/`**

Returns a single trade record.

**Permissions:** Authenticated (owner only)

**Success Response — `200 OK`:** full trade object

---

### 4. Update Trade

**`PUT /api/tradelog/trades/<uuid:id>/`** / **`PATCH /api/tradelog/trades/<uuid:id>/`**

Updates a trade. Recalculates P&L and re-runs rule evaluation.

**Permissions:** Authenticated (owner only)

**Success Response — `200 OK`:** updated trade object

---

### 5. Delete Trade (Soft Delete)

**`DELETE /api/tradelog/trades/<uuid:id>/`**

Soft-deletes the trade by setting `deleted_at` timestamp. Trade is excluded from all queries.

**Permissions:** Authenticated (owner only)

**Success Response — `204 No Content`**

---

### 6. Import Trades (CSV/Excel)

**`POST /api/tradelog/trades/import/`**

Uploads a CSV or Excel file and bulk-imports trades. Auto-detects broker format (Zerodha, Upstox, Groww, or Generic).

**Permissions:** Authenticated

> ⚠️ **Returns `423 Locked`** if the user's discipline session is currently locked.

**Request Body** (`multipart/form-data`):

| Field         | Type   | Required | Description                              |
|---------------|--------|----------|------------------------------------------|
| `file`        | file   | ✅        | `.csv`, `.xlsx`, or `.xls` file          |
| `broker_name` | string | ❌        | Hint broker format: `zerodha` / `upstox` / `groww` |

**Success Response — `201 Created`:**

```json
{
  "imported": 25,
  "failed": 1,
  "errors": [
    { "row": 12, "error": "Invalid date format", "data": {...} }
  ],
  "detected_broker": "zerodha",
  "message": "25 trades imported successfully."
}
```

**Error Response — `423 Locked`:**

```json
{
  "error": "Trading session is locked.",
  "detail": "Your trading session is locked (RED). Complete the required actions in the Discipline section to unlock."
}
```

---

## P&L Calculation Formula

```
Long:  total_pnl = (exit_price - entry_price) × quantity × leverage − fees
Short: total_pnl = (entry_price - exit_price) × quantity × leverage − fees
```

P&L is `null` for open trades (no `exit_price`).

---

## Trade Model

| Field                | Type     | Description                                                        |
|----------------------|----------|--------------------------------------------------------------------|
| `id`                 | UUID     | Primary key                                                        |
| `user`               | FK       | Owner user                                                         |
| `session`            | FK       | Linked DisciplineSession (auto-set by signal)                      |
| `strategy`           | FK       | Linked Strategy (nullable)                                         |
| `trade_date`         | date     | Date of the trade                                                  |
| `trade_time`         | time     | Time of trade (nullable)                                           |
| `symbol`             | string   | Instrument symbol                                                  |
| `market_type`        | enum     | `indian_stocks` / `forex` / `crypto` / `options`                   |
| `direction`          | enum     | `long` / `short`                                                   |
| `quantity`           | decimal  | Number of units                                                    |
| `entry_price`        | decimal  | Entry price per unit                                               |
| `exit_price`         | decimal  | Exit price (nullable for open trades)                              |
| `fees`               | decimal  | Brokerage/commission paid                                          |
| `stop_loss`          | decimal  | Stop loss level (nullable)                                         |
| `target`             | decimal  | Target level (nullable)                                            |
| `leverage`           | decimal  | Leverage multiplier (default: 1)                                   |
| `total_pnl`          | decimal  | Auto-calculated net P&L (null for open trades)                     |
| `emotional_state`    | enum     | Trader's emotional state at entry                                  |
| `entry_confidence`   | integer  | Confidence at entry (1-10)                                         |
| `satisfaction_rating`| integer  | Post-trade satisfaction (1-10)                                     |
| `violation_modes`    | JSON     | Array of violation tags                                            |
| `lessons_learned`    | text     | Free-text reflection                                               |
| `rules_followed`     | JSON     | List of rule IDs followed                                          |
| `is_disciplined`     | boolean  | `false` if a hard rule was violated on this trade                  |
| `is_tagged_complete` | boolean  | `true` when strategy + emotional_state + entry_confidence all set  |
| `screenshot_urls`    | JSON     | Array of screenshot URLs                                           |
| `import_source`      | enum     | `manual` / `csv_import`                                            |
| `broker_name`        | string   | Broker name from import                                            |
| `deleted_at`         | datetime | Soft-delete timestamp (null = active)                              |
| `created_at`         | datetime | Record creation timestamp                                          |
| `updated_at`         | datetime | Last update timestamp                                              |

### Computed Properties

| Property    | Type    | Description                       |
|-------------|---------|-----------------------------------|
| `is_winner` | boolean | `true` if `total_pnl > 0`         |

---

## Supported Broker Formats (CSV Import)

| Broker    | Detection               |
|-----------|-------------------------|
| Zerodha   | Auto-detected by headers|
| Upstox    | Auto-detected by headers|
| Groww     | Auto-detected by headers|
| Generic   | Fallback for any format |

---

## URL Configuration

```python
# tradelog/urls.py
urlpatterns = [
    path('trades/',              TradeListCreateView.as_view(),  name='trade-list-create'),
    path('trades/import/',       TradeImportView.as_view(),      name='trade-import'),
    path('trades/<uuid:pk>/',    TradeDetailView.as_view(),      name='trade-detail'),
]
```

---

## Error Reference

| Status Code | Meaning                                      |
|-------------|----------------------------------------------|
| `200`       | OK                                           |
| `201`       | Created                                      |
| `204`       | No Content (deleted)                         |
| `400`       | Bad Request — validation error               |
| `401`       | Unauthorized                                 |
| `423`       | Locked — discipline session is locked        |
