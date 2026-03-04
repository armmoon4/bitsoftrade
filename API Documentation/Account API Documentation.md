# Account API Documentation

## Overview

The **Account** module handles user authentication, registration, profile management, and subscription-based access control for the BitsOfTrade platform.

---

## Base URL

```
/api/account/
```

---

## Authentication

This API uses **JWT (JSON Web Token)** authentication via `djangorestframework-simplejwt`.

Include the access token in the `Authorization` header for protected endpoints:

```
Authorization: Bearer <access_token>
```

---

## Endpoints

### 1. Register User

**`POST /api/account/register/`**

Creates a new user account and returns JWT tokens.

**Permissions:** Public (no authentication required)

**Request Body:**

| Field              | Type     | Required | Description                     |
|--------------------|----------|----------|---------------------------------|
| `username`         | string   | ✅        | Unique username                 |
| `email`            | string   | ✅        | User email address              |
| `password`         | string   | ✅        | Password (write-only)           |
| `password_confirm` | string   | ✅        | Must match `password`           |
| `first_name`       | string   | ❌        | User's first name               |
| `last_name`        | string   | ❌        | User's last name                |

**Success Response — `201 Created`:**

```json
{
  "message": "User registered successfully",
  "user": {
    "id": 1,
    "username": "johndoe",
    "email": "john@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "subscription_type": "none",
    "profile_picture": null,
    "created_at": "2025-01-01T00:00:00Z"
  },
  "tokens": {
    "refresh": "<refresh_token>",
    "access": "<access_token>"
  }
}
```

**Error Response — `400 Bad Request`:**

```json
{
  "password": ["Password fields didn't match."]
}
```

---

### 2. Login

**`POST /api/account/login/`**

Authenticates a user and returns JWT tokens.

**Permissions:** Public

**Request Body:**

| Field      | Type   | Required | Description    |
|------------|--------|----------|----------------|
| `username` | string | ✅        | Username       |
| `password` | string | ✅        | User password  |

**Success Response — `200 OK`:**

```json
{
  "message": "Login successful",
  "user": {
    "id": 1,
    "username": "johndoe",
    "email": "john@example.com",
    "subscription_type": "tool",
    "profile_picture": null,
    "created_at": "2025-01-01T00:00:00Z"
  },
  "tokens": {
    "refresh": "<refresh_token>",
    "access": "<access_token>"
  }
}
```

**Error Response — `401 Unauthorized`:**

```json
{
  "error": "Invalid username or password"
}
```

---

### 3. Logout

**`POST /api/account/logout/`**

Blacklists the provided refresh token to invalidate the session.

**Permissions:** Authenticated

**Request Body:**

| Field     | Type   | Required | Description           |
|-----------|--------|----------|-----------------------|
| `refresh` | string | ❌        | Refresh token to revoke |

**Success Response — `200 OK`:**

```json
{
  "message": "Logout successful"
}
```

---

### 4. Get Current User

**`GET /api/account/me/`**

Returns the profile of the currently authenticated user.

**Permissions:** Authenticated

**Success Response — `200 OK`:**

```json
{
  "id": 1,
  "username": "johndoe",
  "email": "john@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "subscription_type": "both",
  "profile_picture": "/media/profiles/avatar.jpg",
  "created_at": "2025-01-01T00:00:00Z"
}
```

---

### 5. Profile

**`GET /api/account/profile/`**

Returns the authenticated user's full profile.

**Permissions:** Authenticated

**Success Response — `200 OK`:** *(same as `/me/`)*

---

**`PUT /api/account/profile/`**

Fully updates the user's profile (all fields required).

**Permissions:** Authenticated

**Request Body:**

| Field             | Type   | Required | Description           |
|-------------------|--------|----------|-----------------------|
| `first_name`      | string | ✅        | First name            |
| `last_name`       | string | ✅        | Last name             |
| `email`           | string | ✅        | Email address         |
| `profile_picture` | file   | ❌        | Profile image upload  |

**Success Response — `200 OK`:**

```json
{
  "message": "Profile updated successfully",
  "user": { ... }
}
```

---

**`PATCH /api/account/profile/`**

Partially updates the user's profile (only provided fields are updated).

**Permissions:** Authenticated

**Request Body:** Any subset of fields from `PUT`.

---

### 6. Token — Obtain Pair

**`POST /api/account/token/`**

Standard SimpleJWT endpoint. Returns access and refresh tokens from credentials.

**Request Body:**

| Field      | Type   | Required |
|------------|--------|----------|
| `username` | string | ✅        |
| `password` | string | ✅        |

**Success Response — `200 OK`:**

```json
{
  "access": "<access_token>",
  "refresh": "<refresh_token>"
}
```

---

### 7. Token — Refresh

**`POST /api/account/token/refresh/`**

Returns a new access token using a valid refresh token.

**Request Body:**

| Field     | Type   | Required |
|-----------|--------|----------|
| `refresh` | string | ✅        |

**Success Response — `200 OK`:**

```json
{
  "access": "<new_access_token>"
}
```

---

## User Model

| Field                  | Type          | Description                                              |
|------------------------|---------------|----------------------------------------------------------|
| `id`                   | integer       | Auto-generated primary key                               |
| `username`             | string        | Unique username (inherited from `AbstractUser`)          |
| `email`                | string        | Email address                                            |
| `first_name`           | string        | First name                                               |
| `last_name`            | string        | Last name                                                |
| `profile_picture`      | image         | Uploaded to `profiles/`                                  |
| `trading_capital`      | decimal       | User's capital for % based trading rules                 |
| `subscription_type`    | enum          | `none` / `tool` / `learning` / `both`                    |
| `subscription_status`  | enum          | `active` / `expired` / `cancelled`                       |
| `subscription_start`   | datetime      | When the subscription started                            |
| `subscription_end`     | datetime      | When the subscription expires (`null` = no expiry)       |
| `razorpay_customer_id` | string        | Razorpay customer ID for payment integration             |
| `current_streak`       | integer       | Current journal streak count                             |
| `longest_streak`       | integer       | All-time longest journal streak                          |
| `is_active`            | boolean       | Whether the account is active                            |
| `deleted_at`           | datetime      | Soft-delete timestamp                                    |
| `created_at`           | datetime      | Account creation timestamp                               |
| `updated_at`           | datetime      | Last update timestamp                                    |

### Computed Properties

| Property             | Type    | Description                                                                 |
|----------------------|---------|-----------------------------------------------------------------------------|
| `has_tool_access`    | boolean | `True` if subscription is `tool` or `both`, status is `active`, and not expired |
| `has_learning_access`| boolean | `True` if subscription is `learning` or `both`, status is `active`, and not expired |

---

## Subscription Types

| Value      | Label              | Tool Access | Learning Access |
|------------|--------------------|-------------|-----------------|
| `none`     | None               | ❌           | ❌               |
| `tool`     | Tool Plan (Pro)    | ✅           | ❌               |
| `learning` | Learning Plan      | ❌           | ✅               |
| `both`     | Tool + Learning    | ✅           | ✅               |

---

## Decorators

Defined in `decorator.py`, these can be applied to any view function to enforce subscription-based access control.

### `@require_tool_subscription`

Blocks access unless the user has an active `tool` or `both` subscription.

**Returns on failure:**

- `401 Unauthorized` — if the user is not authenticated
- `403 Forbidden` — if the user lacks the required subscription

```json
{
  "error": "subscription_required",
  "detail": "Active Tool or Both plan required."
}
```

**Usage:**

```python
from account.decorator import require_tool_subscription

@api_view(['GET'])
@require_tool_subscription
def my_tool_view(request):
    ...
```

---

### `@require_learning_subscription`

Blocks access unless the user has an active `learning` or `both` subscription.

**Returns on failure:**

- `401 Unauthorized` — if the user is not authenticated
- `403 Forbidden` — if the user lacks the required subscription

```json
{
  "error": "subscription_required",
  "detail": "Active Learning or Both plan required."
}
```

**Usage:**

```python
from account.decorator import require_learning_subscription

@api_view(['GET'])
@require_learning_subscription
def my_learning_view(request):
    ...
```

---

## URL Configuration

```python
# account/urls.py
urlpatterns = [
    path('register/',       views.register_view,            name='register'),
    path('login/',          views.login_view,                name='login'),
    path('logout/',         views.logout_view,               name='logout'),
    path('me/',             views.current_user_view,         name='current_user'),
    path('profile/',        views.profile_view,              name='profile'),
    path('token/',          TokenObtainPairView.as_view(),   name='token_obtain_pair'),
    path('token/refresh/',  TokenRefreshView.as_view(),      name='token_refresh'),
]
```

---

## Error Reference

| Status Code | Meaning                                  |
|-------------|------------------------------------------|
| `200`       | OK — Request successful                  |
| `201`       | Created — Resource created successfully  |
| `400`       | Bad Request — Validation error           |
| `401`       | Unauthorized — Authentication required   |
| `403`       | Forbidden — Insufficient subscription    |

---

## Dependencies

- `djangorestframework`
- `djangorestframework-simplejwt`
- `django.contrib.auth` (`AbstractUser`)
- `Pillow` (for `ImageField`)
- `Razorpay` (payment integration via `razorpay_customer_id`)
