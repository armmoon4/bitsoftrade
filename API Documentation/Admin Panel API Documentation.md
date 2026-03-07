# Admin Panel API

## Overview

The **Admin Panel** module provides a separate, privileged API for platform administrators. Admin authentication uses a **custom JWT token** (separate from user tokens) with an `admin_id` and `access_level` payload. All admin endpoints require the admin token in the `Authorization` header.

---

## Base URL

```
/api/admin/
```

---

## First-Time Setup: Create Super Admin

Before using the admin panel, you must create the first super admin account using the management command. This only needs to be run **once**.

### Using Docker

```bash
docker-compose run web python manage.py create_super_admin \
  --email superadmin@example.com \
  --name "superadmin" \
  --password superadmin
```

### Without Docker (Local)

```bash
python manage.py create_super_admin \
  --email superadmin@example.com \
  --name "superadmin" \
  --password superadmin
```

> **Note:** After the super admin is created, all additional admins can be managed via the API endpoints below. You do not need to run this command again.

---

## Authentication

Admin endpoints use a custom JWT token issued by the admin login endpoint:

```
Authorization: Bearer <admin_access_token>
```

> **Important:** Admin tokens are issued independently from user tokens. Even if a user account exists with the same email, the user JWT **cannot** be used for admin panel endpoints.

---

## Access Levels

| Level         | Permissions                                                       |
|---------------|-------------------------------------------------------------------|
| `super_admin` | Full access: manage users, admins, rules, strategies              |
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

Returns all active (non-deleted) users with optional filters.

**Permissions:** Admin

**Query Parameters:**

| Parameter           | Description                                         |
|---------------------|-----------------------------------------------------|
| `subscription_type` | Filter by `none` / `tool` / `learning` / `both`     |
| `search`            | Search by `username` or `email` (case-insensitive)  |

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

Toggles the user's `is_active` flag. Action is automatically logged to `AdminUserAction`.

**Permissions:** Admin

**Success Response — `200 OK`:**

```json
{ "is_active": false }
```

---

#### 5. Delete User (Soft Delete)

**`DELETE /api/admin/users/<int:user_id>/delete/`**

Soft-deletes a user by setting `deleted_at` and `is_active=False`. Action is automatically logged.

**Permissions:** Admin

**Success Response — `204 No Content`**

---

### Admin Management

#### 6. List Admins

**`GET /api/admin/admins/`**

Returns all active (non-deleted) admins.

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

| Field          | Type   | Required | Description              |
|----------------|--------|----------|--------------------------|
| `full_name`    | string | ✅        | Admin display name       |
| `email`        | string | ✅        | Unique email address     |
| `password`     | string | ✅        | Account password         |
| `access_level` | enum   | ✅        | `admin` or `super_admin` |

**Success Response — `201 Created`:**

```json
{ "id": "uuid", "email": "newadmin@example.com" }
```

---

#### 8. Update Admin

**`PUT /api/admin/admins/<uuid:admin_id>/`**

Updates an existing admin's details.

**Permissions:** `super_admin` only

> **Note:** A super admin cannot modify their own account via this endpoint. Attempting to do so returns `403 Forbidden`.

**Request Body (all fields optional):**

| Field          | Type   | Required | Description              |
|----------------|--------|----------|--------------------------|
| `full_name`    | string | ❌        | New full name            |
| `access_level` | enum   | ❌        | `admin` or `super_admin` |
| `password`     | string | ❌        | New password             |

**Success Response — `200 OK`:**

```json
{ "message": "Admin updated." }
```

---

#### 9. Delete Admin (Soft Delete)

**`DELETE /api/admin/admins/<uuid:admin_id>/`**

Soft-deletes an admin by setting `deleted_at`.

**Permissions:** `super_admin` only

> **Note:** A super admin cannot delete their own account via this endpoint. Attempting to do so returns `403 Forbidden`.

**Success Response — `204 No Content`**

---

### Rules Management

#### 10. List Admin Rules

**`GET /api/admin/rules/`**

Returns all admin-defined global rules that have not been deleted.

**Permissions:** Admin

**Success Response — `200 OK`:** array of rule objects

---

#### 11. Create Admin Rule

**`POST /api/admin/rules/`**

Creates a new global rule. `is_admin_defined` is set to `True` automatically.

**Permissions:** Admin

**Request Body:**

| Field               | Type   | Required | Default      | Description                                              |
|---------------------|--------|----------|--------------|----------------------------------------------------------|
| `rule_name`         | string | ✅        | —            | Rule display name                                        |
| `description`       | string | ❌        | `""`         | Rule description                                         |
| `category`          | enum   | ❌        | `"other"`    | `risk` / `process` / `psychology` / `time` / `other`    |
| `rule_type`         | enum   | ❌        | `"soft"`     | `hard` / `soft`                                          |
| `trigger_scope`     | enum   | ❌        | `"per_day"`  | `per_day` / `per_trade` / `post_trigger`                 |
| `trigger_condition` | object | ❌        | `{}`         | JSON condition e.g. `{"maxLoss": 5000}`                  |
| `action`            | enum   | ❌        | `"warn"`     | `lock` / `warn` / `require_journal` / `restrict_import` |

**Success Response — `201 Created`:** full rule object

---

#### 12. Get Admin Rule

**`GET /api/admin/rules/<uuid:id>/`**

Retrieves a single rule's full details. Typically used to pre-populate admin edit forms.

**Permissions:** Admin

**Success Response — `200 OK`:** full rule object

---

#### 13. Update Admin Rule

**`PUT /api/admin/rules/<uuid:id>/`**

Updates a global rule. Any subset of fields can be provided.

**Permissions:** Admin

**Request Body (all fields optional):**

`rule_name`, `description`, `category`, `rule_type`, `trigger_scope`, `trigger_condition`, `action`, `is_active`

**Success Response — `200 OK`:** updated rule object

---

#### 14. Delete Admin Rule

**`DELETE /api/admin/rules/<uuid:id>/`**

Soft-deletes the rule by setting `deleted_at`.

**Permissions:** Admin

**Success Response — `204 No Content`**

---

### Strategy Template Management

#### 15. List Template Strategies

**`GET /api/admin/strategies/`**

Returns all non-deleted admin template strategies, ordered by `-created_at`.

**Permissions:** Admin

**Success Response — `200 OK`:** array of strategy objects

---

#### 16. Create Template Strategy

**`POST /api/admin/strategies/`**

Creates a new template strategy. `is_template=True` and `user=None` are set automatically.

**Permissions:** Admin

**Request Body:**

| Field                   | Type    | Required | Default | Description                              |
|-------------------------|---------|----------|---------|------------------------------------------|
| `strategy_name`         | string  | ✅        | —       | Strategy name                            |
| `description`           | string  | ❌        | `""`    | Description                              |
| `tags`                  | array   | ❌        | `[]`    | Array of tag strings                     |
| `market_types`          | array   | ❌        | `[]`    | Array of market type strings             |
| `trade_type`            | enum    | ❌        | `null`  | `intraday` / `swing` / `positional`      |
| `is_public`             | boolean | ❌        | `false` | Whether visible to all users             |
| `sample_size_threshold` | integer | ❌        | `30`    | Minimum trades before stats are shown    |

**Success Response — `201 Created`:** full strategy object

---

#### 17. Get Template Strategy

**`GET /api/admin/strategies/<uuid:id>/`**

Retrieves a single template strategy.

**Permissions:** Admin

**Success Response — `200 OK`:** full strategy object

---

#### 18. Update Template Strategy

**`PUT /api/admin/strategies/<uuid:id>/`**

Updates an existing template strategy. Any subset of fields can be provided.

**Permissions:** Admin

**Editable fields:** `strategy_name`, `description`, `tags`, `market_types`, `trade_type`, `is_public`, `sample_size_threshold`

**Success Response — `200 OK`:** updated strategy object

---

#### 19. Delete Template Strategy

**`DELETE /api/admin/strategies/<uuid:id>/`**

Soft-deletes the strategy by setting `deleted_at`.

**Permissions:** Admin

**Success Response — `204 No Content`**

---

## Action Audit Log

All sensitive admin actions are automatically logged:

| Table               | Logged Actions                          |
|---------------------|-----------------------------------------|
| `AdminUserAction`   | User toggle active, user soft-delete    |
| `AdminAdminAction`  | Admin create, admin edit, admin delete  |

Each log entry stores: the acting admin, the target, action type, action detail (JSON), and timestamp.

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

| Status Code | Meaning                                                                 |
|-------------|-------------------------------------------------------------------------|
| `200`       | OK                                                                      |
| `201`       | Created                                                                 |
| `204`       | No Content (deleted)                                                    |
| `400`       | Bad Request — missing required field or duplicate email                 |
| `401`       | Unauthorized — invalid or expired admin token                           |
| `403`       | Forbidden — insufficient access level, or attempting to modify own account |
| `404`       | Not Found — resource does not exist or has been soft-deleted            |