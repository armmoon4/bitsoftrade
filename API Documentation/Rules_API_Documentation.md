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

Returns all non-deleted rules visible to the authenticated user: **admin-defined global rules** + **the user's own custom rules**. By default this includes both active and inactive rules. Use the `is_active` query parameter to filter.

**Permissions:** Authenticated

**Query Parameters:**

| Parameter   | Type    | Description |
|-------------|---------|-------------|
| `is_active` | boolean | `true` — return only active rules. `false` — return only inactive rules. Omit to return all non-deleted rules. |

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
    "trigger_condition": { "maxLoss": 5000 },
    "action": "lock",
    "is_active": true,
    "is_admin_defined": true,
    "user": null,
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z"
  }
]
```

> Results are ordered: admin-defined rules first, then by `category`, then by `rule_name`.

---

### 2. Create Custom Rule

**`POST /api/rules/`**

Creates a new user-custom rule. `is_admin_defined`, `created_by_admin`, and `user` are always set server-side and cannot be supplied in the request body.

**Permissions:** Authenticated

**Request Body:**

| Field               | Type    | Required | Description                                           |
|---------------------|---------|----------|-------------------------------------------------------|
| `rule_name`         | string  | ✅        | Display name (max 200 chars)                          |
| `description`       | string  | ❌        | Human-readable explanation                            |
| `category`          | enum    | ✅        | `risk` / `process` / `psychology` / `time` / `other` |
| `rule_type`         | enum    | ✅        | `hard` (locks session) or `soft` (warns)              |
| `trigger_scope`     | enum    | ✅        | `per_day` / `per_trade` / `per_session`               |
| `trigger_condition` | object  | ✅        | JSON condition — see Trigger Condition Reference      |
| `action`            | enum    | ✅        | `lock` / `warn` / `require_journal`                   |
| `is_active`         | boolean | ❌        | Default: `true`                                       |

**Success Response — `201 Created`:** full rule object

---

### 3. Retrieve Rule

**`GET /api/rules/<uuid:id>/`**

Returns a single rule. Only accessible for the **user's own custom rules**. Admin-defined rules are not accessible via this endpoint and will return `404`.

**Permissions:** Authenticated (owner only)

---

### 4. Update Rule

**`PUT /api/rules/<uuid:id>/`** / **`PATCH /api/rules/<uuid:id>/`**

Updates a user's custom rule. Only accessible for the **user's own custom rules**. Admin-defined rules are not accessible via this endpoint and will return `404`.

**Permissions:** Authenticated (owner only)

**Success Response — `200 OK`:** updated rule object

---

### 5. Delete Rule (Soft Delete)

**`DELETE /api/rules/<uuid:id>/`**

Soft-deletes a user's custom rule by setting `deleted_at` to the current timestamp. Only accessible for the **user's own custom rules**.

**Permissions:** Authenticated (owner only)

**Error Response — `403 Forbidden`** *(if somehow an admin-defined rule is reached)*:

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
{ "maxLoss": 5000 }
```

- `maxLoss` — absolute loss limit in base currency (INR).
- Fires when the sum of `total_pnl` across all of today's trades is a loss equal to or exceeding this value.

### Position Size Limit

```json
{ "maxPositionSize": 50000 }
```

- Fires if any single trade's position value (`entry_price × quantity`) exceeds this absolute amount in base currency (INR).
- No dependency on `user.trading_capital`.

### Max Trades Per Day

```json
{ "maxTrades": 5 }
```

- Fires when the number of trades in the current lock cycle **exceeds** (strictly greater than) the limit. The trade that hits the limit is saved; the next trade is blocked.
- When `trigger_scope` is `per_day`, counts all trades today from `lock_cycle_started_at` onward so each unlock cycle gets a fresh quota.

### Consecutive Loss Limit

```json
{ "consecutiveLosses": 3 }
```

- Fires if the last N closed trades (across all dates) are all losses.
- Only trades with a recorded `total_pnl` are considered.

---

## Trigger Scope Behaviour

| Scope         | Evaluation Window                                                                                                                                              |
|---------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `per_day`     | Aggregates across all trades in the session's date.                                                                                                            |
| `per_trade`   | Evaluates against the single trade that just saved. Each trade can independently trigger the same rule.                                                        |
| `per_session` | Skips evaluation entirely if `session_state` is `green`. Only fires once the user has already triggered at least one violation this session (state is `yellow` or `red`). |

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
| `trigger_scope`     | enum     | `per_day` / `per_trade` / `per_session`                 |
| `trigger_condition` | JSON     | Machine-readable condition definition                   |
| `action`            | enum     | `lock` / `warn` / `require_journal`                     |
| `is_active`         | boolean  | Whether rule is currently active                        |
| `is_admin_defined`  | boolean  | `true` = global rule created by admin                   |
| `deleted_at`        | datetime | Soft-delete timestamp (null = active)                   |
| `created_at`        | datetime | Creation timestamp                                      |
| `updated_at`        | datetime | Last update timestamp                                   |

---

## Rule Evaluation Engine

Rules are evaluated automatically after **every trade save** (via `rules.engine.evaluate_rules_for_user`). The engine:

1. Reloads the `DisciplineSession` from the database to avoid stale state
2. Loads all active non-deleted rules for the user (admin global + user custom)
3. Evaluates each rule against today's trades, respecting `trigger_scope`
4. For `per_trade` rules: deduplicates per `(session, rule, trade, lock_cycle)` — each trade can trigger the same rule independently
5. For `per_day` / `per_session` rules: deduplicates per `(session, rule, lock_cycle)` — fires at most once per rule per lock cycle
6. Escalates `DisciplineSession.session_state`: `green` → `yellow` (soft violation) or `red` (hard violation). State only ever escalates within a cycle, never auto-downgrades.
7. Updates `peak_state` — the highest state ever reached, never downgraded
8. Creates a `ViolationsLog` entry and increments `violations_count`, `hard_violations`, or `soft_violations` for each new violation
9. Sets a cooldown (`cooldown_ends_at`) on state escalation

### Session States

| State    | Meaning                        | Triggered by                 |
|----------|--------------------------------|------------------------------|
| `green`  | Normal — trading allowed       | Default                      |
| `yellow` | Warning — cooldown active      | Soft (`warn`) rule violation |
| `red`    | Locked — trading blocked       | Hard (`lock`) rule violation |

### Cooldown Behaviour

| State    | Cooldown Duration |
|----------|-------------------|
| `yellow` | 2 minutes         |
| `red`    | 5 minutes         |

A YELLOW session is still locked after the cooldown expires until the user completes the **Quick Journal** in the Discipline section (`required_actions_completed = True`). A RED session remains locked regardless of cooldown until manually unlocked.

### Lock Cycle

Each time a session is unlocked, `lock_cycle` increments. This gives every unlock cycle a fresh quota for `maxTrades` rules and prevents the same violation from being double-counted across cycles.

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

| Status Code | Meaning                                                         |
|-------------|-----------------------------------------------------------------|
| `200`       | OK                                                              |
| `201`       | Created                                                         |
| `204`       | No Content (deleted)                                            |
| `400`       | Bad Request — validation error                                  |
| `401`       | Unauthorized                                                    |
| `403`       | Forbidden — cannot delete an admin-defined rule                 |
| `404`       | Rule not found or not owned by the requesting user              |
