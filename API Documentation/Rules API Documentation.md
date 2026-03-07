# Rules API Documentation

## Overview

The **Rules** module manages trading rules that power the Discipline Guard. Rules can be **admin-defined** (global, applied to all users) or **user-custom**. Each rule has a type (`hard`/`soft`), a category, a trigger scope, a trigger condition (JSON), and an action. The rule evaluation engine evaluates all active rules after every trade save.

---

## Base URL

```
/api/rules/
```

---

## Authentication

All endpoints require JWT authentication:

```
Authorization: Bearer <access_token>
```

---

## Endpoints

### 1. List Rules

**`GET /api/rules/`**

Returns all active rules visible to the authenticated user: **admin-defined global rules** + **the user's own custom rules**.

**Permissions:** Authenticated

**Success Response — `200 OK`:**

```json
[
  {
    "id": "uuid",
    "rule_name": "Max Daily Loss",
    "description": "Stop trading if daily loss exceeds limit.",
    "category": "risk",
    "rule_type": "hard",
    "trigger_scope": "per_day",
    "trigger_condition": { "maxLoss": 5000, "maxDailyPercent": 3 },
    "action": "lock",
    "is_active": true,
    "is_admin_defined": true,
    "user": null,
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z"
  }
]
```

---

### 2. Create Custom Rule

**`POST /api/rules/`**

Creates a new user-custom rule. Admin-defined rules cannot be created via this endpoint.

**Permissions:** Authenticated

**Request Body:**

| Field               | Type    | Required | Description                                          |
|---------------------|---------|----------|------------------------------------------------------|
| `rule_name`         | string  | ✅        | Display name (max 200 chars)                         |
| `description`       | string  | ❌        | Human-readable explanation                           |
| `category`          | enum    | ✅        | `risk` / `process` / `psychology` / `time` / `other`|
| `rule_type`         | enum    | ✅        | `hard` (locks session) or `soft` (warns)             |
| `trigger_scope`     | enum    | ✅        | `per_day` / `per_trade` / `post_trigger`             |
| `trigger_condition` | object  | ✅        | JSON condition — see Trigger Condition Reference     |
| `action`            | enum    | ✅        | `lock` / `warn` / `require_journal` / `restrict_import` |
| `is_active`         | boolean | ❌        | Default: `true`                                      |

**Success Response — `201 Created`:** full rule object

---

### 3. Retrieve Rule

**`GET /api/rules/<uuid:id>/`**

Returns a single rule. Only accessible for the user's own custom rules.

**Permissions:** Authenticated (owner only)

---

### 4. Update Rule

**`PUT /api/rules/<uuid:id>/`** / **`PATCH /api/rules/<uuid:id>/`**

Updates a user's custom rule. Admin-defined rules cannot be modified via this endpoint.

**Permissions:** Authenticated (owner only)

**Success Response — `200 OK`:** updated rule object

---

### 5. Delete Rule (Soft Delete)

**`DELETE /api/rules/<uuid:id>/`**

Soft-deletes a user's custom rule. Admin-defined rules cannot be deleted by users.

**Permissions:** Authenticated (owner only)

**Error Response — `403 Forbidden`:**

```json
{
  "error": "Admin-defined rules cannot be deleted."
}
```

**Success Response — `204 No Content`**

---

## Trigger Condition Reference

The `trigger_condition` field is a JSON object. The structure varies by condition type:

### Max Daily Loss

```json
{ "maxLoss": 5000, "maxDailyPercent": 3 }
```

- `maxLoss` — absolute loss limit in base currency (INR)
- `maxDailyPercent` — loss as % of `trading_capital`

### Position Size Limit

```json
{ "maxPositionPercent": 10 }
```

- Fires if any single trade's position value exceeds X% of `trading_capital`

### Max Trades Per Day

```json
{ "maxTrades": 5 }
```

- Fires if the number of trades today exceeds the limit

### Consecutive Loss Limit

```json
{ "consecutiveLosses": 3 }
```

- Fires if the last N trades are all losses

---

## Trigger Scope Behaviour

| Scope          | Evaluation Window                                    |
|----------------|------------------------------------------------------|
| `per_day`      | Aggregates across all trades in the session's date   |
| `per_trade`    | Evaluates against the single trade that just saved   |
| `post_trigger` | Only fires after at least one prior violation this cycle |

---

## Rule Model

| Field               | Type     | Description                                             |
|---------------------|----------|---------------------------------------------------------|
| `id`                | UUID     | Primary key                                             |
| `created_by_admin`  | FK       | Admin who created it (null for user custom rules)       |
| `user`              | FK       | User owner (null for admin-defined rules)               |
| `rule_name`         | string   | Rule display name                                       |
| `description`       | text     | Optional description                                    |
| `category`          | enum     | `risk` / `process` / `psychology` / `time` / `other`   |
| `rule_type`         | enum     | `hard` (locks) / `soft` (warns)                         |
| `trigger_scope`     | enum     | `per_day` / `per_trade` / `post_trigger`                |
| `trigger_condition` | JSON     | Machine-readable condition definition                   |
| `action`            | enum     | `lock` / `warn` / `require_journal` / `restrict_import` |
| `is_active`         | boolean  | Whether rule is currently active                        |
| `is_admin_defined`  | boolean  | `true` = global rule created by admin                   |
| `deleted_at`        | datetime | Soft-delete timestamp (null = active)                   |
| `created_at`        | datetime | Creation timestamp                                      |
| `updated_at`        | datetime | Last update timestamp                                   |

---

## Rule Evaluation Engine

Rules are evaluated automatically after **every trade save** (via `rules.engine.evaluate_rules_for_user`). The engine:

1. Loads all active rules for the user (admin global + user custom)
2. Evaluates each rule against today's trades, respecting `trigger_scope`
3. Skips duplicates within the same `lock_cycle`
4. Escalates `DisciplineSession.session_state`: GREEN → YELLOW (soft) or RED (hard)
5. Creates a `ViolationsLog` entry for each new violation

---

## URL Configuration

```python
# rules/urls.py
urlpatterns = [
    path('',            RuleListCreateView.as_view(),  name='rule-list-create'),
    path('<uuid:pk>/',  RuleDetailView.as_view(),      name='rule-detail'),
]
```

---

## Error Reference

| Status Code | Meaning                                     |
|-------------|---------------------------------------------|
| `200`       | OK                                          |
| `201`       | Created                                     |
| `204`       | No Content (deleted)                        |
| `400`       | Bad Request — validation error              |
| `401`       | Unauthorized                                |
| `403`       | Forbidden — cannot modify admin-defined rule|
| `404`       | Rule not found                              |
