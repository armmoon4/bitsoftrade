# Discipline API Documentation

## Overview

The **Discipline** module manages the Discipline Guard — a session-based system that monitors rule violations and escalates trading session states. Each user gets one `DisciplineSession` per trading day. State escalates `green → yellow → red` as rules are violated and can only be reset through an explicit unlock flow.

Rule evaluation is **automatic** — it runs via a `post_save` signal after every `Trade` save. Views never trigger evaluation directly.

---

## Base URL

```
/api/discipline/
```

---

## Authentication

All endpoints require JWT authentication:

```
Authorization: Bearer <access_token>
```

---

## Endpoints

### 1. Get Current Session

**`GET /api/discipline/current-session/`**

Returns the most relevant active session for the Discipline Guard UI. No date parameter is needed — the server resolves the active session using a fixed priority order.

**Permissions:** Authenticated

**Session Resolution Priority:**

| Priority | Condition | Returned |
|----------|-----------|----------|
| 1 | Any RED session exists | Most recent RED session (past or today) |
| 2 | Any YELLOW session exists | Most recent YELLOW session (past or today) |
| 3 | Fallback | Today's GREEN session (created if it doesn't exist yet) |

**Success Response — `200 OK`:**

```json
{
  "id": "uuid",
  "user": 1,
  "session_date": "2025-01-15",
  "session_state": "yellow",
  "peak_state": "yellow",
  "rules_violated": ["rule-uuid-1", "rule-uuid-2"],
  "violations_count": 2,
  "hard_violations": 0,
  "soft_violations": 2,
  "required_actions_completed": false,
  "cooldown_ends_at": null,
  "journal_completed": false,
  "trade_review_completed": false,
  "unlocked_at": null,
  "lock_cycle": 0,
  "lock_cycle_started_at": "2025-01-15T00:00:00Z",
  "created_at": "2025-01-15T09:00:00Z",
  "updated_at": "2025-01-15T10:30:00Z"
}
```

---

### 2. Session History

**`GET /api/discipline/sessions/`**

Returns the full session history for the authenticated user, ordered by most recent date first.

**Permissions:** Authenticated

**Success Response — `200 OK`:**

```json
[
  {
    "id": "uuid",
    "user": 1,
    "session_date": "2025-01-15",
    "session_state": "green",
    "peak_state": "red",
    "rules_violated": ["rule-uuid-1"],
    "violations_count": 1,
    "hard_violations": 1,
    "soft_violations": 0,
    "required_actions_completed": true,
    "cooldown_ends_at": null,
    "journal_completed": true,
    "trade_review_completed": true,
    "unlocked_at": "2025-01-15T14:00:00Z",
    "lock_cycle": 1,
    "lock_cycle_started_at": "2025-01-15T14:00:00Z",
    "created_at": "2025-01-15T09:00:00Z",
    "updated_at": "2025-01-15T14:00:00Z"
  }
]
```

---

### 3. Unlock Session

**`POST /api/discipline/unlock/`**

Submits a unlock action against the currently active session (same session resolved by `/current-session/`). Actions are cumulative — each call records one step of the unlock checklist. The session unlocks automatically once all required actions are completed **and** the cooldown has elapsed.

**Permissions:** Authenticated

**Request Body:**

| Field    | Type   | Required | Description |
|----------|--------|----------|-------------|
| `action` | string | ✅        | One of: `complete_journal` / `complete_trade_review` / `complete_all` |

**Action Behaviour:**

| Action                  | Effect |
|-------------------------|--------|
| `complete_journal`      | Sets `journal_completed = true` |
| `complete_trade_review` | Sets `trade_review_completed = true` |
| `complete_all`          | Sets both to `true` and **starts the cooldown timer** if not already started |

> **Important:** The cooldown timer only starts when `complete_all` is called, not when the session first locks. Cooldown duration depends on session state at the time of `complete_all`.

**Unlock Requirements by State:**

| Session State | Required Actions to Unlock |
|---------------|---------------------------|
| `yellow`      | `journal_completed = true` only |
| `red`         | Both `journal_completed = true` AND `trade_review_completed = true` |

**Cooldown Durations (started on `complete_all`):**

| Session State | Cooldown |
|---------------|----------|
| `yellow`      | 45 minutes |
| `red`         | 120 minutes |

**Success Response — `200 OK`** *(unlock completed or action recorded)*:

```json
{
  "message": "Session unlocked.",
  "session": { "...full session object..." }
}
```

```json
{
  "message": "Action recorded. Complete required steps to unlock.",
  "session": { "...full session object..." }
}
```

**Cooldown Active Response — `202 Accepted`** *(all actions done but timer still running)*:

```json
{
  "message": "Cooldown active. 37 minute(s) remaining.",
  "cooldown_ends_at": "2025-01-15T14:37:00Z",
  "session": { "...full session object..." }
}
```

> **Note:** On a successful unlock, the session state resets to `green`, `lock_cycle` increments by 1, `lock_cycle_started_at` is set to `now()`, and `journal_completed`/`trade_review_completed` are reset to `false`. Violation counters (`violations_count`, `hard_violations`, `soft_violations`, `rules_violated`) are **not** reset — they are permanent historical records for the session date.

---

### 4. Violations Timeline

**`GET /api/discipline/violations-timeline/`**

Returns a day-by-day breakdown of session states and violation counts for a date range. Days with no session record are included as empty entries (so the frontend always gets a continuous series).

**Permissions:** Authenticated

**Query Parameters:**

| Parameter | Type   | Default | Description |
|-----------|--------|---------|-------------|
| `from`    | string | 7 days ago | Start date — `YYYY-MM-DD` |
| `to`      | string | Today | End date — `YYYY-MM-DD` |

**Success Response — `200 OK`:**

```json
[
  {
    "session_date": "2025-01-10",
    "session_state": "green",
    "violations_count": 0,
    "hard_violations": 0,
    "soft_violations": 0,
    "day_label": "Fri",
    "day_full": "Friday"
  },
  {
    "session_date": "2025-01-11",
    "session_state": null,
    "violations_count": 0,
    "hard_violations": 0,
    "soft_violations": 0,
    "day_label": "Sat",
    "day_full": "Saturday"
  },
  {
    "session_date": "2025-01-13",
    "session_state": "red",
    "violations_count": 2,
    "hard_violations": 1,
    "soft_violations": 1,
    "day_label": "Mon",
    "day_full": "Monday"
  }
]
```

> Days with no session record have `session_state: null` and all counts set to `0`. The response always covers every calendar day in the requested range with no gaps.

---

## Session States

| State    | Meaning | Triggered by |
|----------|---------|--------------|
| `green`  | Normal — trading allowed | Default / after successful unlock |
| `yellow` | Warning — cooldown active or journal required | Soft rule violation (`warn` action) |
| `red`    | Locked — trading fully blocked | Hard rule violation (`lock` action) |

State only **escalates** within a lock cycle. It never auto-downgrades — only an explicit unlock resets it to `green`.

---

## Session Model

| Field                      | Type     | Writable | Description |
|----------------------------|----------|----------|-------------|
| `id`                       | UUID     | ❌        | Primary key |
| `user`                     | FK       | ❌        | Session owner |
| `session_date`             | date     | ✅        | Trading date this session covers |
| `session_state`            | enum     | ❌        | Current state: `green` / `yellow` / `red` — set by engine |
| `peak_state`               | enum     | —        | Highest state ever reached for this date — never downgraded on unlock |
| `rules_violated`           | JSON     | ❌        | List of rule UUIDs that fired this session |
| `violations_count`         | integer  | ❌        | Total violations logged (permanent) |
| `hard_violations`          | integer  | ❌        | Count of hard violations (permanent) |
| `soft_violations`          | integer  | ❌        | Count of soft violations (permanent) |
| `required_actions_completed` | boolean | —      | `true` after the unlock action sets state back to green |
| `cooldown_ends_at`         | datetime | —        | When the cooldown timer expires. Set on `complete_all`, cleared on unlock |
| `journal_completed`        | boolean  | —        | Whether journal step is done in current unlock attempt |
| `trade_review_completed`   | boolean  | —        | Whether trade review step is done (required for RED unlock) |
| `unlocked_at`              | datetime | —        | Timestamp of most recent successful unlock |
| `lock_cycle`               | integer  | ❌        | Number of times this session has been unlocked. Increments on each unlock. |
| `lock_cycle_started_at`    | datetime | ❌        | Start of the current lock cycle — used by the rule engine to scope trade quotas |
| `created_at`               | datetime | ❌        | Session creation timestamp |
| `updated_at`               | datetime | ❌        | Last update timestamp |

---

## ViolationsLog Model

Each rule violation creates one `ViolationsLog` entry. These power the violations timeline chart and the behavior report.

| Field                | Type     | Description |
|----------------------|----------|-------------|
| `id`                 | UUID     | Primary key |
| `user`               | FK       | User who triggered the violation |
| `session`            | FK       | The `DisciplineSession` this violation belongs to |
| `trade`              | FK       | The trade that triggered the violation (nullable — `SET_NULL` on trade delete) |
| `rule`               | FK       | The rule that was violated |
| `rule_name`          | string   | Read-only denormalized name from `rule.rule_name` (serializer field) |
| `violation_type`     | enum     | `hard` / `soft` |
| `session_state_after`| enum     | Session state after this violation was recorded: `green` / `yellow` / `red` |
| `violated_at`        | datetime | Auto-set to when the violation was logged |
| `lock_cycle`         | integer  | Snapshot of `session.lock_cycle` at the time of logging — used for deduplication |

---

## Rule Evaluation — How It Works

Rule evaluation is triggered automatically via a Django `post_save` signal on the `Trade` model (`discipline/signals.py`). Views never call the engine directly.

**Evaluation is skipped when** an `update_fields` save touches only: `total_pnl`, `is_tagged_complete`, `is_disciplined`, or `session`.

**On each qualifying trade save the signal:**

1. Gets or creates the `DisciplineSession` for the trade's date
2. Sets `lock_cycle_started_at` to midnight of the session date if not already set (ensures all trades on that day are included in the cycle count from the start)
3. Links the trade to the session via `trade.session` if not already set
4. Calls `rules.engine.evaluate_rules_for_user(user, session, trade)`
5. After evaluation, sets `trade.is_disciplined = True` only if no hard violations were logged for this trade in the current lock cycle

---

## Lock Cycle

The `lock_cycle` counter increments by 1 on every successful unlock. It serves two purposes:

- **Deduplication:** Violation deduplication is scoped to `(session, rule, lock_cycle)`, so the same rule can re-fire in a new cycle after an unlock.
- **Trade quota reset:** The `maxTrades` rule counts only trades created at or after `lock_cycle_started_at`, giving a fresh quota each cycle.

---

## URL Configuration

```python
# discipline/urls.py
urlpatterns = [
    path('current-session/',      current_session_view,      name='discipline-current-session'),
    path('sessions/',             session_history_view,      name='discipline-session-history'),
    path('unlock/',               unlock_session_view,       name='discipline-unlock'),
    path('violations-timeline/',  violations_timeline_view,  name='discipline-timeline'),
]
```

---

## Error Reference

| Status Code | Meaning |
|-------------|---------|
| `200`       | OK — request successful or session unlocked |
| `202`       | Accepted — action recorded but cooldown is still active |
| `400`       | Bad Request — validation error |
| `401`       | Unauthorized — missing or invalid JWT token |

---

## Dependencies

- `rules` — `Rule` model and `evaluate_rules_for_user` engine
- `tradelog` — `Trade` model (signal source and `is_disciplined` flag target)
- `accounts` — `User` model (`trading_capital` used by rule conditions)
