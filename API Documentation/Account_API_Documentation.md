# Account API Documentation

## Overview

The **Account** module handles user authentication, registration, profile management, onboarding, and subscription-based access control for the BitsOfTrade platform.

---

## Base URL

```
/api/auth/
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

**`POST /api/auth/register/`**

Creates a new user account and returns JWT tokens.

**Permissions:** Public (no authentication required)

**Request Body:**

| Field              | Type   | Required | Description                   |
|--------------------|--------|----------|-------------------------------|
| `email`            | string | ✅        | Unique email address          |
| `password`         | string | ✅        | Password (write-only)         |
| `password_confirm` | string | ✅        | Must match `password`         |
| `first_name`       | string | ❌        | User's first name             |
| `last_name`        | string | ❌        | User's last name              |

**Success Response — `201 Created`:**

```json
{
  "message": "User registered successfully",
  "user": {
    "id": 1,
    "email": "john@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "subscription_type": "none",
    "profile_picture": null,
    "created_at": "2025-01-01T00:00:00Z",
    "onboarding_completed": false
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

**`POST /api/auth/login/`**

Authenticates a user and returns JWT tokens.

**Permissions:** Public

**Request Body:**

| Field      | Type   | Required | Description    |
|------------|--------|----------|----------------|
| `email`    | string | ✅        | Email address  |
| `password` | string | ✅        | User password  |

**Success Response — `200 OK`:**

```json
{
  "message": "Login successful",
  "user": {
    "id": 1,
    "email": "john@example.com",
    "first_name": "John",
    "last_name": "Doe",
    "subscription_type": "tool",
    "profile_picture": null,
    "created_at": "2025-01-01T00:00:00Z",
    "onboarding_completed": false
  },
  "tokens": {
    "refresh": "<refresh_token>",
    "access": "<access_token>"
  }
}
```

> **Onboarding Logic:** Check `user.onboarding_completed` in the response.
> - `false` → Redirect to `/onboarding`
> - `true` → Redirect to `/dashboard`

**Error Response — `401 Unauthorized`:**

```json
{
  "error": "Invalid email or password"
}
```

---

### 3. Logout

**`POST /api/auth/logout/`**

Blacklists the provided refresh token to invalidate the session.

**Permissions:** Authenticated

**Request Body:**

| Field     | Type   | Required | Description             |
|-----------|--------|----------|-------------------------|
| `refresh` | string | ❌        | Refresh token to revoke |

**Success Response — `200 OK`:**

```json
{
  "message": "Logout successful"
}
```

---

### 4. Get Current User

**`GET /api/auth/me/`**

Returns the profile of the currently authenticated user.

**Permissions:** Authenticated

**Success Response — `200 OK`:**

```json
{
  "id": 1,
  "email": "john@example.com",
  "first_name": "John",
  "last_name": "Doe",
  "subscription_type": "both",
  "profile_picture": "/media/profiles/avatar.jpg",
  "created_at": "2025-01-01T00:00:00Z",
  "onboarding_completed": true
}
```

---

### 5. Profile

**`GET /api/auth/profile/`**

Returns the authenticated user's full profile.

**Permissions:** Authenticated

**Success Response — `200 OK`:** *(same as `/me/`)*

---

**`PUT /api/auth/profile/`**

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
  "user": { "..." }
}
```

---

**`PATCH /api/auth/profile/`**

Partially updates the user's profile (only provided fields are updated).

**Permissions:** Authenticated

**Request Body:** Any subset of fields from `PUT`.

---

### 6. Complete Onboarding

**`POST /api/auth/onboarding/complete/`**

Marks the onboarding flow as completed for the currently authenticated user. Call this endpoint when the user finishes the onboarding steps. After this, subsequent logins will return `onboarding_completed: true` and the frontend should redirect directly to the dashboard.

**Permissions:** Authenticated

**Request Body:** None required.

**Success Response — `200 OK`:**

```json
{
  "message": "Onboarding completed"
}
```

**Error Response — `401 Unauthorized`:** *(if not authenticated)*

---

### 7. Change Password

**`POST /api/auth/password/change/`**

Allows an authenticated user to change their current password.

**Permissions:** Authenticated

**Request Body:**

| Field          | Type   | Required | Description              |
|----------------|--------|----------|--------------------------|
| `old_password` | string | ✅        | The user's current password |
| `new_password` | string | ✅        | The desired new password (validated against Django's password rules) |

**Success Response — `200 OK`:**

```json
{
  "message": "Password updated successfully"
}
```

**Error Response — `400 Bad Request`:**

```json
{
  "old_password": ["Wrong password."]
}
```

---

### 8. Request Password Reset

**`POST /api/auth/password/reset/`**

Generates a password reset link and sends it to the user's email address. Always returns a success message regardless of whether the email exists, to prevent user enumeration.

**Permissions:** Public

**Request Body:**

| Field   | Type   | Required | Description           |
|---------|--------|----------|-----------------------|
| `email` | string | ✅        | The account's email address |

**Success Response — `200 OK`:**

```json
{
  "message": "If an account with that email exists, a reset link has been sent."
}
```

---

### 9. Confirm Password Reset

**`POST /api/auth/password/reset/confirm/`**

Verifies the token from the reset link and sets the new password.

**Permissions:** Public

**Request Body:**

| Field          | Type   | Required | Description                                 |
|----------------|--------|----------|---------------------------------------------|
| `uidb64`       | string | ✅        | Base64-encoded user ID from the reset link  |
| `token`        | string | ✅        | Password reset token from the reset link    |
| `new_password` | string | ✅        | The new password to set                     |

**Success Response — `200 OK`:**

```json
{
  "message": "Password reset successful."
}
```

**Error Response — `400 Bad Request`:**

```json
{
  "error": "Invalid or expired token."
}
```

---

### 10. Google Login

**`POST /api/auth/google-login/`**

Verifies a Google ID token, creates a new user account if one does not exist, and returns JWT tokens.

**Permissions:** Public

**Request Body:**

| Field   | Type   | Required | Description                              |
|---------|--------|----------|------------------------------------------|
| `token` | string | ✅        | Google OAuth2 ID token from the client   |

**Success Response — `200 OK`:**

```json
{
  "message": "Google Login successful",
  "user": {
    "id": 2,
    "email": "jane@gmail.com",
    "first_name": "Jane",
    "last_name": "Doe",
    "subscription_type": "none",
    "profile_picture": null,
    "created_at": "2025-01-01T00:00:00Z",
    "onboarding_completed": false
  },
  "tokens": {
    "refresh": "<refresh_token>",
    "access": "<access_token>"
  },
  "is_new_user": true
}
```

> **Note:** For Google login, you can use either `is_new_user` or `onboarding_completed` to detect first-time users. `onboarding_completed` is more reliable — it stays `false` even if a user closes mid-onboarding, whereas `is_new_user` is only `true` on the very first login.

**Error Responses:**

```json
{ "error": "Invalid Google token" }
```
```json
{ "error": "Google Client ID not configured on server" }
```

---

### 11. Token — Obtain Pair

**`POST /api/auth/token/`**

Standard SimpleJWT endpoint. Returns access and refresh tokens directly from email and password credentials.

**Request Body:**

| Field      | Type   | Required |
|------------|--------|----------|
| `email`    | string | ✅        |
| `password` | string | ✅        |

**Success Response — `200 OK`:**

```json
{
  "access": "<access_token>",
  "refresh": "<refresh_token>"
}
```

---

### 12. Token — Refresh

**`POST /api/auth/token/refresh/`**

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

| Field                  | Type     | Description                                                          |
|------------------------|----------|----------------------------------------------------------------------|
| `id`                   | integer  | Auto-generated primary key                                           |
| `email`                | string   | Unique email address — used as the login identifier                  |
| `first_name`           | string   | First name                                                           |
| `last_name`            | string   | Last name                                                            |
| `profile_picture`      | image    | Uploaded to `profiles/`                                              |
| `trading_capital`      | decimal  | User's capital for % based trading rules                             |
| `onboarding_completed` | boolean  | `false` until user completes onboarding; persists across sessions    |
| `subscription_type`    | enum     | `none` / `tool` / `learning` / `both`                                |
| `subscription_status`  | enum     | `active` / `expired` / `cancelled`                                   |
| `subscription_start`   | datetime | When the subscription started                                        |
| `subscription_end`     | datetime | When the subscription expires (`null` = no expiry)                   |
| `razorpay_customer_id` | string   | Razorpay customer ID for payment integration                         |
| `current_streak`       | integer  | Current journal streak count                                         |
| `longest_streak`       | integer  | All-time longest journal streak                                      |
| `is_active`            | boolean  | Whether the account is active                                        |
| `deleted_at`           | datetime | Soft-delete timestamp                                                |
| `created_at`           | datetime | Account creation timestamp                                           |
| `updated_at`           | datetime | Last update timestamp                                                |

> **Note:** There is no `username` field. The `User` model uses `email` as the unique identifier (`USERNAME_FIELD = 'email'`).

### Computed Properties

| Property              | Type    | Description                                                                      |
|-----------------------|---------|----------------------------------------------------------------------------------|
| `has_tool_access`     | boolean | `True` if subscription is `tool` or `both`, status is `active`, and not expired  |
| `has_learning_access` | boolean | `True` if subscription is `learning` or `both`, status is `active`, and not expired |

---

## Onboarding Flow

The onboarding flag is designed to show the onboarding page **only on a user's very first login**, and never again after they complete it.

### How it works

```
User logs in / registers
        │
        ▼
  onboarding_completed == false?
        │
   YES  │  NO
        │   └──► Redirect to /dashboard
        ▼
  Show /onboarding page
        │
  User completes onboarding
        │
        ▼
  POST /api/auth/onboarding/complete/
        │
        ▼
  Redirect to /dashboard
  (all future logins go straight to /dashboard)
```

### Frontend Implementation Guide

**On login/register response:**
```javascript
const { user, tokens } = response.data;

if (!user.onboarding_completed) {
  router.push('/onboarding');
} else {
  router.push('/dashboard');
}
```

**On finishing onboarding:**
```javascript
await axios.post('/api/auth/onboarding/complete/', {}, {
  headers: { Authorization: `Bearer ${accessToken}` }
});

router.push('/dashboard');
```

### Onboarding State Reference

| Scenario                        | `onboarding_completed` |
|---------------------------------|------------------------|
| Brand new user (just registered) | `false`               |
| Google sign-in, new account     | `false`                |
| User closed mid-onboarding      | `false`                |
| User completed onboarding       | `true`                 |
| Returning user (any login)      | `true`                 |

---

## Subscription Types

| Value      | Label           | Tool Access | Learning Access |
|------------|-----------------|-------------|-----------------|
| `none`     | None            | ❌           | ❌               |
| `tool`     | Tool Plan (Pro) | ✅           | ❌               |
| `learning` | Learning Plan   | ❌           | ✅               |
| `both`     | Tool + Learning | ✅           | ✅               |

---

## Decorators

Defined in `decorators.py`, these can be applied to any view function to enforce subscription-based access control.

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
from accounts.decorators import require_tool_subscription

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
from accounts.decorators import require_learning_subscription

@api_view(['GET'])
@require_learning_subscription
def my_learning_view(request):
    ...
```

---

## URL Configuration

```python
# accounts/urls.py
urlpatterns = [
    # Core Auth
    path('register/',               views.register_view,            name='register'),
    path('login/',                  views.login_view,               name='login'),
    path('logout/',                 views.logout_view,              name='logout'),

    # JWT Standard endpoints
    path('token/',                  TokenObtainPairView.as_view(),  name='token_obtain_pair'),
    path('token/refresh/',          TokenRefreshView.as_view(),     name='token_refresh'),

    # Profile Management
    path('me/',                     views.current_user_view,        name='current_user'),
    path('profile/',                views.profile_view,             name='profile'),

    # Onboarding
    path('onboarding/complete/',    views.complete_onboarding_view, name='complete_onboarding'),

    # Password Management
    path('password/change/',        views.change_password_view,     name='change_password'),
    path('password/reset/',         views.request_password_reset,   name='request_password_reset'),
    path('password/reset/confirm/', views.confirm_password_reset,   name='confirm_password_reset'),

    # Google Auth
    path('google-login/',           views.google_login_view,        name='google_login'),
]
```

---

## Error Reference

| Status Code | Meaning                                   |
|-------------|-------------------------------------------|
| `200`       | OK — Request successful                   |
| `201`       | Created — Resource created successfully   |
| `400`       | Bad Request — Validation error            |
| `401`       | Unauthorized — Authentication required    |
| `403`       | Forbidden — Insufficient subscription     |
| `500`       | Internal Server Error — Server misconfiguration (e.g. missing `GOOGLE_OAUTH2_CLIENT_ID`) |

---

## Dependencies

- `djangorestframework`
- `djangorestframework-simplejwt`
- `django.contrib.auth` (`AbstractUser`)
- `Pillow` (for `ImageField`)
- `google-auth` (for Google OAuth2 token verification)
- `Razorpay` (payment integration via `razorpay_customer_id`)
