# Discipline Guard — Unlock System
## How It Works & Frontend Integration Guide

---

## Overview

The Discipline Guard is a **session-based lock system** that blocks the Import Trade button
when a user violates trading rules. A session can be in one of three states:

| State    | Icon | Meaning                       | Import Trade |
|----------|------|-------------------------------|--------------|
| `green`  | 🟢   | All clear — no violations     | ✅ Enabled   |
| `yellow` | 🟡   | Soft rule violated            | 🔒 Blocked   |
| `red`    | 🔴   | Hard rule violated            | 🔒 Blocked   |

A locked session (`yellow` or `red`) **can only be unlocked** once the user completes
a recovery checklist. The critical gate: **every flagged trade must have at least one
mistake tagged before unlock is permitted.**

---

## State Machine

```
                  soft rule fires
  GREEN ─────────────────────────────► YELLOW
    │                                     │
    │  hard rule fires                    │  hard rule fires
    ├─────────────────────────────────►   │
    │                                     ▼
    │                                   RED
    │
    │ ◄──────── all checklist tasks done + mistakes tagged ──────────
```

- State **only escalates** (`green → yellow`, `yellow → red`, `green → red`).  
- State **never auto-downgrades** — the user must complete the unlock flow.  
- On unlock, `lock_cycle` increments so the same rule can re-fire in the next cycle.

---

## How Rule Violations Are Logged

Rule evaluation is **fully automatic** — it runs via a Django `post_save` signal
after every `Trade` save. You never need to call an evaluation endpoint from the frontend.

When a trade triggers a rule:
1. A `ViolationsLog` entry is created linking `(session, rule, trade)`.
2. The session state escalates (`yellow` or `red`).
3. A cooldown timer starts automatically.
4. The trade is added to the **flagged trades** list for this session.

---

## The Mistakes-Tagging Gate

This is the **critical unlock requirement** introduced in this version.

### What "mistakes tagged" means

A flagged trade is considered **tagged** when the user has linked at least one
`TradeMistake` to it (via the Mistakes panel in the trade detail view).

```
ViolationsLog row exists for trade  →  trade is "flagged"
TradeMistake row exists for trade   →  trade is "tagged"
```

### The gate condition

```
all_tagged = (set of flagged_trade_ids) == (set of trades_with_at_least_one_TradeMistake)
```

- If even **one** flagged trade has no mistake tagged → `all_tagged = false` → unlock blocked.
- Only when **every** flagged trade has ≥ 1 mistake tagged → `all_tagged = true` → unlock proceeds.

### Where the gate sits

The gate is checked inside `POST /api/discipline/unlock/` **before** the session transitions to `green`:

| State    | Full unlock condition                                                 |
|----------|----------------------------------------------------------------------|
| `yellow` | `journal_completed = true` **AND** `all_tagged = true`              |
| `red`    | `journal_completed = true` **AND** `trade_review_completed = true` **AND** `all_tagged = true` |

The cooldown must also have elapsed for RED state.

---

## API Reference

### Base URL
```
/api/discipline/
```

### Authentication
```
Authorization: Bearer <access_token>
```

---

### 1. `GET /api/discipline/current-session/`

Returns the active session with full checklist progress.

**Session resolution priority:**

| Priority | Returns |
|----------|---------|
| 1 | Most recent RED session (any date) |
| 2 | Most recent YELLOW session (any date) |
| 3 | Today's GREEN session (created if missing) |

**Response `200 OK`:**

```json
{
  "id": "uuid",
  "user": 1,
  "session_date": "2025-01-15",
  "session_state": "yellow",
  "peak_state": "yellow",
  "rules_violated": ["rule-uuid-1"],
  "violations_count": 1,
  "hard_violations": 0,
  "soft_violations": 1,
  "required_actions_completed": false,
  "cooldown_ends_at": "2025-01-15T10:31:00Z",
  "journal_completed": false,
  "trade_review_completed": false,
  "unlocked_at": null,
  "lock_cycle": 0,
  "lock_cycle_started_at": "2025-01-15T00:00:00Z",
  "created_at": "2025-01-15T09:00:00Z",
  "updated_at": "2025-01-15T10:30:00Z",

  "trades_tag_status": {
    "flagged_count": 3,
    "tagged_count": 1,
    "all_tagged": false,
    "untagged_trade_ids": ["trade-uuid-2", "trade-uuid-3"]
  }
}
```

#### `trades_tag_status` field — explained

| Key                  | Type     | Description |
|----------------------|----------|-------------|
| `flagged_count`      | integer  | Total trades with a ViolationsLog entry in this session |
| `tagged_count`       | integer  | How many of those have ≥ 1 TradeMistake linked |
| `all_tagged`         | boolean  | `true` when `tagged_count == flagged_count` |
| `untagged_trade_ids` | string[] | UUIDs of trades still needing a mistake tagged |

> **Frontend tip:** Poll this endpoint every few seconds while the Discipline Check panel
> is open. When `all_tagged` flips to `true`, enable the unlock button / show a green checkmark.

---

### 2. `POST /api/discipline/unlock/`

Submits a checklist action. Call this as the user completes each step.

**Request body:**

```json
{ "action": "complete_journal" }
```

| `action` value           | Effect |
|--------------------------|--------|
| `complete_journal`       | Sets `journal_completed = true` |
| `complete_trade_review`  | Sets `trade_review_completed = true` |
| `complete_all`           | Sets both to `true` |

**Response — action recorded, not yet unlocked `200 OK`:**

```json
{
  "message": "Action recorded. Complete required steps to unlock.",
  "all_trades_tagged": false,
  "session": { "...full session object including trades_tag_status..." }
}
```

> `all_trades_tagged` tells you immediately whether the tagging gate is blocking unlock.

**Response — cooldown still active `202 Accepted`:**

```json
{
  "message": "Cooldown active. 37 minute(s) remaining.",
  "cooldown_ends_at": "2025-01-15T14:37:00Z",
  "all_trades_tagged": true,
  "session": { "...full session object..." }
}
```

**Response — session unlocked `200 OK`:**

```json
{
  "message": "Session unlocked.",
  "session": { "session_state": "green", "lock_cycle": 1, "..." }
}
```

> On unlock: `session_state` → `green`, `lock_cycle` increments, `cooldown_ends_at` → `null`,
> `journal_completed` and `trade_review_completed` reset to `false`.

---

### 3. `GET /api/discipline/violations-timeline/`

Day-by-day session state breakdown.

**Query params:** `from=YYYY-MM-DD` and `to=YYYY-MM-DD` (defaults: last 7 days)

```json
[
  {
    "session_date": "2025-01-15",
    "session_state": "yellow",
    "peak_state": "yellow",
    "violations_count": 1,
    "hard_violations": 0,
    "soft_violations": 1,
    "day_label": "Wed",
    "day_full": "Wednesday"
  }
]
```

---

### 4. `GET /api/discipline/sessions/`

Full session history, newest first. Same shape as `current-session/`.

---

## Frontend Integration Guide

### Step 1 — On Dashboard Load

```
GET /api/discipline/current-session/
```

Read `session_state`:

| `session_state` | Action |
|-----------------|--------|
| `green`         | Show Import Trade button normally. No banners. |
| `yellow`        | Disable Import Trade. Show YELLOW warning banner. Open Discipline Check panel. |
| `red`           | Disable Import Trade. Show RED overlay. Start countdown from `cooldown_ends_at`. |

---

### Step 2 — Discipline Check Panel (YELLOW)

Display a checklist with 3 items:

```
[ ] Step 1 — Review flagged trades
[ ] Step 2 — Tag mistakes on flagged trades      ← driven by trades_tag_status
[ ] Step 3 — Complete journal
```

**Live progress for Step 2 (mistakes tagging):**

Poll `GET /api/discipline/current-session/` every 5 seconds while panel is open.

```js
const status = session.trades_tag_status;
// status.tagged_count / status.flagged_count  →  "1 / 3 tagged"
// status.all_tagged                           →  show green checkmark
// status.untagged_trade_ids                   →  highlight these trades in the trade list
```

**Checklist item state logic:**

| Checklist item | Completed when |
|----------------|----------------|
| Review trades  | `session.trade_review_completed === true` |
| Tag mistakes   | `session.trades_tag_status.all_tagged === true` |
| Journal done   | `session.journal_completed === true` |

**Unlock button state:**

```js
const canUnlock =
  session.journal_completed &&
  session.trades_tag_status.all_tagged &&
  (!session.cooldown_ends_at || new Date() > new Date(session.cooldown_ends_at));
```

---

### Step 3 — Discipline Check Panel (RED)

Same as YELLOW but with:
1. A **45-minute countdown timer** running from `cooldown_ends_at`.
2. All checklist items **disabled** until the timer hits 00:00.
3. An extra **"Confirm Limits"** checkbox step.

**Countdown logic:**

```js
const remaining = new Date(session.cooldown_ends_at) - new Date();
// remaining is in ms — convert to MM:SS for display
// When remaining <= 0 → unlock checklist items, show "Cooling period complete"
```

> **Important:** Always compute remaining time from `cooldown_ends_at` (server timestamp),
> never from a local timer started in the browser. This ensures the timer survives page
> refresh and logout/login.

**YELLOW vs RED checklist unlock conditions:**

| State    | Unlock requires |
|----------|-----------------|
| `yellow` | `journal_completed` + `all_tagged` |
| `red`    | `journal_completed` + `trade_review_completed` + `all_tagged` + cooldown elapsed |

---

### Step 4 — Submitting Checklist Actions

When user completes a step, call:

```
POST /api/discipline/unlock/
{ "action": "complete_journal" }
```

Check the response:
- `message: "Session unlocked."` → hide overlay, re-enable Import Trade button.
- `message: "Action recorded..."` → update checklist UI, keep polling.
- `202 Accepted` with `cooldown_ends_at` → show remaining time, keep timer running.

---

### Step 5 — Tagging a Mistake (How the User Tags)

The user tags a mistake from inside the **Trade Detail view**:

1. User opens a trade from `untagged_trade_ids`.
2. User selects a mistake from the Mistakes dropdown/panel.
3. Frontend calls `POST /api/mistakes/trade-mistakes/` to create a `TradeMistake` entry.
4. Frontend re-polls `GET /api/discipline/current-session/`.
5. `trades_tag_status.tagged_count` increases. When `all_tagged = true`, the tagging
   checklist item turns green automatically.

> The backend does not auto-tag mistakes. Tagging is always an explicit user action
> via the Mistakes panel on the trade detail page.

---

### Step 6 — Import Trade Button Guard

Every time the user clicks Import Trade, the frontend should first check:

```
GET /api/discipline/current-session/
```

If `session_state !== 'green'` → show the lock message and abort.

The backend also enforces this at the API level — `POST /api/tradelog/trades/import/`
returns `423 Locked` if any session is red or yellow.

---

## Full Unlock Flow Diagram

```
User opens Dashboard
        │
        ▼
GET /api/discipline/current-session/
        │
   session_state?
   ┌────┴──────┐
 green       yellow / red
   │             │
   ▼             ▼
 Normal      Show lock UI
 access      Start polling current-session every 5s
                 │
         User reviews trades
         User opens trade → selects mistake
         POST /api/mistakes/trade-mistakes/
                 │
         Poll → trades_tag_status.all_tagged = true ✓
                 │
         User writes journal
         POST /api/discipline/unlock/ { action: "complete_journal" }
                 │
         (RED only) Wait for cooldown_ends_at
                 │
         POST /api/discipline/unlock/ { action: "complete_trade_review" }
                 │
         Response: "Session unlocked."
                 │
                 ▼
           session_state = green
           Import Trade re-enabled
           Overlay/banner dismissed
```

---

## Data Flow Summary

```
Trade saved
    │
    ▼
post_save signal fires
    │
    ▼
evaluate_rules_for_user()
    │
    ├── rule triggered?
    │       │
    │       ▼
    │   ViolationsLog.create(session, rule, trade)
    │   session.session_state → yellow / red
    │   cooldown_ends_at set automatically
    │
    ▼
Frontend polls GET /current-session/
    │
    ▼
trades_tag_status.untagged_trade_ids → highlight trades
    │
User tags mistakes via Mistakes panel (TradeMistake rows created)
    │
    ▼
trades_tag_status.all_tagged = true
    │
User submits journal → POST /unlock/ { action: "complete_journal" }
    │
Backend gate:
  journal_completed AND all_tagged (AND trade_review for RED) AND cooldown elapsed
    │
    ▼
session_state = green → Import Trade unlocked
```

---

## Key Rules to Know

| Rule | Detail |
|------|--------|
| Tagging gate is server-side | Frontend cannot bypass it — backend always re-checks `TradeMistake` count |
| Partial tagging is NOT enough | Even one untagged flagged trade keeps the session locked |
| Cooldown survives refresh | `cooldown_ends_at` is stored in DB — always compute remaining time from it |
| All other sessions bulk-unlocked | When the active session unlocks, all other yellow/red sessions for the same user also unlock |
| Violation counters never reset | `violations_count`, `hard_violations`, `soft_violations` are permanent historical records |
| `lock_cycle` increments on unlock | Allows the same rule to re-fire in the next trading cycle |

---

## Dependencies

| Module      | Used for |
|-------------|----------|
| `mistakes`  | `TradeMistake` — junction table that records user-tagged mistakes per trade |
| `tradelog`  | `Trade` model — source of `ViolationsLog.trade` FK |
| `discipline`| `DisciplineSession`, `ViolationsLog` — session state and violation records |
| `rules`     | `Rule` model + `evaluate_rules_for_user()` engine |
