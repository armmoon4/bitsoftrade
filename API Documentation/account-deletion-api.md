# Account Deletion API

Permanently deletes the authenticated user's account and all associated data. This action is irreversible.

---

## Endpoint

```
DELETE /api/accounts/me/delete/
```

**Authentication:** JWT Bearer token required.

---

## Request

**Headers**

| Header | Value |
|---|---|
| `Authorization` | `Bearer <access_token>` |
| `Content-Type` | `application/json` |

**Body**

| Field | Type | Required | Description |
|---|---|---|---|
| `password` | string | ✅ Yes | User's current password (confirmation) |
| `refresh` | string | ⬜ Optional | Refresh token to blacklist on deletion |

**Example**

```json
{
  "password": "mySecurePassword123",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

---

## Responses

### 200 — Success

```json
{
  "message": "Your account and all associated data have been permanently deleted."
}
```

### 400 — Missing password

```json
{
  "error": "Password is required to confirm account deletion."
}
```

### 401 — Not authenticated

```json
{
  "error": "Authentication credentials were not provided."
}
```

### 403 — Wrong password

```json
{
  "error": "Incorrect password. Account deletion cancelled."
}
```

---

## Behaviour

- **Hard delete** — the user record and all related data are permanently removed from the database via Django's cascade delete. There is no recovery.
- **Token blacklisting** — if a `refresh` token is provided, it is blacklisted before deletion so it cannot be reused.
- **Cascading data** — any model with a `ForeignKey` to `User` using `on_delete=CASCADE` is automatically deleted. This includes journal entries, trades, subscriptions, and profile data.

---

## Notes

- The `password` field is mandatory to prevent accidental or unauthorized deletions.
- Passing the `refresh` token is strongly recommended so the client token is invalidated immediately.
- The user's `access` token will expire naturally after deletion — no further action is needed for it.
- This endpoint does **not** support soft deletion or a grace period recovery window.
