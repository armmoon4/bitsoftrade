# Notifications API Documentation

**Base URL:** `/api/notifications/`  
**Authentication:** All endpoints require a valid JWT token in the `Authorization` header.  
**Content-Type:** `application/json`

---

## Table of Contents

- [Models](#models)
- [Endpoints](#endpoints)
  - [List Notifications](#1-list-notifications)
  - [Unread Notifications](#2-unread-notifications)
  - [Mark Single as Read](#3-mark-single-notification-as-read)
  - [Mark All as Read](#4-mark-all-notifications-as-read)
  - [Delete Single Notification](#5-delete-single-notification)
  - [Clear All Notifications](#6-clear-all-notifications)
  - [Get Notification Settings](#7-get-notification-settings)
  - [Update Notification Settings](#8-update-notification-settings)
- [Notification Types](#notification-types)
- [Severity Levels](#severity-levels)
- [How Notifications Are Created](#how-notifications-are-created)
- [Error Responses](#error-responses)

---

## Models

### Notification

| Field               | Type      | Description                                              |
|---------------------|-----------|----------------------------------------------------------|
| `id`                | UUID      | Unique identifier                                        |
| `notification_type` | string    | One of: `rule_triggered`, `rule_violated`, `session_locked`, `session_unlocked` |
| `severity`          | string    | One of: `info`, `warning`, `error`                       |
| `title`             | string    | Short notification title                                 |
| `message`           | string    | Full notification message                                |
| `is_read`           | boolean   | Whether the user has read this notification              |
| `rule_id`           | UUID/null | Linked rule ID (if triggered by a rule)                  |
| `rule_name`         | string/null | Linked rule name                                       |
| `session_id`        | UUID/null | Linked discipline session ID                             |
| `session_date`      | date/null | Date of the linked session                               |
| `trade_id`          | UUID/null | Linked trade ID (if triggered by a specific trade)       |
| `created_at`        | datetime  | When the notification was created                        |

### NotificationSettings

| Field                    | Type    | Default | Description                                      |
|--------------------------|---------|---------|--------------------------------------------------|
| `notify_rule_triggered`  | boolean | `true`  | Receive notifications when a soft rule triggers  |
| `notify_rule_violated`   | boolean | `true`  | Receive notifications when a hard rule is violated |
| `notify_session_locked`  | boolean | `true`  | Receive notifications when session is locked     |
| `notify_session_unlocked`| boolean | `true`  | Receive notifications when session is unlocked   |
| `auto_delete_after_days` | integer | `30`    | Auto-delete notifications older than N days (0 = never) |
| `updated_at`             | datetime| —       | Last time settings were updated                  |

---

## Endpoints

### 1. List Notifications

Returns all notifications for the authenticated user, newest first.

**`GET /api/notifications/`**

#### Query Parameters

| Parameter  | Type   | Required | Description                                                  |
|------------|--------|----------|--------------------------------------------------------------|
| `unread`   | string | No       | Pass `true` to return only unread notifications              |
| `type`     | string | No       | Filter by `notification_type` (e.g. `rule_violated`)         |
| `severity` | string | No       | Filter by severity (`info`, `warning`, `error`)              |

#### Example Request

```http
GET /api/notifications/?unread=true&severity=error
Authorization: Bearer <token>
```

#### Example Response `200 OK`

```json
[
  {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "notification_type": "rule_violated",
    "severity": "error",
    "title": "Rule Violated: Max Daily Loss",
    "message": "A hard rule has been violated: \"Max Daily Loss\". Your session is now RED.",
    "is_read": false,
    "rule_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "rule_name": "Max Daily Loss",
    "session_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
    "session_date": "2024-01-15",
    "trade_id": "d4e5f6a7-b8c9-0123-defa-234567890123",
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

---

### 2. Unread Notifications

Returns only unread notifications along with the total unread count.

**`GET /api/notifications/unread/`**

#### Example Request

```http
GET /api/notifications/unread/
Authorization: Bearer <token>
```

#### Example Response `200 OK`

```json
{
  "unread_count": 3,
  "results": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "notification_type": "session_locked",
      "severity": "warning",
      "title": "Trading Session YELLOW — Locked",
      "message": "Your trading session has been locked (YELLOW). Please complete the required actions in the Discipline section to resume trading.",
      "is_read": false,
      "rule_id": null,
      "rule_name": null,
      "session_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
      "session_date": "2024-01-15",
      "trade_id": null,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

---

### 3. Mark Single Notification as Read

Marks a specific notification as read.

**`PATCH /api/notifications/{id}/read/`**

#### Path Parameters

| Parameter | Type | Description             |
|-----------|------|-------------------------|
| `id`      | UUID | The notification UUID   |

#### Example Request

```http
PATCH /api/notifications/a1b2c3d4-e5f6-7890-abcd-ef1234567890/read/
Authorization: Bearer <token>
```

#### Example Response `200 OK`

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "notification_type": "rule_violated",
  "severity": "error",
  "title": "Rule Violated: Max Daily Loss",
  "message": "A hard rule has been violated: \"Max Daily Loss\". Your session is now RED.",
  "is_read": true,
  "rule_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "rule_name": "Max Daily Loss",
  "session_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "session_date": "2024-01-15",
  "trade_id": null,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### Error Response `404 Not Found`

```json
{
  "detail": "Notification not found."
}
```

---

### 4. Mark All Notifications as Read

Marks every notification for the authenticated user as read.

**`PATCH /api/notifications/read-all/`**

#### Example Request

```http
PATCH /api/notifications/read-all/
Authorization: Bearer <token>
```

#### Example Response `200 OK`

```json
{
  "marked_read": 5
}
```

> `marked_read` is the count of notifications that were updated.

---

### 5. Delete Single Notification

Permanently deletes a specific notification.

**`DELETE /api/notifications/{id}/delete/`**

#### Path Parameters

| Parameter | Type | Description           |
|-----------|------|-----------------------|
| `id`      | UUID | The notification UUID |

#### Example Request

```http
DELETE /api/notifications/a1b2c3d4-e5f6-7890-abcd-ef1234567890/delete/
Authorization: Bearer <token>
```

#### Example Response `204 No Content`

```json
{
  "detail": "Notification deleted."
}
```

#### Error Response `404 Not Found`

```json
{
  "detail": "Notification not found."
}
```

---

### 6. Clear All Notifications

Permanently deletes ALL notifications for the authenticated user.

**`DELETE /api/notifications/clear-all/`**

#### Example Request

```http
DELETE /api/notifications/clear-all/
Authorization: Bearer <token>
```

#### Example Response `200 OK`

```json
{
  "deleted": 12
}
```

> `deleted` is the total count of notifications removed.

---

### 7. Get Notification Settings

Returns the current notification preferences for the authenticated user. A settings row is automatically created with defaults if it doesn't exist yet.

**`GET /api/notifications/settings/`**

#### Example Request

```http
GET /api/notifications/settings/
Authorization: Bearer <token>
```

#### Example Response `200 OK`

```json
{
  "notify_rule_triggered": true,
  "notify_rule_violated": true,
  "notify_session_locked": true,
  "notify_session_unlocked": true,
  "auto_delete_after_days": 30,
  "updated_at": "2024-01-15T09:00:00Z"
}
```

---

### 8. Update Notification Settings

Updates one or more notification preferences. All fields are optional — only send what you want to change.

**`PATCH /api/notifications/settings/`**

#### Request Body

| Field                    | Type    | Description                                              |
|--------------------------|---------|----------------------------------------------------------|
| `notify_rule_triggered`  | boolean | Enable/disable soft rule trigger notifications           |
| `notify_rule_violated`   | boolean | Enable/disable hard rule violation notifications         |
| `notify_session_locked`  | boolean | Enable/disable session locked notifications              |
| `notify_session_unlocked`| boolean | Enable/disable session unlocked notifications            |
| `auto_delete_after_days` | integer | Days before auto-deletion (0 = never auto-delete)        |

#### Example Request — Disable session unlocked notifications

```http
PATCH /api/notifications/settings/
Authorization: Bearer <token>
Content-Type: application/json

{
  "notify_session_unlocked": false
}
```

#### Example Request — Update multiple settings

```http
PATCH /api/notifications/settings/
Authorization: Bearer <token>
Content-Type: application/json

{
  "notify_rule_triggered": false,
  "notify_session_unlocked": false,
  "auto_delete_after_days": 7
}
```

#### Example Response `200 OK`

```json
{
  "notify_rule_triggered": false,
  "notify_rule_violated": true,
  "notify_session_locked": true,
  "notify_session_unlocked": false,
  "auto_delete_after_days": 7,
  "updated_at": "2024-01-15T11:00:00Z"
}
```

---

## Notification Types

| Type               | Triggered When                              | Default Severity |
|--------------------|---------------------------------------------|------------------|
| `rule_triggered`   | A soft rule threshold is breached           | `warning`        |
| `rule_violated`    | A hard rule threshold is breached           | `error`          |
| `session_locked`   | Session escalates to YELLOW or RED          | `warning` / `error` |
| `session_unlocked` | User completes required actions and unlocks | `info`           |

---

## Severity Levels

| Severity  | Used For                                      |
|-----------|-----------------------------------------------|
| `info`    | Session unlocked — informational only         |
| `warning` | Soft rule triggered or session is YELLOW      |
| `error`   | Hard rule violated or session is RED          |

---

## How Notifications Are Created

Notifications are **created automatically** by the system — you never POST to create one manually.

```
Trade saved
    └── Rule Engine runs (rules/engine.py)
            ├── Rule triggered/violated
            │       └── create_rule_notification() → Notification row created
            │               (skipped if user disabled that type in settings)
            └── Session state escalates (GREEN → YELLOW/RED)
                    └── create_session_notification(event='locked') → Notification row created

User unlocks session (discipline/views.py)
    └── create_session_notification(event='unlocked') → Notification row created
```

---

## Error Responses

| Status | Meaning                                              |
|--------|------------------------------------------------------|
| `400`  | Bad request — invalid field value in settings PATCH  |
| `401`  | Unauthorized — missing or invalid JWT token          |
| `404`  | Notification not found or belongs to another user    |
| `204`  | Success with no response body (single delete)        |
