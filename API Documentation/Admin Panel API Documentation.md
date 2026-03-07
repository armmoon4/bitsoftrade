# Admin Panel API Documentation

## Overview

The **Admin Panel** module provides a separate, privileged API for platform administrators. Admin authentication uses a **custom JWT token** (separate from user tokens) with an `admin_id` and `access_level` payload. All admin endpoints require the admin token in the `Authorization` header.

---

## Base URL

```
/api/admin/
```

---

## Authentication

Admin endpoints use a custom JWT token issued by the admin login endpoint:

```
Authorization: Bearer <admin_access_token>
```

> **Note:** Admin tokens are issued independently from user tokens. Even if a user is an admin, the user JWT cannot be used for admin panel endpoints.

---

## Access Levels

| Level         | Permissions                                  |
|---------------|----------------------------------------------|
| `super_admin` | Full access: manage users, admins, rules, strategies |
| `admin`       | Manage users, rules, and strategies (cannot create/delete admins) |

---

## Endpoints

### Auth

#### 1. Admin Login

**`POST /api/admin/auth/login/`**

Authenticates an admin and returns JWT tokens.

**Permissions:** Public

**Request Body:**

| Field      | Type   | Required | Description    |
|------------|--------|----------|----------------|
| `email`    | string | ✅        | Admin email    |
| `password` | string | ✅        | Admin password |

**Success Response — `200 OK`:**

```json
{
  "admin_id": "uuid",
  "full_name": "Super Admin",
  "email": "admin@bitsoftrade.com",
  "access_level": "super_admin",
  "tokens": {
    "refresh": "<refresh_token>",
    "access": "<access_token>"
  },
  "message": "Login successful."
}
```

**Error — `401 Unauthorized`:**

```json
{ "error": "Invalid credentials." }
```

---

### Dashboard

#### 2. Dashboard Stats

**`GET /api/admin/dashboard/stats/`**

Returns platform-level KPI counts.

**Permissions:** Admin

**Success Response — `200 OK`:**

```json
{
  "total_users": 1250,
  "todays_new_users": 18,
  "total_subscribers": 320,
  "total_trade_imports": 4500
}
```

---

### User Management

#### 3. List Users

**`GET /api/admin/users/`**

Returns all active users with optional filters.

**Permissions:** Admin

**Query Parameters:**

| Parameter           | Description                                             |
|---------------------|---------------------------------------------------------|
| `subscription_type` | Filter by `none` / `tool` / `learning` / `both`         |
| `search`            | Search by `username` or `email` (case-insensitive)      |

**Success Response — `200 OK`:**

```json
{
  "count": 1250,
  "results": [
    {
      "id": 1,
      "username": "johndoe",
      "email": "john@example.com",
      "subscription_type": "tool",
      "subscription_status": "active",
      "is_active": true,
      "date_joined": "2025-01-01T00:00:00Z"
    }
  ]
}
```

---

#### 4. Toggle User Active Status

**`PUT /api/admin/users/<int:user_id>/toggle/`**

Toggles the user's `is_active` flag. Logs the action automatically.

**Permissions:** Admin

**Success Response — `200 OK`:**

```json
{ "is_active": false }
```

---

#### 5. Delete User (Soft Delete)

**`DELETE /api/admin/users/<int:user_id>/delete/`**

Soft-deletes a user account.

**Permissions:** Admin

**Success Response — `204 No Content`**

---

### Admin Management

#### 6. List Admins

**`GET /api/admin/admins/`**

Returns all active admins.

**Permissions:** Admin (any level)

**Success Response — `200 OK`:**

```json
[
  {
    "id": "uuid",
    "full_name": "Super Admin",
    "email": "admin@bitsoftrade.com",
    "access_level": "super_admin",
    "created_at": "2025-01-01T00:00:00Z"
  }
]
```

---

#### 7. Create Admin

**`POST /api/admin/admins/create/`**

Creates a new admin account.

**Permissions:** `super_admin` only

**Request Body:**

| Field          | Type   | Required | Description             |
|----------------|--------|----------|-------------------------|
| `full_name`    | string | ✅        | Admin display name      |
| `email`        | string | ✅        | Unique email address    |
| `password`     | string | ✅        | Account password        |
| `access_level` | enum   | ✅        | `admin` or `super_admin`|

**Success Response — `201 Created`:**

```json
{ "id": "uuid", "email": "newadmin@example.com" }
```

---

#### 8. Update / Delete Admin

**`PUT /api/admin/admins/<uuid:id>/`** — Update admin name, access level, or password

**`DELETE /api/admin/admins/<uuid:id>/`** — Soft-delete an admin

**Permissions:** `super_admin` only (cannot modify own account via this endpoint)

**Update Request Body:**

| Field          | Type   | Required | Description                |
|----------------|--------|----------|----------------------------|
| `full_name`    | string | ❌        | New full name              |
| `access_level` | enum   | ❌        | `admin` or `super_admin`   |
| `password`     | string | ❌        | New password               |

**Success Response (PUT) — `200 OK`:**

```json
{ "message": "Admin updated." }
```

**Success Response (DELETE) — `204 No Content`**

---

### Rules Management

#### 9. List / Create Admin Rules

**`GET /api/admin/rules/`** — List all admin-defined global rules

**`POST /api/admin/rules/`** — Create a new global rule

**Permissions:** Admin

**POST Request Body:**

| Field               | Type    | Required | Description                                              |
|---------------------|---------|----------|----------------------------------------------------------|
| `rule_name`         | string  | ✅        | Rule display name                                        |
| `description`       | string  | ❌        | Rule description                                         |
| `category`          | enum    | ✅        | `risk` / `process` / `psychology` / `time` / `other`    |
| `rule_type`         | enum    | ✅        | `hard` / `soft`                                          |
| `trigger_scope`     | enum    | ✅        | `per_day` / `per_trade` / `post_trigger`                 |
| `trigger_condition` | object  | ✅        | JSON condition e.g. `{"maxLoss": 5000}`                  |
| `action`            | enum    | ✅        | `lock` / `warn` / `require_journal` / `restrict_import` |

**Success Response (POST) — `201 Created`:** full rule object

---

#### 10. Get / Update / Delete Admin Rule

**`GET /api/admin/rules/<uuid:id>/`** — Retrieve single rule details (for pre-populating edit form)

**`PUT /api/admin/rules/<uuid:id>/`** — Update a global rule

**`DELETE /api/admin/rules/<uuid:id>/`** — Soft-delete a global rule

**Permissions:** Admin

**PUT Request Body:** any subset of the rule fields (`rule_name`, `description`, `category`, `rule_type`, `trigger_scope`, `trigger_condition`, `action`, `is_active`)

**Success Responses:**

- `GET` → `200 OK` — full rule object
- `PUT` → `200 OK` — updated rule object
- `DELETE` → `204 No Content`

---

### Strategy Template Management

#### 11. List / Create Template Strategies

**`GET /api/admin/strategies/`** — List all admin template strategies

**`POST /api/admin/strategies/`** — Create a new template strategy

**Permissions:** Admin

**POST Request Body:**

| Field                   | Type    | Required | Description                              |
|-------------------------|---------|----------|------------------------------------------|
| `strategy_name`         | string  | ✅        | Strategy name                            |
| `description`           | string  | ❌        | Description                              |
| `tags`                  | array   | ❌        | Array of tag strings                     |
| `market_types`          | array   | ❌        | Array of market type strings             |
| `trade_type`            | enum    | ❌        | `intraday` / `swing` / `positional`      |
| `is_public`             | boolean | ❌        | Visible to all users (default: `false`)  |
| `sample_size_threshold` | integer | ❌        | Maturity threshold (default: 30)         |

---

#### 12. Get / Update / Delete Template Strategy

**`GET /api/admin/strategies/<uuid:id>/`** — Retrieve template

**`PUT /api/admin/strategies/<uuid:id>/`** — Update template

**`DELETE /api/admin/strategies/<uuid:id>/`** — Soft-delete template

**Permissions:** Admin

---

## Action Audit Log

All sensitive admin actions are automatically logged in `AdminUserAction` and `AdminAdminAction` tables, including:
- User toggle/delete
- Admin create/edit/delete

---

## URL Configuration

```python
# admin_panel/urls.py
urlpatterns = [
    path('auth/login/',                  admin_login_view,                name='admin-login'),
    path('dashboard/stats/',             admin_dashboard_stats_view,      name='admin-dashboard-stats'),
    path('users/',                       admin_user_list_view,             name='admin-user-list'),
    path('users/<int:user_id>/toggle/',  admin_user_toggle_view,          name='admin-user-toggle'),
    path('users/<int:user_id>/delete/',  admin_user_delete_view,          name='admin-user-delete'),
    path('admins/',                      admin_list_view,                  name='admin-admin-list'),
    path('admins/create/',               admin_create_view,                name='admin-admin-create'),
    path('admins/<uuid:admin_id>/',      admin_manage_view,                name='admin-admin-manage'),
    path('rules/',                       admin_rule_list_create_view,      name='admin-rule-list'),
    path('rules/<uuid:pk>/',             admin_rule_detail_view,           name='admin-rule-detail'),
    path('strategies/',                  admin_strategy_list_create_view,  name='admin-strategy-list'),
    path('strategies/<uuid:pk>/',        admin_strategy_detail_view,       name='admin-strategy-detail'),
]
```

---

## Error Reference

| Status Code | Meaning                                                  |
|-------------|----------------------------------------------------------|
| `200`       | OK                                                       |
| `201`       | Created                                                  |
| `204`       | No Content (deleted)                                     |
| `400`       | Bad Request — missing field or duplicate email           |
| `401`       | Unauthorized — invalid or expired admin token            |
| `403`       | Forbidden — insufficient access level                    |
| `404`       | Not found                                                |
