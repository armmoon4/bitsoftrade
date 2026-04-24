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
docker exec -it bitsoftrade-web-1 python manage.py create_super_admin --email superadmin@example.com --name superadmin --password superadmin
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
| `super_admin` | Full access: manage users, admins, rules, strategies, mistakes    |
| `admin`       | Manage users, rules, strategies, mistakes (cannot create/delete admins) |

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

### Profile

#### 2. Get My Profile

**`GET /api/admin/me/`**

Returns the authenticated admin's own profile.

**Permissions:** Admin

**Success Response — `200 OK`:**

```json
{
  "id": "uuid",
  "full_name": "Super Admin",
  "email": "admin@bitsoftrade.com",
  "phone_number": "+91XXXXXXXXXX",
  "access_level": "super_admin",
  "profile_picture_url": "https://...",
  "created_at": "2025-01-01T00:00:00Z"
}
```

---

#### 3. Update My Profile

**`PUT /api/admin/me/`** or **`PATCH /api/admin/me/`**

Updates the authenticated admin's own profile. `email` and `access_level` cannot be changed here.

**Permissions:** Admin

**Request Body (all fields optional):**

| Field                 | Type   | Required | Description                        |
|-----------------------|--------|----------|------------------------------------|
| `full_name`           | string | ❌        | Admin display name                 |
| `phone_number`        | string | ❌        | Contact number                     |
| `profile_picture_url` | string | ❌        | URL of profile picture             |
| `password`            | string | ❌        | New password (hashed on save)      |

**Success Response — `200 OK`:**

```json
{
  "id": "uuid",
  "full_name": "Updated Name",
  "email": "admin@bitsoftrade.com",
  "phone_number": "+91XXXXXXXXXX",
  "access_level": "super_admin",
  "profile_picture_url": "https://...",
  "updated_at": "2025-06-01T00:00:00Z"
}
```

---

### Dashboard

#### 4. Dashboard Stats

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

#### 5. List Users

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

#### 6. Toggle User Active Status

**`PUT /api/admin/users/<int:user_id>/toggle/`**

Toggles the user's `is_active` flag. Action is automatically logged to `AdminUserAction`.

**Permissions:** Admin

**Success Response — `200 OK`:**

```json
{ "is_active": false }
```

---

#### 7. Delete User (Soft Delete)

**`DELETE /api/admin/users/<int:user_id>/delete/`**

Soft-deletes a user by setting `deleted_at` and `is_active=False`. Action is automatically logged.

**Permissions:** Admin

**Success Response — `204 No Content`**

---

### Admin Management

#### 8. List Admins

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

#### 9. Create Admin

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

#### 10. Update Admin

**`PUT /api/admin/admins/<uuid:admin_id>/`**

Updates an existing admin's details.

**Permissions:** `super_admin` only

> **Note:** A super admin cannot modify their own account via this endpoint. Use `PUT /api/admin/me/` instead. Attempting to do so returns `403 Forbidden`.

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

#### 11. Delete Admin (Soft Delete)

**`DELETE /api/admin/admins/<uuid:admin_id>/`**

Soft-deletes an admin by setting `deleted_at`.

**Permissions:** `super_admin` only

> **Note:** A super admin cannot delete their own account via this endpoint. Attempting to do so returns `403 Forbidden`.

**Success Response — `204 No Content`**

---

### Rules Management

#### 12. List Admin Rules

**`GET /api/admin/rules/`**

Returns all admin-defined global rules that have not been deleted.

**Permissions:** Admin

**Success Response — `200 OK`:** array of rule objects

---

#### 13. Create Admin Rule

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

#### 14. Get Admin Rule

**`GET /api/admin/rules/<uuid:id>/`**

Retrieves a single rule's full details.

**Permissions:** Admin

**Success Response — `200 OK`:** full rule object

---

#### 15. Update Admin Rule

**`PUT /api/admin/rules/<uuid:id>/`**

Updates a global rule. Any subset of fields can be provided.

**Permissions:** Admin

**Editable fields:** `rule_name`, `description`, `category`, `rule_type`, `trigger_scope`, `trigger_condition`, `action`, `is_active`

**Success Response — `200 OK`:** updated rule object

---

#### 16. Delete Admin Rule

**`DELETE /api/admin/rules/<uuid:id>/`**

Soft-deletes the rule by setting `deleted_at`.

**Permissions:** Admin

**Success Response — `204 No Content`**

---

### Strategy Template Management

#### 17. List Template Strategies

**`GET /api/admin/strategies/`**

Returns all non-deleted admin template strategies, ordered by `-created_at`.

**Permissions:** Admin

**Success Response — `200 OK`:** array of strategy objects

---

#### 18. Create Template Strategy

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

#### 19. Get Template Strategy

**`GET /api/admin/strategies/<uuid:id>/`**

Retrieves a single template strategy.

**Permissions:** Admin

**Success Response — `200 OK`:** full strategy object

---

#### 20. Update Template Strategy

**`PUT /api/admin/strategies/<uuid:id>/`**

Updates an existing template strategy. Any subset of fields can be provided.

**Permissions:** Admin

**Editable fields:** `strategy_name`, `description`, `tags`, `market_types`, `trade_type`, `is_public`, `sample_size_threshold`

**Success Response — `200 OK`:** updated strategy object

---

#### 21. Delete Template Strategy

**`DELETE /api/admin/strategies/<uuid:id>/`**

Soft-deletes the strategy by setting `deleted_at`.

**Permissions:** Admin

**Success Response — `204 No Content`**

---

### Mistake Management

Admin-defined mistakes are global mistakes visible to all users. Users can see them but cannot delete them.

#### 22. List Admin Mistakes

**`GET /api/admin/mistakes/`**

Returns all non-deleted admin-defined mistakes.

**Permissions:** Admin

**Success Response — `200 OK`:** array of mistake objects

```json
[
  {
    "id": "uuid",
    "mistake_name": "Ignored Stop Loss",
    "mistake_mode": "ignored_stop_loss",
    "category": "risk",
    "description": "...",
    "severity_weight": 9,
    "is_custom": false,
    "is_admin_defined": true,
    "created_at": "2025-01-01T00:00:00Z"
  }
]
```

---

#### 23. Create Admin Mistake

**`POST /api/admin/mistakes/`**

Creates a new global mistake. `is_admin_defined=True`, `is_custom=False`, and `user=None` are set automatically.

**Permissions:** Admin

**Request Body:**

| Field             | Type    | Required | Description                                                                                      |
|-------------------|---------|----------|--------------------------------------------------------------------------------------------------|
| `mistake_name`    | string  | ✅        | Display name                                                                                     |
| `category`        | enum    | ✅        | `execution` / `psychology` / `process` / `risk`                                                 |
| `severity_weight` | integer | ✅        | Severity score 1–10                                                                              |
| `mistake_mode`    | enum    | ❌        | `overtrading` / `revenge_trading` / `fomo` / `early_exit` / `ignored_stop_loss` / `late_exit` / `no_plan` / `oversized_position` |
| `description`     | string  | ❌        | Additional detail                                                                                |

**Success Response — `201 Created`:** full mistake object

---

#### 24. Get Admin Mistake

**`GET /api/admin/mistakes/<uuid:id>/`**

Retrieves a single admin-defined mistake.

**Permissions:** Admin

**Success Response — `200 OK`:** full mistake object

---

#### 25. Update Admin Mistake

**`PUT /api/admin/mistakes/<uuid:id>/`** or **`PATCH /api/admin/mistakes/<uuid:id>/`**

Updates an admin-defined mistake. Use `PATCH` for partial updates.

**Permissions:** Admin

**Editable fields:** `mistake_name`, `mistake_mode`, `category`, `description`, `severity_weight`

**Success Response — `200 OK`:** updated mistake object

---

#### 26. Delete Admin Mistake (Soft Delete)

**`DELETE /api/admin/mistakes/<uuid:id>/`**

Soft-deletes the mistake by setting `deleted_at`. The mistake will no longer appear in user or admin listings.

**Permissions:** Admin

**Success Response — `204 No Content`**

---

### CMS — Reviews

#### 27. List All Reviews (Admin)

**`GET /api/admin/cms/reviews/`**

Returns all reviews including hidden ones.

**Permissions:** Admin

**Success Response — `200 OK`:** array of review objects

---

#### 28. Create Review

**`POST /api/admin/cms/reviews/`**

**Permissions:** Admin

**Request Body:**

| Field            | Type    | Required | Default | Description              |
|------------------|---------|----------|---------|--------------------------|
| `reviewer_name`  | string  | ✅        | —       | Name of the reviewer     |
| `rating`         | integer | ✅        | `5`     | 1–5 stars                |
| `review_text`    | string  | ✅        | —       | Review content           |
| `is_visible`     | boolean | ❌        | `true`  | Show on landing page     |
| `display_order`  | integer | ❌        | `0`     | Lower = shown first      |

**Success Response — `201 Created`:** full review object

---

#### 29. Get Review

**`GET /api/admin/cms/reviews/<uuid:id>/`**

**Permissions:** Admin

**Success Response — `200 OK`:** full review object

---

#### 30. Update Review

**`PUT /api/admin/cms/reviews/<uuid:id>/`**

**Permissions:** Admin

**Success Response — `200 OK`:** updated review object

---

#### 31. Delete Review

**`DELETE /api/admin/cms/reviews/<uuid:id>/`**

Hard-deletes the review record.

**Permissions:** Admin

**Success Response — `204 No Content`**

---

#### 32. Toggle Review Visibility

**`PATCH /api/admin/cms/reviews/<uuid:id>/toggle-visibility/`**

Flips `is_visible` between `true` and `false`.

**Permissions:** Admin

**Success Response — `200 OK`:**

```json
{ "id": "uuid", "is_visible": false }
```

---

#### 33. Public Review List

**`GET /api/cms/reviews/`**

Returns only visible reviews. No authentication required.

**Permissions:** Public

**Success Response — `200 OK`:** array of visible review objects

---

### CMS — Pricing Plans

#### 34. List All Pricing Plans (Admin)

**`GET /api/admin/cms/pricing/`**

Returns all pricing plans including inactive ones.

**Permissions:** Admin

**Success Response — `200 OK`:** array of plan objects

---

#### 35. Create Pricing Plan

**`POST /api/admin/cms/pricing/`**

**Permissions:** Admin

**Request Body:**

| Field           | Type    | Required | Default     | Description                                                              |
|-----------------|---------|----------|-------------|--------------------------------------------------------------------------|
| `name`          | string  | ✅        | —           | Plan name e.g. `"Pro"`                                                   |
| `price`         | decimal | ✅        | —           | Price in ₹ e.g. `499`                                                    |
| `billing_cycle` | enum    | ✅        | `"monthly"` | `forever` / `monthly` / `quarterly` / `biannual` / `annual`             |
| `features`      | array   | ❌        | `[]`        | List of feature strings                                                  |
| `is_popular`    | boolean | ❌        | `false`     | Highlights the plan as popular                                           |
| `is_active`     | boolean | ❌        | `true`      | Whether shown to users                                                   |
| `display_order` | integer | ❌        | `0`         | Lower = shown first                                                      |

**Success Response — `201 Created`:** full plan object

---

#### 36. Get Pricing Plan

**`GET /api/admin/cms/pricing/<uuid:id>/`**

**Permissions:** Admin

**Success Response — `200 OK`:** full plan object

---

#### 37. Update Pricing Plan

**`PUT /api/admin/cms/pricing/<uuid:id>/`**

**Permissions:** Admin

**Success Response — `200 OK`:** updated plan object

---

#### 38. Delete Pricing Plan

**`DELETE /api/admin/cms/pricing/<uuid:id>/`**

Hard-deletes the pricing plan.

**Permissions:** Admin

**Success Response — `204 No Content`**

---

#### 39. Toggle Plan Active Status

**`PATCH /api/admin/cms/pricing/<uuid:id>/toggle-active/`**

Flips `is_active` between `true` and `false`.

**Permissions:** Admin

**Success Response — `200 OK`:**

```json
{ "id": "uuid", "is_active": false }
```

---

#### 40. Public Pricing List

**`GET /api/cms/pricing/`**

Returns only active plans. No authentication required.

**Permissions:** Public

**Success Response — `200 OK`:** array of active plan objects

---

### CMS — Learning Hub

The Learning Hub CMS manages the course curriculum displayed on the landing page. Content is structured as **Modules** (top-level sections) containing **Topics** (individual bullet points). Both levels support visibility toggling independently.

#### 41. Public Learning Hub

**`GET /api/cms/learning-hub/`**

Returns all visible modules with their visible topics nested inside. No authentication required — consumed directly by the frontend landing page.

**Permissions:** Public

**Success Response — `200 OK`:**

```json
[
  {
    "id": "uuid",
    "title": "Market Basics & Foundations",
    "subtitle": "",
    "display_order": 0,
    "is_visible": true,
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z",
    "topics": [
      {
        "id": "uuid",
        "module_id": "uuid",
        "title": "Understanding the Stock Market",
        "display_order": 0,
        "is_visible": true,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z"
      }
    ]
  }
]
```

---

#### 42. List All Modules (Admin)

**`GET /api/admin/cms/learning-hub/modules/`**

Returns all modules including hidden ones, each with their full topic list.

**Permissions:** Admin

**Success Response — `200 OK`:** array of module objects (with nested topics)

---

#### 43. Create Module

**`POST /api/admin/cms/learning-hub/modules/`**

Creates a new learning module.

**Permissions:** Admin

**Request Body:**

| Field           | Type    | Required | Default | Description                              |
|-----------------|---------|----------|---------|------------------------------------------|
| `title`         | string  | ✅        | —       | Module title e.g. `"MODULE 1: CORE INTRODUCTION"` |
| `subtitle`      | string  | ❌        | `""`    | Optional short description shown under the title |
| `display_order` | integer | ❌        | `0`     | Lower = shown first                      |
| `is_visible`    | boolean | ❌        | `true`  | Show on landing page                     |

**Success Response — `201 Created`:**

```json
{
  "id": "uuid",
  "title": "MODULE 1: CORE INTRODUCTION",
  "subtitle": "",
  "display_order": 1,
  "is_visible": true,
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-01T00:00:00Z",
  "topics": []
}
```

---

#### 44. Get Module

**`GET /api/admin/cms/learning-hub/modules/<uuid:id>/`**

Returns a single module with all its topics.

**Permissions:** Admin

**Success Response — `200 OK`:** full module object with nested topics

---

#### 45. Update Module

**`PUT /api/admin/cms/learning-hub/modules/<uuid:id>/`**

Updates an existing module. Any subset of fields can be provided.

**Permissions:** Admin

**Editable fields:** `title`, `subtitle`, `display_order`, `is_visible`

**Success Response — `200 OK`:** updated module object with nested topics

---

#### 46. Delete Module

**`DELETE /api/admin/cms/learning-hub/modules/<uuid:id>/`**

Hard-deletes the module. **All topics belonging to this module are also deleted (cascade).**

**Permissions:** Admin

**Success Response — `204 No Content`**

---

#### 47. Toggle Module Visibility

**`PATCH /api/admin/cms/learning-hub/modules/<uuid:id>/toggle-visibility/`**

Flips `is_visible` between `true` and `false`. Hiding a module hides all its topics from the public endpoint as well.

**Permissions:** Admin

**Success Response — `200 OK`:**

```json
{ "id": "uuid", "is_visible": false }
```

---

#### 48. List Topics for a Module

**`GET /api/admin/cms/learning-hub/modules/<uuid:module_id>/topics/`**

Returns all topics (including hidden) for the given module.

**Permissions:** Admin

**Success Response — `200 OK`:** array of topic objects

---

#### 49. Create Topic

**`POST /api/admin/cms/learning-hub/modules/<uuid:module_id>/topics/`**

Adds a single topic to a module.

**Permissions:** Admin

**Request Body:**

| Field           | Type    | Required | Default | Description                         |
|-----------------|---------|----------|---------|-------------------------------------|
| `title`         | string  | ✅        | —       | Topic title e.g. `"Why Focus on Price Action"` |
| `display_order` | integer | ❌        | `0`     | Order within the module             |
| `is_visible`    | boolean | ❌        | `true`  | Show on landing page                |

**Success Response — `201 Created`:**

```json
{
  "id": "uuid",
  "module_id": "uuid",
  "title": "Why Focus on Price Action",
  "display_order": 0,
  "is_visible": true,
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-01T00:00:00Z"
}
```

---

#### 50. Bulk Create Topics

**`POST /api/admin/cms/learning-hub/modules/<uuid:module_id>/topics/bulk/`**

Inserts multiple topics under a module in a single request. Useful for seeding an entire module's curriculum at once.

**Permissions:** Admin

**Request Body:**

```json
{
  "topics": [
    { "title": "Understanding the Stock Market", "display_order": 0 },
    { "title": "Structure of Primary and Secondary Markets", "display_order": 1 },
    { "title": "Indian Exchanges: NSE & BSE", "display_order": 2 }
  ]
}
```

| Field                    | Type    | Required | Default | Description                   |
|--------------------------|---------|----------|---------|-------------------------------|
| `topics`                 | array   | ✅        | —       | Non-empty list of topic dicts |
| `topics[].title`         | string  | ✅        | —       | Topic title                   |
| `topics[].display_order` | integer | ❌        | index   | Falls back to array index     |
| `topics[].is_visible`    | boolean | ❌        | `true`  | Show on landing page          |

**Success Response — `201 Created`:** array of created topic objects

**Error — `400 Bad Request`:**

```json
{ "error": "topics[1].title is required." }
```

---

#### 51. Get Topic

**`GET /api/admin/cms/learning-hub/modules/<uuid:module_id>/topics/<uuid:id>/`**

Returns a single topic.

**Permissions:** Admin

**Success Response — `200 OK`:** full topic object

---

#### 52. Update Topic

**`PUT /api/admin/cms/learning-hub/modules/<uuid:module_id>/topics/<uuid:id>/`**

Updates an existing topic.

**Permissions:** Admin

**Editable fields:** `title`, `display_order`, `is_visible`

**Success Response — `200 OK`:** updated topic object

---

#### 53. Delete Topic

**`DELETE /api/admin/cms/learning-hub/modules/<uuid:module_id>/topics/<uuid:id>/`**

Hard-deletes the topic.

**Permissions:** Admin

**Success Response — `204 No Content`**

---

#### 54. Toggle Topic Visibility

**`PATCH /api/admin/cms/learning-hub/modules/<uuid:module_id>/topics/<uuid:id>/toggle-visibility/`**

Flips `is_visible` between `true` and `false` for a single topic.

**Permissions:** Admin

**Success Response — `200 OK`:**

```json
{ "id": "uuid", "is_visible": false }
```

---

### Broadcast Notifications

#### 55. List Broadcasts

**`GET /api/admin/notifications/broadcasts/`**

Returns all broadcasts, most recent first.

**Permissions:** Admin

**Success Response — `200 OK`:**

```json
[
  {
    "id": "uuid",
    "title": "System Maintenance",
    "message": "We will be down for 30 minutes.",
    "recipients": "all",
    "delivered_count": 1250,
    "sent_by": "Super Admin",
    "created_at": "2025-01-01T00:00:00Z"
  }
]
```

---

#### 56. Send Broadcast

**`POST /api/admin/notifications/broadcasts/`**

Sends a broadcast notification to users.

**Permissions:** Admin

**Request Body:**

| Field        | Type   | Required | Description                              |
|--------------|--------|----------|------------------------------------------|
| `title`      | string | ✅        | Notification title                       |
| `message`    | string | ✅        | Notification body                        |
| `recipients` | string | ❌        | Target audience e.g. `"all"`, `"pro"`    |

**Success Response — `201 Created`:** full broadcast object

---

#### 57. Delete Broadcast

**`DELETE /api/admin/notifications/broadcasts/<uuid:id>/delete/`**

Hard-deletes the broadcast record.

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
# Protected admin routes — mount under /api/admin/
urlpatterns = [
    # Auth
    path('auth/login/',                                                                          admin_login_view,                               name='admin-login'),

    # Profile
    path('me/',                                                                                  admin_me_view,                                  name='admin-me'),

    # Dashboard
    path('dashboard/stats/',                                                                     admin_dashboard_stats_view,                     name='admin-dashboard-stats'),

    # User Management
    path('users/',                                                                               admin_user_list_view,                           name='admin-user-list'),
    path('users/<int:user_id>/toggle/',                                                          admin_user_toggle_view,                         name='admin-user-toggle'),
    path('users/<int:user_id>/delete/',                                                          admin_user_delete_view,                         name='admin-user-delete'),

    # Admin Management
    path('admins/',                                                                              admin_list_view,                                name='admin-admin-list'),
    path('admins/create/',                                                                       admin_create_view,                              name='admin-admin-create'),
    path('admins/<uuid:admin_id>/',                                                              admin_manage_view,                              name='admin-admin-manage'),

    # Rules
    path('rules/',                                                                               admin_rule_list_create_view,                    name='admin-rule-list'),
    path('rules/<uuid:pk>/',                                                                     admin_rule_detail_view,                         name='admin-rule-detail'),

    # Strategies
    path('strategies/',                                                                          admin_strategy_list_create_view,                name='admin-strategy-list'),
    path('strategies/<uuid:pk>/',                                                                admin_strategy_detail_view,                     name='admin-strategy-detail'),

    # Mistakes
    path('mistakes/',                                                                            admin_mistake_list_create_view,                 name='admin-mistake-list'),
    path('mistakes/<uuid:pk>/',                                                                  admin_mistake_detail_view,                      name='admin-mistake-detail'),

    # CMS: Reviews
    path('cms/reviews/',                                                                         admin_review_list_create_view,                  name='admin-review-list'),
    path('cms/reviews/<uuid:pk>/',                                                               admin_review_detail_view,                       name='admin-review-detail'),
    path('cms/reviews/<uuid:pk>/toggle-visibility/',                                             admin_review_toggle_visibility_view,            name='admin-review-toggle'),

    # CMS: Pricing
    path('cms/pricing/',                                                                         admin_pricing_list_create_view,                 name='admin-pricing-list'),
    path('cms/pricing/<uuid:pk>/',                                                               admin_pricing_detail_view,                      name='admin-pricing-detail'),
    path('cms/pricing/<uuid:pk>/toggle-active/',                                                 admin_pricing_toggle_active_view,               name='admin-pricing-toggle'),

    # CMS: Learning Hub — Modules
    path('cms/learning-hub/modules/',                                                            admin_learning_module_list_create_view,         name='admin-learning-module-list'),
    path('cms/learning-hub/modules/<uuid:pk>/',                                                  admin_learning_module_detail_view,              name='admin-learning-module-detail'),
    path('cms/learning-hub/modules/<uuid:pk>/toggle-visibility/',                                admin_learning_module_toggle_visibility_view,   name='admin-learning-module-toggle'),

    # CMS: Learning Hub — Topics
    path('cms/learning-hub/modules/<uuid:module_pk>/topics/',                                   admin_learning_topic_list_create_view,          name='admin-learning-topic-list'),
    path('cms/learning-hub/modules/<uuid:module_pk>/topics/bulk/',                              admin_learning_topic_bulk_create_view,          name='admin-learning-topic-bulk-create'),
    path('cms/learning-hub/modules/<uuid:module_pk>/topics/<uuid:pk>/',                         admin_learning_topic_detail_view,               name='admin-learning-topic-detail'),
    path('cms/learning-hub/modules/<uuid:module_pk>/topics/<uuid:pk>/toggle-visibility/',       admin_learning_topic_toggle_visibility_view,    name='admin-learning-topic-toggle'),

    # Broadcasts
    path('notifications/broadcasts/',                                                            admin_broadcast_list_create_view,               name='admin-broadcast-list'),
    path('notifications/broadcasts/<uuid:pk>/delete/',                                           admin_broadcast_delete_view,                    name='admin-broadcast-delete'),
]

# Public CMS — mount under /api/cms/
public_cms_urlpatterns = [
    path('reviews/',       public_review_list_view,    name='public-review-list'),
    path('pricing/',       public_pricing_list_view,   name='public-pricing-list'),
    path('learning-hub/',  public_learning_hub_view,   name='public-learning-hub'),
]
```

---

## Error Reference

| Status Code | Meaning                                                                    |
|-------------|----------------------------------------------------------------------------|
| `200`       | OK                                                                         |
| `201`       | Created                                                                    |
| `204`       | No Content (deleted)                                                       |
| `400`       | Bad Request — missing required field or validation error                   |
| `401`       | Unauthorized — invalid or expired admin token                              |
| `403`       | Forbidden — insufficient access level, or attempting to modify own account |
| `404`       | Not Found — resource does not exist or has been soft-deleted               |
