# Payments API Documentation

Base path: `/api/payments/`  
Admin base path: `/api/admin/`

---

## Table of Contents

1. [Data Models](#data-models)
2. [Endpoints](#endpoints)
   - [Create Order](#1-create-order)
   - [Webhook](#2-webhook)
   - [Payment History](#3-payment-history)
   - [Admin — All Payments](#4-admin--all-payments)
3. [Plan Types & Pricing](#plan-types--pricing)
4. [Transaction Statuses](#transaction-statuses)
5. [Error Responses](#error-responses)

---

## Data Models

### PaymentTransaction

| Field                  | Type        | Description                                      |
|------------------------|-------------|--------------------------------------------------|
| `id`                   | UUID        | Auto-generated primary key                       |
| `user`                 | FK → User   | The authenticated user who made the payment      |
| `razorpay_order_id`    | string      | Order ID returned by Razorpay on order creation  |
| `razorpay_payment_id`  | string      | Payment ID from Razorpay (set on webhook success)|
| `amount`               | decimal     | Amount in INR (rupees, not paise)                |
| `currency`             | string      | Always `INR`                                     |
| `plan_type`            | string      | One of `tool`, `learning`, `both`                |
| `status`               | string      | One of `pending`, `success`, `failed`, `refunded`|
| `paid_at`              | datetime    | Timestamp of successful payment (nullable)       |
| `created_at`           | datetime    | Record creation timestamp                        |

---

## Endpoints

### 1. Create Order

Creates a Razorpay order and a pending `PaymentTransaction` record.

```
POST /api/payments/create-order/
```

**Authentication:** Required (Bearer token / session)

**Request Body**

| Field       | Type   | Required | Description                              |
|-------------|--------|----------|------------------------------------------|
| `plan_type` | string | Yes      | One of `tool`, `learning`, `both`        |

**Example Request**

```json
{
  "plan_type": "tool"
}
```

**Success Response — `201 Created`**

```json
{
  "order_id": "order_QxYzABC123",
  "amount": 99900,
  "currency": "INR",
  "key": "rzp_live_xxxxxxxxxxxx",
  "transaction_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

| Field            | Description                                                    |
|------------------|----------------------------------------------------------------|
| `order_id`       | Razorpay order ID — pass to the Razorpay checkout SDK         |
| `amount`         | Amount in **paise** (e.g. `99900` = ₹999)                     |
| `currency`       | Always `INR`                                                   |
| `key`            | Razorpay public key ID for the frontend SDK                    |
| `transaction_id` | Internal UUID for this transaction                             |

**Error Responses**

| Status | Condition                         | Body                                                      |
|--------|-----------------------------------|-----------------------------------------------------------|
| `400`  | Invalid or missing `plan_type`    | `{"error": "Invalid plan_type. Choose from: [...]"}`      |
| `401`  | Unauthenticated request           | Standard DRF 401                                          |
| `500`  | Razorpay SDK not installed        | `{"error": "Razorpay SDK not installed. Run: pip install razorpay"}` |

---

### 2. Webhook

Receives Razorpay payment event notifications. On a `payment.captured` event, marks the transaction as successful and activates the user's subscription for 365 days.

```
POST /api/payments/webhook/
```

**Authentication:** None (public endpoint). Requests are verified using an HMAC-SHA256 signature when `RAZORPAY_WEBHOOK_SECRET` is configured.

**Headers**

| Header                    | Description                              |
|---------------------------|------------------------------------------|
| `X-Razorpay-Signature`    | HMAC-SHA256 hex digest of the raw body, signed with `RAZORPAY_WEBHOOK_SECRET` |

**Expected Payload (Razorpay standard format)**

```json
{
  "event": "payment.captured",
  "payload": {
    "payment": {
      "entity": {
        "id": "pay_QxYzABC456",
        "order_id": "order_QxYzABC123"
      }
    }
  }
}
```

**Supported Events**

| Event               | Behaviour                                                                 |
|---------------------|---------------------------------------------------------------------------|
| `payment.captured`  | Sets transaction `status` → `success`, records `paid_at`, activates user subscription for 365 days |
| `payment.failed`    | Sets transaction `status` → `failed` (only if currently `pending`)        |
| Any other event     | Ignored — returns `200 OK`                                                |

**Success Response — `200 OK`**

```json
{ "status": "ok" }
```

Razorpay expects a `200` response; any non-`200` triggers a retry. The endpoint is **idempotent** — duplicate `payment.captured` events for an already-successful transaction are safely ignored.

**Error Responses**

| Status | Condition                   | Body                          |
|--------|-----------------------------|-------------------------------|
| `400`  | Signature verification fails | `{"error": "Invalid signature"}` |

> **Note:** Configure `RAZORPAY_WEBHOOK_SECRET` in your Django settings to enable signature verification. Without it, all webhook requests are accepted without validation.

---

### 3. Payment History

Returns a paginated list of all payment transactions for the authenticated user, ordered most-recent first.

```
GET /api/payments/history/
```

**Authentication:** Required (Bearer token / session)

**Query Parameters:** None

**Success Response — `200 OK`**

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "razorpay_order_id": "order_QxYzABC123",
    "razorpay_payment_id": "pay_QxYzABC456",
    "amount": "999.00",
    "currency": "INR",
    "plan_type": "tool",
    "status": "success",
    "paid_at": "2025-01-15T10:30:00Z",
    "created_at": "2025-01-15T10:28:00Z"
  }
]
```

The `user` field is excluded from the response (read-only, server-side only).

**Error Responses**

| Status | Condition              |
|--------|------------------------|
| `401`  | Unauthenticated request |

---

### 4. Admin — All Payments

Returns all payment transactions across all users. Intended for internal admin dashboards. Protected by a custom `IsAdminAuthenticated` permission class — **no session or token auth headers are required**, but the request must satisfy the admin authentication policy.

```
GET /api/admin/payments/
```

**Authentication:** Custom admin auth (`IsAdminAuthenticated`). Standard user tokens are not accepted.

**Query Parameters:** None

**Success Response — `200 OK`**

```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "user_name": "Jane Doe",
    "email": "jane@example.com",
    "amount": 999.0,
    "plan_type": "tool",
    "status": "success",
    "paid_at": "2025-01-15T10:30:00Z",
    "created_at": "2025-01-15T10:28:00Z"
  }
]
```

| Field        | Description                                              |
|--------------|----------------------------------------------------------|
| `id`         | Transaction UUID                                         |
| `user_name`  | Full name of the user, falls back to `username` if blank |
| `email`      | User's email address                                     |
| `amount`     | Amount in INR as a float                                 |
| `plan_type`  | One of `tool`, `learning`, `both`                        |
| `status`     | Transaction status                                       |
| `paid_at`    | Payment confirmation timestamp (null if not paid)        |
| `created_at` | Order creation timestamp                                 |

Results are ordered by `created_at` descending (newest first).

---

## Plan Types & Pricing

| `plan_type` | Label              | Price (INR) | Amount (paise) |
|-------------|--------------------|-------------|----------------|
| `tool`      | Tool Plan          | ₹999        | 99900          |
| `learning`  | Learning Plan      | ₹499        | 49900          |
| `both`      | Tool + Learning    | ₹1,399      | 139900         |

---

## Transaction Statuses

| Status     | Description                                                         |
|------------|---------------------------------------------------------------------|
| `pending`  | Order created; payment not yet confirmed                            |
| `success`  | Payment captured via webhook; subscription activated                |
| `failed`   | Payment failed (only set if previously `pending`)                   |
| `refunded` | Payment refunded (set manually or via future refund flow)           |

---

## Settings Reference

The following Django settings are required for the payments app:

| Setting                    | Description                                              |
|----------------------------|----------------------------------------------------------|
| `RAZORPAY_KEY_ID`          | Razorpay public API key                                  |
| `RAZORPAY_KEY_SECRET`      | Razorpay secret API key                                  |
| `RAZORPAY_WEBHOOK_SECRET`  | Webhook signing secret (optional but strongly recommended) |
