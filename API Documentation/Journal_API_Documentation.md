# Journal API Documentation

## Overview

The **Journal** module provides five independent journaling resources for BitsOfTrade:

| Resource        | Purpose |
|-----------------|---------|
| `DailyJournal`  | Daily reflection, session state, and streak tracking — one entry per user per date |
| `TradeNote`     | Qualitative per-trade notes with freeform tags |
| `PsychologyLog` | Pre/post-trade emotional state and confidence tracking |
| `SessionRecap`  | Post-session review with structured what-went-right / what-slipped data |
| `LearningNote`  | Notes from the Learning Hub or external sources, optionally linked to a mistake, rule, or strategy |

All list endpoints are **paginated** via `StandardResultsSetPagination`. All endpoints are scoped to the authenticated user — no user can read or modify another user's data.

---

## Base URL

```
/api/journal/
```

---

## Authentication

All endpoints require JWT authentication:

```
Authorization: Bearer <access_token>
```

---

## Pagination

All list endpoints return paginated responses:

```json
{
  "count": 42,
  "next": "http://localhost:13025/api/journal/daily/?page=2",
  "previous": null,
  "results": [ "...items..." ]
}
```

---

## Endpoints

---

### 1. Daily Journal

One entry per user per date — enforced at both the DB level (`unique_together`) and the view level.

---

#### `GET /api/journal/daily/`

Returns all daily journal entries for the authenticated user, ordered by most recent date first.

**Permissions:** Authenticated

**Success Response — `200 OK`:** paginated list of daily journal objects.

---

#### `POST /api/journal/daily/`

Creates a daily journal entry. Only one entry per `journal_date` is allowed per user.

**Permissions:** Authenticated

**Request Body:**

| Field                    | Type   | Required | Description |
|--------------------------|--------|----------|-------------|
| `journal_date`           | date   | ✅        | `YYYY-MM-DD`. Must be unique per user. |
| `session_state`          | enum   | ❌        | `green` / `yellow` / `red` |
| `prompt_text`            | string | ❌        | Prompt shown to the user |
| `reflection`             | string | ❌        | User's free-text reflection |
| `intention_next_session` | string | ❌        | Intention for the next trading session |
| `limits_followed`        | enum   | ❌        | `yes` / `mostly` / `no` |

**Success Response — `201 Created`:**

```json
{
  "id": "uuid",
  "user": 1,
  "journal_date": "2025-01-15",
  "session_state": "green",
  "prompt_text": "What was your biggest lesson today?",
  "reflection": "I stuck to my plan on all trades.",
  "intention_next_session": "Keep position sizes small.",
  "limits_followed": "yes",
  "created_at": "2025-01-15T18:00:00Z",
  "updated_at": "2025-01-15T18:00:00Z"
}
```

**Error Response — `400 Bad Request`** *(duplicate date)*:

```json
{
  "journal_date": ["You have already created a journal entry for this date."]
}
```

---

#### `GET /api/journal/daily/<uuid:id>/`

Returns a single daily journal entry owned by the authenticated user.

#### `PUT /api/journal/daily/<uuid:id>/`

Fully updates the journal entry. All writable fields must be provided.

#### `PATCH /api/journal/daily/<uuid:id>/`

Partially updates the journal entry. Only provided fields are updated.

#### `DELETE /api/journal/daily/<uuid:id>/`

Deletes the journal entry.

**Permissions:** Authenticated (owner only)

**Success Response:** `200 OK` (GET/PUT/PATCH) — full journal object. `204 No Content` (DELETE).

---

### 2. Trade Notes

Per-trade qualitative notes with freeform hashtag-style tags. Multiple notes per trade are allowed.

---

#### `GET /api/journal/trade-notes/`

Returns all trade notes for the authenticated user, ordered by most recently created first.

**Permissions:** Authenticated

**Success Response — `200 OK`:** paginated list of trade note objects.

---

#### `POST /api/journal/trade-notes/`

Creates a trade note linked to a specific trade.

**Permissions:** Authenticated

**Request Body:**

| Field       | Type   | Required | Description |
|-------------|--------|----------|-------------|
| `trade`     | UUID   | ✅        | ID of the trade this note belongs to |
| `note_text` | string | ✅        | Free-text note content |
| `tags`      | array  | ❌        | List of tag strings, e.g. `["#FOMO", "#breakout"]`. Defaults to `[]`. |

**Success Response — `201 Created`:**

```json
{
  "id": "uuid",
  "user": 1,
  "trade": "trade-uuid",
  "note_text": "Entered too early, chased the breakout.",
  "tags": ["#FOMO", "#breakout"],
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T10:00:00Z"
}
```

---

#### `GET /api/journal/trade-notes/<uuid:id>/`

Returns a single trade note owned by the authenticated user.

#### `PUT /api/journal/trade-notes/<uuid:id>/`

Fully updates the trade note.

#### `PATCH /api/journal/trade-notes/<uuid:id>/`

Partially updates the trade note.

#### `DELETE /api/journal/trade-notes/<uuid:id>/`

Deletes the trade note.

**Permissions:** Authenticated (owner only)

**Success Response:** `200 OK` (GET/PUT/PATCH) — full trade note object. `204 No Content` (DELETE).

---

### 3. Psychology Logs

Pre/post-trade emotional tracking. Can be linked to a specific trade or logged independently.

---

#### `GET /api/journal/psychology/`

Returns all psychology logs for the authenticated user, ordered by most recent log date then creation time.

**Permissions:** Authenticated

**Success Response — `200 OK`:** paginated list of psychology log objects.

---

#### `POST /api/journal/psychology/`

Creates a psychology log entry.

**Permissions:** Authenticated

**Request Body:**

| Field               | Type    | Required | Description |
|---------------------|---------|----------|-------------|
| `log_date`          | date    | ✅        | `YYYY-MM-DD` |
| `emotional_state`   | enum    | ✅        | `calm` / `anxious` / `fomo` / `angry` / `overconfident` / `uncertain` |
| `confidence_before` | integer | ✅        | Pre-trade confidence rating, scale 1–10 |
| `satisfaction_after`| integer | ✅        | Post-trade satisfaction rating, scale 1–10 |
| `trade`             | UUID    | ❌        | Trade this log is linked to (nullable) |
| `pressure_source`   | enum    | ❌        | `money` / `time` / `missed_move` / `anger` / `uncertainty` |

**Success Response — `201 Created`:**

```json
{
  "id": "uuid",
  "user": 1,
  "log_date": "2025-01-15",
  "trade": "trade-uuid",
  "emotional_state": "anxious",
  "confidence_before": 5,
  "satisfaction_after": 3,
  "pressure_source": "money",
  "created_at": "2025-01-15T11:00:00Z"
}
```

---

#### `GET /api/journal/psychology/<uuid:id>/`

Returns a single psychology log owned by the authenticated user.

#### `PUT /api/journal/psychology/<uuid:id>/`

Fully updates the psychology log.

#### `PATCH /api/journal/psychology/<uuid:id>/`

Partially updates the psychology log.

#### `DELETE /api/journal/psychology/<uuid:id>/`

Deletes the psychology log.

**Permissions:** Authenticated (owner only)

**Success Response:** `200 OK` (GET/PUT/PATCH) — full psychology log object. `204 No Content` (DELETE).

---

### 4. Session Recaps

Post-session structured review. Captures what went right, what slipped, and a rule to focus on next session.

---

#### `GET /api/journal/recaps/`

Returns all session recaps for the authenticated user, ordered by most recent recap date first.

**Permissions:** Authenticated

**Success Response — `200 OK`:** paginated list of session recap objects.

---

#### `POST /api/journal/recaps/`

Creates a session recap.

**Permissions:** Authenticated

**Request Body:**

| Field              | Type   | Required | Description |
|--------------------|--------|----------|-------------|
| `recap_date`       | date   | ✅        | `YYYY-MM-DD` |
| `session_state`    | enum   | ✅        | `green` / `yellow` / `red` |
| `outcome`          | enum   | ✅        | `good` / `neutral` / `bad` |
| `what_went_right`  | array  | ❌        | List of strings. Defaults to `[]`. |
| `what_slipped`     | array  | ❌        | List of strings. Defaults to `[]`. |
| `rule_to_focus`    | string | ❌        | Rule the user intends to focus on next session |

**Success Response — `201 Created`:**

```json
{
  "id": "uuid",
  "user": 1,
  "recap_date": "2025-01-15",
  "session_state": "yellow",
  "outcome": "neutral",
  "what_went_right": ["Respected stop loss", "No revenge trades"],
  "what_slipped": ["Overtraded in the afternoon"],
  "rule_to_focus": "Max 3 trades per session",
  "created_at": "2025-01-15T17:00:00Z"
}
```

---

#### `GET /api/journal/recaps/<uuid:id>/`

Returns a single session recap owned by the authenticated user.

#### `PUT /api/journal/recaps/<uuid:id>/`

Fully updates the session recap.

#### `PATCH /api/journal/recaps/<uuid:id>/`

Partially updates the session recap.

#### `DELETE /api/journal/recaps/<uuid:id>/`

Deletes the session recap.

**Permissions:** Authenticated (owner only)

**Success Response:** `200 OK` (GET/PUT/PATCH) — full session recap object. `204 No Content` (DELETE).

---

### 5. Learning Notes

Notes from the Learning Hub or external sources. Can optionally be linked to a mistake, rule, or strategy by UUID.

---

#### `GET /api/journal/learning-notes/`

Returns all learning notes for the authenticated user, ordered by most recently created first.

**Permissions:** Authenticated

**Success Response — `200 OK`:** paginated list of learning note objects.

---

#### `POST /api/journal/learning-notes/`

Creates a learning note.

**Permissions:** Authenticated

**Request Body:**

| Field              | Type   | Required | Description |
|--------------------|--------|----------|-------------|
| `lesson_source`    | string | ✅        | Source of the lesson (max 255 chars), e.g. `"BitsOfTrade Learning Hub"` |
| `key_takeaway`     | string | ✅        | The main insight extracted |
| `application_plan` | string | ✅        | How the user plans to apply this learning |
| `linked_type`      | enum   | ❌        | `mistake` / `rule` / `strategy` / `none`. Defaults to `none`. |
| `linked_id`        | UUID   | ❌        | ID of the related mistake, rule, or strategy. Required when `linked_type` is not `none`. |

**Success Response — `201 Created`:**

```json
{
  "id": "uuid",
  "user": 1,
  "lesson_source": "BitsOfTrade Learning Hub",
  "key_takeaway": "Never average down on losing positions.",
  "application_plan": "Add a hard rule: no averaging down allowed.",
  "linked_type": "rule",
  "linked_id": "rule-uuid",
  "created_at": "2025-01-15T20:00:00Z"
}
```

---

#### `GET /api/journal/learning-notes/<uuid:id>/`

Returns a single learning note owned by the authenticated user.

#### `PUT /api/journal/learning-notes/<uuid:id>/`

Fully updates the learning note.

#### `PATCH /api/journal/learning-notes/<uuid:id>/`

Partially updates the learning note.

#### `DELETE /api/journal/learning-notes/<uuid:id>/`

Deletes the learning note.

**Permissions:** Authenticated (owner only)

**Success Response:** `200 OK` (GET/PUT/PATCH) — full learning note object. `204 No Content` (DELETE).

---

## Model Reference

### DailyJournal

| Field                    | Type     | Writable | Description |
|--------------------------|----------|----------|-------------|
| `id`                     | UUID     | ❌        | Primary key |
| `user`                   | FK       | ❌        | Set from authenticated user |
| `journal_date`           | date     | ✅        | Entry date — unique per user |
| `session_state`          | enum     | ✅        | `green` / `yellow` / `red` |
| `prompt_text`            | string   | ✅        | Prompt text |
| `reflection`             | string   | ✅        | Free-text reflection |
| `intention_next_session` | string   | ✅        | Next session intention |
| `limits_followed`        | enum     | ✅        | `yes` / `mostly` / `no` |
| `created_at`             | datetime | ❌        | Auto-set on creation |
| `updated_at`             | datetime | ❌        | Auto-updated on save |

### TradeNote

| Field        | Type     | Writable | Description |
|--------------|----------|----------|-------------|
| `id`         | UUID     | ❌        | Primary key |
| `user`       | FK       | ❌        | Set from authenticated user |
| `trade`      | FK       | ✅        | Linked `Trade` |
| `note_text`  | string   | ✅        | Note content |
| `tags`       | array    | ✅        | List of tag strings. Defaults to `[]`. |
| `created_at` | datetime | ❌        | Auto-set on creation |
| `updated_at` | datetime | ❌        | Auto-updated on save |

### PsychologyLog

| Field                | Type     | Writable | Description |
|----------------------|----------|----------|-------------|
| `id`                 | UUID     | ❌        | Primary key |
| `user`               | FK       | ❌        | Set from authenticated user |
| `log_date`           | date     | ✅        | Date of the log |
| `trade`              | FK       | ✅        | Linked `Trade` (nullable) |
| `emotional_state`    | enum     | ✅        | `calm` / `anxious` / `fomo` / `angry` / `overconfident` / `uncertain` |
| `confidence_before`  | integer  | ✅        | 1–10 pre-trade confidence |
| `satisfaction_after` | integer  | ✅        | 1–10 post-trade satisfaction |
| `pressure_source`    | enum     | ✅        | `money` / `time` / `missed_move` / `anger` / `uncertainty` (nullable) |
| `created_at`         | datetime | ❌        | Auto-set on creation |

### SessionRecap

| Field             | Type     | Writable | Description |
|-------------------|----------|----------|-------------|
| `id`              | UUID     | ❌        | Primary key |
| `user`            | FK       | ❌        | Set from authenticated user |
| `recap_date`      | date     | ✅        | Date of the recap |
| `session_state`   | enum     | ✅        | `green` / `yellow` / `red` |
| `outcome`         | enum     | ✅        | `good` / `neutral` / `bad` |
| `what_went_right` | array    | ✅        | List of strings. Defaults to `[]`. |
| `what_slipped`    | array    | ✅        | List of strings. Defaults to `[]`. |
| `rule_to_focus`   | string   | ✅        | Rule to focus on next session |
| `created_at`      | datetime | ❌        | Auto-set on creation |

### LearningNote

| Field              | Type     | Writable | Description |
|--------------------|----------|----------|-------------|
| `id`               | UUID     | ❌        | Primary key |
| `user`             | FK       | ❌        | Set from authenticated user |
| `lesson_source`    | string   | ✅        | Source of the lesson (max 255 chars) |
| `key_takeaway`     | string   | ✅        | Main insight |
| `application_plan` | string   | ✅        | How to apply this learning |
| `linked_type`      | enum     | ✅        | `mistake` / `rule` / `strategy` / `none`. Defaults to `none`. |
| `linked_id`        | UUID     | ✅        | ID of linked resource (nullable) |
| `created_at`       | datetime | ❌        | Auto-set on creation |

---

## URL Configuration

```python
# journal/urls.py
urlpatterns = [
    # Daily Journals
    path('daily/',                     DailyJournalListCreateView.as_view(),   name='journal-daily-list'),
    path('daily/<uuid:pk>/',           DailyJournalDetailView.as_view(),       name='journal-daily-detail'),

    # Trade Notes
    path('trade-notes/',               TradeNoteListCreateView.as_view(),      name='journal-tradenote-list'),
    path('trade-notes/<uuid:pk>/',     TradeNoteDetailView.as_view(),          name='journal-tradenote-detail'),

    # Psychology Logs
    path('psychology/',                PsychologyLogListCreateView.as_view(),  name='journal-psych-list'),
    path('psychology/<uuid:pk>/',      PsychologyLogDetailView.as_view(),      name='journal-psych-detail'),

    # Session Recaps
    path('recaps/',                    SessionRecapListCreateView.as_view(),   name='journal-recap-list'),
    path('recaps/<uuid:pk>/',          SessionRecapDetailView.as_view(),       name='journal-recap-detail'),

    # Learning Notes
    path('learning-notes/',            LearningNoteListCreateView.as_view(),   name='journal-learningnote-list'),
    path('learning-notes/<uuid:pk>/',  LearningNoteDetailView.as_view(),       name='journal-learningnote-detail'),
]
```

---

## Error Reference

| Status Code | Meaning |
|-------------|---------|
| `200`       | OK — request successful |
| `201`       | Created — resource created successfully |
| `204`       | No Content — resource deleted |
| `400`       | Bad Request — validation error (including duplicate `journal_date`) |
| `401`       | Unauthorized — missing or invalid JWT token |
| `404`       | Not found — resource does not exist or belongs to another user |

---

## Dependencies

- `tradelog` — `Trade` model (linked by `TradeNote` and `PsychologyLog`)
- `accounts` — `User` model
- `tradelog.pagination` — `StandardResultsSetPagination` (shared paginator)
